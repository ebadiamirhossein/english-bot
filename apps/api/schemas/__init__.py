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

from datetime import date, datetime
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

    #: **Which session this attempt happened in.** W11.
    #:
    #: `item_attempts.session_id` has existed since migration 012, whose comment
    #: says *"W10 needs it for `block_breakdown`"* -- and **nothing has ever
    #: written it**: `answer_item` took the argument, the route never passed one,
    #: and the column is NULL on every attempt this system has recorded.
    #:
    #: W11 is the first path that cannot work without it. A checkpoint is scored
    #: by counting the attempts that belong to its sitting, so an attempt that
    #: cannot say which sitting it belongs to cannot be counted -- and a
    #: checkpoint would score 0 of 12 however well it was answered.
    #:
    #: Nullable, because free practice outside a session is a first-class path
    #: (012's own reason for making the column nullable) and `/items` is still
    #: reachable without one.
    session_id: int | None = Field(default=None, ge=1)


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
    #: Whether this card asks for a TYPED answer before the reveal (#157).
    #: Derived server-side from `core.cards.TYPED_ANSWER_CARD_TYPES` and sent on
    #: the wire, so `apps/web` holds no copy of the table — the rule W6 settled
    #: for `response_mode`. A mirrored table is a table that drifts.
    typed: bool
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
    #: **Still sent, and no learner surface renders it** (#160). The session
    #: sizes block 1 from it and W19 will read it; the ban is on presenting a
    #: duty counter, not on the number existing — the same standing
    #: `murphy_units` has under #187.
    counts: DeckCountsOut
    #: `users.native_language` (#159). One per response, never per card: it is a
    #: per-user fact and eighty copies is eighty chances for two to disagree.
    l1_language: str


class CardAttemptRequest(BaseModel):
    """A typed answer, before the back is revealed (#157).

    Bounded at the same 500 characters as `ItemAnswerRequest.text`. A card's
    back is a word or a phrase; anything longer is not an attempt at it.
    """

    text: str = Field(max_length=500)


class CardAttemptResult(BaseModel):
    """Did it match. **Nothing was written.**

    The attempt is recorded by the grade call, which recomputes this verdict
    from the stored string rather than trusting one the client carries back
    (#108's shape).
    """

    matched: bool


class GradeRequest(BaseModel):
    """One grade. `rating` is named, never numeric, on the wire.

    The client sends `good`, not `3`. `fsrs.Rating`'s integers are an
    implementation detail of the scheduler; putting them on the wire would mean
    a client that hardcoded them keeps working while the meaning shifts under it.
    """

    rating: Literal["again", "hard", "good", "easy"]
    duration_ms: int | None = None
    #: The session this grade happened inside, when it happened inside one
    #: (#160 — block 1). NULL from `/review`, which stays reachable outside a
    #: session, exactly as `item_attempts.session_id` is nullable because
    #: migration 012 named free practice a first-class path.
    session_id: int | None = None
    #: What the learner typed before revealing the back (#157). Stored verbatim;
    #: **the match is recomputed server-side** and is never sent by the client.
    typed_response: str | None = Field(default=None, max_length=500)


class GradeResult(BaseModel):
    due: datetime
    interval_days: int
    counts: DeckCountsOut


class BlockOut(BaseModel):
    """One of PRD §4.1's five blocks.

    **`state` is why this is a model and not a nullable payload.** `empty` and
    `unavailable` are different facts — nothing is due, versus this block could
    not be built — and a learner told *nothing’s due, go watch something*
    because a query fell over has been lied to in a way that looks identical to
    the truth on a screen. `core.sessions.BLOCK_STATES` is the authority and a
    test asserts the two agree.
    """

    n: int
    kind: str
    state: str
    payload: dict[str, Any]


class LessonOut(BaseModel):
    """One unit's grammar lesson. W10b.

    **`sections` and `diagrams` are free-form here on purpose.** Their shape is
    owned by `core.lessons.schema`, which is where it is enforced -- restating
    the five diagram kinds as pydantic models in the API layer would be a second
    copy of a contract, and the two would drift the way the two halves of
    `docs/TASKS-v3-web.md` did (#130). The service parses into typed models
    before this is built, so nothing untyped reaches the route.

    **No `user_id` and nothing per-learner.** Lessons are global; the route
    authorises on a session and selects on nothing.
    """

    unit_number: int
    sections: list[dict[str, Any]]
    diagrams: list[dict[str, Any]]


class SessionTodayOut(BaseModel):
    """Today's session, hydrated. PRD §4.1.

    **Nothing was generated to build this.** ARCHITECTURE §7: items are produced
    and gated the night before, never while the learner waits — and W10 produces
    none at all, so the property holds trivially today and is asserted anyway,
    because it stops being trivial with the generation slice.
    """

    session_id: int
    #: The learner's LOCAL date, from `users.timezone` — the same basis every
    #: other `sessions.date` uses. See migration 016's header for why not UTC.
    date: date
    l1_language: str
    current_block: int
    completed: bool
    blocks: list[BlockOut]


__all__ = [
    "BlockOut",
    "CardAttemptRequest",
    "CardAttemptResult",
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
    "SessionTodayOut",
]


