"""W19's one route: `GET /progress`. PRD §9.

It parses, authorises, calls **one** service function and serialises
(CLAUDE.md §2). No business logic and no SQL here; the queries are in
`core/services/progress.py`.

**PLAIN `def`** (standing rule 6 / #7): it blocks on a psycopg pool checkout.

**The clock is read exactly once per request, here**, and passed in as `now`.

**IT WRITES ONE ROW** — today's `progress_snapshots` point (029), which is the
known-word history and the XP high-water mark. The service's docstring argues
it; the write is idempotent and bills nothing. No model call.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from apps.api.deps import rate_limit, require_current_user
from apps.api.schemas import KnownPointOut, ProgressOut
from core.services import progress as progress_service
from core.services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(tags=["progress"])


@router.get(
    "/progress",
    response_model=ProgressOut,
    dependencies=[
        # `/week`'s ceiling, for `/week`'s reason: far above real use, far below
        # anything that would make the server work for a stolen session.
        Depends(rate_limit("progress", per_client=200, overall=800, window_seconds=3600))
    ],
)
def progress(
    session: AuthenticatedUser = Depends(require_current_user),
) -> ProgressOut:
    """This learner's progress. 404 when the `users` row is gone."""
    summary = progress_service.progress_summary(
        session.id, now=datetime.now(timezone.utc)
    )
    if summary is None:
        raise HTTPException(status_code=404, detail="not_found")
    logger.info("progress read user_id=%s", session.id)
    return progress_out(summary)


def progress_out(summary: progress_service.Progress) -> ProgressOut:
    """The wire shape. **`scripts/export_progress_fixture.py` builds the
    frontend's fixture through this same function** (#190), so the client is
    tested against what the route serialises, not against a guess."""
    return ProgressOut(
        known_words=summary.known_words,
        known_history=[
            KnownPointOut(local_date=p.local_date, known_words=p.known_words)
            for p in summary.known_history
        ],
        xp=summary.xp,
        streak_days=summary.streak_days,
        freezes=summary.freezes,
        units_passed=summary.units_passed,
    )
