"""The within-unit clock, and what block 3 serves from it.

OPERATOR RULING, 2026-08-29 (#245): **a section advances per COMPLETED SESSION,
not per calendar day** -- a learner who skips a day loses nothing and sees the
next section when they next open a session. **When the sections run out before
Saturday, block 3 shows practice only: no new teaching and no repeated section.**

The ruling is neither of the two options that were costed, and it is better than
both for a reason worth keeping: under a calendar clock a missed day is a LOST
SECTION -- teaching deleted by the calendar, never presented as a backlog and so
never caught. CLAUDE.md §4 says missed days shrink the task and never pile up;
under a calendar rule they do neither.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import psycopg
import pytest

from core.config import load_settings
from core.services.syllabus import record_unit_entry, unit_section_index

ENTERED = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        try:
            yield connection
        finally:
            connection.rollback()


@pytest.fixture
def units_present(conn):
    from core.services.syllabus import upsert_units
    from core.syllabus.content import units

    upsert_units(conn, units())
    return conn


@pytest.fixture
def learner(conn, units_present):
    row = conn.execute(
        "INSERT INTO users (name, native_language, auth_email, onboarded, timezone) "
        "VALUES ('W11 pacing', 'fa', 'w11-pacing@example.test', TRUE, 'Europe/Vilnius') "
        "RETURNING id"
    ).fetchone()
    user_id = int(row[0])
    record_unit_entry(conn, user_id, 1, now=ENTERED)
    return user_id


def _session(conn, learner: int, on: date, *, focus_done: bool) -> None:
    conn.execute(
        "INSERT INTO sessions (user_id, date, task_type, completed, block_breakdown) "
        "VALUES (%s, %s, 'daily', TRUE, %s)",
        (learner, on, '{"focus": "done"}' if focus_done else '{"focus": "ready"}'),
    )


def _index(conn, learner: int, today: date) -> int:
    return unit_section_index(conn, learner, 1, local_today=today)


def test_the_first_session_is_section_zero(conn, learner) -> None:
    assert _index(conn, learner, date(2026, 9, 1)) == 0


def test_each_completed_focus_block_advances_one_section(conn, learner) -> None:
    _session(conn, learner, date(2026, 9, 1), focus_done=True)
    assert _index(conn, learner, date(2026, 9, 2)) == 1
    _session(conn, learner, date(2026, 9, 2), focus_done=True)
    assert _index(conn, learner, date(2026, 9, 3)) == 2


def test_a_skipped_day_loses_no_section(conn, learner) -> None:
    """**The ruling's whole point, and the one assertion that distinguishes it
    from what was declined.**

    Two completed sessions, five calendar days apart. A calendar clock would put
    this learner on section 5 and they would never see 2, 3 and 4. The ruled rule
    puts them on section 2, which is where they actually are.
    """
    _session(conn, learner, date(2026, 9, 1), focus_done=True)
    _session(conn, learner, date(2026, 9, 2), focus_done=True)
    assert _index(conn, learner, date(2026, 9, 6)) == 2


def test_a_session_completed_without_the_focus_block_does_not_advance(
    conn, learner
) -> None:
    """The STRICT reading of *completed session*, and it is the right one.

    A learner can complete a session having skipped block 3. Counting that would
    advance them past a section they never saw -- the one failure the ruling
    exists to prevent, one layer down. `block_breakdown->>'focus' = 'done'` is
    written by `complete_block`, so *the teaching block was actually finished* is
    a fact the system already records.
    """
    _session(conn, learner, date(2026, 9, 1), focus_done=False)
    assert _index(conn, learner, date(2026, 9, 2)) == 0


def test_todays_own_session_does_not_advance_today(conn, learner) -> None:
    """`s.date < local_today`: strictly PRIOR sessions.

    Without this, finishing block 3 would move the section under the learner
    inside the same sitting.
    """
    _session(conn, learner, date(2026, 9, 2), focus_done=True)
    assert _index(conn, learner, date(2026, 9, 2)) == 0


def test_sessions_before_the_unit_was_entered_do_not_count(conn, learner) -> None:
    """`entered_at` is the lower bound -- restated by the 2026-08-29 ruling as
    *when this learner first reached this unit*, which is what makes it one."""
    _session(conn, learner, date(2026, 8, 20), focus_done=True)
    assert _index(conn, learner, date(2026, 9, 2)) == 0


def test_the_section_index_restarts_at_zero_on_the_next_unit(conn, learner) -> None:
    """Scoped to the unit. A learner who passes unit 1 starts unit 2 at its
    first section -- which is correct, and is why the day after a pass is a
    screen worth looking at (block 3 has no lesson for unit 2)."""
    _session(conn, learner, date(2026, 9, 1), focus_done=True)
    _session(conn, learner, date(2026, 9, 2), focus_done=True)
    record_unit_entry(conn, learner, 2, now=datetime(2026, 9, 3, 8, tzinfo=timezone.utc))
    assert unit_section_index(conn, learner, 2, local_today=date(2026, 9, 3)) == 0


def test_at_most_one_daily_session_per_date_bounds_the_counter(conn, learner) -> None:
    """The counter is sessions, not days, so *could a learner advance five
    sections in one day?* is a fair question. **No, by construction:**
    `sessions_one_daily_per_user_per_date` (016) is a partial UNIQUE on
    `(user_id, date) WHERE task_type = 'daily'`. Checked rather than assumed --
    the counter would otherwise look unbounded to a later reader."""
    _session(conn, learner, date(2026, 9, 1), focus_done=True)
    with pytest.raises(psycopg.errors.UniqueViolation):
        with conn.transaction():
            _session(conn, learner, date(2026, 9, 1), focus_done=True)
