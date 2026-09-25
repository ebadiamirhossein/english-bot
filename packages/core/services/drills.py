"""Weak spots from the error journal — W17.

W17 was re-scoped on 2026-09-08 (W14r): its input was per-phoneme accuracy from
Azure, and that input stopped. **The journal is the input now**: `errors` already
holds what this learner actually gets wrong, and it is the thing CLAUDE.md §5
calls the product.

**THE EVIDENCE RULE, and it is the whole slice's safety property.** A pattern —
one `error_types.code` — is drillable for a learner only when the journal holds at
least `EVIDENCE_MIN_ROWS` rows of it for that learner inside
`EVIDENCE_WINDOW_DAYS`. A pattern with less is **never drilled and never reported
as mastered**: silence is not mastery. The journal undersamples by design (#412:
the journal's cap of two, G2's stated limits), so a learner who has never written
a sentence that needs the third-person `-s` has produced NO evidence about it, and
this module must not turn that absence into a claim.

**THE COUNT IS A THRESHOLD, NEVER A RANK AND NEVER A NUMBER ON THE WIRE.** #412:
a count capped by design must not be read as a rate, so which evidenced pattern is
served is decided by rotation (least recently drilled), not by which count is
largest. And CLAUDE.md §4: no count, score or tally reaches a learner. The count
is returned here for the operator's CLI (`python -m core.items.drills`) and for
nothing else.

**SQL lives here and in `core.services.items`, nowhere else** (CLAUDE.md §2).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from psycopg.rows import tuple_row

from core.db import cursor

#: **Three rows of one pattern.** The operator's ruling for the build run
#: (2026-09-25). One row is an incident; two can be one sentence corrected twice
#: in a week; three is the smallest number that says *this keeps happening*.
EVIDENCE_MIN_ROWS = 3

#: **The window the evidence must fall inside.** The build-run prompt says *"inside
#: the retention window"*, and **the tree has none**: nothing purges `errors`, and
#: the journal is kept for good (CLAUDE.md §5). So W17 defines one and says so
#: (decisions log, 2026-09-25): **60 days, the top rung of the journal's own
#: spacing ladder** (`core.services.errors.SPACING_DAYS[4]`). A pattern not seen
#: for longer than the ladder's longest interval is no longer current evidence of
#: anything, and the drills for it stop being served — silently, because a drop is
#: never announced (CLAUDE.md §4).
EVIDENCE_WINDOW_DAYS = 60

#: **Sources that are someone else's English do not evidence this learner's
#: pattern.** `capture` and `video` are barred from the journal already
#: (`core.lexicon.states.NOT_HARVESTED_SOURCES`); they are excluded here by name as
#: well, so a row that ever slipped in cannot become a drill. ASR sources (`voice`,
#: `diary`, `shadow`) DO count: a mishearing is never journaled (CLAUDE.md §5), so
#: a grammar error in a spoken sentence is the learner's own.
NOT_EVIDENCE_SOURCES = ("capture", "video")


@dataclass(frozen=True, slots=True)
class Pattern:
    """One evidenced weak spot. `evidence` never leaves the operator's CLI."""

    code: str
    learner_label: str
    evidence: int
    last_seen: datetime


def evidenced_patterns(user_id: int, *, now: datetime) -> list[Pattern]:
    """Every pattern this learner's journal evidences, **by code, alphabetical.**

    Alphabetical and not by count, deliberately (#412; the module docstring).
    A code with no `learner_label` (the three spoken codes) is never a drill: it
    has no name a learner could be shown, and W14r retired its instrument.
    """
    since = now - timedelta(days=EVIDENCE_WINDOW_DAYS)
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            """
            SELECT e.error_type, et.learner_label, count(*)::int, max(e.created_at)
              FROM errors e
              JOIN error_types et ON et.code = e.error_type
             WHERE e.user_id = %s
               AND e.created_at >= %s
               AND e.source <> ALL(%s)
               AND et.learner_label IS NOT NULL
             GROUP BY e.error_type, et.learner_label
            HAVING count(*) >= %s
             ORDER BY e.error_type
            """,
            (user_id, since, list(NOT_EVIDENCE_SOURCES), EVIDENCE_MIN_ROWS),
        )
        return [
            Pattern(code=row[0], learner_label=row[1], evidence=row[2], last_seen=row[3])
            for row in cur.fetchall()
        ]


def drill_labels(user_id: int, item_ids: Sequence[int]) -> dict[int, str]:
    """`{item_id: learner_label}` for the drills among `item_ids`. **The label only.**

    Read by id rather than carried on `ItemPresentation`, so the presentation —
    whose fields are a capability boundary (`core.services.items.ItemPresentation`)
    — is untouched, and a refetch that re-reads the session's stored ids gets the
    same labels as the first read.
    """
    if not item_ids:
        return {}
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            """
            SELECT items.id, et.learner_label
              FROM items
              JOIN error_types et ON et.code = items.error_type
             WHERE items.user_id = %s
               AND items.id = ANY(%s)
               AND items.payload ->> 'cohort' = 'drill'
               AND et.learner_label IS NOT NULL
            """,
            (user_id, list(item_ids)),
        )
        return {int(row[0]): row[1] for row in cur.fetchall()}


def learner_l1(user_id: int) -> str | None:
    """`users.native_language`, for the generator's `l1_to_l2_production` slot.

    The unit generator's payload carries no L1 (#424), which was harmless while
    only one learner had items. A drill is written for ONE learner's journal, so
    its production item must be in THAT learner's language.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute("SELECT native_language FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return row[0] if row else None
