"""`python -m core.lexicon.seed` — load `data/lexemes.tsv` into the database.

Two commands, both idempotent, both run by hand:

    python -m core.lexicon.seed             # the reference table
    python -m core.lexicon.seed --ledger    # the v2 harvest

**W13c: `--ledger` no longer writes the frequency floor.** The floor is
`users.known_word_floor` (migration 030), computed at read time, and it is
corrected with `python -m core.lexicon.floor`. No `assumption` row is written by
anything any more; the W4-era ones are kept and not read.

**Where this sits relative to the deployment sequence, which does not change.**
The sequence is still `backup → pull → pip install -e packages/core → migrate →
restart`. This is a slice-specific one-off, run between `migrate` (the tables
must exist) and `restart`, on the deploy that first applies 010 and never again
unless `data/lexemes.tsv` changes. It is not a new permanent step.

A second run reports `0 inserted, 0 updated` and rewrites no row. Nothing here
ever deletes: a "sync" that removed lemmas absent from the file would cascade
through `user_lexemes` and destroy ledger history.

No SQL in this module — it parses the file and hands rows to
`core.services.lexicon`, which owns every query (CLAUDE.md §2).
"""

from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def seed_lexemes(conn) -> object:
    from core.services.lexicon import seed_rows_from_file, upsert_lexemes

    rows = seed_rows_from_file()
    counts = upsert_lexemes(conn, rows)
    logger.info("lexemes: %s (%d in file)", counts, len(rows))
    return counts


def seed_ledger(conn) -> None:
    """The v2 harvest, for every onboarded learner. The floor is not written."""
    from core.services.lexicon import harvest_v2, onboarded_user_ids

    for user_id in onboarded_user_ids(conn):
        harvested, barred = harvest_v2(conn, user_id)
        logger.info("user %s: v2 harvest %s", user_id, harvested)
        if barred:
            logger.warning(
                "user %s: %d `errors` rows have source='capture'. Capture is "
                "someone else's English and is barred from the journal "
                "(CLAUDE.md §5); these were NOT harvested. This is a "
                "pre-existing data defect worth filing.",
                user_id,
                barred,
            )


def main(argv: list[str] | None = None) -> int:
    from core.db import connection

    parser = argparse.ArgumentParser(description="Seed the lexicon.")
    parser.add_argument(
        "--ledger",
        action="store_true",
        help="also apply the v2 harvest per learner (the floor is not written)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    with connection() as conn:
        seed_lexemes(conn)
        if args.ledger:
            seed_ledger(conn)
        conn.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
