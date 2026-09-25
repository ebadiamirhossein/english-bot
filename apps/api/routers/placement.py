"""W18's six routes: the placement test. PRD §6, ARCHITECTURE §6
(*"POST /placement/start | /answer | /finish"*).

Each parses, authorises, calls **one** service function and serialises
(CLAUDE.md §2). No business logic and no SQL; the queries are in
`core/services/placement.py`.

**Nothing here holds the hidden half of an item** — the service returns the
learner-visible face as plain data, and `/audio` receives BYTES
(`tests/test_core_boundary.py::test_the_api_never_reaches_the_hidden_half_of_an_item`).

**PLAIN `def` ON FIVE OF SIX** (standing rule 6 / #7): they block on a pool
checkout, `/answer` may make the speaking rubric's model call, and `/audio`
synthesises. **`POST /speak/{id}` is the one `async def`**, for
`/conversation/turn/voice`'s reason: the body cap must be enforced before the
body is read, and the blocking work goes through `asyncio.to_thread`.

**The clock is read once per request, here**, and passed down as `now`.

**404 and never 403 for the voice gate (#364)**: a learner without voice must
not be able to tell a gate from an absent feature.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from apps.api.deps import rate_limit, require_current_user
from apps.api.routers.cards import require_json
from apps.api.schemas import (
    PlacementAnswerIn,
    PlacementItemOut,
    PlacementOut,
    PlacementPointOut,
    PlacementResultOut,
    PlacementShownOut,
    PlacementSkillOut,
    PlacementStepOut,
)
from core.services import placement as svc
from core.services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/placement", tags=["placement"])

#: `/conversation/turn/voice`'s cap: two minutes of audio. PRD §6's answer is
#: ninety seconds.
MAX_AUDIO_BYTES = 2_000_000

#: Generous for a sitting (~95 answers) and a resumed one; far below abuse.
_LIMIT = Depends(rate_limit("placement", per_client=400, overall=1200, window_seconds=3600))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def shown_out(shown) -> PlacementShownOut:
    """The wire shape of `core.placement.scoring.Shown`. **The progress route and
    the fixture exporter build it through this same function** (#190)."""
    return PlacementShownOut(
        where_to_start=shown.where_to_start,
        radar=[PlacementSkillOut(skill=k, band=v) for k, v in shown.radar.items()],
        history=[PlacementPointOut(finished_on=p.finished_on, band=p.band) for p in shown.history],
        vocab_estimate=shown.vocab_estimate,
        raised_from=shown.raised_from,
        raised_skills=list(shown.raised_skills),
    )


def step_out(step) -> PlacementStepOut:
    return PlacementStepOut(
        section=step.section,
        item=PlacementItemOut(**step.item) if step.item is not None else None,
    )


def overview_out(view) -> PlacementOut:
    return PlacementOut(
        state=view.state,
        ready=view.ready,
        available=view.available,
        next_from=view.next_from,
        voice=view.voice,
        step=step_out(view.step) if view.step is not None else None,
        shown=shown_out(view.shown) if view.shown is not None else None,
    )


def result_out(result) -> PlacementResultOut:
    return PlacementResultOut(shown=shown_out(result.shown), next_from=result.next_from)


def _refusal(exc: svc.PlacementError) -> HTTPException:
    if isinstance(exc, (svc.NoSitting, svc.NotConsented)):
        return HTTPException(status.HTTP_404_NOT_FOUND, "no_sitting")
    if isinstance(exc, svc.NotReady):
        return HTTPException(status.HTTP_409_CONFLICT, "bank_not_ready")
    if isinstance(exc, svc.NotYet):
        return HTTPException(status.HTTP_409_CONFLICT, "not_yet")
    if isinstance(exc, svc.NotDone):
        return HTTPException(status.HTTP_409_CONFLICT, "not_done")
    if isinstance(exc, svc.StaleAnswer):
        return HTTPException(status.HTTP_409_CONFLICT, "stale")
    if isinstance(exc, svc.AudioUnavailable):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "audio_unavailable")
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "placement_error")


@router.get("", response_model=PlacementOut, dependencies=[_LIMIT])
def overview(session: AuthenticatedUser = Depends(require_current_user)) -> PlacementOut:
    """Where the learner is: nothing yet, a sitting open, or a result."""
    try:
        return overview_out(svc.overview(session.id, now=_now()))
    except svc.PlacementError as exc:
        raise _refusal(exc)


@router.post("/start", response_model=PlacementStepOut,
             dependencies=[Depends(require_json), _LIMIT])
def start(session: AuthenticatedUser = Depends(require_current_user)) -> PlacementStepOut:
    """Start a sitting, or resume the open one. **409** too soon or no bank."""
    try:
        return step_out(svc.start(session.id, now=_now()))
    except svc.PlacementError as exc:
        raise _refusal(exc)


@router.post("/answer", response_model=PlacementStepOut,
             dependencies=[Depends(require_json), _LIMIT])
def answer(
    body: PlacementAnswerIn,
    session: AuthenticatedUser = Depends(require_current_user),
) -> PlacementStepOut:
    """One answer; returns the next step. **409** when the item is not the one
    being asked. **The text is never logged and never stored.**"""
    submission = svc.Submission(
        text=body.text, option=body.option, tile_index=body.tile_index,
        order=tuple(body.order), pairs=dict(body.pairs),
    )
    try:
        return step_out(svc.answer(
            session.id, body.item_id, submission, now=_now(),
            known=body.known, skip=body.skip,
        ))
    except svc.PlacementError as exc:
        raise _refusal(exc)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad_answer")


@router.post("/speak/{item_id}", response_model=PlacementStepOut, dependencies=[_LIMIT])
async def speak(
    item_id: int,
    request: Request,
    session: AuthenticatedUser = Depends(require_current_user),
) -> PlacementStepOut:
    """The spoken answer. **413** oversized · **404** voice not enabled (#364) ·
    **422** nothing heard. Transcribed in memory and discarded."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "recording is too long")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_AUDIO_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "recording is too long")
        chunks.append(chunk)
    try:
        step = await asyncio.to_thread(
            svc.answer_voice, session.id, item_id, b"".join(chunks), now=_now()
        )
    except svc.PlacementError as exc:
        raise _refusal(exc)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "not_recognised")
    return step_out(step)


@router.get(
    "/items/{item_id}/audio",
    response_class=Response,
    responses={200: {"content": {"audio/mpeg": {}}}},
    dependencies=[_LIMIT],
)
def audio(
    item_id: int,
    session: AuthenticatedUser = Depends(require_current_user),
) -> Response:
    """A served listening clip, as speech. **404** unless it was served to this
    learner; **503** when the provider fails."""
    try:
        data = svc.item_audio(session.id, item_id)
    except svc.PlacementError as exc:
        raise _refusal(exc)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return Response(content=data, media_type="audio/mpeg")


@router.post("/finish", response_model=PlacementResultOut,
             dependencies=[Depends(require_json), _LIMIT])
def finish(session: AuthenticatedUser = Depends(require_current_user)) -> PlacementResultOut:
    """Read the sitting and write its result. **409** before every section is
    answered. Idempotent after it."""
    try:
        return result_out(svc.finish(session.id, now=_now()))
    except svc.PlacementError as exc:
        raise _refusal(exc)
