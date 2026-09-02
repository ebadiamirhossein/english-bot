"""W11b's one route. ARCHITECTURE §6, PRD §4.2.

It parses, authorises, calls **one** service function and serialises
(CLAUDE.md §2). No business logic here and no SQL: the five queries are in
`core/services/week.py`, which is what `test_no_sql_outside_services` holds.

**PLAIN `def`.** Standing rule 6 / #7: this blocks on a psycopg pool checkout,
and an `async def` would put that on the event loop and stall every other
request the worker is serving.

**The clock is read exactly once per request, here.** `core.services.week` takes
`now` as an argument and calls `datetime.now()` nowhere, which is what lets a
test walk the week boundary without freezing time (CLAUDE.md §3 rule 6) and what
makes `sunday` a fact the server owns rather than a browser's idea of the day.

**IT IS A READ AND IT WRITES NOTHING.** No table, no column, no migration, and
no model call — `GET /session/today` persists a block breakdown from a GET and
argues for it; this route has nothing of the kind to argue for.

**NO QUERY PARAMETER, DELIBERATELY.** `week_summary` takes a `week_ending` so a
test can assert the window's two ends without freezing the clock; exposing it
here would be a route with a parameter no client sends, and a learner asking for
an arbitrary past week is not a thing PRD §4.2 describes. The service picks the
week from the learner's own today.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from apps.api.deps import rate_limit, require_current_user
from apps.api.schemas import WeekOut
from core.services import week as week_service
from core.services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(tags=["week"])


@router.get(
    "/week",
    response_model=WeekOut,
    dependencies=[
        # Home fetches this once per open on Sunday and the report page once per
        # visit; a phone that backgrounds and resumes refetches. The same
        # ceiling `/session/today` carries, for the same reason: far above real
        # use, far below anything that would make the server work for a stolen
        # session. This read bills nothing.
        Depends(rate_limit("week", per_client=200, overall=800, window_seconds=3600))
    ],
)
def week(
    session: AuthenticatedUser = Depends(require_current_user),
) -> WeekOut:
    """The week this learner has just had.

    404 rather than 500 when the learner has no `users` row: an authenticated
    session whose user is gone is a fact about a deleted account, not a fault.
    **An EMPTY week is a 200**, not a 404 — an empty week is a fact about the
    week, and week one is both learners' state.
    """
    report = week_service.week_summary(session.id, now=datetime.now(timezone.utc))
    if report is None:
        raise HTTPException(status_code=404, detail="not_found")
    return WeekOut(
        week_ending=report.week_ending,
        sunday=report.sunday,
        days_with_a_session=report.days_with_a_session,
        items_answered=report.items_answered,
        items_right=report.items_right,
        cards_reviewed=report.cards_reviewed,
        words_now_known=report.words_now_known,
        units_passed=report.units_passed,
        empty=report.empty,
    )
