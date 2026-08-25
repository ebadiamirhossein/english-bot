"""The v2 → FSRS seeding mapping. Every expected value is hand-computed.

Nothing here calls `seed_from_v2` to find out what to expect: the ladder is
1 → 3 → 7 → 21 → 60 and the difficulty is a linear map of the error rate onto
[1, 10], both written out by hand below. That is CLAUDE.md §3 rule 5, and it
matters more here than usual — a seeding mapping that agreed with itself would
pass any test derived from it while putting a wrong schedule under a learner.

The no-history test is the one the slice turns on. A fabricated stability is
indistinguishable from a measured one a month later, so "there is no number
here" has to be asserted rather than assumed.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from core.cards.seeding import SEED_MAPPING, ladder_interval, seed_from_v2

TODAY = date(2026, 8, 25)


def _seed(**over):
    kwargs = dict(
        times_right=0, times_wrong=0, streak_right=0, next_review=None, today=TODAY
    )
    kwargs.update(over)
    return seed_from_v2(**kwargs)


# ── the ladder, written out rather than imported ──────────────────────────


@pytest.mark.parametrize(
    "streak,expected",
    [(0, 1), (1, 3), (2, 7), (3, 21), (4, 60), (5, 60), (99, 60)],
)
def test_the_ladder_is_v2s_own(streak: int, expected: int) -> None:
    """1 → 3 → 7 → 21 → 60, clamped. Hardcoded, not read from SPACING_DAYS."""
    assert ladder_interval(streak) == expected


# ── branch (a): nothing measured, nothing asserted ────────────────────────


def test_a_chunk_with_no_graded_review_gets_no_stability() -> None:
    """**The criterion "no card carries a fabricated stability".**

    A chunk presented but never graded is a real and probably common case, and
    it must produce py-fsrs' genuine new-card representation rather than a
    plausible-looking number. `basis is None` is what keeps
    `seeded_from_history` FALSE, and migration 013's CHECK then keeps the two
    cases distinguishable by query forever.
    """
    state, basis = _seed(times_right=0, times_wrong=0)
    assert state.stability is None
    assert state.difficulty is None
    assert state.fsrs_state == "learning"
    assert state.fsrs_step == 0
    assert state.last_review is None
    assert state.lapses == 0 and state.reps == 0
    assert basis is None


def test_a_chunk_with_no_history_is_due_on_its_v2_date() -> None:
    state, _ = _seed(next_review=date(2026, 9, 1))
    assert state.due == datetime(2026, 9, 1, tzinfo=timezone.utc)


def test_a_chunk_with_no_history_and_no_date_is_due_today() -> None:
    state, _ = _seed(next_review=None)
    assert state.due == datetime(2026, 8, 25, tzinfo=timezone.utc)


# ── branch (b): the mapping, hand-computed ────────────────────────────────


def test_a_perfect_history_seeds_the_easiest_difficulty() -> None:
    """0 wrong of 4 → difficulty 1.0, FSRS' own minimum."""
    state, _ = _seed(times_right=4, times_wrong=0, streak_right=4)
    assert state.difficulty == pytest.approx(1.0)
    assert state.stability == pytest.approx(60.0)  # ladder step 4


def test_an_always_wrong_history_seeds_the_hardest_difficulty() -> None:
    state, _ = _seed(times_right=0, times_wrong=3, streak_right=0)
    assert state.difficulty == pytest.approx(10.0)
    assert state.stability == pytest.approx(1.0)  # ladder step 0


def test_the_difficulty_is_a_linear_map_of_the_error_rate() -> None:
    """1 wrong of 4 → 1 + 9 × 0.25 = 3.25. Computed by hand, not by the module."""
    state, _ = _seed(times_right=3, times_wrong=1, streak_right=2)
    assert state.difficulty == pytest.approx(3.25)
    assert state.stability == pytest.approx(7.0)  # ladder step 2


def test_the_lapse_and_rep_counts_come_from_the_v2_totals() -> None:
    state, _ = _seed(times_right=5, times_wrong=2, streak_right=1)
    assert state.lapses == 2
    assert state.reps == 7


def test_last_review_is_the_v2_date_minus_the_v2_interval() -> None:
    """Arithmetic over stored values, never an invented event.

    v2 set `next_review = review_date + interval`, so this recovers the date of
    the review that produced it. It is needed because py-fsrs' Review branch
    reads `days_since_last_review`, and it is deliberately not written into
    `card_reviews` — the log starts empty and its first row is a real one.
    """
    state, _ = _seed(
        times_right=3, times_wrong=1, streak_right=2, next_review=date(2026, 8, 30)
    )
    # ladder step 2 is 7 days; 30 Aug − 7 = 23 Aug
    assert state.due == datetime(2026, 8, 30, tzinfo=timezone.utc)
    assert state.last_review == datetime(2026, 8, 23, tzinfo=timezone.utc)


def test_a_seeded_card_is_in_the_review_state_with_both_parameters() -> None:
    """Migration 013's `cards_review_state_carries_both_parameters` would
    otherwise refuse the row, and py-fsrs would assert at grade time."""
    state, _ = _seed(times_right=2, times_wrong=0, streak_right=2)
    assert state.fsrs_state == "review"
    assert state.fsrs_step is None
    assert state.stability is not None and state.difficulty is not None


# ── the basis, which is what makes a wrong mapping recoverable ────────────


def test_a_seeded_card_carries_its_inputs_verbatim() -> None:
    """If the mapping turns out wrong, a re-seed is an UPDATE with a formula.

    A derived number whose inputs were discarded cannot be corrected, only
    guessed at again — and `chunks` being left untouched is the other half of
    the same guarantee.
    """
    _, basis = _seed(
        times_right=3, times_wrong=1, streak_right=2, next_review=date(2026, 8, 30)
    )
    assert basis == {
        "mapping": SEED_MAPPING,
        "mapping_version": 1,
        "times_right": 3,
        "times_wrong": 1,
        "streak_right": 2,
        "next_review": "2026-08-30",
        "ladder_interval_days": 7,
    }


def test_the_stability_is_monotone_in_the_streak() -> None:
    """More consecutive recalls must never seed a shorter interval."""
    stabilities = [
        _seed(times_right=s + 1, times_wrong=0, streak_right=s)[0].stability
        for s in range(5)
    ]
    assert stabilities == sorted(stabilities)
    assert len(set(stabilities)) == 5


def test_dates_become_midnight_utc_and_not_the_local_day() -> None:
    """Any other choice makes a migrated due date depend on the server's
    timezone at the moment the pass happened to run."""
    state, _ = _seed(times_right=1, times_wrong=0, streak_right=1, next_review=date(2026, 12, 31))
    assert state.due.tzinfo == timezone.utc
    assert (state.due.hour, state.due.minute, state.due.second) == (0, 0, 0)
