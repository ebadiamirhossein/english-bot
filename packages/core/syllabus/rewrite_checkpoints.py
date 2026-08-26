"""W8d: move every checkpoint's freed vocabulary items back into its grammar.

Human-run, dry by default, and it rewrites 24 production rows.

    python -m core.syllabus.rewrite_checkpoints            # prints 24 rows, writes nothing
    python -m core.syllabus.rewrite_checkpoints --apply    # type the count back, then write

**Why this exists.** #161 ruled the syllabus a GRAMMAR SPINE, which left every
checkpoint's `lexeme_items` block with no source (#166). At `lexeme_items: 3` a unit
had nine grammar items out of twelve -- 75% against an 80% pass mark -- so a learner
answering every grammar item correctly still failed. Eight units, seven of them the
first seven weeks. W8d sets the block to 0 and gives its items back to the unit's own
grammar targets, proportionally, so all twelve items test that unit's grammar.

The redistribution itself lives in `data/syllabus_units.json`, not here: this module
moves what the file says onto the rows, and the rule that produced those numbers is in
the decisions log where a rule belongs.

## Why it does not write its own statement

The write is `core.services.syllabus.upsert_units` -- the only thing that has ever
written `syllabus_units`. A second writer for one column would be a second place to
keep the JSONB shape right, and `upsert_units` already guards with `IS DISTINCT FROM`,
so a row that is already correct is not rewritten and a second run reports nothing done.

The cost is that `upsert_units` writes the whole row, and this command promises that
only `checkpoint` moves. **So it refuses to write when any other authored column
differs from the file** -- naming the column and the unit -- rather than silently
correcting drift its own report never showed. A refusal there is a finding about
production, not an obstacle: report it.

## What it prints, and what counts as verification

Every one of the 24 rows, before and after, changed or not. Nothing is summarised away
before a write: the dry run is the last record of the distribution as it stands on
production, and it belongs in the decisions log before `--apply` is ever run.

After writing, the rows are **read back from the database** and checked there. A count
this command prints about its own work is not verification of it -- the independent
`psql` query is a separate step in the deploy sequence, and that one is the evidence.

**No SQL lives here.** Both the read and the write are `core.services.syllabus`
functions, so `tests/test_core_boundary.py::test_syllabus_package_is_pure` stays
unexempted and #59 remains the only boundary exemption in this project.
"""

from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)

# The authored columns compared before the write, `checkpoint` excluded because it
# is the one this command is here to change.
_UNCHANGED_COLUMNS = (
    "stage",
    "can_do",
    "grammar_targets",
    "output_task_spoken",
    "output_task_written",
)


def _blocks(checkpoint: dict) -> str:
    """`4/3/3/2 + 0` -- the per-target counts and the lexeme block."""
    per_target = checkpoint.get("per_target") or {}
    counts = "/".join(str(per_target[name]) for name in per_target)
    return f"{counts} + {checkpoint.get('lexeme_items')}"


def _target_order(stored_targets) -> list[str]:
    return [entry.get("target") for entry in (stored_targets or [])]


def _file_targets(unit) -> list[str]:
    return [t.target for t in unit.grammar_targets]


def _stored_blocks_in_file_order(stored: dict, order: list[str]) -> str:
    """The stored counts, printed in the FILE's target order so the two rows line up.

    `checkpoint` is JSONB: Postgres returns object keys in its own order, not as
    authored, so printing the stored map as it arrives would put the before and
    after rows in different orders and make the comparison unreadable.
    """
    per_target = stored.get("per_target") or {}
    counts = "/".join(str(per_target.get(name, "?")) for name in order)
    return f"{counts} + {stored.get('lexeme_items')}"


