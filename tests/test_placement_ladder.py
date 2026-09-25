"""W18 — the adaptive grammar ladder, `core.placement.ladder`. **Pure; no database.**

User action: the learner answers the grammar part of a placement sitting; after
each answer `core.services.placement._next_step` replays this ladder to choose
the band of the next item, and `finish` reads its result.

**Every expected value is written out by hand** from the spec (*start at B1;
up after 2 consecutive correct, down after 2 wrong; stop when stable*) and the
module's stated stopping rules — never computed by the function under test
(CLAUDE.md §3 rule 5).

**RED DEMONSTRATIONS (2026-09-25), each one edit to `ladder.py`, run, and
restored:** `STEP = 3` turned four red, `test_two_right_steps_up_and_two_wrong_steps_down`
first; the oscillation rule reading the last TWO moves instead of three turned
`test_three_moves_up_and_up_and_down_is_not_oscillation` red; `held_band`
returning the highest band REACHED instead of the highest held turned
`test_oscillating_between_b1_and_b2_places_at_b1` and the thin-bank test red.
**One claimed demonstration did not go red and is recorded as such:** removing
a check that the three moves alternate in kind changed nothing — moves on one
pair alternate by construction — so the check was redundant and was deleted
rather than kept as decoration.
**Every other test here, by a scripted mutation each (2026-09-25, run with
`python -B` and `__pycache__` cleared — see below):** `START = "A2"`; the run
not reset after a move; `HOLD_ITEMS = 9`; the `boundary` stop removed (both
boundary tests); `MAX_ITEMS = 26`; the off-ladder `raise` removed; the empty
history's floor `{"A2"}`. **A same-size mutation can run STALE BYTECODE** — the
first sweep reported `RETEST_DAYS = 30` green in the scoring file because the
edited source kept its size and the old `.pyc` was reused; the sweep now runs
`-B` with the caches removed, and that mutation went red.
"""

from __future__ import annotations

import pytest

from core.placement import ladder

R, W = True, False


def _walk(*answers: bool) -> list[tuple[str, bool]]:
    """Answers → the history the service would record: each item served at the
    band the ladder was on when it was served. Uses `replay` only to read the
    band for the NEXT item, which is the service's own loop — the expected
    values below are still hardcoded."""
    history: list[tuple[str, bool]] = []
    for correct in answers:
        band = ladder.replay(history).band
        history.append((band, correct))
    return history


def test_the_ladder_starts_at_b1() -> None:
    state = ladder.replay([])
    assert state.band == "B1"
    assert state.stop is None and state.result is None


def test_two_right_steps_up_and_two_wrong_steps_down() -> None:
    assert ladder.replay(_walk(R, R)).band == "B2"
    assert ladder.replay(_walk(W, W)).band == "A2"
    # One right then one wrong is not a move either way.
    assert ladder.replay(_walk(R, W)).band == "B1"
    assert ladder.replay(_walk(R, W, R, W)).band == "B1"


def test_the_run_resets_after_a_move() -> None:
    # R R → B2; then R alone is not a second step.
    assert ladder.replay(_walk(R, R, R)).band == "B2"
    assert ladder.replay(_walk(R, R, R, R)).band == "C1"


def test_oscillating_between_b1_and_b2_places_at_b1() -> None:
    # up (B1→B2), down (B2→B1), up (B1→B2): three alternating moves, one pair.
    state = ladder.replay(_walk(R, R, W, W, R, R))
    assert state.stop == "oscillation"
    assert state.result == "B1"


def test_three_moves_up_and_up_and_down_is_not_oscillation() -> None:
    # B1→B2→C1, then C1→B2: not the same pair three times.
    state = ladder.replay(_walk(R, R, R, R, W, W))
    assert state.band == "B2"
    assert state.stop is None


def test_holding_one_band_for_eight_answers_stops_there() -> None:
    state = ladder.replay(_walk(R, W, R, W, R, W, R, W))
    assert state.stop == "held"
    assert state.result == "B1"


def test_two_step_ups_at_the_top_stop_at_c1() -> None:
    # B1→B2→C1, then two capped step-ups at C1.
    state = ladder.replay(_walk(R, R, R, R, R, R, R, R))
    assert state.stop == "boundary"
    assert state.result == "C1"


def test_two_step_downs_at_the_bottom_stop_at_a2_and_claim_nothing_lower() -> None:
    state = ladder.replay(_walk(W, W, W, W, W, W))
    assert state.stop == "boundary"
    assert state.result == "A2"


def test_twenty_five_answers_is_the_most_a_sitting_asks() -> None:
    # Up and down between A2 and B1 and then B1 and B2 without three alternating
    # moves on one pair, padded with alternating answers that hold a band for
    # fewer than eight — built by hand so no rule but the count can fire.
    answers = (
        [W, W]            # B1→A2
        + [R, W, R, W, R, W, R]  # 7 at A2, no move
        + [R]             # A2 R R → B1 (the 7th was R, so this is the second)
        + [R, W, R, W, R, W, R]  # 7 at B1
        + [R]             # → B2
        + [R, W, R, W, R, W, R]  # 7 at B2
    )
    assert len(answers) == 25
    state = ladder.replay(_walk(*answers))
    assert state.answered == 25
    assert state.stop == "max_items"
    # B2 held: 4 of 7 right at B2 (≥ half of ≥ 4 answers), and B1 was passed.
    assert state.result == "B2"


def test_an_item_served_off_the_ladder_is_refused() -> None:
    with pytest.raises(ValueError, match="served at C1 while the ladder was at B1"):
        ladder.replay([("C1", True)])


def test_a_thin_bank_stops_the_ladder_and_reads_what_was_answered() -> None:
    state = ladder.stop_for_thin_bank(_walk(R, R, R))
    assert state.stop == "bank_thin"
    assert state.band == "B2"
    # B1 was passed (two right there); B2 has one answer — not held.
    assert state.result == "B1"


def test_a_thin_bank_with_nothing_answered_reads_the_start() -> None:
    assert ladder.stop_for_thin_bank([]).result == "B1"
