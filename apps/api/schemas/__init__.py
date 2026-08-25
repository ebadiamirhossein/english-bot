"""Pydantic models — the source of truth for the OpenAPI client.

``apps/web/lib/api.ts`` is written against the schema these produce, so a
field renamed here shows up as a type error in the frontend rather than as a
runtime surprise (ARCHITECTURE-v3 §3).

**The WebAuthn credential JSON is deliberately not modelled here.** It arrives
as a plain ``dict`` and goes straight to ``core.passkeys``, which parses it with
py_webauthn's own parser. A hand-written pydantic mirror of the WebAuthn
response shape would be a second, subtly-wrong copy of a spec that already has a
maintained parser, and a mismatch would reach the learner as "it didn't work".
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.services.correction import MAX_CHARS as CORRECTION_MAX_CHARS
from core.services.correction import MIN_CHARS as CORRECTION_MIN_CHARS


class Health(BaseModel):
    """``GET /health``. ``schema_version`` is null only when the DB is down."""

    ok: bool
    schema_version: int | None


class Session(BaseModel):
    """A resolved session. The body of a successful sign-in, and of /health/auth."""

    user_id: int
    name: str
    expires_at: datetime


class RegisterBeginRequest(BaseModel):
    """First enrolment. Both fields are required and neither is ever logged."""

    email: str = Field(min_length=3, max_length=320)
    claim_token: str = Field(min_length=8, max_length=256)


class CredentialEnvelope(BaseModel):
    """Carries the raw ``PublicKeyCredential`` JSON under one key.

    The credential is a free-form ``dict`` on purpose (see the module docstring):
    py_webauthn parses and validates it. Wrapping it in an envelope rather than
    posting it at the top level keeps room for sibling fields — which is exactly
    what ``RegisterFinishRequest`` needs.
    """

    credential: dict[str, Any]


class RegisterFinishRequest(CredentialEnvelope):
    """The attestation plus the claim token it is being spent against.

    The token travels in the **body**, never in a query string: URLs reach
    access logs, browser history and Referer headers, and this one is a
    single-use authentication factor.
    """

    claim_token: str = Field(min_length=8, max_length=256)


class Passkey(BaseModel):
    """One credential as its owner sees it. No key material, no sign count."""

    id: str
    nickname: str | None
    created_at: datetime
    last_used_at: datetime | None
    backed_up: bool | None


class CorrectRequest(BaseModel):
    """`POST /correct`. The bounds are the service's, not a second opinion."""

    text: str = Field(min_length=CORRECTION_MIN_CHARS, max_length=CORRECTION_MAX_CHARS)


class Correction(BaseModel):
    """One correction, in the v2 shape the learners already read in Telegram.

    `murphy_units` is the Murphy reference for the error type — the "why" half,
    which is the half that teaches.
    """

    you_said: str
    correct_form: str
    error_type: str
    explanation: str
    murphy_units: str | None = None


class CorrectionResult(BaseModel):
    """What one piece of writing produced.

    `has_errors: false` with a `did_well` is the ordinary good outcome, not an
    empty response — the praise is the content in that case.
    """

    is_english: bool
    has_errors: bool
    did_well: str
    corrections: list[Correction] = []


class ItemPresentationOut(BaseModel):
    """One item as the learner receives it. **`projection` is opaque here.**

    Typed as a free-form ``dict`` deliberately, and for the opposite reason the
    WebAuthn envelope is: mirroring the eleven projection shapes in pydantic
    would be a second learner-visible serialiser, which is the one thing W6
    exists to prevent. `core.items.projection.visible_projection` decides what a
    learner sees; this model's job is to carry that decision unaltered.

    `response_mode` is on the wire so `apps/web` needs no copy of
    `core.items.RESPONSE_MODE`. A mirrored table is a table that drifts.
    """

    id: int
    response_mode: str
    projection: dict[str, Any]


class ItemAnswerRequest(BaseModel):
    """One learner response. The client sends the field its mode produces.

    Every field is optional because which one is read is decided in
    `core.items.response`, from the item's own type — never from a flag the
    client sets. A client that sends the wrong field grades as wrong, which is
    the correct outcome for a response that answers nothing.
    """

    #: `typed` — verbatim. Bounded generously; a dictation sentence is short and
    #: anything past this is not an answer.
    text: str | None = Field(default=None, max_length=500)
    #: `tap` on `mcq` / `collocation_pick`.
    option: str | None = Field(default=None, max_length=200)
    #: `tap` on `error_spot`.
    tile_index: int | None = Field(default=None, ge=0, le=64)
    #: `tap` on `word_bank_order`.
    order: list[str] = Field(default_factory=list, max_length=32)
    #: `tap` on `match_pairs`.
    pairs: dict[str, str] = Field(default_factory=dict)
    #: `spoken` — the learner's own mark. W6 has no scoring instrument (W14).
    self_marked: bool | None = None
    #: Render → submit, measured in the browser. Clamped by the service, which
    #: stores NULL rather than a lie for anything outside its range (#108).
    latency_ms: int | None = Field(default=None, ge=0)


