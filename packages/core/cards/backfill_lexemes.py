"""W8f: give the existing cards the `lexeme_id` they were never given.

Human-run, dry by default, and it writes to production rows.

    python -m core.cards.backfill_lexemes            # every row and its resolution, writes nothing
    python -m core.cards.backfill_lexemes --apply    # type the count back, then write

---

## Why this exists, and why it is part of the import slice

W8f's duplicate guarantee is "one card per (learner, lemma, card type)". It is
enforced by migration 015's `cards_one_card_per_lemma` and by the importer's
anti-join, and **both read `cards.lexeme_id`**.

`core.cards.migrate_chunks` never set it. The string `lexeme` does not occur in
that module at all: its card spec is built from a `common` dict with no
`lexeme_id` key, so `create_card`'s `None` default applied to all fourteen
production cards. It also sets `source_chunk_id` on every branch.

So before this pass, **every card in the deck was invisible to both halves of
the guarantee**. An import of the very file S24a already imported would have
reported nine new words and written a second `tier` card beside card 17 — the
command written to prevent duplicates would have been the thing that created
them. Neither half works alone, which is why this ships in the same slice, the
same way `retire_chunk_cloze` shipped with `migrate_chunks`' creator change.

## The resolution rule, and the trap it exists to avoid

`core.services.cards.resolve_capture_lemma` — identity first, `ensure_lexeme`
otherwise, and **never `lemmatize`'s suffix step**. The reason is in that
function's docstring and it is worth naming here too, because this pass is where
it would have done its damage:

    lemmatize("tier") -> "ti"

`ti` is a real row in the seed list (rank 9,856), so nothing was "invented" and
the guard `lemmatize` advertises did not fire. A backfill through it would have
pointed card 17 at `ti`, and migration 013 says `lexeme_id` "is what `grade_card`
writes the ledger from" — so every future grade would have written ledger
evidence for the wrong word. **And it would have read green**, because the
importer makes the identical error on the identical input.

The dry run prints the resolution PATH, not just a count, for exactly this
reason: `7 identity + 2 grown` is the check. A total of `9` hides it.

## What it will not touch

- **Only `lexeme_id`.** No other column, and `chunks` is never read or written.
- **A phrase back stays NULL.** `ensure_lexeme`'s `GROWABLE` regex rejects
  anything with a space, so the reading and slang cards fall out by themselves.
  That is permanent and correct — a phrase has no lemma for a captured word to
  collide with — and it is stated so nobody later "fixes" it.
- **A card that already has a `lexeme_id`.** `set_card_lexeme` carries
  `AND lexeme_id IS NULL` in its own WHERE, so a second run writes nothing and a
  value some later slice corrected is not overwritten.

## What stops it

**A collision stops the run before anything is written.** Two cards resolving to
the same `(user_id, lemma, card_type)` would violate 015's index; this pass
counts those groups first and stops with the ids named, rather than applying half
the rows and failing on the one that collides. Two independent guarantees, the
shape `retire_chunk_cloze` uses: this module refuses on a collision it read, and
the index refuses on one it did not.

**No SQL lives here.** Every read and write is a `core.services.cards` function,
so `tests/test_core_boundary.py::test_cards_package_is_pure` stays unexempted and
#59 remains the only boundary exemption in this project.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter, defaultdict

from core.db import connection
from core.services import cards as cards_service

logger = logging.getLogger(__name__)

#: Resolution paths that mean "this card gets a lemma". `would_grow` is the dry
#: run's stand-in for `grown`, so the two runs report the same shape.
RESOLVED_PATHS = frozenset({"identity", "grown", "would_grow"})


def _plan(conn, *, grow: bool) -> list[tuple[int, int, str, str, int | None, str]]:
    """(card id, user id, card type, back, lexeme id, path) for every NULL card.

    `grow=False` keeps the whole pass read-only — see `resolve_capture_lemma`.
    """
    out = []
    for card_id, user_id, card_type, back in cards_service.cards_needing_a_lexeme(
        conn
    ):
        lexeme_id, path = cards_service.resolve_capture_lemma(conn, back, grow=grow)
        out.append((card_id, user_id, card_type, back, lexeme_id, path))
    return out


def _print_rows(rows) -> None:
    """Every candidate, whole. Nothing is summarised away before a write."""
    for card_id, user_id, card_type, back, _lexeme_id, path in rows:
        mark = "→" if path in RESOLVED_PATHS else "·"
        print(f"  {card_id:>4} · user {user_id} · {card_type:<11} · {back!r:<34} "
              f"{mark} {path}")


def _collisions(rows) -> dict[tuple[int, str, str], list[int]]:
    """Groups that would violate `cards_one_card_per_lemma`, keyed by the index.

    Keyed on the normalised back rather than on the resolved id, so a dry run —
    which resolves nothing it would have to create — reports the same collisions
    the apply would hit.
    """
    groups: dict[tuple[int, str, str], list[int]] = defaultdict(list)
    for card_id, user_id, card_type, back, _lexeme_id, path in rows:
        if path in RESOLVED_PATHS:
            groups[(user_id, back.strip().lower(), card_type)].append(card_id)
    return {key: ids for key, ids in groups.items() if len(ids) > 1}


def _summarise(rows) -> Counter:
    return Counter(path for *_rest, path in rows)


def _report(conn, *, grow: bool):
    rows = _plan(conn, grow=grow)
    print(f"{len(rows)} card(s) carry no lexeme_id.")
    if rows:
        print()
        _print_rows(rows)
        print()
        counts = _summarise(rows)
        for path in ("identity", "grown", "would_grow", "unresolved"):
            if counts.get(path):
                print(f"  {path:<12} {counts[path]}")
    return rows


def _stop_on_collisions(rows) -> bool:
    """Print and refuse. Returns True when the run must not continue."""
    clashes = _collisions(rows)
    if not clashes:
        return False
    print(f"\nSTOPPED. {len(clashes)} lemma(s) would land on two cards at once:")
    for (user_id, lemma, card_type), ids in sorted(clashes.items()):
        print(f"  user {user_id} · {lemma!r} · {card_type} · cards {sorted(ids)}")
    print(
        "\nNothing was written. Migration 015's `cards_one_card_per_lemma` would\n"
        "refuse these, and applying the rest first would leave the deck in a\n"
        "state neither half predicted. Report this rather than working around it."
    )
    return True


def _confirm(count: int) -> bool:
    """Make someone type the count back. There is no `--yes`.

    The guard `retire_chunk_cloze` and `core.items.seed_fixtures --purge` use,
    for the same reason: a flag that can be pasted from a runbook is not a
    decision, and this pass writes to cards two learners are reviewing.
    """
    print(f"\nAbout to set lexeme_id on {count} card(s) on this database.")
    print("Only that column is written; `chunks` is not touched. Confirm the")
    print("count against the rows listed above.")
    typed = input(f"Type the count ({count}) to continue, anything else to stop: ")
    return typed.strip() == str(count)


def dry_run() -> int:
    with connection() as conn:
        rows = _report(conn, grow=False)
        if not rows:
            print("\nNothing to do.")
            return 0
        if _stop_on_collisions(rows):
            return 1
        print("\ndry run — nothing was written. Re-run with --apply to write.")
        print(
            "Read the PATH column, not the total: a word absent from the seed\n"
            "list must report `would_grow`. If `tier` reports `identity`, the\n"
            "lemmatiser's suffix step is live and has resolved it to `ti` — stop."
        )
    return 0


def apply() -> int:
    with connection() as conn:
        rows = _report(conn, grow=False)
        if not rows:
            print("\nNothing to do.")
            return 0
        if _stop_on_collisions(rows):
            return 1

        expected = [r[0] for r in rows if r[5] in RESOLVED_PATHS]
        if not expected:
            print("\nNo card resolves to a lemma. Nothing to do.")
            return 0
        if not _confirm(len(expected)):
            print("Stopped. Nothing was written.")
            return 1

        # Resolve again WITH growth, inside the transaction that writes. The
        # dry pass above deliberately created nothing, so this is the first
        # moment `lexemes` may gain a row.
        written: list[int] = []
        with conn.transaction():
            for card_id, _user_id, _card_type, back, _lexeme_id, _path in rows:
                lexeme_id, path = cards_service.resolve_capture_lemma(
                    conn, back, grow=True
                )
                if lexeme_id is None:
                    continue
                if cards_service.set_card_lexeme(conn, card_id, lexeme_id):
                    written.append(card_id)
                logger.info("backfill card=%s path=%s", card_id, path)

        print(f"\nwrote lexeme_id on {len(written)} card(s): {sorted(written)}")
        missed = sorted(set(expected) - set(written))
        if missed:
            print(
                f"\nFINDING: {len(missed)} card(s) previewed but NOT written: "
                f"{missed}.\nThe service refuses a card that already has a "
                "lexeme_id, so one was set\nbetween the read and the write. This "
                "is not a successful run — record it."
            )
            return 1

    print(
        "\nConfirm the counts independently, in psql — the queries are the\n"
        "deployment step in BUILD_PROGRESS.md. A count this command prints about\n"
        "its own work is not verification of it. Read `lexemes WHERE\n"
        "origin='grown'` too: this pass may have added rows."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Set cards.lexeme_id from each card's back. Dry by default; "
        "--apply writes after the count is typed back."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the rows (default is a dry run that writes nothing)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    return apply() if args.apply else dry_run()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
