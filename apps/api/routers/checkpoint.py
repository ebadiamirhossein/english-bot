"""The Saturday checkpoint's three routes. PRD §3, §4.2.

Each parses, authorises, calls **one** service function, and serialises. The
same three properties `apps/api/routers/session.py` records hold here and for
the same reasons:

* **Plain `def`, all three.** Each blocks on a psycopg pool checkout. Standing
  rule 6 (issue #7 with a wider blast radius): an `async def` here puts that on
  the event loop and stalls every other request the worker is serving.

* **The clock is read exactly once per request, here.** The service takes `now`
  and calls `datetime.now()` nowhere, which is what lets a test walk local
  midnight without freezing time (CLAUDE.md §3 rule 6) -- and `retake_due_on` is
  four days from the LEARNER's local date, so this matters more than usual.

* **NOTHING IS GENERATED WHILE THE LEARNER WAITS.** A checkpoint's twelve items
  are written days earlier by `python -m core.items.generate --checkpoint`,
  human-run and attended (operator ruling 1, 2026-08-27). This route reads a
  bank.

**ANSWERING IS `POST /items/{id}/answer`, NOT A ROUTE HERE**, and that is
deliberate rather than an omission. A checkpoint item is an `items` row like any
other; grading it through a second path would mean two graders, and the one that
is not `core.items.response` would drift. The client passes `session_id` so the
attempt lands on the sitting, which is what `POST /checkpoint/{id}/complete`
counts from.

**NO PUNISHMENT COPY.** The fail path returns `passed: false`, a
`retake_due_on`, and **no score** -- see `CheckpointOut`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from apps.api.deps import rate_limit, require_current_user
from apps.api.schemas import CheckpointOut, ItemPresentationOut
from core.services import checkpoints as checkpoints_service
from core.services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/checkpoint", tags=["checkpoint"])


def _out(sitting: checkpoints_service.Checkpoint) -> CheckpointOut:
    return CheckpointOut(
        session_id=sitting.session_id,
        unit_number=sitting.unit_number,
        can_do=sitting.can_do,
        item_count=sitting.item_count,
        state=sitting.state,
        items=[
            ItemPresentationOut(
                id=one.id, response_mode=one.response_mode, projection=one.projection
            )
            for one in sitting.items
        ],
        passed=sitting.passed,
        score_pct=sitting.score_pct,
        retake_due_on=sitting.retake_due_on,
    )


@router.get(
    "/today",
    response_model=CheckpointOut,
    dependencies=[
        Depends(
            rate_limit(
                "checkpoint_today", per_client=200, overall=800, window_seconds=3600
            )
        )
    ],
)
def today(
    session: AuthenticatedUser = Depends(require_current_user),
) -> CheckpointOut:
    """This learner's sitting for today, hydrated.

    **Creates the sitting if it does not exist -- idempotently, through migration
    018's `sessions_one_checkpoint_per_user_per_date`.** A GET that writes, and
    the shape is the one `_get_or_create_daily` already uses: an
    `INSERT ... ON CONFLICT DO NOTHING` decided by a unique index, so a phone
    that backgrounds and resumes cannot produce two sittings. What must never go
    on a read path is a MUTATING write; an idempotent create-once is a different
    thing, and 018 is what makes it one.

    404 rather than 500 when the learner has no `users` row: an authenticated
    session whose user is gone is a fact about a deleted account, not a fault.
    """
    sitting = checkpoints_service.today(
        session.id, now=datetime.now(timezone.utc)
    )
    if sitting is None:
        raise HTTPException(status_code=404, detail="not_found")
    return _out(sitting)


@router.post(
    "/{session_id}/complete",
    response_model=CheckpointOut,
    dependencies=[
        Depends(
            rate_limit(
                "checkpoint_complete", per_client=60, overall=200, window_seconds=3600
            )
        )
    ],
)
def complete(
    session_id: int,
    session: AuthenticatedUser = Depends(require_current_user),
) -> CheckpointOut:
    """Score the sitting and write the unit's state. **Idempotent by the claim.**

    **No request body, so no `require_json`**, the same deliberate difference
    `POST /session/{id}/block/{n}/complete` records: the CSRF barrier a JSON POST
    relies on is its preflight, and a bodiless POST is a simple request, so the
    barrier here is the session cookie's `SameSite` plus the fact that a second
    call changes nothing.

    **A second call changes nothing because of the claim**, not because of
    politeness: `core.services.checkpoints.complete` claims the sitting's row by
    flipping `completed` from false to true and returning its id, all in one
    statement -- and when no id comes back it returns the recorded result without
    calling `record_checkpoint`. Without that, a double tap would bump
    `checkpoint_attempts` twice and **move `retake_due_on` with it**.

    The statement itself is in the service, where every statement in this project
    lives (CLAUDE.md §2). It is described here and not quoted, because a route
    that quotes SQL is one edit away from running it.

    The score is counted from `item_attempts`, never from a number the client
    sends -- #108's standing lesson.
    """
    sitting = checkpoints_service.complete(
        session.id, session_id, now=datetime.now(timezone.utc)
    )
    if sitting is None:
        raise HTTPException(status_code=404, detail="not_found")
    return _out(sitting)
