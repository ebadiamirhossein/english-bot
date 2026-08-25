"""The FSRS wrapper. **The only module in this repository that imports `fsrs`.**

Held by `tests/test_core_boundary.py::test_only_one_module_imports_fsrs`, the
same rule that makes `core.llm` and `core.speech` the only provider wrappers and
`core.items.gates` the only items module reaching a model. The reason is stated
in CLAUDE.md §2: swapping a provider must be one file, and duplicated
construction drifts where tests cannot see it.

Nothing outside this module ever holds an `fsrs.Card`. The boundary type is
`CardState`, a frozen dataclass of exactly the eight columns migration 013
persists, so `core.services.cards` reads and writes rows and never library
objects.

**Four properties, each load-bearing rather than stylistic.**

1. **`now` is injected and never read here.** Same shape as
   `core.services.errors.spacing_step(..., today=)` and
   `core.services.chunks.mark_chunk_result(..., now=)`. FSRS is a date
   calculation, and CLAUDE.md §3 rule 6 says a test must not depend on
   wall-clock date — with the clock injected, no test has to freeze anything.
   It passes an instant and asserts a delta.

2. **`enable_fuzzing=False`.** py-fsrs defaults it to `True`, which calls
   `random()` inside `review_card` and makes every due date irreproducible.
   Fuzz exists to spread thousand-card Anki decks so reviews do not clump on one
   day; at two learners and a deck of tens of cards it buys nothing measurable
   and costs every deterministic assertion in `tests/test_cards_fsrs.py`.

3. **UTC only.** py-fsrs raises `ValueError` on a datetime that is not
   timezone-aware and set to UTC. `_require_utc` raises the same refusal one
   frame earlier, with our own message, so a naive datetime fails at our
   boundary rather than inside a third-party library.

4. **FSRS-6, and PRD §5's "FSRS-5" is corrected in the same commit.** py-fsrs
   6.x carries 21 parameters where FSRS-5 had 19. The 5.x line is installable
   and unmaintained; pinning the deck's first day to it would buy a document
   match and cost a migration slice later. The correction is named in PRD §5
   rather than quietly reconciled, the way W6 corrected ARCHITECTURE §6.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from fsrs import Card, Rating, Scheduler, State

from core.cards import DESIRED_RETENTION, FSRS_STATES

# ── the boundary type ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CardState:
    """A card's scheduling state — exactly what migration 013 persists.

    Frozen because a scheduler that mutates its input makes "what was true
    before this review" unanswerable, and `card_reviews` records both halves.
    """

    fsrs_state: str
    fsrs_step: int | None
    stability: float | None
    difficulty: float | None
    due: datetime
    last_review: datetime | None
    lapses: int
    reps: int


@dataclass(frozen=True, slots=True)
class ReviewResult:
    """One graded review: the state that goes back to the row, plus the log.

    `elapsed_days` and `scheduled_days` are computed here and not in the
    service, because both depend on the `last_review` this same review
    overwrites. Computing them after the write would silently produce zero.
    """

    before: CardState
    after: CardState
    elapsed_days: int | None
    scheduled_days: int | None


# ── translation, both directions, asserted by a test ───────────────────────

_TO_LIBRARY_STATE: dict[str, State] = {
    "learning": State.Learning,
    "review": State.Review,
    "relearning": State.Relearning,
}
_FROM_LIBRARY_STATE: dict[State, str] = {v: k for k, v in _TO_LIBRARY_STATE.items()}

assert set(_TO_LIBRARY_STATE) == set(FSRS_STATES)


def scheduler() -> Scheduler:
    """The one configured scheduler. See properties 2 and 4 in the docstring."""
    return Scheduler(
        desired_retention=DESIRED_RETENTION,
        enable_fuzzing=False,
    )


def _require_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware and UTC, got {value!r}")
    return value.astimezone(timezone.utc)


def _to_card(state: CardState) -> Card:
    return Card(
        card_id=1,  # never persisted; migration 013's `cards.id` is the identity
        state=_TO_LIBRARY_STATE[state.fsrs_state],
        step=state.fsrs_step,
        stability=state.stability,
        difficulty=state.difficulty,
        due=_require_utc(state.due, "due"),
        last_review=(
            _require_utc(state.last_review, "last_review")
            if state.last_review is not None
            else None
        ),
    )


def _from_card(card: Card, *, lapses: int, reps: int) -> CardState:
    return CardState(
        fsrs_state=_FROM_LIBRARY_STATE[card.state],
        fsrs_step=card.step,
        stability=card.stability,
        difficulty=card.difficulty,
        due=card.due,
        last_review=card.last_review,
        lapses=lapses,
        reps=reps,
    )


# ── the four public functions ──────────────────────────────────────────────


def initial_state(*, due: datetime) -> CardState:
    """A genuinely new card. **No stability and no difficulty.**

    This is py-fsrs' own new-card representation, not an approximation of one.
    The library computes the first stability and difficulty from the *first real
    rating* (`_initial_stability` / `_initial_difficulty` in its `State.Learning`
    branch), which is the correct source for them. Anything we invented here
    would be a number with no measurement behind it, and migration 013's
    `cards_seeded_rows_carry_their_basis` CHECK exists so that the two cases stay
    distinguishable by query forever.
    """
    return CardState(
        fsrs_state="learning",
        fsrs_step=0,
        stability=None,
        difficulty=None,
        due=_require_utc(due, "due"),
        last_review=None,
        lapses=0,
        reps=0,
    )


def review(state: CardState, rating: int, *, now: datetime) -> ReviewResult:
    """Grade one card. `rating` is 1–4 (`fsrs.Rating`: Again … Easy).

    The clock is injected; see property 1. Both halves of the transition are
    returned because `card_reviews` logs before and after, and a log that can
    only say "after" cannot be replayed.
    """
    if rating not in (1, 2, 3, 4):
        raise ValueError(f"rating must be 1-4, got {rating!r}")
    moment = _require_utc(now, "now")

    elapsed_days: int | None = None
    if state.last_review is not None:
        elapsed_days = max(0, (moment - _require_utc(state.last_review, "last_review")).days)

    card, _log = scheduler().review_card(
        _to_card(state), Rating(rating), review_datetime=moment
    )

    # A lapse is `Again` on a card that was not already being relearned. Counted
    # here rather than read off the library, which does not track it: PRD §5's
    # leech rule is "6 lapses", so the count is a product fact and must not
    # depend on a library's internal bookkeeping staying the same across a minor
    # version.
    lapsed = rating == Rating.Again and state.fsrs_state != "relearning"
    after = _from_card(
        card,
        lapses=state.lapses + (1 if lapsed else 0),
        reps=state.reps + 1,
    )
    scheduled_days = max(0, (after.due - moment).days)
    return ReviewResult(
        before=state,
        after=after,
        elapsed_days=elapsed_days,
        scheduled_days=scheduled_days,
    )


def retrievability(state: CardState, *, now: datetime) -> float:
    """Probability of recall right now, 0–1. Read-only; nothing schedules on it."""
    return float(
        scheduler().get_card_retrievability(
            _to_card(state), current_datetime=_require_utc(now, "now")
        )
    )


def with_due(state: CardState, due: datetime) -> CardState:
    """The same state on a different date. Used only by the leech rewrite."""
    return replace(state, due=_require_utc(due, "due"))
