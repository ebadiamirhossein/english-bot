"""W24e — *keep going*: `GET /keep-going` and `POST /keep-going/watch`.

Both plain `def` (TASKS standing rule 6): `options` may rank the video pool —
local CPU over stored transcripts, ~10 ms each — and a blocking call in an
`async def` would stall the worker. A route parses, authorises, calls ONE
service function and serialises (CLAUDE.md §2); everything else is in
`core.services.keep_going`.

**No model is called by either route**, and neither writes to the error
journal. `watch` writes at most one `extra` video assignment per learner per
day (migration 034).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from apps.api.deps import rate_limit, require_current_user
from apps.api.schemas import KeepGoingOut, WatchOut
from core.services import keep_going as keep_going_service
from core.services.auth import AuthenticatedUser

router = APIRouter(prefix="/keep-going", tags=["keep-going"])


def _now() -> datetime:
    """The route's clock, one seam so a test can pin the day (§3 rule 6)."""
    return datetime.now(timezone.utc)


@router.get(
    "",
    response_model=KeepGoingOut,
    dependencies=[Depends(rate_limit("keep_going", per_client=120, overall=480,
                                     window_seconds=3600))],
)
def options(session: AuthenticatedUser = Depends(require_current_user)) -> KeepGoingOut:
    """What may be offered now, as kinds. The client shows it only once the
    session is `finished`, or on Sunday (R2, R1)."""
    kinds = keep_going_service.options(session.id, now=_now())
    if kinds is None:
        raise HTTPException(status_code=404, detail="no_learner")
    return KeepGoingOut(options=list(kinds))


@router.post(
    "/watch",
    response_model=WatchOut,
    dependencies=[Depends(rate_limit("keep_going_watch", per_client=60, overall=240,
                                     window_seconds=3600))],
)
def watch(session: AuthenticatedUser = Depends(require_current_user)) -> WatchOut:
    """Today's open video, or one extra assigned by the selection score (R2).

    404 `nothing_to_watch` when there is none — nothing in band and unseen, or
    today's extra is already watched. Never a repeat, never below band.
    """
    chosen = keep_going_service.watch(session.id, now=_now())
    if chosen is None:
        raise HTTPException(status_code=404, detail="nothing_to_watch")
    return WatchOut(l1_language=chosen.l1_language, video=chosen.video)
