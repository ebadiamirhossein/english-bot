"""The adaptive grammar ladder. **Pure: a history in, a position and a verdict out.**

PRD §6 and the build run's spec: *start at B1; step up after 2 consecutive
correct answers, and down after 2 wrong; stop when the band is stable.*

**The state is never stored.** It is REPLAYED from the sitting's own history —
`(band served at, correct)` for every grammar item answered — so a sitting that
resumes after a closed tab is at exactly the rung it left, and there is no
second copy of the ladder's position to drift from the answers that produced it.

**WHAT "STABLE" MEANS HERE — the spec says *stable* and does not define it, so
this module does, and the definition is the thing to argue with:**

* ``oscillation`` — the last three moves went back and forth between the same
  two bands (up, down, up or down, up, down): the learner holds the lower band
  and not the upper one, twice over.
* ``held`` — `HOLD_ITEMS` answers in a row at one band without a move: right
  about half the time, which is the band.
* ``boundary`` — two moves in a row off the same end of the ladder (two
  step-ups at C1, or two step-downs at A2): nothing above or below to try.
* ``max_items`` — PRD §6's 25, whatever the pattern.
* ``bank_thin`` — no unserved item at the band the ladder is on. Decided by the
  caller (it needs the bank), recorded on the run, never shown.

**THE RESULT** is the highest band the learner HELD: a band they stepped up from
(two right in a row there), or one where at least half of `HELD_MIN_ITEMS` or
more answers were right. If they held none, the lowest band they reached — the
instrument claims nothing below A2.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.placement import BANDS

START = "B1"
#: PRD §6: *"25 items adaptive"*.
MAX_ITEMS = 25
#: Consecutive answers at one band, with no move, that count as holding it.
HOLD_ITEMS = 8
#: Fewest answers at a band before a ≥50% record there counts as holding it.
HELD_MIN_ITEMS = 4
#: Two in a row, the spec's number, both ways.
STEP = 2

UP, DOWN, CAP_UP, CAP_DOWN = "up", "down", "cap_up", "cap_down"


@dataclass(frozen=True, slots=True)
class Move:
    kind: str  # up | down | cap_up | cap_down
    at: str  # the band the move was made FROM
    to: str  # the band after it (== at for a cap)


@dataclass(frozen=True, slots=True)
class Ladder:
    """Where the ladder is after a history, and whether it has stopped."""

    band: str
    answered: int
    moves: tuple[Move, ...]
    since_move: int
    stop: str | None
    #: Set once stopped; the band the sitting reports for grammar.
    result: str | None


def replay(history: Sequence[tuple[str, bool]]) -> Ladder:
    """Walk the ladder over ``(band served at, correct)`` pairs, in order.

    **Raises if an item was served off the ladder** — at a band other than the
    one the ladder was on. That can only be a bug in the caller, and replaying
    past it would compute a result from a sitting that did not happen.
    """
    band = START
    right = wrong = 0
    since_move = 0
    moves: list[Move] = []
    for n, (served, correct) in enumerate(history):
        if served != band:
            raise ValueError(
                f"answer {n} was served at {served} while the ladder was at {band}"
            )
        since_move += 1
        if correct:
            right, wrong = right + 1, 0
        else:
            right, wrong = 0, wrong + 1
        if right == STEP or wrong == STEP:
            here = BANDS.index(band)
            if right == STEP:
                nxt = min(here + 1, len(BANDS) - 1)
                kind = UP if nxt != here else CAP_UP
            else:
                nxt = max(here - 1, 0)
                kind = DOWN if nxt != here else CAP_DOWN
            moves.append(Move(kind, band, BANDS[nxt]))
            band = BANDS[nxt]
            right = wrong = since_move = 0

    stop = _stopped(len(history), tuple(moves), since_move)
    result = held_band(history, tuple(moves)) if stop else None
    return Ladder(band, len(history), tuple(moves), since_move, stop, result)


def _stopped(answered: int, moves: tuple[Move, ...], since_move: int) -> str | None:
    real = [m for m in moves if m.kind in (UP, DOWN)]
    # Three real moves on one pair of adjacent bands. They alternate by
    # construction — a second move up from B1 to B2 needs a move down between.
    if len(real) >= 3:
        a, b, c = real[-3:]
        if {a.at, a.to} == {b.at, b.to} == {c.at, c.to}:
            return "oscillation"
    if len(moves) >= 2 and moves[-1].kind == moves[-2].kind and moves[-1].kind in (CAP_UP, CAP_DOWN):
        return "boundary"
    if since_move >= HOLD_ITEMS:
        return "held"
    if answered >= MAX_ITEMS:
        return "max_items"
    return None


def held_band(history: Sequence[tuple[str, bool]], moves: Sequence[Move]) -> str:
    """The highest band held — see the module docstring. Never raises on an
    empty history (it answers `START`'s floor, the lowest band reached)."""
    held: set[str] = {m.at for m in moves if m.kind in (UP, CAP_UP)}
    for band in BANDS:
        answers = [c for b, c in history if b == band]
        if len(answers) >= HELD_MIN_ITEMS and sum(answers) * 2 >= len(answers):
            held.add(band)
    if held:
        return max(held, key=BANDS.index)
    reached = {b for b, _ in history} | {m.to for m in moves} or {START}
    return min(reached, key=BANDS.index)


def stop_for_thin_bank(history: Sequence[tuple[str, bool]]) -> Ladder:
    """The caller found nothing unserved at the ladder's band: stop there, and
    read the result from what was answered. A ladder already stopped is
    returned as it is."""
    state = replay(history)
    if state.stop:
        return state
    return Ladder(
        state.band, state.answered, state.moves, state.since_move, "bank_thin",
        held_band(history, state.moves),
    )
