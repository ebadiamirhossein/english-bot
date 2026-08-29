"""W8: the unit state machine, and the two constraints that are time-dependent.

**No test in this file reads the wall clock.** Every timestamp is passed in
explicitly and every expected value is hardcoded. That is CLAUDE.md §3 rule 6,
and it is load-bearing here for the same reason it was at W7: mastery is defined
as "a pass plus retained performance 3+ weeks later", so a test that computed
its own dates would begin failing on a calendar boundary rather than on a code
change — which is exactly how `test_vocabulary_due_and_anki` broke.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from core.config import load_settings
from core.syllabus import MASTERY_RETENTION_DAYS
from core.syllabus.states import (
    ALLOWED_TRANSITIONS,
    COMPLETED_STATES,
    LOCKED,
    UNIT_STATES,
    may_enter,
    may_move,
    validate,
)

# Fixed points, never `datetime.now()`. Chosen once and never recomputed.
PASSED_AT = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
EXACTLY_THREE_WEEKS = PASSED_AT + timedelta(days=21)
ONE_DAY_SHORT = PASSED_AT + timedelta(days=20)


# ── the pure half ───────────────────────────────────────────────────────────


def test_locked_is_not_a_storable_state() -> None:
    assert LOCKED not in UNIT_STATES
    with pytest.raises(ValueError, match="absence of a user_unit_state row"):
        validate(LOCKED)


def test_every_state_may_be_re_asserted() -> None:
    """An idempotent write is not a transition, and must never be refused."""
    for state in UNIT_STATES:
        assert may_move(state, state), state


def test_a_failed_checkpoint_keeps_the_unit_in_progress() -> None:
    """PRD §3: "the unit stays `in_progress` ... and you retake in 4 days."

    This is the transition a monotonic "never decrease" rule would have had to
    special-case, and getting it wrong is W4's failure shape: a rule stated as
    an ordering blocks a legitimate write the ordering did not anticipate.
    """
    assert may_move("in_progress", "in_progress")


def test_a_pass_is_never_undone() -> None:
    """A later failed checkpoint does not un-pass a unit.

    `passed_at` is the clock mastery is measured from; if a failure could reset
    it, W11 could never time a retention window. PRD §3's failure path is about
    a unit that was never passed.
    """
    assert not may_move("passed", "in_progress")
    assert not may_move("passed", "available")


def test_mastery_is_terminal() -> None:
    assert ALLOWED_TRANSITIONS["mastered"] == frozenset({"mastered"})


def test_a_unit_cannot_be_skipped_straight_to_passed() -> None:
    assert not may_move("available", "passed")
    assert not may_move("available", "mastered")


def test_a_learner_enters_at_available_or_in_progress() -> None:
    """The legal FIRST states. **Widened by operator ruling, 2026-08-29.**

    THIS TEST READ, UNTIL THAT RULING -- quoted rather than deleted, because the
    assertion it dropped is the one a later reader will want to find:

        def test_a_learner_enters_only_at_available() -> None:
            '''A first row in any other state would carry an `entered_at` for a
            moment that never happened, and W19's history reads these
            timestamps.'''
            assert may_enter("available")
            for state in ("in_progress", "passed", "mastered"):
                assert not may_enter(state), state

    **`in_progress` moved across the line and nothing else did.** #217: under
    operator ruling 2 of 2026-08-27, W11 writes `passed` only and never
    `available` -- that predicate is W9's and W9 does not exist -- so the old
    rule left PRD SS3's fail path with no row to write to. Candidate (b) was
    ruled: widen `may_enter`, and restate `entered_at` as **"when this learner
    first reached this unit"**, which is what `record_unit_entry` can honestly
    write and what W19's history actually wants.

    **Ruling 2 is untouched.** Nothing in W11 writes `available`.
    """
    assert may_enter("available")
    assert may_enter("in_progress")


def test_a_first_row_still_cannot_claim_a_pass() -> None:
    """The half of the old rule that SURVIVED, asserted on its own.

    A widened rule that is not shown to still refuse anything is not shown to be
    a rule. **Migration 014 would accept a directly-inserted `passed` first row**
    -- `user_unit_state_a_pass_needs_the_threshold` is satisfied by any row
    carrying `passed_at` and a score >= 80 -- so `may_enter` is the only thing
    that stops it, and it is exactly the write `record_checkpoint` would produce
    if an entry write were ever skipped.
    """
    for state in ("passed", "mastered"):
        assert not may_enter(state), state


def test_completed_states_are_pass_and_mastery() -> None:
    assert COMPLETED_STATES == frozenset({"passed", "mastered"})


def test_every_state_has_a_transition_row() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(UNIT_STATES)
    for state, allowed in ALLOWED_TRANSITIONS.items():
        assert allowed <= set(UNIT_STATES), state


# ── the database half: the constraints refuse what the docstrings claim ─────


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row is not None and int(row[0] or 0) >= 14, (
            "run `python -m core.db migrate` — 014 is not applied"
        )
        try:
            yield connection
        finally:
            connection.rollback()


@pytest.fixture
def units_present(conn):
    """The real 24 units, inside this test's transaction.

    `user_unit_state.unit_number` is a foreign key, so a progress row needs its
    unit to exist. Loaded from `data/syllabus_units.json` through the real
    `upsert_units` rather than from a hand-built stub: a stub would let these
    constraints be exercised against a unit shape the seed could never produce.
    Everything rolls back with the fixture.
    """
    from core.services.syllabus import upsert_units
    from core.syllabus.content import units

    upsert_units(conn, units())
    return conn


@pytest.fixture
def user_id(conn, units_present):
    row = conn.execute(
        "INSERT INTO users (name, native_language, auth_email, onboarded) "
        "VALUES (%s, %s, %s, TRUE) RETURNING id",
        ("W8 state fixture", "fa", "w8-states@example.test"),
    ).fetchone()
    return row[0]


def _insert(conn, user_id, **kwargs):
    unit_number = kwargs.pop("unit_number", 1)
    state = kwargs.pop("state", "available")
    columns = ["user_id", "unit_number", "state", *kwargs]
    values = [user_id, unit_number, state, *kwargs.values()]
    placeholders = ", ".join(["%s"] * len(values))
    conn.execute(
        f"INSERT INTO user_unit_state ({', '.join(columns)}) VALUES ({placeholders})",
        values,
    )


def test_mastery_needs_exactly_three_weeks_not_twenty_days(conn, user_id) -> None:
    """The boundary, asserted from both sides with hardcoded dates."""
    # A savepoint, not conn.rollback(): rolling the whole transaction back
    # would take the 24 units with it and the second half would fail on the
    # foreign key instead of on the thing under test.
    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.transaction():
            _insert(
                conn,
                user_id,
                unit_number=1,
                state="mastered",
                passed_at=PASSED_AT,
                mastered_at=ONE_DAY_SHORT,
                last_checkpoint_score=90,
            )
    _insert(
        conn,
        user_id,
        unit_number=1,
        state="mastered",
        passed_at=PASSED_AT,
        mastered_at=EXACTLY_THREE_WEEKS,
        last_checkpoint_score=90,
    )
    row = conn.execute(
        "SELECT mastered_at - passed_at FROM user_unit_state WHERE user_id = %s",
        (user_id,),
    ).fetchone()
    assert row[0] == timedelta(days=MASTERY_RETENTION_DAYS)


def test_mastery_without_a_pass_is_refused(conn, user_id) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(
            conn,
            user_id,
            unit_number=2,
            state="mastered",
            mastered_at=EXACTLY_THREE_WEEKS,
            last_checkpoint_score=90,
        )


def test_a_pass_below_the_threshold_is_refused(conn, user_id) -> None:
    """80 is the pass mark; 79 is not a pass however it is labelled."""
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(
            conn,
            user_id,
            unit_number=3,
            state="passed",
            passed_at=PASSED_AT,
            last_checkpoint_score=79,
        )


def test_a_pass_with_no_recorded_score_is_refused(conn, user_id) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(conn, user_id, unit_number=4, state="passed", passed_at=PASSED_AT)


def test_a_timestamp_without_its_state_is_refused(conn, user_id) -> None:
    """A row that disagrees with itself: in progress, but carrying a pass time."""
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(
            conn,
            user_id,
            unit_number=5,
            state="in_progress",
            passed_at=PASSED_AT,
            last_checkpoint_score=90,
        )


def test_locked_cannot_be_stored(conn, user_id) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(conn, user_id, unit_number=6, state="locked")


def test_one_row_per_learner_per_unit(conn, user_id) -> None:
    _insert(conn, user_id, unit_number=7, state="available")
    with pytest.raises(psycopg.errors.UniqueViolation):
        with conn.transaction():
            _insert(conn, user_id, unit_number=7, state="in_progress")


def test_a_unit_outside_one_to_twenty_four_is_refused(conn, user_id) -> None:
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _insert(conn, user_id, unit_number=25, state="available")
