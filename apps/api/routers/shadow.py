"""W14's one route. ARCHITECTURE §6, PRD §7.3, PRD §8 rung 1.

It parses, authorises, calls **one** service function, and serialises
(CLAUDE.md §2). No business logic and no SQL: the queries are in
`core/services/shadow_score.py`, which is what `test_no_sql_outside_services`
holds.

**ONE ROUTE AND NOT TWO — §1e, ruled 2026-09-03.** There is no
`GET /shadow/today`: **the line is served in block 4's payload from
`GET /session/today`**, the way block 2's video already arrives, so exactly one
place decides what today's line is. A second producer of that contract is
#190's defect — two call sites assembling one shape, one of them incomplete,
both suites green because the halves never meet.

**`async def` PLUS `asyncio.to_thread` — THE SANCTIONED ESCAPE, AND THE PLAN
SAID PLAIN `def`. THE DEVIATION IS DELIBERATE AND IS REPORTED.**

The plan asked for two things that **cannot both hold** under FastAPI:
*plain `def`* and *the body cap enforced before anything reads the body*. A
sync route cannot read a request incrementally, so FastAPI buffers the ENTIRE
upload before the handler runs and the cap becomes a post-buffer check — which
is not a cap, on the one route whose whole risk is an upload that never ends.

`tests/test_api.py` already settles which requirement yields. Its
`OFF_LOOP_HELPERS` and `_COMPLIANT_SOURCE` name *"the sanctioned escape when a
route genuinely must be async: push the blocking call off the loop"*, and
`await asyncio.to_thread(...)` is asserted as compliant. **#7's actual rule is
*never block the event loop*, and streaming the body honours it strictly better
than a sync handler that buffers megabytes before it is entered.**

`BLOCKING_CALLS` gained `("speech", "assess_pronunciation")` in the same commit
as the wrapper — **a sweep that does not know about a new blocking call passes
vacuously** — and this route is checked by it, not exempted from it.

**AND IT AVOIDS A NEW DEPENDENCY.** The plan specified `multipart/form-data`;
`UploadFile` requires **`python-multipart`**, which is a new runtime dependency
and a licence gate this slice did not budget (W4's `fsrs` and W7's are the
precedent for that gate being real work). A raw `audio/wav` body carries one
binary part and no fields, so multipart buys nothing here.

**NOTHING IS GENERATED HERE — §1a, ruled 2026-09-03.** *Scoring is measurement,
not generation*: no model produces content, nothing enters a deck, the journal
or the item bank, and the output is a number about something the learner just
did. The 2026-08-27 standing ruling governs generation and does not reach this.

**THE BODY CAP IS ENFORCED BEFORE ANYTHING READS THE BODY.** `Content-Length`
is checked first, then the actual bytes are re-checked after reading — a client
can lie about the header, and the cap is the only defence a free quota has
against a recorder that never stopped.

**NO AUDIO REACHES A DISK AND NO TRANSCRIPT REACHES A LOG.** The bytes arrive
in memory, go to one service function, and are dropped;
`core.speech.PronunciationResult` has no field for what Azure heard, so no
handler here can leak one.
"""

from __future__ import annotations

import logging

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status

from apps.api.deps import rate_limit, require_current_user
from apps.api.schemas import ShadowScoreOut, ShadowWordOut
from core import speech
from core.services import shadow_score as shadow_service
from core.services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shadow", tags=["shadow"])


@router.post(
    "/{card_id}/score",
    response_model=ShadowScoreOut,
    dependencies=[
        Depends(
            rate_limit(
                "shadow_score", per_client=60, overall=200, window_seconds=3600
            )
        )
    ],
)
async def score(
    card_id: int,
    request: Request,
    session_id: int | None = None,
    session: AuthenticatedUser = Depends(require_current_user),
) -> ShadowScoreOut:
    """Score one spoken attempt at this card's sentence.

    **413** when the upload is too large — checked on the declared length before
    the body is read, and on the real length after.
    **409** when this month's free scoring is spent: **a stated condition, not
    an error**, and the client renders it as *scoring is off today* rather than
    as a failure of the attempt.
    **422** when the provider heard no usable speech. **Not a low score** — a
    learner who said nothing has produced no measurement, and storing a zero
    would be inventing one.
    **404** when the card is not this learner's or is not a shadowable line
    (§1b's cue exclusion, re-checked in the service and never trusted from the
    client).
    """
    # **The declared length first — it refuses before a byte is read.** A client
    # can lie about it, which is why the stream below counts as well; but an
    # honest oversized upload is rejected without transferring it at all.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit():
        if int(declared) > shadow_service.MAX_AUDIO_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "recording is too long"
            )

    # **Streamed, with a running total, so the cap holds against a lying header
    # too.** Nothing is written anywhere: the chunks are held in memory and
    # joined, and the request is abandoned the moment it passes the ceiling.
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > shadow_service.MAX_AUDIO_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "recording is too long"
            )
        chunks.append(chunk)
    payload = b"".join(chunks)

    try:
        # The sanctioned escape: the provider call, the pool checkouts and the
        # WAV parse all run off the event loop.
        scored = await asyncio.to_thread(
            shadow_service.score_attempt,
            session.id,
            card_id,
            payload,
            session_id=session_id,
        )
    except (shadow_service.NoSuchLine, shadow_service.NotConsented):
        # **404 for BOTH, deliberately.** A blocked learner must not be
        # able to tell a consent gate from an absent line: a 403 would
        # announce a feature she is excluded from (#364).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such line")
    except shadow_service.QuotaExhausted:
        raise HTTPException(status.HTTP_409_CONFLICT, "scoring unavailable")
    except shadow_service.AudioRejected as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except speech.NotRecognised:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "not recognised")
    except speech.SpeechQuotaExceeded:
        # The provider refused even though our own ledger had room. **Same face
        # to the learner as our own ceiling** -- the two counters can disagree
        # (ours counts what we sent, theirs what they billed) and which one
        # refused is not the learner's problem.
        raise HTTPException(status.HTTP_409_CONFLICT, "scoring unavailable")
    except speech.SpeechError:
        # Deliberately not echoed: a provider message can carry request detail,
        # and this route must leak nothing about the utterance.
        logger.warning("shadow scoring failed for card=%s", card_id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "scoring failed")

    return ShadowScoreOut(
        attempt_id=scored.attempt_id,
        words=[
            ShadowWordOut(
                word=w["word"],
                accuracy=w["accuracy"],
                clean=w["error_type"] == speech.NO_ERROR,
            )
            for w in scored.words
        ],
        improved=scored.improved,
    )
