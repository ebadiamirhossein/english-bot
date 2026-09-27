"""Word practice — `/practice`. **W31d** (W24f, un-deferred by C6).

Three routes, each parsing, authorising, calling **one** service function and
serialising. **Plain `def`** (#7). The drill and the answer reach no model; the
audio reaches `core.speech` through `core.services.practice.word_audio`, which
returns bytes — the route never holds the word (for *hear it → type it* the
spoken text IS the answer, `items`' audio route's reason).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status

from apps.api.deps import rate_limit, require_current_user
from apps.api.schemas import (
    PracticeAnswerIn,
    PracticeAnswerOutcomeOut,
    PracticeExerciseOut,
    PracticeOut,
)
from core.services import practice as practice_service
from core.services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/practice", tags=["practice"])


@router.post(
    "/start",
    response_model=PracticeOut,
    response_model_exclude_none=True,
    dependencies=[Depends(rate_limit("practice_start", per_client=60, overall=240, window_seconds=3600))],
)
def start(session: AuthenticatedUser = Depends(require_current_user)) -> PracticeOut:
    """About five minutes of exercises from the learner's own cards, due first."""
    exercises = practice_service.start(session.id, now=datetime.now(timezone.utc))
    return PracticeOut(exercises=[PracticeExerciseOut(**e.wire()) for e in exercises])


@router.post(
    "/answer",
    response_model=PracticeAnswerOutcomeOut,
    response_model_exclude_none=True,
    dependencies=[Depends(rate_limit("practice_answer", per_client=600, overall=2000, window_seconds=3600))],
)
def answer(
    body: PracticeAnswerIn,
    session: AuthenticatedUser = Depends(require_current_user),
) -> PracticeAnswerOutcomeOut:
    """One answer. **Graded through FSRS only when the card is due** (Q8)."""
    outcome = practice_service.answer(
        session.id, card_id=body.card_id, kind=body.kind, response=body.response,
        now=datetime.now(timezone.utc), duration_ms=body.duration_ms,
    )
    if outcome is None:
        raise HTTPException(status_code=404, detail="not_found")
    return PracticeAnswerOutcomeOut(
        correct=outcome.correct, answer=outcome.answer, sentence=outcome.sentence,
        meaning=outcome.meaning, graded=outcome.graded,
    )


@router.get(
    "/{card_id}/audio",
    response_class=Response,
    responses={200: {"content": {"audio/mpeg": {}}}},
    dependencies=[Depends(rate_limit("practice_audio", per_client=200, overall=800, window_seconds=3600))],
)
def audio(card_id: int, session: AuthenticatedUser = Depends(require_current_user)) -> Response:
    """The card's word, spoken. A provider failure is a 503, `items`' rule."""
    try:
        data = practice_service.word_audio(session.id, card_id)
    except practice_service.PracticeAudioUnavailable:
        logger.warning("Practice audio unavailable user_id=%s card_id=%s", session.id, card_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="audio_unavailable"
        ) from None
    if data is None:
        raise HTTPException(status_code=404, detail="not_found")
    return Response(content=data, media_type="audio/mpeg")