class CheckpointOut(BaseModel):
    """One checkpoint sitting, as the learner receives it. W11, PRD §3.

    **`score_pct` IS NULL ON A FAILURE, AND THAT IS THE POINT.**
    `user_unit_state.last_checkpoint_score` is stored because migration 014
    requires a `passed` row to name the score that passed -- storing it is not
    licence to show it. v2's carried rule is *drops are silent, raises are
    announced*, and a fraction on a screen after a failed checkpoint is a
    punishment screen with no banned word in it. `pass_mark` travels for the
    same reason it does not: it is served only on a pass.

    `items` carries `ItemPresentationOut`, the SAME projection block 3 uses --
    not a second serialiser. See `core/services/items.py`'s "what a learner is
    allowed to receive" banner.
    """

    session_id: int
    unit_number: int
    can_do: str
    item_count: int
    #: ``ready`` | ``not_ready`` | ``done``. `not_ready` is an HONEST state: the
    #: bank could not fill this sitting's quota map, and a SHORT checkpoint is
    #: never served in its place (CLAUDE.md §3 rule 7).
    state: str
    items: list[ItemPresentationOut] = []
    #: How many of the twelve are already answered (#269). Counted from
    #: `item_attempts`, so the number the learner sees and the number they are
    #: graded on cannot disagree — and a resumed sitting knows where it is.
    answered: int = 0
    passed: bool | None = None
    score_pct: int | None = None
    retake_due_on: date | None = None


# ── W13-i: the player ───────────────────────────────────────────────────────


class VideoProgressIn(BaseModel):
    """Where the learner has got to, in whole seconds.

    **THE ONLY FIELD, AND THERE IS DELIBERATELY NO `completed` FLAG.** The
    client does not get to say a video is finished: `core.video.watch` decides
    that from the position and the stored duration, and a client-asserted
    completion would be a second producer of a column the record treats as the
    product (#190, #291). A browser that wanted to lie could still send a large
    position -- but it would be lying about a POSITION, which is clamped to the
    video's own length, rather than about a verdict.
    """

    #: `None` is accepted rather than rejected: a player that has not started
    #: reports no position, and `watch.clamp_position` floors it at 0.
    position_s: int | None = None


class VideoTodayOut(BaseModel):
    """Today's assigned video — **and no transcript and no coverage figure.**

    **The transcript, the unknown-word set and the band come through block 2 of
    `GET /session/today`, and this model deliberately cannot carry them.** One
    contract, one producer (#190): two routes assembling the player's payload is
    how one of them ends up incomplete while both suites stay green.

    **NO PERCENTAGE EXISTS ON THIS MODEL OR ON BLOCK 2's PAYLOAD.**
    `core.video.badge` yields a band token or nothing, so a client cannot render
    a figure it was never given. Three reasons, written out at
    `core/video/badge.py`: #288 (proper nouns inside the assumed-known floor
    inflate every figure by an uncounted amount), #334 (`coverage_fit` returns
    1.0 across the whole band, so the obvious extraction would show 100%) and
    #330 (a percentage over a 234-character transcript).
    """

    video_id: int
    youtube_id: str
    title: str | None = None
    duration_s: int | None = None
    #: Where the learner stopped. Written by the progress ping and by nothing
    #: else; `0` until they start, which is migration 019's own default.
    resume_position_s: int = 0
    #: **`completed_at IS NOT NULL`, flattened to a boolean.** The timestamp is
    #: the record's; what a client needs is whether to resume or to offer a
    #: rewatch, and shipping the instant invites a client to compute something
    #: from it.
    completed: bool = False


class WeekOut(BaseModel):
    """W11b: the Sunday weekly report. **Six numbers, and nothing that was not
    done.**

    **THERE IS NO FIELD HERE FOR `minutes`, `xp`, `completed` OR A BLOCK
    BREAKDOWN, AND THAT IS THE MODEL'S MAIN JOB.** Each is a column nothing
    writes — `complete_block` was `minutes` and `completed_at`'s only writer and
    W11 removed it with the button nobody tapped; `sessions.xp` is NULL on every
    row that exists because W19 owns the weighting — so a field for any of them
    would put a number on the wire that is always zero. **A zero on a report is
    a score**, and a score of zero on a week nobody promised anything about is
    guilt with no banned word in it (CLAUDE.md §4). A client cannot render what
    it was never given, which is the standing `murphy_units` has under #187 and
    the coverage percentage has under #288 — applied here to an absence rather
    than to a secret.

    **NO BACKLOG KEY EITHER.** Nothing counts a missed day, a shortfall or a
    comparison with last week: *drops are silent, raises are announced*, and
    #160's ruling is that a screen with its own counter becomes a backlog.
    `tests/test_week_route.py` scans this payload with `test_session_route.py`'s
    own tuple rather than a copy of it.

    **The zeros that ARE here are honest**, and `empty` is what the surface
    reads. The no-zero rule lives on the screen, in one place — a service that
    withheld the number would move that judgement into the client and then it
    would live in two.
    """

    #: The Sunday this week ends on, in the learner's local calendar. PRD §4.2's
    #: week runs Mon → Sun, so Sunday is the last day.
    week_ending: date
    #: Whether the learner's today IS that Sunday. **Home reads this**, because
    #: a `new Date().getDay()` in the browser puts a learner in Vilnius on the
    #: browser's idea of Sunday — `saturday-link.tsx` records the same reasoning.
    sunday: bool

    days_with_a_session: int
    items_answered: int
    items_right: int
    cards_reviewed: int
    words_now_known: int
    units_passed: int

    #: Nothing happened this week. Week one is both learners' state, and the
    #: surface renders one line rather than a table of zeros.
    empty: bool
