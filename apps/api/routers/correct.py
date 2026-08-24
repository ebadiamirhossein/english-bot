"""`POST /correct` — the first route that teaches, and the first that spends.

Three properties of this route are load-bearing rather than stylistic, and each
one is a rule from somewhere else finally biting:

* **Plain `def`.** It reaches `core.llm.chat`, which is synchronous by design.
  Known issue #7 with a wider blast radius: an `async def` here would put a
  multi-second model call on the event loop and stall every other request the
  worker is serving. `tests/test_api.py::test_llm_and_speech_routes_are_plain_def`
  fails the commit that changes it.
* **JSON only.** W2 recorded that `SameSite=Lax` is not the CSRF barrier — the
  barrier is that every state-changing route is a JSON `POST`, which is never a
  [simple request](https://developer.mozilla.org/docs/Web/HTTP/CORS#simple_requests)
  and therefore always preflights, and the preflight is answered only for the
  two allowed origins. `/correct` is the first route that actually writes, so
  that position stops being theoretical. Accepting a form encoding would make
  this a simple request, remove the preflight, and remove the defence.
* **Behind a session, and rate limited.** It costs money per call on a surface
  the production access log shows is scanned continuously.

It calls exactly one service function. The correction logic is
`core.services.correction`, shared with the Telegram handler — there is one
correction path in this project, not two.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from apps.api.deps import rate_limit, require_current_user
from apps.api.schemas import CorrectionResult, CorrectRequest
from core.services import correction
from core.services.auth import AuthenticatedUser
from core.services.users import get_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["correct"])

JSON_CONTENT_TYPE = "application/json"


def require_json(request: Request) -> None:
    """Refuse anything that is not JSON, explicitly.

    FastAPI would already answer 422 for a form body against a JSON model, but
    that is the right outcome for an incidental reason. This makes the refusal
    the route's own decision, so it survives someone later adding a `Form(...)`
    parameter — which would silently turn this into a simple request and delete
    the CSRF barrier described in the module docstring.
    """
    media_type = (request.headers.get("content-type") or "").split(";")[0].strip()
    if media_type.lower() != JSON_CONTENT_TYPE:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="json_required",
        )


@router.post(
    "/correct",
    response_model=CorrectionResult,
    dependencies=[
        Depends(require_json),
        # A learner writing every two minutes for a solid hour would use 30.
        # Anything past that is not practice. The global ceiling bounds the
        # whole surface, because the realistic threat here is one stolen
        # session rather than a stranger — a stranger has no session at all.
        Depends(rate_limit("correct", per_client=30, overall=120, window_seconds=3600)),
    ],
)
def correct(
    body: CorrectRequest,
    session: AuthenticatedUser = Depends(require_current_user),
) -> CorrectionResult:
    """Correct a piece of free writing and write any errors to the journal."""
    user = get_user(session.id)
    if user is None:
        # A live session whose users row vanished. Not reachable through any
        # normal path — the session lookup joins that row — so it is a real
        # inconsistency rather than a client error.
        logger.error(
            "Session resolved for a missing user row user_id=%s",
            session.id,
        )
        raise HTTPException(status_code=401, detail="not_authenticated")

    try:
        outcome = correction.correct(user, body.text.strip())
    except correction.CorrectionUnavailable:
        # The model failed or answered with something unparseable. The bot
        # retries because it can tell the learner it is retrying; here the
        # honest answer is that it did not work, and the client offers a retry.
        logger.warning("Correction unavailable user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="correction_unavailable",
        ) from None

    return CorrectionResult(
        is_english=outcome.is_english,
        has_errors=outcome.has_errors,
        did_well=outcome.did_well,
        corrections=outcome.corrections,
    )
