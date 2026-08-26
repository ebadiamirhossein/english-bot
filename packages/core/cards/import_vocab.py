"""W8f: a Language Reactor or Trancy export → cards. Human-run, dry by default.

    python -m core.cards.import_vocab --file PATH --user N            # writes nothing
    python -m core.cards.import_vocab --file PATH --user N --apply    # type the count back

---

## What this replaces, and what it deliberately does not rebuild

The only import route this system has is the v2 Telegram CSV handler, which dies
at W22. `docs/PRD-v3-web.md` §7.1 keeps CSV import on purpose — Netflix and
Disney+ are "not embeddable, not scrapable", so an export IS the mechanism for
series input — and no v3 slice owned it until this one.

**Language Reactor is the primary path; Trancy is the degraded one.** An LR row
carries the sentence the learner actually met the word in. A Trancy row carries a
bare word, which is why S24a generated a sentence around it — and W8b measured
where those sentences went: **7 of 14 cards work-framed, 50% against §4's 20%
cap** (#99), from a generator prompt with no track weighting anywhere in it.

**So this module makes no model call, on any path.** A Trancy row becomes a
smaller card, not an invented sentence. `core.llm` is not imported here and a
test asserts it.

## Dry by default, and what the dry run is for

`retire_chunk_cloze`'s shape: every row printed whole with its verdict, a typed
count, and an independent read-back afterwards that this command does not
perform on its own behalf.

The report is a **bucket table, not a total**, and the buckets sum to the rows
read — `migrate_chunks`' accounting property. "Nothing was silently lost" is then
a subtraction anyone can do from the output, rather than a claim the importer
makes about itself. Two buckets are always zero and say so; see
`core.cards.capture`.

## The refusals

- **A `native_language` mismatch refuses the WHOLE FILE, before anything is
  written.** `users.native_language` wins over the export's own target-language
  column: the user row is what every other surface reads, and a gloss in a
  language the learner does not read is noise. That is S24's own reason for never
  auto-sharing a Trancy import — *"operator Trancy exports carry Persian
  meanings; User B is Lithuanian"*. It is a whole-file property, so failing loud
  on the file beats importing it row by row and skipping most of them.
- **An unrecognised format refuses.** Exactly one structural match or none —
  `classify_csv_format`'s rule, kept.

## Duplicates

Three different collisions, and they are not one question:

1. **already in `lexemes`** — not a collision at all; the dictionary is shared.
   `resolve_capture_lemma` handles it, and grows the row when it is absent.
2. **already in the ledger** at `known`/`mastered` — skip. At `seen`/`learning`,
   import: having met a word and not yet learned it is the case a card is for.
3. **already a card** — skip, **row-level**. Any existing card for the lemma
   skips the whole row, so a word with a production card does not quietly gain a
   recognition one. Filed as a cost against W13, which owns whether a
   partially-carded word is topped up.

**There is no frequency floor.** A capture is the strongest statement of intent
this system receives; see `core.cards.capture` for the ruling and its reasons.

**No SQL lives here.** Every read and write is a `core.services.cards` or
`core.services.lexicon` function.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from core.cards.capture import BUCKETS, IMPORTED, plan_for_capture
from core.cards.exports import parse_export
from core.db import connection
from core.services import cards as cards_service
from core.services import lexicon as lexicon_service
from core.services import users as users_service

logger = logging.getLogger(__name__)


class ImportRefused(Exception):
    """The file is not importable for this learner. Nothing was written."""


def _check_language(records, *, native_language: str) -> None:
    """Refuse the whole file when the export's L1 is not the learner's.

    The user row wins, always. This does not close #159 — carrying the language
    onto the card FACE is W10's — it stops this slice from making it worse.
    """
    declared = {r.target_language for r in records if r.target_language}
    if not declared:
        # Trancy carries no target-language column. Nothing to disagree with;
        # the operator chose the file and the user row governs the gloss.
        return
    mismatched = {lang for lang in declared if lang.lower() != native_language.lower()}
    if mismatched:
        raise ImportRefused(
            f"the export targets {sorted(mismatched)} but this learner's "
            f"users.native_language is {native_language!r}. Refusing the whole "
            "file — a gloss in a language they do not read is noise, and the "
            "user row wins over the export's own column."
        )


def _print_rows(planned) -> None:
    """Every row, whole, with its verdict. Nothing summarised away."""
    for plan, path in planned:
        cards = f"{len(plan.cards)} card(s)" if plan.cards else "—"
        print(f"  {plan.lemma:<16} {plan.bucket:<22} {cards:<11} lemma:{path}")


def _identity(counts: Counter, rows_read: int) -> bool:
    """`migrate_chunks`' accounting property, checked rather than asserted."""
    return sum(counts[b] for b in BUCKETS) == rows_read


def _confirm(count: int) -> bool:
    """Type the count back. There is no `--yes`."""
    print(f"\nAbout to create cards for {count} word(s) on this database.")
    print("Confirm the count against the rows listed above.")
    typed = input(f"Type the count ({count}) to continue, anything else to stop: ")
    return typed.strip() == str(count)