class ItemAnswerResult(BaseModel):
    """The verdict and the teaching half.

    A **separate model from `ItemPresentationOut`, on purpose**: `canonical` is
    the answer, and having it live in a different type from the one the item is
    fetched with is what makes "before grading" and "after grading" two
    different shapes rather than one shape with a nullable field.

    `explanation` is almost always null — the generator prompt never asks for
    one (#103). `murphy_units` is present when the item declares an
    `error_type` (#104).
    """

    correct: bool
    graded_by: str
    canonical: str | None
    explanation: str | None
    murphy_units: str | None
    #: `match_pairs`' correct bijection, **after grading only** (#118).
    #:
    #: Its answer is a mapping, not a string, so `canonical` is NULL for this
    #: type by migration 012's `items_answer_present_iff_type_has_one` CHECK —
    #: which meant a learner who got it wrong was told "Here it is:" and shown
    #: nothing. W6a could only stop the box promising what it could not produce;
    #: this is the half that needed an API change.
    #:
    #: **Not a projection leak.** It has exactly the same standing as
    #: `canonical`: it is returned by the answer route, after the attempt is
    #: recorded, and `core.items.projection.visible_projection` is untouched.
    #: `tests/test_items_projection.py` still asserts the pairing appears
    #: nowhere in what the learner is served *before* answering.
    pairs: list[tuple[str, str]] | None = None


class CardFace(BaseModel):
    """One card as the reviewer renders it (PRD §5, §8.5.4).

    There is no hidden half to withhold, unlike an item: the `back` IS what the
    learner asks to see, and not showing it before the reveal is client-side
    sequencing rather than serialisation. So this is not a second learner-visible
    serialiser and `core.items.projection`'s cross-slice contract is unaffected.

    The four §8.5.4 fields are guaranteed present for an `informal`/`slang` card
    by migration 013's `cards_informal_shows_the_four_things` CHECK, so the
    component has no "if missing" branch to get wrong.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: int
    card_type: str
    front: str
    back: str
    cue: str | None
    context_sentence: str | None
    source_ref: str | None
    meaning: str | None
    #: Aliased, not renamed. `register` is PRD §8.5.1's word and it is what
    #: goes on the wire; the Python attribute avoids it only because pydantic's
    #: metaclass already carries a `register` method (from `ABCMeta`) and warns
    #: about the shadow on every import. FastAPI serialises by alias, so the
    #: client contract is unchanged.
    register_tag: str = Field(
        validation_alias="register", serialization_alias="register"
    )
    neutral_equivalent: str | None
    who_says_this: str | None
    #: What each of the four buttons would schedule, in days, computed
    #: server-side. **There is no interval arithmetic in TypeScript** — the same
    #: rule W6 established for grading, and a scan over the deck tree fails the
    #: commit that adds one.
    intervals: dict[str, int]


class DeckCountsOut(BaseModel):
    """How much of today's deck is left, after the caps.

    Never the raw overdue count: CLAUDE.md §4 — missed days shrink the task,
    they never pile up, and a backlog is never presented.
    """

    new_remaining: int
    review_remaining: int
    total_remaining: int


class ReviewQueueOut(BaseModel):
    cards: list[CardFace]
    counts: DeckCountsOut


class GradeRequest(BaseModel):
    """One grade. `rating` is named, never numeric, on the wire.

    The client sends `good`, not `3`. `fsrs.Rating`'s integers are an
    implementation detail of the scheduler; putting them on the wire would mean
    a client that hardcoded them keeps working while the meaning shifts under it.
    """

    rating: Literal["again", "hard", "good", "easy"]
    duration_ms: int | None = None


class GradeResult(BaseModel):
    due: datetime
    interval_days: int
    counts: DeckCountsOut


__all__ = [
    "CardFace",
    "DeckCountsOut",
    "GradeRequest",
    "GradeResult",
    "ReviewQueueOut",
    "CorrectRequest",
    "ItemAnswerRequest",
    "ItemAnswerResult",
    "ItemPresentationOut",
    "Correction",
    "CorrectionResult",
    "CredentialEnvelope",
    "Health",
    "Passkey",
    "RegisterBeginRequest",
    "RegisterFinishRequest",
    "Session",
]
