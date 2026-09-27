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

from core.writing.rules import MAX_CHARS as WRITING_MAX_CHARS
from core.writing.rules import MIN_CHARS as WRITING_MIN_CHARS


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


class WriteTodayOut(BaseModel):
    """`GET /write/today` (W16a). Every field traced to a design frame.

    `day_kind` → `1c`/`1d`; `session_id` → posted back for Ruling 1, never
    rendered; `ceiling_reached` → `1q` unavailable. **A boolean, never a count
    and never a reset time** (Ruling 3).
    """

    day_kind: Literal["journal", "paragraph"]
    session_id: int | None
    ceiling_reached: bool
    #: W16b → `1e`'s prompt card. The unit's task, verbatim; `null` on the journal.
    prompt: str | None = None


class CorrectRequest(BaseModel):
    """`POST /correct` (W16a). The bounds are the writing service's, not a second opinion.

    `day_kind` is the kind the learner was SHOWN — a server re-derivation across
    local midnight would correct one kind as the other — and W16a accepts only
    `journal`; W16b widens it. `session_id` is Ruling 1's, validated
    server-side and silently dropped when it is not the learner's own today.
    """

    text: str = Field(min_length=WRITING_MIN_CHARS, max_length=WRITING_MAX_CHARS)
    day_kind: Literal["journal", "paragraph"] = "journal"
    session_id: int | None = None


class Correction(BaseModel):
    """One correction card, `1k`'s anatomy.

    **W16a removed `error_type` and `murphy_units` from the wire** — nothing
    rendered either (#183's citation left the screen at W8h; the code was a
    React key). `label` is the eyebrow, from `error_types.learner_label`, and is
    absent when the taxonomy has none.
    """

    you_said: str
    correct_form: str
    explanation: str
    label: str | None = None


class CorrectionResult(BaseModel):
    """What one journal entry produced (W16a).

    **`did_well` is ABSENT when there is nothing worth saying — never blank,
    never a fallback** (Ruling 2). The route serialises with
    `response_model_exclude_none`, so absent means absent on the wire.
    **`has_errors` is gone**: the client reads `corrections` and nothing read
    the flag.
    """

    is_english: bool
    did_well: str | None = None
    corrections: list[Correction] = []
    #: W16b → `1n`. Absent on the journal and when the gate refuses it.
    structure: list["StructureParagraph"] | None = None
    #: W16b → `1o`. `[]` on the journal and when nothing survives the offer rule.
    word_offers: list["WordOffer"] = []


class StructureSegment(BaseModel):
    """One run of structure prose; `quote: true` is the learner's own words → italic."""

    text: str
    quote: bool


class StructureParagraph(BaseModel):
    segments: list[StructureSegment]


class WordOffer(BaseModel):
    """`1o`'s KeepRow: the phrase, the app's sentence it came from, and the in-deck state."""

    phrase: str
    sentence: str
    in_deck: bool
    #: #419 (W15). The signature `POST /write/keep` requires back.
    token: str


class KeepRequest(BaseModel):
    """`POST /write/keep` (W16b). **Verified as offered (#419, W15), then re-filtered.**"""

    phrase: str = Field(min_length=1, max_length=80)
    sentence: str = Field(min_length=1, max_length=WRITING_MAX_CHARS)
    #: The offer's signature, from `word_offers`. Required.
    token: str = Field(min_length=1, max_length=64)


class KeepOut(BaseModel):
    status: Literal["saved", "already"]


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


class CardImage(BaseModel):
    """A picturable word's picture, and the credit its licence requires. W13d.

    **Everything the card must SHOW travels with the picture**, because CC BY
    requires the credit to be visible (TASKS' W13d row): a picture that arrived
    without its author and licence could not be rendered lawfully, so the
    fields are not optional where the licence needs them. `author` is None only
    for a public-domain or CC0 file whose author Commons does not name.
    """

    id: int
    #: `jpg` or `png` — the URL is `/lexeme-images/{id}.{ext}`, built by
    #: `lexemeImageUrl` in `apps/web/lib/api.ts`.
    ext: str
    width: int
    height: int
    #: The lemma. The word is printed beside the picture, so this names it for
    #: a screen reader rather than describing the photograph.
    alt: str
    author: str | None
    licence: str
    licence_url: str | None
    source_url: str


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
    #: W13d. None for a phrase card, a collocation card and every word without
    #: an operator-approved picture — PRD §2.6.3's *"demonstrably unchanged"*.
    image: CardImage | None


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
    #: **W24e.** Every work block that served something is done — derived at
    #: hydration from the blocks (`core.sessions.blocks.finished`), never from
    #: `completed`, which has no writer (#349). The client shows keep going on it.
    finished: bool = False
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


