"""Remove a lesson the operator has read and rejected. Human-run, typed, by unit.

    python -m core.lessons.remove --unit 1

**This is the half that makes #235's repair safe, and it exists as a COMMAND for
one reason: a rule with no command behind it stops being followed.**

`--apply` now writes the exact bytes `--live` verified (#235), which guarantees
that the row a learner renders is the artefact the gates passed -- but it does
NOT move the operator's reading before the write, and it does not claim to. The
reading still happens afterwards. So *"delete it if it is bad"* has to be
something you can actually run, at a path that is written down, with a
confirmation that names what is about to go.

**Typed confirmation, no `--yes`**, the same guard `core.lessons.generate`,
`seed_fixtures`, `rewrite_checkpoints` and `retire_chunk_cloze` all use: a flag
that can be pasted out of a runbook is not a decision. **You type the unit
number**, so the confirmation names the thing being removed rather than agreeing
to an abstraction.

**This module makes NO model call and holds NO SQL.** It goes through
`core.services.lessons`, so `test_no_sql_outside_services` stays unexempted and
it is deliberately absent from `LESSONS_MODEL_CALLERS` --
`test_lessons_package_is_pure` fails if it ever reaches a provider.

**What removal costs, stated so it is not discovered:** the unit serves no lesson
until `--live` and `--apply` are run again, and block 3 falls back to the line
saying the written explanation is on its way. That is the same screen a unit
which has never been generated shows, so a learner sees something coherent rather
than a hole. The billed cost of regenerating is one `--live` for that unit.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from core.runs import confirm
from core.syllabus import UNIT_COUNT

logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove one unit's grammar lesson. Human-run, typed."
    )
    parser.add_argument(
        "--unit", type=int, required=True,
        help="the unit whose lesson is to be removed. No default, deliberately.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    if not 1 <= args.unit <= UNIT_COUNT:
        parser.error(f"--unit must be between 1 and {UNIT_COUNT}")

    from core.services import lessons as lessons_service

    stored = lessons_service.for_unit(args.unit)
    if stored is None:
        print(f"Unit {args.unit} has no lesson at the current version. "
              "Nothing to remove.")
        return 0

    print(f"About to REMOVE the lesson for unit {args.unit}:")
    for section in stored.sections:
        print(f"    - {section.target}")
    print(f"  {len(stored.diagrams)} diagram(s).")
    print("\n  Block 3 will fall back to the line saying the written "
          "explanation is on its way,")
    print("  which is what a unit with no lesson already shows. Regenerating "
          "costs one --live.")

    if not confirm(f"\nRemove unit {args.unit}'s lesson?", str(args.unit)):
        print("Stopped. Nothing was removed.")
        return 1

    if lessons_service.delete_lesson(args.unit):
        print(f"Removed. Unit {args.unit} now serves no lesson.")
        print(f"  To replace it: python -m core.lessons.generate --live "
              f"--units {args.unit}")
        return 0
    print(f"Nothing was removed for unit {args.unit}.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
