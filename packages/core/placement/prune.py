"""`python -m core.placement.prune` — removes yes/no words the draw now refuses.
**Human-run, dry by default (#196). No billed call; no network.**

    python -m core.placement.prune            # dry: lists what would go and why; writes nothing
    python -m core.placement.prune --apply    # deletes them; the count is typed back

**Why it exists (launch 2026-09-26, B4).** W18-R1's reading of the host's bank
found *englishman* shown lower-case and both *mustache* and *moustache* drawn.
The draw now refuses both kinds (`targets.CAPITALISED_IN_USE`,
`targets.spelling_key`); this removes the rows already written. **Nobody has
sat the check** (`placement_run_items` is 0 on the host), so none is served.

**What it removes, and nothing else:** a real-word row whose word is in
`CAPITALISED_IN_USE`, and a real-word row whose spelling is a second spelling
of one already in the bank — **the later row by id goes; the first drawn
stays** (*moustache*, id after *mustache*). **A served row is REFUSED, never
deleted:** it is named in the print and left, and the DELETE itself carries the
same condition (`services.placement.delete_unserved_vocabulary`), so a sitting
that starts between the read and the write cannot lose an item it was shown.

**Predicted on the host, 2026-09-26 — exactly two:** `englishman` and
`moustache`. The draw is seeded, so the Mac's dry `core.placement.bank --free`
on an empty bank reproduces the host's 240 words; that list holds both, plus
*mustache*, and no other word either rule removes.

After it, `core.placement.bank`'s dry run plans the two words back — drawn
under the new rules.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

from core.placement.targets import CAPITALISED_IN_USE, spelling_key


@dataclass(frozen=True, slots=True)
class Candidate:
    id: int
    word: str
    reason: str
    served: bool


def candidates(rows: list[dict]) -> list[Candidate]:
    """Rows either rule removes, from `vocabulary_real_words` (oldest first)."""
    first_of: dict[str, str] = {}
    out: list[Candidate] = []
    for row in sorted(rows, key=lambda r: r["id"]):
        word, key = row["word"], spelling_key(row["word"])
        if word in CAPITALISED_IN_USE:
            out.append(Candidate(row["id"], word, "written with a capital", bool(row["served"])))
        elif key in first_of:
            out.append(Candidate(row["id"], word, f"second spelling of {first_of[key]!r}",
                                 bool(row["served"])))
        else:
            first_of[key] = word
    return out


def report(found: list[Candidate]) -> list[int]:
    """Print every candidate; return the ids that may be deleted."""
    for c in found:
        mark = "REFUSED — served, kept" if c.served else "remove"
        print(f"  {mark:<24} id {c.id:>6}  {c.word:<16} {c.reason}")
    deletable = [c.id for c in found if not c.served]
    print(f"rows to remove: {len(deletable)} · refused (served): "
          f"{sum(c.served for c in found)}")
    return deletable


def run(conn, *, apply: bool) -> list[int]:
    """The command's work on an open connection. Returns the ids deleted
    (``[]`` when dry). **Does not commit** — `main` does."""
    from core.services import placement as svc

    print("W18 placement bank — words the draw now refuses")
    deletable = report(candidates(svc.vocabulary_real_words(conn)))
    if not apply or not deletable:
        return []
    return svc.delete_unserved_vocabulary(conn, deletable)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove capitalised and second-spelling yes/no words from the "
        "placement bank. Dry by default; a served row is never removed.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)  # #140

    from core.db import connection
    from core.runs import confirm

    with connection() as conn:
        if not args.apply:
            run(conn, apply=False)
            conn.rollback()
            print("\ndry run — nothing was written.")
            return 0
        from core.services import placement as svc

        n = len([c for c in candidates(svc.vocabulary_real_words(conn)) if not c.served])
        conn.rollback()
        if n == 0:
            run(conn, apply=False)
            print("\nnothing to remove.")
            return 0
        if not confirm(f"This deletes {n} unserved placement_bank rows.", str(n)):
            print("stopped — nothing was written.")
            return 1
        deleted = run(conn, apply=True)
        conn.commit()
    print(f"deleted: {len(deleted)} rows (ids {deleted})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
