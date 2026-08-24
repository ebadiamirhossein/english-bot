"""`python -m core.lexicon.repair` — undo the W4 harvest's demotions.

    python -m core.lexicon.repair --dry-run    # counts only, writes nothing
    python -m core.lexicon.repair              # applies, prints the same counts

**What it repairs.** W4's conflict rule gated demotion on source rank alone, so
`v2_encountered` at rank 1 outranked the rank-0 frequency floor and a passive
exposure pulled `known` down to `seen`. On the first production harvest that
cost one learner 231 of their 2,000 floor lemmas — the more they had used the
app, the lower their coverage read. W4a fixes the rule; this fixes the rows it
already wrote, which no future write would ever raise back, because
`v2_encountered` can only ever assert `seen`.

**Why a command and not a migration.** The row set depends on
`LEXICON_ASSUMED_KNOWN_TOP_N`, which is configuration, and a migration must not
read configuration — it would bake one deployment's setting into the schema
history. W4a carries no migration at all: the rule lives in a SQL string in
`core.services.lexicon`, and nothing about the schema changes.

Idempotent: a second run reports zero, because the rows it repaired now read
`assumption` and fall outside the filter. No SQL in this module — it prints and
calls the service, which owns every query (CLAUDE.md §2).
"""

from __future__ import annotations

import argparse
import sys

def _render(title: str, counts: list[tuple[int, int]]) -> None:
    print(title)
    if not counts:
        print("  (none)")
        return
    for user_id, count in counts:
        print(f"  user {user_id}: {count} rows")
    print(f"  total: {sum(c for _, c in counts)} rows")


def _coverage(conn, title: str, totals) -> None:
    print(title)
    for user_id, covered, total in totals(conn):
        print(f"  user {user_id}: covered {covered} / total {total}")


def main(argv: list[str] | None = None) -> int:
    from core.config import load_settings
    from core.db import connection
    from core.services.lexicon import (
        VERIFICATION_QUERY,
        count_demoted_floor_rows,
        coverage_totals,
        restore_demoted_floor_rows,
    )

    parser = argparse.ArgumentParser(description="Repair W4's demoted floor rows.")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the counts and write nothing"
    )
    parser.add_argument("--top-n", type=int, default=None)
    args = parser.parse_args(argv)

    top_n = args.top_n or load_settings().lexicon_assumed_known_top_n

    with connection() as conn:
        print(f"floor size (LEXICON_ASSUMED_KNOWN_TOP_N): {top_n}\n")
        _coverage(conn, "Before — coverage by learner:", coverage_totals)

        counts = count_demoted_floor_rows(conn, top_n)
        print()
        _render("Floor lemmas demoted by the W4 harvest:", counts)

        if args.dry_run:
            print("\n--dry-run: nothing written.")
            conn.rollback()
        else:
            applied = restore_demoted_floor_rows(conn, top_n)
            conn.commit()
            print()
            _render("Restored to known/assumption:", applied)
            print()
            _coverage(conn, "After — coverage by learner:", coverage_totals)

    print(
        "\nVerify independently:\n\n" + VERIFICATION_QUERY + "\n\n"
        "Expected: covered >= the floor size for every learner, and strictly\n"
        "greater for the two with v2 history — their harvest also inserted\n"
        "genuinely new lemmas outside the floor."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
