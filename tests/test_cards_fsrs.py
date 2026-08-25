"""`core.cards.fsrs` — the wrapper, and how a date calculation is tested.

Three constraints collide here and the file exists to satisfy all three.

* **CLAUDE.md §3 rule 5** — a test must never derive its expected value from the
  function under test. So the numbers below are **transcribed as literals from
  py-fsrs' own upstream test suite** (`tests/test_basic.py` in
  open-spaced-repetition/py-fsrs). That is an independent source: it is the
  library's specification of its own behaviour, not a second run of our code.
  Nothing here calls the wrapper to find out what to expect.

* **CLAUDE.md §3 rule 6** — a test must not depend on wall-clock date. Nothing
  is frozen and no clock is patched: the wrapper takes `now` as an argument, so
  every test passes a fixed instant and asserts a **delta** from it. No
  assertion compares against a calendar date, so none can begin failing on a
  boundary the way `test_vocabulary_due_and_anki` did.

* **Determinism** — `enable_fuzzing=False` (see the wrapper's docstring).
  Without it `review_card` calls `random()` and every assertion below is flaky
  by construction.

The relational tests at the bottom are the ones that actually catch a broken
wrapper. A transcribed vector proves the library still behaves as documented; a
wrapper that dropped a field, or returned its input unchanged, would fail the
monotonicity assertions and nothing else.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.cards import FSRS_STATES, RATINGS
from core.cards.fsrs import CardState, initial_state, retrievability, review

AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4

#: The instant every test starts from. Arbitrary, fixed, and never `now()`.
T0 = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)


# ── the constants correspond to the library's own enums ────────────────────


def test_the_rating_names_map_to_the_library_integers() -> None:
    """`fsrs.Rating` is an IntEnum and the integers travel into the database.

    Read out of the library rather than restated, because `card_reviews.rating`
    stores them and a stored log must be replayable through the scheduler
    without a lookup table.
    """
    from fsrs import Rating

    assert RATINGS == {
        "again": int(Rating.Again),
        "hard": int(Rating.Hard),
        "good": int(Rating.Good),
        "easy": int(Rating.Easy),
    }


def test_the_state_names_correspond_to_the_library_enum() -> None:
    from fsrs import State

    assert {s.name.lower() for s in State} == set(FSRS_STATES)


# ── transcribed upstream vectors ───────────────────────────────────────────

#: py-fsrs `tests/test_basic.py::TestPyFSRS::test_review_card`, verbatim.
#: A new card reviewed repeatedly, each review taken at the moment the previous
#: one fell due. The intervals are the library's published answer.
UPSTREAM_RATINGS = (
    GOOD, GOOD, GOOD, GOOD, GOOD, GOOD,
    AGAIN, AGAIN,
    GOOD, GOOD, GOOD, GOOD, GOOD,
)
UPSTREAM_INTERVALS = [0, 2, 11, 46, 163, 498, 0, 0, 2, 4, 7, 12, 21]


def test_the_wrapper_reproduces_the_upstream_interval_sequence() -> None:
    """Thirteen reviews, thirteen published intervals, no arithmetic of ours.

    If the wrapper mis-translates a state, drops `step`, or loses `last_review`
    between calls, this sequence diverges — and it diverges early, at the third
    review, because the Review branch reads all three.
    """
    state = initial_state(due=T0)
    moment = T0
    intervals: list[int] = []
    for rating in UPSTREAM_RATINGS:
        result = review(state, rating, now=moment)
        state = result.after
        intervals.append((state.due - state.last_review).days)
        moment = state.due
    assert intervals == UPSTREAM_INTERVALS


#: py-fsrs `tests/test_basic.py::TestPyFSRS::test_memo_state`, verbatim.
MEMO_RATINGS = (AGAIN, GOOD, GOOD, GOOD, GOOD, GOOD)
MEMO_GAPS_DAYS = [0, 0, 1, 3, 8, 21]
MEMO_STABILITY = 53.62691
MEMO_DIFFICULTY = 6.3574867


def test_the_wrapper_reproduces_the_upstream_memory_state() -> None:
    """Stability and difficulty after a lapse and five recoveries."""
    state = initial_state(due=T0)
    moment = T0
    for rating, gap in zip(MEMO_RATINGS, MEMO_GAPS_DAYS):
        moment += timedelta(days=gap)
        state = review(state, rating, now=moment).after
    assert state.stability == pytest.approx(MEMO_STABILITY, abs=1e-4)
    assert state.difficulty == pytest.approx(MEMO_DIFFICULTY, abs=1e-4)


# ── relational properties: what a broken wrapper actually fails ────────────


def _mature() -> CardState:
    """A settled Review card. Hand-written; nothing computed it."""
    return CardState(
        fsrs_state="review",
        fsrs_step=None,
        stability=10.0,
        difficulty=5.0,
        due=T0,
        last_review=T0 - timedelta(days=10),
        lapses=0,
        reps=4,
    )


def test_the_four_grades_are_strictly_ordered_by_how_far_they_schedule() -> None:
    """Again < Hard < Good < Easy, always. No parameter set violates it.

    This is the property the four buttons *mean*. A wrapper that returned the
    same due date for all four would pass "four buttons render" and fail here.
    """
    dues = [review(_mature(), r, now=T0).after.due for r in (AGAIN, HARD, GOOD, EASY)]
    assert dues == sorted(dues)
    assert len(set(dues)) == 4


def test_every_grade_schedules_strictly_after_the_moment_it_was_graded() -> None:
    for rating in (AGAIN, HARD, GOOD, EASY):
        assert review(_mature(), rating, now=T0).after.due > T0


def test_again_counts_a_lapse_and_the_other_three_do_not() -> None:
    """PRD §5's leech rule counts lapses, so the count is a product fact.

    Counted in the wrapper rather than read off the library: a minor version
    that changed its internal bookkeeping would otherwise move the leech
    threshold silently.
    """
    assert review(_mature(), AGAIN, now=T0).after.lapses == 1
    for rating in (HARD, GOOD, EASY):
        assert review(_mature(), rating, now=T0).after.lapses == 0


def test_a_relearning_card_does_not_count_a_second_lapse() -> None:
    """A card already in relearning has already been counted once."""
    relearning = CardState(
        fsrs_state="relearning",
        fsrs_step=0,
        stability=2.0,
        difficulty=7.0,
        due=T0,
        last_review=T0 - timedelta(days=1),
        lapses=1,
        reps=5,
    )
    assert review(relearning, AGAIN, now=T0).after.lapses == 1


def test_every_grade_counts_a_repetition() -> None:
    for rating in (AGAIN, HARD, GOOD, EASY):
        assert review(_mature(), rating, now=T0).after.reps == 5


def test_a_stronger_card_schedules_further_out() -> None:
    """Monotone in stability. The seeding mapping relies on this being true."""
    strong = CardState(
        fsrs_state="review",
        fsrs_step=None,
        stability=60.0,
        difficulty=5.0,
        due=T0,
        last_review=T0 - timedelta(days=60),
        lapses=0,
        reps=8,
    )
    assert (
        review(strong, GOOD, now=T0).after.due > review(_mature(), GOOD, now=T0).after.due
    )


def test_two_good_reviews_produce_a_longer_second_interval() -> None:
    first = review(_mature(), GOOD, now=T0)
    second = review(first.after, GOOD, now=first.after.due)
    assert second.scheduled_days > first.scheduled_days


# ── the new-card branch invents nothing ────────────────────────────────────


def test_a_new_card_carries_no_stability_and_no_difficulty() -> None:
    """**The whole reason `initial_state` exists.**

    py-fsrs computes the first stability and difficulty from the first real
    rating. Anything we wrote here would be a number with no measurement behind
    it, and a month later it would be indistinguishable from a measured one.
    """
    state = initial_state(due=T0)
    assert state.fsrs_state == "learning"
    assert state.stability is None
    assert state.difficulty is None
    assert state.last_review is None
    assert state.reps == 0 and state.lapses == 0


def test_the_first_review_of_a_new_card_supplies_both() -> None:
    after = review(initial_state(due=T0), GOOD, now=T0).after
    assert after.stability is not None and after.difficulty is not None


# ── elapsed days, and the clock discipline ─────────────────────────────────


def test_elapsed_days_is_none_on_a_card_that_has_never_been_reviewed() -> None:
    assert review(initial_state(due=T0), GOOD, now=T0).elapsed_days is None


def test_elapsed_days_measures_from_the_previous_review() -> None:
    state = CardState(
        fsrs_state="review",
        fsrs_step=None,
        stability=10.0,
        difficulty=5.0,
        due=T0,
        last_review=T0 - timedelta(days=7),
        lapses=0,
        reps=3,
    )
    assert review(state, GOOD, now=T0).elapsed_days == 7


def test_a_naive_datetime_is_refused_at_our_boundary() -> None:
    """Refused one frame earlier than py-fsrs would, with our own message.

    A naive datetime here would mean the clock was read somewhere that does not
    know it is UTC, which is the bug worth naming rather than the exception.
    """
    with pytest.raises(ValueError, match="UTC"):
        review(_mature(), GOOD, now=datetime(2026, 1, 1, 9, 0))


def test_a_non_utc_datetime_is_refused() -> None:
    with pytest.raises(ValueError, match="UTC"):
        review(
            _mature(),
            GOOD,
            now=datetime(2026, 1, 1, 9, 0, tzinfo=timezone(timedelta(hours=3))),
        )


def test_a_rating_outside_one_to_four_is_refused() -> None:
    for bad in (0, 5, -1):
        with pytest.raises(ValueError, match="1-4"):
            review(_mature(), bad, now=T0)


def test_grading_does_not_mutate_the_state_it_was_given() -> None:
    """`card_reviews` logs before and after; a mutating scheduler loses before."""
    state = _mature()
    result = review(state, AGAIN, now=T0)
    assert result.before == state
    assert state.lapses == 0 and state.due == T0


# ── scheduling is reproducible ─────────────────────────────────────────────


def test_the_same_inputs_schedule_the_same_due_date_every_time() -> None:
    """`enable_fuzzing=False`. Without it this is flaky by construction, and
    every relational assertion above becomes a coin toss near a boundary."""
    dues = {review(_mature(), GOOD, now=T0).after.due for _ in range(20)}
    assert len(dues) == 1


def test_retrievability_falls_as_time_passes() -> None:
    state = _mature()
    fresh = retrievability(state, now=T0 - timedelta(days=9))
    stale = retrievability(state, now=T0 + timedelta(days=30))
    assert 0.0 <= stale < fresh <= 1.0
