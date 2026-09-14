"""`POST /correct` and `GET /write/today` — the writing surface (W3, then W16a).

Three properties of this router are load-bearing rather than stylistic, and each
one is a rule from somewhere else finally biting:

* **Plain `def`.** `POST /correct` reaches `core.llm.chat`, which is synchronous
  by design. Known issue #7 with a wider blast radius: an `async def` here would
  put a multi-second model call on the event loop and stall every other request
  the worker is serving. `tests/test_api.py::test_llm_and_speech_routes_are_plain_def`
  fails the commit that changes it.
* **JSON only.** W2 recorded that `SameSite=Lax` is not the CSRF barrier — the
  barrier is that every state-changing route is a JSON `POST`, which is never a
  [simple request](https://developer.mozilla.org/docs/Web/HTTP/CORS#simple_requests)
  and therefore always preflights, and the preflight is answered only for the
  two allowed origins. Accepting a form encoding would make this a simple
  request, remove the preflight, and remove the defence.
* **Behind a session, and rate limited.** It costs money per call on a surface
  the production access log shows is scanned continuously. The per-day
  **ceiling** (Ruling 3) is a separate thing from the rate limit: the limit
  bounds abuse per hour, the ceiling bounds a learner's day and reaches the
  screen as a boolean.

**W16a: THIS ROUTE NO LONGER CALLS `core.services.correction`.** That module is
v2's correction path and the Telegram handler still uses it unchanged; the web
calls `core.services.writing`, whose prompt, gates and log are the journal's.
Each route parses, authorises, calls **one** service function, and serialises.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from apps.api.deps import rate_limit, require_current_user
from apps.api.schemas import (
    CorrectionResult,
    CorrectRequest,
    KeepOut,
    KeepRequest,
    WriteTodayOut,
)
from core.services import writing
from core.services.auth import AuthenticatedUser
from core.services.users import get_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["correct"])

JSON_CONTENT_TYPE = "application/json"


def _now() -> datetime:
    """The route's clock, in one place so a test can pin it (CLAUDE.md §3 rule 6).

    Added with finding (c): once the service refuses a paragraph outside its day,
    a route test that read the wall clock would pass on Thursdays only.
    """
    return datetime.now(timezone.utc)


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


def result_out(outcome: writing.WritingOutcome) -> CorrectionResult:
    """The one serialiser for a journal correction.

    **Named and module-level so `scripts/export_write_fixture.py` uses it** — the
    Vitest and Playwright fixtures are this function's output, not a hand-written
    guess at it (#190).
    """
    return CorrectionResult(
        is_english=outcome.is_english,
        did_well=outcome.did_well,
        corrections=[
            {
                "you_said": c["you_said"],
                "correct_form": c["correct_form"],
                "explanation": c["explanation"],
                "label": c["label"],
            }
            for c in outcome.corrections
        ],
        structure=None if outcome.structure is None else list(outcome.structure),
        word_offers=list(outcome.word_offers),
    )


@router.get(
    "/write/today",
    response_model=WriteTodayOut,
    dependencies=[
        Depends(rate_limit("write_today", per_client=200, overall=800, window_seconds=3600))
    ],
)
def write_today(
    session: AuthenticatedUser = Depends(require_current_user),
) -> WriteTodayOut:
    """Today's writing task: the kind, the session to link to, and whether the day is used.

    **Reads only.** It never creates a session — `/write` reached from home
    before the session was opened gets `session_id: null`.
    """
    today = writing.today(session.id, now=_now())
    if today is None:
        raise HTTPException(status_code=404, detail="not_found")
    return WriteTodayOut(
        day_kind=today.day_kind,
        session_id=today.session_id,
        ceiling_reached=today.ceiling_reached,
        prompt=today.prompt,
    )


@router.post(
    "/correct",
    response_model=CorrectionResult,
    # Ruling 2: a refused opening line is ABSENT on the wire, not `null`.
    response_model_exclude_none=True,
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
    """Correct one journal entry, log it, and write what survives to the journal."""
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
        outcome = writing.correct_submission(
            user,
            body.text.strip(),
            day_kind=body.day_kind,
            session_id=body.session_id,
            now=_now(),
        )
    except writing.WrongDayKind:
        # Finding (c). A paragraph posted outside its day — usually a Thursday tab
        # left open into Friday. The client asks `GET /write/today` again and
        # keeps the text; nothing was spent and nothing was written.
        logger.info("Writing day kind refused user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="wrong_day_kind"
        ) from None
    except writing.CeilingReached:
        # Ruling 3. The same status and detail `/talk` uses, and no number: the
        # client shows the day's-writing-is-done state and nothing else.
        logger.info("Writing ceiling reached user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="cap_reached"
        ) from None
    except writing.NoParagraphTask:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="no_task"
        ) from None
    except writing.WritingUnavailable:
        # The model failed or answered with something unparseable. The honest
        # answer is that it did not work, and the client offers a retry.
        logger.warning("Correction unavailable user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="correction_unavailable",
        ) from None

    return result_out(outcome)


@router.post(
    "/write/keep",
    response_model=KeepOut,
    dependencies=[
        Depends(require_json),
        Depends(rate_limit("write_keep", per_client=60, overall=240, window_seconds=3600)),
    ],
)
def keep(
    body: KeepRequest,
    session: AuthenticatedUser = Depends(require_current_user),
) -> KeepOut:
    """W16b — keep one offered phrase in the deck (`1o`).

    **The offer rule is re-applied in the service**: a non-word, or a phrase whose
    words are not in the sentence sent with it, is a 422, never a card. **It cannot
    prove the phrase was OFFERED** — the client sends both halves, so a consistent
    invented pair is saved (#419; #408 is narrowed on this surface, not closed).
    *(This docstring read "a phrase that would not have been offered is a 422,
    never a card" — quoted, #82; finding (a).)* Plain `def`: it holds a pool
    checkout and a transaction lock.
    """
    try:
        status_ = writing.keep_phrase(session.id, body.phrase, body.sentence, now=_now())
    except writing.NotOfferable:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="not_offerable"
        ) from None
    return KeepOut(status=status_)
