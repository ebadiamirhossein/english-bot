"""`python -m core.lexicon.seed` — load `data/lexemes.tsv` into the database.

Two commands, both idempotent, both run by hand:

    python -m core.lexicon.seed             # the reference table
    python -m core.lexicon.seed --ledger    # the frequency floor + the v2 harvest

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


def seed_ledger(conn, top_n: int) -> None:
    """The frequency floor and the v2 harvest, for every onboarded learner."""
    from core.services.lexicon import (
        assume_top_frequency_known,
        harvest_v2,
        onboarded_user_ids,
    )

    for user_id in onboarded_user_ids(conn):
        floor = assume_top_frequency_known(conn, user_id, top_n)
        harvested, barred = harvest_v2(conn, user_id)
        logger.info(
            "user %s: floor(top %d) %s | v2 harvest %s", user_id, top_n, floor, harvested
        )
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
    from core.config import load_settings
    from core.db import connection

    parser = argparse.ArgumentParser(description="Seed the lexicon.")
    parser.add_argument(
        "--ledger",
        action="store_true",
        help="also apply the frequency floor and the v2 harvest per learner",
    )
    parser.add_argument("--top-n", type=int, default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    top_n = args.top_n or load_settings().lexicon_assumed_known_top_n

    with connection() as conn:
        seed_lexemes(conn)
        if args.ledger:
            seed_ledger(conn, top_n)
        conn.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