def report(conn) -> tuple[list[int], list[str]]:
    """Print all 24 before/after rows. Returns (changing unit numbers, refusals)."""
    from core.services.syllabus import stored_units
    from core.syllabus import UNIT_COUNT
    from core.syllabus.content import units

    # Loading the file runs the blueprint gate first, so content that has not
    # passed it cannot reach a row.
    authored = {u.unit_number: u for u in units()}
    stored = {row.unit_number: row for row in stored_units(conn)}

    refusals: list[str] = []
    if set(stored) != set(range(1, UNIT_COUNT + 1)):
        refusals.append(
            f"the table holds units {sorted(stored)}, not 1-{UNIT_COUNT} -- "
            "run `python -m core.syllabus.seed` first"
        )
        print("\n".join(refusals))
        return [], refusals

    changing: list[int] = []
    print(f"{UNIT_COUNT} unit(s). per_target counts in the file's target order, "
          "then the lexeme block.\n")
    for number in range(1, UNIT_COUNT + 1):
        unit = authored[number]
        row = stored[number]
        order = _file_targets(unit)

        for column in _UNCHANGED_COLUMNS:
            file_value = getattr(unit, column)
            row_value = getattr(row, column)
            if column == "grammar_targets":
                file_value = order
                row_value = _target_order(row_value)
            if file_value != row_value:
                refusals.append(
                    f"unit {number}: `{column}` on the row differs from the file "
                    f"-- {row_value!r} vs {file_value!r}"
                )

        before = _stored_blocks_in_file_order(row.checkpoint, order)
        after = _blocks(unit.checkpoint)
        moves = before != after
        if moves:
            changing.append(number)
        flag = "  CHANGES" if moves else "  (already correct)"
        print(f"  unit {number:>2} · {before:>16}  ->  {after:<16}{flag}")

    print(f"\n{len(changing)} of {UNIT_COUNT} row(s) would change.")
    if refusals:
        print("\nSTOPPED. A column other than `checkpoint` differs from the file:")
        for line in refusals:
            print(f"  {line}")
        print(
            "\nNothing was written. This command promises that only `checkpoint` "
            "moves,\nand the writer rewrites the whole row -- so a difference here "
            "would be\ncorrected silently. Report it; do not work around it."
        )
    return changing, refusals


def _confirm(count: int) -> bool:
    """Make someone type the count back. There is no `--yes`.

    The guard `core.items.seed_fixtures --purge` and
    `core.cards.retire_chunk_cloze --purge` both use, for the same reason: a flag
    that can be pasted out of a runbook is not a decision.
    """
    print(f"\nAbout to rewrite the checkpoint blueprint on {count} row(s).")
    print("Confirm the count against the rows listed above.")
    typed = input(f"Type the count ({count}) to continue, anything else to stop: ")
    return typed.strip() == str(count)


def _verify(conn) -> int:
    """Read the rows back and check them there, not from what the write reported.

    This reads inside the same transaction, so it catches a write that did not do
    what this command believed it did. It cannot catch a commit that never landed
    -- the separate `psql` query in the deploy sequence is what covers that, and it
    is a human step for exactly that reason.
    """
    from core.services.syllabus import stored_units
    from core.syllabus import CHECKPOINT_ITEM_COUNT

    bad: list[str] = []
    rows = stored_units(conn)
    for row in rows:
        checkpoint = row.checkpoint
        lexeme_items = checkpoint.get("lexeme_items")
        grammar = sum((checkpoint.get("per_target") or {}).values())
        if lexeme_items != 0 or grammar != CHECKPOINT_ITEM_COUNT:
            bad.append(
                f"  unit {row.unit_number}: {grammar} grammar item(s), "
                f"lexeme_items {lexeme_items!r}"
            )
    print(f"\nread back from the database: {len(rows)} row(s)")
    if bad:
        print("FINDING -- these rows are not what was written:")
        print("\n".join(bad))
        return 1
    print(
        f"  all {len(rows)} carry {CHECKPOINT_ITEM_COUNT} grammar items and "
        "lexeme_items 0."
    )
    return 0


def dry_run(conn) -> int:
    changing, refusals = report(conn)
    if refusals:
        return 1
    if not changing:
        print("\nNothing to do — every row already matches the file.")
        return 0
    print("\ndry run — nothing was written. Re-run with --apply to write.")
    return 0


def apply(conn) -> int:
    from core.services.syllabus import upsert_units
    from core.syllabus.content import units

    changing, refusals = report(conn)
    if refusals:
        return 1
    if not changing:
        print("\nNothing to do — every row already matches the file.")
        return 0
    if not _confirm(len(changing)):
        print("Stopped. Nothing was written.")
        return 1

    counts = upsert_units(conn, units())
    print(f"\nsyllabus_units: {counts}")
    if counts.inserted:
        # upsert_units inserts a unit that is absent, and every unit was present
        # a moment ago -- so an insert means the row set moved under the command.
        print(
            f"\nFINDING: {counts.inserted} row(s) were INSERTED, not updated. "
            "Every unit\nexisted when the report above was read. Record this."
        )
        return 1
    return _verify(conn)


def main(argv: list[str] | None = None) -> int:
    from core.db import connection

    parser = argparse.ArgumentParser(
        description="Move each checkpoint's freed vocabulary items back into its "
        "grammar targets (W8d). Dry by default; --apply writes after the count is "
        "typed back."
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

    with connection() as conn:
        code = apply(conn) if args.apply else dry_run(conn)
        if code == 0 and args.apply:
            conn.commit()
        else:
            conn.rollback()
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