class KnownPointOut(BaseModel):
    """One day's known-word count, as the progress screen read it (W19)."""

    local_date: date
    known_words: int


class PlacementSkillOut(BaseModel):
    """One radar axis (W18): a skill and the band shown for it, or null when
    that skill has never been measured. **A band, never a number.**"""

    skill: Literal["vocabulary", "grammar", "listening", "speaking"]
    band: Literal["A2", "B1", "B2", "C1"] | None


class PlacementPointOut(BaseModel):
    """One finished sitting, as the history shows it: the band as SHOWN after
    it — the high-water mark so far, so a later sitting that read lower draws
    the same band again (drops are silent, CLAUDE.md §4)."""

    finished_on: date
    band: Literal["A2", "B1", "B2", "C1"]


class PlacementShownOut(BaseModel):
    """W18: what a learner is shown of their placements. **No percentage, no
    count of right or wrong answers, no score** — *where to start* is a band.

    Every value is the high-water mark across finished sittings
    (`core.placement.scoring.shown`). `raised_from` is set only when the latest
    sitting raised the band; a sitting that read the same or lower says nothing.
    `vocab_estimate` is rounded to the hundred (PRD §6's ±300).
    """

    where_to_start: Literal["A2", "B1", "B2", "C1"]
    radar: list[PlacementSkillOut]
    history: list[PlacementPointOut]
    vocab_estimate: int | None
    raised_from: Literal["A2", "B1", "B2", "C1"] | None
    raised_skills: list[str]


class PlacementItemOut(BaseModel):
    """The learner-visible face of one placement item — whichever of the three
    shapes its section has. **Never an answer, and for a yes/no word nothing that
    says whether it is real.**"""

    id: int
    #: vocabulary
    word: str | None = None
    #: grammar and listening — the same presentation every item in the app has
    response_mode: str | None = None
    projection: dict[str, Any] | None = None
    #: speaking
    prompt_text: str | None = None
    #: speaking: whether a recording may be sent (#364). False means typed only.
    voice: bool | None = None


class PlacementStepOut(BaseModel):
    """What comes next in a sitting. **No position and no count** — *12 of 60* is
    a backlog running backwards (W13b's `/talk` reasoning), so the screen names
    the part it is on and nothing else."""

    section: Literal["vocabulary", "grammar", "listening", "speaking", "done"]
    item: PlacementItemOut | None = None


class PlacementOut(BaseModel):
    """`GET /placement`."""

    state: Literal["none", "open", "finished"]
    ready: bool
    available: bool
    next_from: date | None
    voice: bool
    step: PlacementStepOut | None
    shown: PlacementShownOut | None


class PlacementResultOut(BaseModel):
    """`POST /placement/finish`."""

    shown: PlacementShownOut
    next_from: date | None


class PlacementAnswerIn(BaseModel):
    """One answer. The client sends the field its item produces; the service
    decides which one is the answer from the section and the item's type."""

    model_config = ConfigDict(extra="forbid")

    item_id: int
    #: vocabulary: *I know this word*
    known: bool | None = None
    #: speaking: move on without answering
    skip: bool = False
    #: typed items and the typed speaking fallback. **Placed and discarded; never
    #: stored.** 4,000 characters is `core.placement.speaking.MAX_CHARS`.
    text: str | None = Field(default=None, max_length=4000)
    option: str | None = None
    tile_index: int | None = None
    order: list[str] = Field(default_factory=list, max_length=40)
    pairs: dict[str, str] = Field(default_factory=dict)