def _plan_file(conn, path: Path, *, user_id: int, now: datetime):
    """Parse, refuse if it is not this learner's, and plan every row. Read-only."""
    profile = users_service.get_user(user_id)
    if profile is None:
        raise ImportRefused(f"no user with id {user_id}")

    source_format, records = parse_export(path.read_text(encoding="utf-8-sig"))
    _check_language(records, native_language=profile.native_language)

    known = lexicon_service.known_lemmas(conn, user_id)
    carded = cards_service.lemmas_with_a_card(conn, user_id)

    planned = []
    for record in records:
        # grow=False: planning writes nothing, including to `lexemes`.
        lexeme_id, lemma_path = cards_service.resolve_capture_lemma(
            conn, record.lemma, grow=False
        )
        plan = plan_for_capture(
            record,
            now=now,
            known_lemmas=known,
            lemmas_with_a_card=carded,
            lexeme_id=lexeme_id,
        )
        planned.append((plan, lemma_path))
    return source_format, planned


def _report(conn, path: Path, *, user_id: int, now: datetime):
    source_format, planned = _plan_file(conn, path, user_id=user_id, now=now)
    counts = Counter(plan.bucket for plan, _ in planned)

    print(f"{path.name} — detected {source_format}, {len(planned)} row(s), "
          f"learner {user_id}.")
    if planned:
        print()
        _print_rows(planned)
    print()
    for bucket in BUCKETS:
        print(f"  {bucket:<24} {counts[bucket]}")
    print(f"  {'cards that would be made':<24} "
          f"{sum(len(p.cards) for p, _ in planned)}")

    if not _identity(counts, len(planned)):
        # The buckets must sum to the rows read. If they do not, a row went
        # somewhere this module does not know about, and that is a finding.
        print(
            f"\nFINDING: the buckets sum to {sum(counts[b] for b in BUCKETS)} "
            f"but {len(planned)} row(s) were read.\nA row is unaccounted for — "
            "record this and stop."
        )
    return planned


def dry_run(path: Path, *, user_id: int, now: datetime) -> int:
    with connection() as conn:
        planned = _report(conn, path, user_id=user_id, now=now)
        importable = [p for p, _ in planned if p.bucket == IMPORTED]
        if not importable:
            print("\nNothing to import — every row is already in this deck.")
        print("\ndry run — nothing was written. Re-run with --apply to write.")
    return 0


def apply(path: Path, *, user_id: int, now: datetime) -> int:
    with connection() as conn:
        planned = _report(conn, path, user_id=user_id, now=now)
        importable = [(p, lp) for p, lp in planned if p.bucket == IMPORTED]
        if not importable:
            print("\nNothing to import — every row is already in this deck.")
            return 0
        if not _confirm(len(importable)):
            print("Stopped. Nothing was written.")
            return 1

        created: list[int] = []
        refused = 0
        with conn.transaction():
            for plan, _lemma_path in importable:
                # Resolve again WITH growth, inside the writing transaction —
                # the planning pass above deliberately created no lexemes.
                lexeme_id, _path = cards_service.resolve_capture_lemma(
                    conn, plan.lemma, grow=True
                )
                for spec in plan.cards:
                    card_id = cards_service.create_card(
                        conn, user_id, **{**spec, "lexeme_id": lexeme_id}
                    )
                    if card_id is None:
                        refused += 1
                    else:
                        created.append(card_id)
                if lexeme_id is not None:
                    # A capture IS a tap: the learner met the word and looked it
                    # up. `tapped` (rank 2) already exists for exactly this, so
                    # the ledger needs no new source value.
                    lexicon_service.record(
                        conn,
                        user_id,
                        [lexicon_service.LedgerEntry(
                            lemma=plan.lemma.strip().lower(),
                            state="seen",
                            source="tapped",
                        )],
                    )

        print(f"\ncreated {len(created)} card(s): {sorted(created)}")
        if refused:
            print(
                f"\nFINDING: {refused} card(s) were refused by a uniqueness "
                "guarantee after the\nanti-join said they were new. That means a "
                "card landed between the read and\nthe write, or the anti-join "
                "cannot see rows the index can. Record it."
            )
            return 1

    print(
        "\nConfirm the counts independently, in psql — the queries are the\n"
        "deployment step in BUILD_PROGRESS.md. A count this command prints about\n"
        "its own work is not verification of it."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import a Language Reactor or Trancy vocabulary export into "
        "the deck. Dry by default; --apply writes after the count is typed back."
    )
    parser.add_argument("--file", required=True, help="the export file")
    parser.add_argument(
        "--user", required=True, type=int, help="users.id of the learner"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="create the cards (default is a dry run that writes nothing)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    path = Path(args.file)
    if not path.is_file():
        print(f"no such file: {path}")
        return 1

    now = datetime.now(timezone.utc)
    try:
        return (apply if args.apply else dry_run)(path, user_id=args.user, now=now)
    except ImportRefused as refusal:
        print(f"REFUSED — nothing was written.\n\n  {refusal}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
