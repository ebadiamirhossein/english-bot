"""`python -m core.syllabus.seed` — load the 24 units and their candidates.

    python -m core.syllabus.seed --dry-run   # validate the files, write nothing
    python -m core.syllabus.seed

**Where this sits relative to the deployment sequence, which does not change.**
The sequence is still `backup -> pull -> pip install -e packages/core ->
migrate -> restart`. This is a slice-specific one-off run BETWEEN `migrate` (the
tables must exist) and `restart`, exactly where `core.lexicon.seed` sits, and
again whenever the content files change. It is not a new permanent step.

Why a command and not DDL inside 014, which is the same question W4 and W7 both
answered the same way: a migration is not a content pipeline; content that will
be CORRECTED wants a re-runnable path; and "run it twice, the second run writes
nothing" is not a testable criterion for a file `schema_version` physically
cannot run twice.

A second run reports `0 inserted, 0 updated, 0 deleted`. The unit rows are
never deleted; the candidate pairs are reconciled, and the asymmetry is
explained in `core.services.syllabus.reconcile_unit_lexemes`.

No SQL in this module — it validates the files and hands the result to
`core.services.syllabus`, which owns every query (CLAUDE.md §2).
"""

from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def seed(conn, *, dry_run: bool = False) -> int:
    """Returns a process exit code: 0 ok, 1 refused."""
    from core.services.syllabus import (
        missing_lemmas,
        orphan_unit_lexemes,
        reconcile_unit_lexemes,
        upsert_units,
        validate_items_fk,
    )
    from core.syllabus import TARGET_LEXEME_FLOOR, UNIT_CANDIDATE_TARGET
    from core.syllabus.content import unit_lexemes, units

    # Both loaders validate as they read and raise ContentError on anything
    # unshippable, so a malformed unit stops the run before a row is written
    # rather than after some of them are.
    all_units = units()
    by_unit = unit_lexemes()
    logger.info(
        "content ok: %d units, %d candidate lexemes, min %d per unit (target %d)",
        len(all_units),
        sum(len(v) for v in by_unit.values()),
        min(len(v) for v in by_unit.values()),
        UNIT_CANDIDATE_TARGET,
    )

    # Every candidate must resolve to a real `lexemes` row. Checked BEFORE the
    # write, so a missing word is named rather than silently dropped by the
    # join inside reconcile_unit_lexemes.
    every = [lemma for lemmas in by_unit.values() for lemma in lemmas]
    absent = missing_lemmas(conn, every)
    if absent:
        logger.error(
            "%d candidate lemma(s) have no `lexemes` row: %s%s",
            len(absent),
            ", ".join(sorted(absent)[:12]),
            " ..." if len(absent) > 12 else "",
        )
        logger.error(
            "The build script only emits lemmas the lexicon seed already holds, "
            "so this means a hand-edited row. Add it with core.services.lexicon."
            "ensure_lexeme (origin='grown') or remove it -- do not let the join "
            "drop it."
        )
        return 1

    if dry_run:
        logger.info("dry run — nothing written")
        return 0

    unit_counts = upsert_units(conn, all_units)
    logger.info("syllabus_units: %s", unit_counts)

    lexeme_counts = reconcile_unit_lexemes(conn, by_unit)
    logger.info("syllabus_unit_lexemes: %s", lexeme_counts)

    orphans = orphan_unit_lexemes(conn)
    logger.info("orphan candidate rows: %d (must be 0)", orphans)
    if orphans:
        return 1

    # The last step, and it is an acceptance criterion rather than a log line:
    # 014 added `items_unit_number_fkey` NOT VALID because `syllabus_units` was
    # empty at migration time. A NOT VALID constraint nobody validates is a
    # silent hole.
    validated = validate_items_fk(conn)
    logger.info("items_unit_number_fkey convalidated: %s", validated)
    if not validated:
        return 1

    logger.info(
        "done. The >=%d bar is PER LEARNER and is measured after the ledger "
        "diff -- run --report to see it.",
        TARGET_LEXEME_FLOOR,
    )
    return 0


def report(conn) -> int:
    """Print the per-learner target counts. The acceptance criterion's instrument.

    The shared candidate count is NOT the criterion and is not reported as
    though it were: the W8 row says ">=30 target lexemes", and a target lexeme
    is one that survives the learner's own ledger.
    """
    from core.services.lexicon import onboarded_user_ids
    from core.services.syllabus import target_counts
    from core.syllabus import TARGET_LEXEME_FLOOR

    failed = False
    for user_id in onboarded_user_ids(conn):
        counts = target_counts(conn, user_id)
        if not counts:
            logger.warning("user %s: no units — is the seed run?", user_id)
            failed = True
            continue
        values = [c for _, c in counts]
        low = [(u, c) for u, c in counts if c < TARGET_LEXEME_FLOOR]
        logger.info(
            "user %s: min %d, max %d, mean %.1f across %d units%s",
            user_id,
            min(values),
            max(values),
            sum(values) / len(values),
            len(values),
            f" — BELOW {TARGET_LEXEME_FLOOR}: {low}" if low else "",
        )
        failed = failed or bool(low)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    from core.db import connection

    parser = argparse.ArgumentParser(description="Seed the 24-unit syllabus.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--report",
        action="store_true",
        help="print per-learner target counts after the ledger diff",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    with connection() as conn:
        if args.report:
            code = report(conn)
        else:
            code = seed(conn, dry_run=args.dry_run)
        if code == 0 and not args.dry_run:
            conn.commit()
        else:
            conn.rollback()
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