class ProgressOut(BaseModel):
    """W19: the progress screen. **Every number traces to a ledger**, named in
    `core.services.progress`'s banner.

    **NO FIELD COUNTS AN ABSENCE**: no missed days, no remaining, no target
    shortfall, no partner comparison (the couple leaderboard is dropped by scope
    ruling). ~~**No field for the radar, placement history, the six-month target
    line or units MASTERED** — each needs data that does not exist yet (W18's
    placement; #135's retention metric), and a field for any of them would be a
    number with nothing behind it.~~ **W18 (2026-09-25), the old text struck
    rather than deleted: `placement` now carries the radar and the placement
    history, in bands.** The six-month target line and units MASTERED still have
    no field, for the reasons above (the target line's baseline is a placement's
    vocabulary estimate from week 1, which no learner has yet; #135). **No `sessions.xp`, `minutes` or
    `completed_at`** (#349): XP is computed from the activity logs.

    Zeros ARE honest here; the screen draws none of them (W11b's split).
    """

    known_words: int
    #: Ascending; at most six months. One point per day the screen was read, so
    #: a line exists only from the second point on.
    known_history: list[KnownPointOut]
    #: Never lower than any value this learner has been shown (029's mark).
    xp: int
    streak_days: int
    freezes: int
    units_passed: int
    #: **W18.** The radar and placement history, TURNED ON HERE — null until the
    #: learner's first sitting finishes. Bands, never a percentage.
    placement: PlacementShownOut | None = None


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


class SaveWordOut(BaseModel):
    """W13-ii: what one tap on a transcript word did.

    **THREE STATES AND NONE OF THEM IS AN ERROR CODE.** `saved`,
    `already_saved` (#178) and `no_gloss` are three different answers to three
    different questions, and a boolean would collapse two of them. **A second
    tap is a 200 with `already_saved`, never a 500** — the raw `UniqueViolation`
    through a route is a server error in front of a learner who did a normal
    thing, which is exactly what #178 was filed about.

    **`no_gloss` IS A FACT AND NOT A PROMPT.** §1a is ruled PRE-GENERATE: the
    definition is written before the week by a human-run command, so a word
    nobody generated stays ungiossed and the request path does not reach a model
    to fix that. The standing ruling of 2026-08-27 is held by construction here.

    **No definition crosses this boundary.** The tap writes cards; the learner
    reads them in the deck, where `card_face` is the single producer (#190). A
    definition on this response would be a second surface for the same content.
    """

    state: Literal["saved", "already_saved", "no_gloss", "pending", "no_line"]
    card_ids: list[int] = Field(default_factory=list)
    #: W31c, `pending` only: whether a meaning is coming (`WORD_GLOSS_JOB` on).
    meaning_soon: bool | None = None


class WordMeaningOut(BaseModel):
    """W31c: a stored gloss, as the word sheet shows it. **Read, never generated.**

    **THIS REVERSES W13-ii's *"no definition crosses this boundary"* — ON A
    SEPARATE, READ-ONLY ROUTE, AND BY THE OPERATOR'S REQUEST (2026-09-27).**
    The reference is Trancy / Language Reactor: tap a word, see what it means,
    then decide to keep it. The save route still returns no definition, and the
    card face is still the deck's single producer (#190) — this is the sheet's
    preview of a candidate, not a second card face.
    """

    model_config = ConfigDict(populate_by_name=True)

    definition: str
    #: Aliased, not renamed — the card schema's precedent above: `register` is
    #: PRD §8.5.1's word on the wire, and pydantic warns on the attribute name.
    register_tag: str = Field(validation_alias="register", serialization_alias="register")
    neutral_equivalent: str | None = None
    who_says_this: str | None = None
    #: The learner's own language (`users.native_language`), when `explain`
    #: produced it (ruling Q7). Shown in the sheet only; card backs stay English.
    l1: str | None = None
    l1_language: str | None = None


class WordLookupOut(BaseModel):
    """W31c: `GET /video/{id}/word` — everything the word sheet shows."""

    word: str
    lemma: str
    line: str | None = None
    meaning: WordMeaningOut | None = None
    image: dict | None = None
    saved: Literal["none", "in_deck", "pending", "no_meaning"]


class SavedWordOut(BaseModel):
    word: str
    sentence: str | None = None
    source_title: str | None = None
    state: Literal["in_deck", "pending", "no_meaning"]
    saved_at: datetime


class MyWordsOut(BaseModel):
    """W31c: `GET /words` — one page, newest first. **No count and no total**
    (CLAUDE.md §4, #160); `next_before` asks for the page after, or is absent."""

    words: list[SavedWordOut]
    next_before: datetime | None = None


class SaveWordIn(BaseModel):
    """The tapped word. **Bounded, because it arrives from a client.**

    No sentence, no video title, no definition: everything else the card needs
    is already server-side in `video_glosses` and `videos`. **A client that
    could supply the context sentence could supply any sentence**, and the card
    would then carry text no transcript ever contained.
    """

    word: str = Field(min_length=1, max_length=80)
    #: W31c: the index of the display line the word was tapped in. **An index,
    #: never text**: the server reads the line from its own `core.video.lines`
    #: and trusts the index only if that line holds the word.
    line: int | None = Field(default=None, ge=0, le=100_000)


