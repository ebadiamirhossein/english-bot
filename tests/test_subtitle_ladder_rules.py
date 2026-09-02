"""W13a: PRD §7.5's movement rules. **Pure — no database, no route, no model.**

The ladder is arithmetic over a state, and this file is where the arithmetic
lives so it can be argued about without Postgres. `core/video/ladder.py` has the
same standing `score.py`, `watch.py` and `cues.py` have.

**THE THREE BANDS AND THEIR EXACT EDGES.** PRD §7.5: *"Two comprehension checks
at ≥85% → move up, announced. Below 60% → move down, silently."* So 85 passes,
84 does not; 60 does NOT demote, 59 does. **Every boundary is asserted at the
exact integer on both sides**, never as a range, because a range is where an
off-by-one hides.

**THE ASYMMETRY IS THE PRODUCT DECISION, NOT AN OVERSIGHT.** A promotion is
announced; a demotion returns `announce = False` and there is no message to
suppress later — *raises announced, drops silent*, and a demotion message would
be a guilt message (CLAUDE.md §4). **#348 is the live instance of exactly that
mistake already shipping**, which is why this is asserted rather than left to
the surface.

**NO ASSERTION HERE ADMITS ITS OWN FAILURE MODE BESIDE THE REAL VALUE (#345).**
Nothing reads `direction in ("up", None)`; every case pins one direction, one
step and one pass count.
"""

from __future__ import annotations

import pytest

from core.video import ladder


def state(step: int, passes: int = 0) -> ladder.LadderState:
    return ladder.LadderState(step=step, passes_at_step=passes)


# ── the constants are PRD's, not literals ───────────────────────────────────


def test_the_thresholds_are_the_prds_numbers() -> None:
    """Stated here so a change to them is a change to a test, not a constant."""
    assert ladder.PROMOTE_PCT == 85
    assert ladder.DEMOTE_PCT == 60
    assert ladder.PASSES_TO_PROMOTE == 2
    assert ladder.FIRST_STEP == 1
    assert ladder.TOP_STEP == 5
    assert ladder.STEPS == (1, 2, 3, 4, 5)


def test_the_two_ladders_are_prds_two_source_types() -> None:
    """PRD §7.5: *"Two ladders: `youtube_curated` and `native_series`."* Kept as
    a constant because migration 022's CHECK mirrors it and a test compares the
    two — one producer, not two hand-kept copies (#132's family)."""
    assert ladder.TRACK_KINDS == ("youtube_curated", "native_series")


# ── promotion: two passes, and the second one is what moves you ─────────────


def test_one_pass_at_the_threshold_moves_nothing_and_announces_nothing() -> None:
    move = ladder.apply_check(state(1), 85)
    assert move.state == state(1, passes=1)
    assert move.direction is None
    assert move.announce is False


def test_the_second_pass_promotes_and_is_announced() -> None:
    move = ladder.apply_check(state(1, passes=1), 85)
    assert move.state == state(2, passes=0)
    assert move.direction == "up"
    assert move.announce is True


def test_eighty_four_is_not_a_pass_and_eighty_five_is() -> None:
    """The exact edge, both sides, from one state."""
    assert ladder.apply_check(state(2), 84).state == state(2, passes=0)
    assert ladder.apply_check(state(2), 85).state == state(2, passes=1)


def test_the_pass_counter_resets_on_promotion_so_it_never_reaches_two() -> None:
    """Migration 022's `passes_at_step BETWEEN 0 AND 1` is this invariant in the
    database. A 2 that persisted would mean the rule stopped promoting."""
    move = ladder.apply_check(state(3, passes=1), 92)
    assert move.state.passes_at_step == 0
    assert move.state.step == 4


def test_a_middling_check_leaves_the_pass_counter_alone() -> None:
    """**RULED HERE, and PRD §7.5 does not say it.** 85 then 70 then 85 promotes.

    The declined alternative is strict consecutiveness — a 70% resetting the
    count. It is refused because 70% is not a failure by this ladder's own bands
    (below 60 is), and making a non-failing score undo earned progress is a
    punishment for a result the product treats as a non-event.
    """
    first = ladder.apply_check(state(1), 85)
    middling = ladder.apply_check(first.state, 70)
    assert middling.state == state(1, passes=1)
    assert middling.direction is None
    second = ladder.apply_check(middling.state, 85)
    assert second.state == state(2, passes=0)
    assert second.direction == "up"


def test_the_top_step_is_the_top_and_passes_do_not_pile_up_there() -> None:
    """Step 5 is *"no subtitles at all"* — the goal, with nowhere above it.

    Passes are not accumulated at the top: a counter climbing toward a promotion
    that cannot happen is a number that means nothing, and it would eventually
    break 022's `BETWEEN 0 AND 1`.
    """
    move = ladder.apply_check(state(5), 100)
    assert move.state == state(5, passes=0)
    assert move.direction is None
    assert move.announce is False


# ── demotion: silent, and that is the whole asymmetry ───────────────────────


def test_below_sixty_demotes_one_step_and_says_nothing() -> None:
    move = ladder.apply_check(state(4), 55)
    assert move.state == state(3, passes=0)
    assert move.direction == "down"
    assert move.announce is False, "a demotion message is a guilt message (§4)"


def test_sixty_exactly_is_not_a_demotion_and_fifty_nine_is() -> None:
    assert ladder.apply_check(state(4), 60).state == state(4, passes=0)
    assert ladder.apply_check(state(4), 59).state == state(3, passes=0)


def test_a_demotion_clears_the_pass_counter() -> None:
    """The count belongs to the step you are on. Carrying it down would leave a
    learner one check from re-promoting to the step they just failed out of."""
    move = ladder.apply_check(state(4, passes=1), 30)
    assert move.state == state(3, passes=0)


def test_the_bottom_step_is_the_floor_and_a_failure_there_is_not_a_movement() -> None:
    """Step 1 is English + L1 — there is nothing gentler to drop to."""
    move = ladder.apply_check(state(1, passes=1), 10)
    assert move.state == state(1, passes=0), "the counter still clears"
    assert move.direction is None, "there was no movement to report"
    assert move.announce is False


# ── the band that does nothing ──────────────────────────────────────────────


@pytest.mark.parametrize("score", [60, 70, 84])
def test_the_middle_band_moves_no_one(score: int) -> None:
    move = ladder.apply_check(state(3), score)
    assert move.state == state(3, passes=0)
    assert move.direction is None
    assert move.announce is False


# ── the announce flag is about direction, never about the score ────────────


def test_only_an_upward_movement_is_ever_announced() -> None:
    """Asserted across every step and every band rather than at one point, so
    'announce' cannot come to mean 'something happened'."""
    for step in ladder.STEPS:
        for passes in (0, 1):
            for score in (0, 59, 60, 84, 85, 100):
                move = ladder.apply_check(state(step, passes), score)
                assert move.announce == (move.direction == "up"), (
                    step, passes, score
                )


def test_a_score_outside_zero_to_one_hundred_is_refused() -> None:
    """A percentage that is not one is a bug upstream, and clamping it here
    would let the bug through wearing a plausible number."""
    with pytest.raises(ValueError):
        ladder.apply_check(state(1), 101)
    with pytest.raises(ValueError):
        ladder.apply_check(state(1), -1)


def test_a_state_outside_the_ladder_is_refused() -> None:
    with pytest.raises(ValueError):
        ladder.LadderState(step=0, passes_at_step=0)
    with pytest.raises(ValueError):
        ladder.LadderState(step=6, passes_at_step=0)
    with pytest.raises(ValueError):
        ladder.LadderState(step=1, passes_at_step=2)
