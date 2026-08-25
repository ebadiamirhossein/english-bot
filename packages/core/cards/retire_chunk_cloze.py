"""W8b's other half: remove the cloze cards `migrate_chunks` already created.

Human-run, dry by default, and it deletes production rows.

    python -m core.cards.retire_chunk_cloze            # lists every row, deletes nothing
    python -m core.cards.retire_chunk_cloze --purge    # type the count back, then delete

**Why this exists at all, and why the two halves are one slice.**
`core.cards.migrate_chunks` stopped planning a cloze card from a chunk in the
same commit as this file. Neither half works alone. Without the creator change,
deleting these rows leaves `UNIQUE (user_id, source_chunk_id, card_type)`
satisfiable again, so the next `migrate_chunks --apply` recreates all fourteen
and the fix is invisible to whoever ran it. Without this file, the fourteen
already on production stay in two learners' decks forever. The ruling and its
three causes are in `migrate_chunks`' docstring; this module is the arm of it
that reaches rows that already exist.

**Why a separate module and not `migrate_chunks --purge`.** The creator carries
a guarantee that it destroys nothing — `chunks` is never modified, held by an
AST scan and by a before/after snapshot — and a deletion path inside it makes
that guarantee read as narrower than it is to anyone who opens the file. The
cost of splitting them is discoverability, and it is paid by `migrate_chunks`
naming this module in its docstring rather than leaving a reader to find the
record.

---

## What it matches on, and what it can never reach

`card_type = 'cloze'` **and** `source_chunk_id IS NOT NULL`. Never a date range,
never a list of ids typed into a file — the reasoning
`core.services.items.delete_items_by_hash` gives one package over: a date range
sweeps rows nobody looked at, and an id list is a claim about the database that
stops being true the moment the database changes.

**W13's cloze cards are outside this command by construction, not by timing.** A
card built from a video line has no `source_chunk_id`, so no run of this command
at any moment can reach it. That is the property worth having: "we ran it before
W13" is a fact about a calendar, and the next person to run it has no way to
check that fact.

## What stops it

**A card that has ever been graded is not deleted, and the run stops.**
`card_reviews` is append-only by design and its composite foreign key cascades
from `cards`, so removing a graded card discards a real learner event silently.
The ruling assumes these fourteen have never been reviewed — W7 recorded
`card_reviews` 0 on production and its five review checks are still unrun — and
if that is false, the decision changes and it is not this module's to re-make.

Two independent guarantees, the shape `migrate_chunks` uses for idempotency:
this module refuses on a review it read, and `delete_chunk_cloze_cards` refuses
on a review it did not — a learner can grade a card between the read and the
write. When the two disagree, the difference is reported as a **finding**, not
absorbed as a success.

## What it prints before it deletes anything

Every row: id, learner, source chunk, front, back, review count. **The dry run
is the last record of these fourteen sentences** — after the purge they are gone
from the only place they existed — so its output belongs in the decisions log
before `--purge` is ever run. It is also the evidence for the work-bias count:
six of the fourteen are about deploys, models and validation sets, in a deck
where CLAUDE.md §4 caps Work at 20%.

**No SQL lives here.** Both queries are `core.services.cards` functions, so
`tests/test_core_boundary.py::test_cards_package_is_pure` stays unexempted and
#59 remains the only boundary exemption in this project.
"""

from __future__ import annotations

import argparse
import logging
import sys

from core.services import cards as cards_service

logger = logging.getLogger(__name__)


def _print_rows(rows: list[tuple]) -> None:
    """Every candidate, whole. Nothing is summarised away before a deletion."""
    for card, reviews in rows:
        flag = "" if reviews == 0 else f"  ** {reviews} REVIEW(S) **"
        print(f"  {card.id} · user {card.user_id} · chunk {card.source_chunk_id} · "
              f"{card.front!r} → {card.back!r} · {reviews} reviews{flag}")


def _reviewed(rows: list[tuple]) -> list[tuple]:
    return [(card, n) for card, n in rows if n > 0]


def _confirm(count: int) -> bool:
    """Make someone type the count back. There is no `--yes`.

    The same guard `core.items.seed_fixtures --purge` uses, for the same reason:
    the failure being guarded against is silent and permanent, and a flag that
    can be pasted from a runbook is not a decision.
    """
    print(f"\nAbout to delete {count} card(s) from the deck. This is permanent.")
    print("They are the chunk-derived cloze cards W8b retired; nothing else can")
    print("match. Confirm the count against the rows listed above.")
    typed = input(f"Type the count ({count}) to continue, anything else to stop: ")
    return typed.strip() == str(count)


def report() -> list[tuple]:
    """Read the candidates and print them. Writes nothing, ever."""
    rows = cards_service.chunk_cloze_cards_with_review_counts()
    print(f"{len(rows)} chunk-derived cloze card(s) — card_type='cloze' AND "
          "source_chunk_id IS NOT NULL.")
    if rows:
        print()
        _print_rows(rows)
    return rows


def dry_run() -> int:
    rows = report()
    if not rows:
        print("\nNothing to do.")
        return 0
    reviewed = _reviewed(rows)
    if reviewed:
        print(f"\n{len(reviewed)} of these have been graded. --purge would "
              "refuse; see the module docstring.")
    print("\ndry run — nothing was deleted. Re-run with --purge to delete.")
    return 0


def purge() -> int:
    rows = report()
    if not rows:
        print("\nNothing to do.")
        return 0

    reviewed = _reviewed(rows)
    if reviewed:
        # Stop. A grade against one of these is a real learner event, and the
        # ruling that retired these cards assumed there were none.
        print(f"\nSTOPPED. {len(reviewed)} card(s) carry a review:")
        for card, n in reviewed:
            print(f"  {card.id} · {n} review(s)")
        print(
            "\nNothing was deleted. `card_reviews` is append-only and cascades "
            "from `cards`,\nso deleting these would discard a graded review. "
            "The ruling assumed there were\nnone — report this rather than "
            "working around it."
        )
        return 1

    expected = [card.id for card, _ in rows]
    if not _confirm(len(expected)):
        print("Stopped. Nothing was deleted.")
        return 1

    deleted = cards_service.delete_chunk_cloze_cards()
    print(f"\ndeleted {len(deleted)} card(s): {sorted(deleted)}")

    missed = sorted(set(expected) - set(deleted))
    if missed:
        # The service's own guard fired, which means a review landed between the
        # read above and the write. Reported as a finding: the deck is now in a
        # state neither half predicted, and the record should say so.
        print(
            f"\nFINDING: {len(missed)} card(s) previewed but NOT deleted: "
            f"{missed}.\nThe service refuses a card carrying a review, so one "
            "was graded between the\nread and the write. This is not a "
            "successful run — record it."
        )
        return 1

    print(
        "\nConfirm the remaining counts independently, in psql — the queries "
        "are the\ndeployment step in BUILD_PROGRESS.md. A count this command "
        "prints about its own\nwork is not verification of it."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Delete the chunk-derived cloze cards W8b retired. Dry by "
        "default; --purge deletes after the count is typed back."
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="delete the rows (default is a dry run that deletes nothing)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    return purge() if args.purge else dry_run()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
