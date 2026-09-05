"""W13b's four routes. PRD §8.6, ARCHITECTURE §6.

Each parses, authorises, calls **one** service function and serialises
(CLAUDE.md §2). No business logic and no SQL.

**THERE IS NO `GET /conversation/today`, AND THAT IS §1e's PRECEDENT APPLIED
UNCHANGED.** The in-session conversation arrives in **block 4's payload from
`GET /session/today`**, the way block 2's video and W14's shadow line already
do, so exactly one place decides what block 4 serves. A second producer of one
contract is #190's defect: two call sites assembling one shape, one of them
incomplete, both suites green because the halves never meet.

**PLAIN `def` ON THREE OF FOUR.** They reach `llm.chat`, so TASKS standing rule
6 and `apps/api/README.md` apply: a blocking provider call inside an `async def`
route stalls every other request this worker is serving (#7, with a wider blast
radius).

**`POST /turn/voice` IS THE ONE `async def`, AND IT USES THE SANCTIONED ESCAPE**
— `await asyncio.to_thread(...)`, `tests/test_api.py`'s `OFF_LOOP_HELPERS`.
`shadow.py` makes the argument in full and it holds here for the same reason:
the body cap must be enforced **before** anything reads the body, and a sync
route makes FastAPI buffer the entire upload first, which is not a cap on the
one route whose risk is a recording that never stopped. `("speech",
"transcribe")` is already in `BLOCKING_CALLS`, so this route is **checked by
that sweep rather than exempted from it**.

**THE CAP NEVER FAILS MID-EXCHANGE.** It is checked before a turn is accepted,
so the learner's last message always gets a reply; the turn *after* that returns
`409`, which the client renders as the conversation being done for today. **No
number crosses the wire** — a remaining-turns count is a backlog running
backwards and a tally is a score (#348, PRD §8.6.4).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from apps.api.deps import rate_limit, require_current_user
from core.services import conversations as svc
from core.services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversation", tags=["conversation"])

#: Two minutes of 16 kHz mono WAV, the ceiling `shadow.py` already uses. The cap
#: is the only defence a free quota has against a recorder that never stopped.
MAX_AUDIO_BYTES = 2_000_000


class OpenIn(BaseModel):
    """§C1. The topic the learner picked, or none to let the app choose."""

    topic_label: str | None = Field(default=None, max_length=200)


class SaveWordIn(BaseModel):
    word: str = Field(min_length=1, max_length=80)


class TurnIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class CorrectionOut(BaseModel):
    """One correction the learner reads.

    **`journalable` IS NOT ON THIS MODEL AND THAT IS DELIBERATE.** Whether a
    correction reached the journal is the write path's business; putting it on
    the wire would invite a client to render *this one didn't count*, which is a
    tally about the learner's own speech.
    """

    you_said: str
    correct_form: str
    explanation: str


class TurnOut(BaseModel):
    conversation_id: int
    topic_label: str
    reply: str
    #: `open` or `closing`. **Never a count.**
    state: str


class CloseOut(BaseModel):
    """§C2 and §C3.

    **`summary` IS NOT ON THIS MODEL.** It is the app's own note about the
    conversation, written for a consumer that does not exist yet (#391); putting
    it on the wire would invite a client to render the app's assessment of the
    learner back at them, which is a report card by another name.
    """

    conversation_id: int
    corrections: list[CorrectionOut]
    did_well: str
    #: §C2. Offered to the deck. **Nothing is saved without a tap.**
    unknown_words: list[str]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_turn(result: svc.TurnResult) -> TurnOut:
    return TurnOut(
        conversation_id=result.conversation_id,
        topic_label=result.topic_label,
        reply=result.reply,
        state=result.state,
    )


@router.post(
    "/open",
    response_model=TurnOut,
    dependencies=[
        Depends(rate_limit("conversation_open", per_client=30, overall=120,
                           window_seconds=3600))
    ],
)
def open_conversation(
    body: OpenIn | None = None,
    session_id: int | None = None,
    session: AuthenticatedUser = Depends(require_current_user),
) -> TurnOut:
    """Open today's conversation. **409 when the day's turns are spent.**

    `topic_label` is §C1's chosen suggestion. Omitting it keeps the original
    behaviour — the opener chooses — so the route is backward compatible with
    the shape W13b shipped.
    """
    try:
        return _as_turn(
            svc.open_conversation(
                session.id,
                _now(),
                session_id=session_id,
                topic_label=body.topic_label if body else None,
            )
        )
    except svc.CapReached:
        raise HTTPException(status.HTTP_409_CONFLICT, "cap_reached")


@router.post(
    "/alternative",
    response_model=TurnOut,
    dependencies=[
        Depends(rate_limit("conversation_alt", per_client=20, overall=80,
                           window_seconds=3600))
    ],
)
def alternative(
    session: AuthenticatedUser = Depends(require_current_user),
) -> TurnOut:
    """**One swap, then the topic stands.** 409 when it is spent."""
    try:
        return _as_turn(svc.alternative_topic(session.id, _now()))
    except svc.NoConversation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no_conversation")
    except svc.AlternativeSpent:
        raise HTTPException(status.HTTP_409_CONFLICT, "alternative_spent")


@router.post(
    "/turn",
    response_model=TurnOut,
    dependencies=[
        Depends(rate_limit("conversation_turn", per_client=120, overall=400,
                           window_seconds=3600))
    ],
)
def turn(
    body: TurnIn,
    session: AuthenticatedUser = Depends(require_current_user),
) -> TurnOut:
    """One typed turn. **Not gated by the allowlist** — typed text already

    reaches Anthropic from `POST /correct`, which both learners use, so gating
    it would withdraw a surface rather than protect one (#364 is about voice).
    """
    try:
        return _as_turn(svc.add_turn(session.id, body.text, _now()))
    except svc.NoConversation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no_conversation")
    except svc.CapReached:
        raise HTTPException(status.HTTP_409_CONFLICT, "cap_reached")


@router.post(
    "/turn/voice",
    response_model=TurnOut,
    dependencies=[
        Depends(rate_limit("conversation_voice", per_client=60, overall=200,
                           window_seconds=3600))
    ],
)
async def voice_turn(
    request: Request,
    session: AuthenticatedUser = Depends(require_current_user),
) -> TurnOut:
    """One spoken turn. **413** oversized · **404** not on the allowlist (#364).

    **The audio is transcribed in-request and discarded.** The bytes are held in
    memory, handed to one service call and dropped; nothing is written to disk
    and nothing reaches R2.

    **404 and never 403 for the consent gate**: a blocked learner must not be
    able to tell a gate from an absent feature, because a 403 announces
    something she is excluded from.
    """
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "recording is too long"
        )

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_AUDIO_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "recording is too long"
            )
        chunks.append(chunk)
    audio = b"".join(chunks)

    now = _now()
    try:
        text = await asyncio.to_thread(svc.transcribe_turn, session.id, audio, now)
        result = await asyncio.to_thread(
            svc.add_turn, session.id, text, now, input_mode="voice"
        )
    except svc.NotConsented:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no_conversation")
    except svc.NoConversation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no_conversation")
    except svc.CapReached:
        raise HTTPException(status.HTTP_409_CONFLICT, "cap_reached")
    except svc.ConversationError:
        # An empty transcript: the provider heard nothing usable. **Not a turn**
        # -- storing one would put an empty sentence in the learner's history.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "not_recognised")
    return _as_turn(result)


@router.post(
    "/close",
    response_model=CloseOut,
    dependencies=[
        Depends(rate_limit("conversation_close", per_client=30, overall=120,
                           window_seconds=3600))
    ],
)
def close(
    session: AuthenticatedUser = Depends(require_current_user),
) -> CloseOut:
    """End it. **Corrections are SHOWN here; only some of them were written.**

    S1's ruling in one route: `journalable` decides the `errors` write inside
    the service and **does not filter this response**. A voice-only conversation
    returns up to two corrections and wrote none of them.
    """
    try:
        result = svc.close_conversation(session.id, _now())
    except svc.NoConversation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no_conversation")
    return CloseOut(
        conversation_id=result.conversation_id,
        corrections=[
            CorrectionOut(
                you_said=c.you_said,
                correct_form=c.correct_form,
                explanation=c.explanation,
            )
            for c in result.corrections
        ],
        did_well=result.did_well,
        unknown_words=list(result.unknown_words),
    )


@router.post(
    "/topics",
    dependencies=[
        Depends(rate_limit("conversation_topics", per_client=30, overall=120,
                           window_seconds=3600))
    ],
)
def topics(
    session: AuthenticatedUser = Depends(require_current_user),
) -> dict[str, Any]:
    """§C1. Three suggestions the learner picks from.

    **NO COUNT, NO BADGE, NO HISTORY OF SKIPPED TOPICS.** Those would make it a
    backlog; three suggestions that accumulate nothing are not one. Calling it
    again reshuffles — and nothing records that it was called.

    **`voice` RIDES ALONG BECAUSE `/talk` IS A PAGE OF ITS OWN NOW (§A) AND HAS
    NO SESSION PAYLOAD TO READ THE GATE FROM.** This is the page's first call,
    so the flag costs no extra round trip. **It is the same predicate the
    shadow surface uses** (`voice_allowed_for`, #364) — one condition, one
    home — and a gated learner gets `false`, which renders **no control at
    all** rather than a disabled one.
    """
    return {
        "topics": svc.suggest_topics(session.id, _now()),
        "voice": svc.voice_allowed_for(session.id),
    }


@router.post(
    "/save-word",
    dependencies=[
        Depends(rate_limit("conversation_save_word", per_client=60, overall=240,
                           window_seconds=3600))
    ],
)
def save_word(
    body: SaveWordIn,
    session: AuthenticatedUser = Depends(require_current_user),
) -> dict[str, str]:
    """§C2. One word from the conversation into the deck. **No model call.**

    Returns `saved` or `already` — **`already` is a state, not an error**
    (#178): a learner who taps a word twice has done nothing wrong.
    """
    try:
        return {"state": svc.save_conversation_word(session.id, body.word, _now())}
    except svc.ConversationError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "empty_word")