class ShadowWordOut(BaseModel):
    """One word of the attempt, as the learner sees it.

    **`accuracy` IS ON THE WIRE AND IS NOT RENDERED AS A NUMBER.** It drives the
    per-word tint and the underline; the component shows no digit. PRD §7.3 asks
    for *per-word colouring*, and a number on a person's voice is the shape
    CLAUDE.md §4 bans (§2.6, ruled 2026-09-03).
    """

    word: str
    accuracy: float
    clean: bool


class ShadowScoreOut(BaseModel):
    """W14. **Per-word colouring, and deliberately NO aggregate scores.**

    **THERE IS NO FIELD HERE FOR `accuracy`, `fluency`, `completeness` OR
    `pron_score`, AND THAT IS THIS MODEL'S MAIN JOB.** All four are persisted in
    `speech_attempts` because PRD §8 asks for them to be — its stated payoff is
    **W17's** weak-spot surface — and none reaches a browser. **A client cannot
    render what it was never given**, which is the standing `murphy_units` has
    under #187 and the coverage percentage has under #288, applied here to a
    score on someone's voice.

    `improved` carries **raises only**: `True` when this attempt beat the last
    on the same card, `None` for both *first attempt* and *worse*. **Drops are
    silent** (CLAUDE.md §4), and the two cases are indistinguishable to the
    client on purpose — a component that could tell them apart would eventually
    say something about the drop.
    """

    attempt_id: int
    words: list[ShadowWordOut]
    improved: bool | None = None


# ── W20: Web Push ────────────────────────────────────────────────────────────
#
# **The endpoint travels in a BODY, never a path or a query string**: it is a
# capability URL (anyone holding it and the keys can put a notification on the
# phone), and a URL lands in access logs. The lengths are migration 031's
# CHECKs, repeated so a malformed body is a 422 here rather than a CHECK
# violation whose DETAIL would print the row (#434's lesson).

_B64URL = r"^[A-Za-z0-9_-]+$"


class PushKeyOut(BaseModel):
    """The VAPID public key, or null when reminders are not set up here."""

    public_key: str | None


class PushKeysIn(BaseModel):
    p256dh: str = Field(min_length=87, max_length=87, pattern=_B64URL)
    auth: str = Field(min_length=22, max_length=22, pattern=_B64URL)


class PushSubscriptionIn(BaseModel):
    """`PushSubscription.toJSON()`, minus `expirationTime` (no browser sets it)."""

    model_config = ConfigDict(extra="ignore")

    endpoint: str = Field(min_length=12, max_length=2048, pattern=r"^https://")
    keys: PushKeysIn


class PushEndpointIn(BaseModel):
    endpoint: str = Field(min_length=12, max_length=2048, pattern=r"^https://")


class PushStateOut(BaseModel):
    """Whether THIS browser receives reminders. Nothing else: no count, no time."""

    on: bool



class AdminUserOut(BaseModel):
    """W23: one learner on the operator's panel — the bot panel's line, as data.

    **ACTIVITY, NEVER CONTENT (CLAUDE.md §5).** Every field is a state or a
    count of days; no field can carry anything a learner wrote or said.
    ``tests/test_admin_route.py`` holds the key set exactly.
    """

    id: int
    name: str
    cefr_level: str
    current_streak: int
    active_days: int
    last_active: date | None
    paused: bool
    revoked: bool


class AdminActivityOut(BaseModel):
    """W23: `GET /admin/activity`. The operator only; 404 for anybody else."""

    pending_requests: int
    #: The bot's `active X/5 of the last 7` line, as its two constants.
    weekly_goal_days: int
    lookback_days: int
    users: list[AdminUserOut]


CorrectionResult.model_rebuild()


class KeepGoingOut(BaseModel):
    """`GET /keep-going` (W24e). **Kinds only — never a count.** Each cap and
    queue behind an option reaches the wire as the option's presence or absence,
    so no client can render how many cards wait or how many turns are left."""

    options: list[Literal["watch", "talk", "cards", "write"]]


class WatchOut(BaseModel):
    """`POST /keep-going/watch` (W24e). The player's payload — the SAME dict
    block 2 carries, from `core.services.sessions.video_payload` (one producer,
    #190) — and the learner's L1 for the player's contract."""

    l1_language: str
    video: dict[str, Any]
