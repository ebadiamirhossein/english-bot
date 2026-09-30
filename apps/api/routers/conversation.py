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
from typing import Any, Literal
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
    """§C1. The topic the learner picked, or none to let the app choose.

    **W15: `kind`.** `talk` (the default, so W13b's shape is unchanged),
    `answer` or `retell`. A rung ignores `topic_label` — its opener is the
    unit's task or the video, never a choice.
    """

    topic_label: str | None = Field(default=None, max_length=200)
    kind: Literal["talk", "answer", "retell"] = "talk"


class SaveWordIn(BaseModel):
    word: str = Field(min_length=1, max_length=80)
    #: #408. The token the close-out signed this word with. Required.
    token: str = Field(min_length=1, max_length=64)


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
    #: W15. `error_types.learner_label`, the card's eyebrow — `/write`'s `1k`
    #: anatomy. **Null when the code has none** (the three spoken codes), and
    #: the card then carries no eyebrow rather than an invented one.
    label: str | None = None


class TurnOut(BaseModel):
    conversation_id: int
    topic_label: str
    #: The app's reply. **Empty on a rung** (W15): a rung takes one turn and
    #: generates nothing until the close.
    reply: str
    #: `open` or `closing`. **Never a count.**
    state: str
    #: **W15 — what Whisper heard, on a VOICE turn only; null otherwise.** G3's
    #: whole bound on #381 is that *the transcript is shown to the learner as
    #: their turn*, and until now it was not: the voice route returned the app's
    #: reply and nothing else, so the screen never showed what was heard.
    heard: str | None = None


class WordOfferOut(BaseModel):
    """#408. A word offered to the deck, and the proof it was offered."""

    word: str
    token: str


class RungOut(BaseModel):
    """W15. One rung on offer today. **No count and no done-today flag** (#160)."""

    #: The unit's can-do (answer) or the video's title (retell).
    label: str
    #: The answer's task, verbatim — the rung's opener. Null on a retell, whose
    #: opener is fixed and needs nothing from the wire until it is opened.
    prompt: str | None = None


class RungsOut(BaseModel):
    answer: RungOut | None
    retell: RungOut | None
    #: The same voice gate `/topics` carries (#364).
    voice: bool


class CloseOut(BaseModel):
    """§C2 and §C3.

    ────────────────────────────────────────────────────────────────────────
    **`summary` IS ON THIS MODEL AS OF 2026-09-08, AND THE REFUSAL IT REVERSES
    IS QUOTED RATHER THAN DELETED** (#82's shape):

        *"**`summary` IS NOT ON THIS MODEL.** It is the app's own note about
        the conversation, written for a consumer that does not exist yet
        (#391); putting it on the wire would invite a client to render the
        app's assessment of the learner back at them, which is a report card
        by another name."*

    **THE REFUSAL WAS NOT WRONG; IT WAS UNTESTED, AND W13b/4 RECORDED IT AS
    DEFERRED PENDING EVIDENCE RATHER THAN DECLINED.** At that point all three
    stored summaries on production were empty, because no conversation had ever
    been closed — **nobody had read one.** The evidence arrived on 2026-09-08,
    conversation 7:

        *"The conversation was about an embarrassing moment at a wedding the
        learner attended with their girlfriend in Trakai, Lithuania. They
        described the venue, activities, and a funny near-fall by the groom's
        father, keeping the exchange lively and engaging throughout."*

    **That is a recap, not a verdict.** It says what was talked about; the one
    evaluative clause is *keeping the exchange lively and engaging*, which is
    praise, and praise is the half CLAUDE.md §4 asks to be announced. **The
    refusal was written against "the app's assessment of the learner rendered
    back at them" and this is not that.** Assistant-recommended,
    operator-accepted 2026-09-08.

    **WHAT STILL HOLDS, AND IS NOW THE PROMPT'S JOB RATHER THAN THE WIRE'S:**
    `conversation_close_v3.txt` forbids a score and forbids quoting the
    learner, and `test_the_summary_prompt_forbids_a_score_and_a_quote` is what
    keeps that true. **The wire stopped being the place that rule was enforced;
    it was never a good place for it.**
    ────────────────────────────────────────────────────────────────────────
    """

    conversation_id: int
    corrections: list[CorrectionOut]
    did_well: str
    #: §C3. What was talked about. **A recap, never a score** — the prompt is
    #: what holds that, and #391's option (a) is closed by this field existing.
    #: Empty on a rung.
    summary: str
    #: §C2. Offered to the deck. **Nothing is saved without a tap**, and since
    #: #402 nothing reaches this list that is not real, CEFR-levelled English.
    #: **#408 (W15): each word travels with the token `save-word` requires.**
    #: Was `unknown_words: list[str]` — quoted, #82's shape.
    word_offers: list[WordOfferOut]
    #: W15. False when a rung's response was not English. Always true on a talk.
    is_english: bool = True
    #: W15, retell. **What the retelling got across, as the video's own points —
    #: never a count or a percentage of them.** Empty on a talk and an answer.
    covered: list[str] = []
    #: W15, retell. The video's other points, as content — never as a shortfall.
    also: list[str] = []
    #: W33 (D), #493. **False when the close's model call failed**: nothing was
    #: read, so the screen says it could not check this one — never praise.
    checked: bool = True


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_turn(result: svc.TurnResult, *, heard: bool = False) -> TurnOut:
    return TurnOut(
        conversation_id=result.conversation_id,
        topic_label=result.topic_label,
        reply=result.reply,
        state=result.state,
        heard=result.learner_text if heard else None,
    )


def _rung(material: svc.RungMaterial | None, *, prompt: bool) -> RungOut | None:
    if material is None:
        return None
    return RungOut(label=material.label, prompt=material.opener if prompt else None)


@router.get("/rungs", response_model=RungsOut)
def rungs(
    session: AuthenticatedUser = Depends(require_current_user),
) -> RungsOut:
    """W15. What `/talk` offers besides the conversation. **A read — no model call.**

    #399 declined a page that bills on load, so the two rungs are shown from a
    database read and cost nothing until the learner opens one.
    """
    out = svc.rungs_today(session.id, _now())
    return RungsOut(
        answer=_rung(out.answer, prompt=True),
        retell=_rung(out.retell, prompt=False),
        voice=out.voice,
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
                kind=body.kind if body else "talk",
            )
        )
    except svc.CapReached:
        raise HTTPException(status.HTTP_409_CONFLICT, "cap_reached")
    except svc.NoRung:
        # Absent, never refused with a reason: a rung not on offer today is
        # simply not there (and the page never offered it).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no_rung")


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
    return _as_turn(result, heard=True)


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
                label=c.label,
            )
            for c in result.corrections
        ],
        did_well=result.did_well,
        summary=result.summary,
        word_offers=[WordOfferOut(word=o.word, token=o.token) for o in result.word_offers],
        is_english=result.is_english,
        covered=list(result.covered),
        also=list(result.also),
        checked=result.checked,
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
        return {
            "state": svc.save_conversation_word(
                session.id, body.word, _now(), token=body.token
            )
        }
    except svc.NotOffered:
        # #408: a word this surface did not offer this learner. Nothing written.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "not_offered")
    except svc.ConversationError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "empty_word")
