"""The daily session's two routes. Each parses, authorises, calls **one**
service function, and serialises. PRD §4.1, ARCHITECTURE §6.

Three properties, load-bearing rather than stylistic:

* **Plain `def`, both.** Each blocks on a psycopg pool checkout and
  `/session/today` takes three of them in sequence. Standing rule 6 (issue #7
  with a wider blast radius): an `async def` here puts that on the event loop
  and stalls every other request the worker is serving.

* **The clock is read exactly once per request, here.** `core.services.sessions`
  takes `now` as an argument and calls `datetime.now()` nowhere, which is what
  lets a test walk local midnight without freezing time (CLAUDE.md §3 rule 6)
  and what makes the boundary between one day's session and the next assertable.

* **NOTHING IS GENERATED WHILE THE LEARNER WAITS.** No model call, no provider
  wrapper, no import of `core.llm` or `core.speech` — ARCHITECTURE §7, and
  `tests/test_session_route.py` asserts it through the network guard rather than
  by reading this comment. W10 generates nothing at all, so it is trivially true
  today; the assertion exists because it stops being trivial with the generation
  slice.

**A whole-route failure is an HTTP error, never five empty blocks.** One block's
dependency falling over becomes that block's `unavailable` state, inside the
service; a failure of the route itself is a 5xx and the client shows a retry.
A learner must never read *nothing’s due, go watch something* because a query
timed out.

**This route does not replace `GET /items`.** `/session/today` is a different
resource — a session, with blocks and progress — hydrated from the same
`core.services.items.presentations_for` the bank uses, which is the cross-slice
contract recorded at `core/services/items.py`'s "what a learner is allowed to
receive" banner. W10 writes no serialiser of its own.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from apps.api.deps import rate_limit, require_current_user
from apps.api.schemas import BlockOut, SessionTodayOut
from core.services import sessions as sessions_service
from core.services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/session", tags=["session"])


def _out(session: sessions_service.DailySession) -> SessionTodayOut:
    return SessionTodayOut(
        session_id=session.id,
        date=session.date,
        l1_language=session.l1_language,
        current_block=session.current_block,
        completed=session.completed,
        finished=session.finished,
        blocks=[
            BlockOut(n=b.n, kind=b.kind, state=b.state, payload=b.payload)
            for b in session.blocks
        ],
    )


@router.get(
    "/today",
    response_model=SessionTodayOut,
    dependencies=[
        # A learner opens this a handful of times a day; a phone that
        # backgrounds and resumes refetches. 200/hour is far above real use and
        # far below anything that would make the server do work for a stolen
        # session. Hydration bills nothing.
        Depends(rate_limit("session_today", per_client=200, overall=800, window_seconds=3600))
    ],
)
def today(
    session: AuthenticatedUser = Depends(require_current_user),
) -> SessionTodayOut:
    """Today's five blocks, hydrated, resumable.

    Creates the day's row if `assign_daily` has not run — idempotently, through
    migration 016's partial UNIQUE, so the job and an early opener cannot make
    two.

    404 rather than 500 when the learner has no `users` row: an authenticated
    session whose user is gone is a fact about a deleted account, not a fault.
    """
    daily = sessions_service.today(
        session.id, now=datetime.now(timezone.utc)
    )
    if daily is None:
        raise HTTPException(status_code=404, detail="not_found")
    return _out(daily)


