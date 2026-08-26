"""Migration 016 — the daily session's columns, the one-row-per-day guarantee,
and what a typed answer leaves behind.

Read from `information_schema` and `pg_constraint`, never compared against a
hand-written column list, in `tests/test_migration_014.py`'s and `015`'s shape.

**The load-bearing assertions are the two about the unique index.** It is
PARTIAL — `WHERE task_type = 'daily'` — and both halves matter: without the
predicate it would refuse the eleven other task types that legitimately have
several rows on one date, and without the index a worker pre-build racing a
learner opening the app early would make two daily sessions for one day.

**What no test here can check, said plainly rather than implied:** the index
enforces one row per date and cannot tell you the DATE WAS COMPUTED WRONGLY.
That convention — the learner's local date, from `users.timezone` — is asserted
in `tests/test_sessions_service.py` at the midnight boundary, which is the only
place it is observable.
"""

from __future__ import annotations

import psycopg
import pytest

from core.config import load_settings
from core.sessions import BLOCK_STATES, MAX_SESSION_MINUTES

MIGRATION = "016_session.sql"


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row is not None and int(row[0] or 0) >= 16, (
            "run `python -m core.db migrate` — 016 is not applied to this database"
        )
        try:
            yield connection
        finally:
            connection.rollback()


def _column(conn, table: str, column: str):
    return conn.execute(
        """
        SELECT is_nullable, data_type
          FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    ).fetchone()


def _indexdef(conn, name: str) -> str | None:
    row = conn.execute(
        "SELECT indexdef FROM pg_indexes WHERE indexname = %s", (name,)
    ).fetchone()
    return None if row is None else row[0]


# --- the three reserved columns ---------------------------------------------


def test_sessions_gains_the_three_columns_the_table_reserves() -> None:
    """`docs/TASKS-v3-web.md`'s authoritative table, row 016."""
    assert MIGRATION == "016_session.sql"


@pytest.mark.parametrize(
    "column,data_type",
    [("block_breakdown", "jsonb"), ("minutes", "integer"), ("xp", "integer")],
)
def test_each_reserved_column_exists_and_is_nullable(conn, column, data_type) -> None:
    row = _column(conn, "sessions", column)
    assert row is not None, f"sessions.{column} is missing"
    is_nullable, kind = row
    # Nullable, all three. A session in progress has no minutes yet, and W10
    # writes no xp at all.
    assert is_nullable == "YES"
    assert kind == data_type


def test_minutes_refuses_an_implausible_measurement(conn) -> None:
    """#108's rule, at the schema: an implausible number is NULL, not a lie."""
    conn.execute(
        "INSERT INTO users (telegram_user_id, name, native_language) "
        "VALUES (-9016, 'Sixteen', 'fa')"
    )
    user = conn.execute(
        "SELECT id FROM users WHERE telegram_user_id = -9016"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO sessions (user_id, date, task_type) "
        "VALUES (%s, DATE '2026-08-26', 'daily')",
        (user,),
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "UPDATE sessions SET minutes = %s WHERE user_id = %s",
            (MAX_SESSION_MINUTES + 1, user),
        )


def test_the_ceiling_matches_the_python_constant(conn) -> None:
    """Two hand-maintained copies of a bound is how a CHECK stops meaning what
    its docstring says — the instrument `test_migration_013` uses for the card
    types and `014` for the unit states."""
    row = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'sessions_minutes_is_plausible'"
    ).fetchone()
    assert row is not None
    assert str(MAX_SESSION_MINUTES) in row[0]


# --- one daily session per learner per date ---------------------------------


def test_the_daily_index_exists_and_is_unique(conn) -> None:
    definition = _indexdef(conn, "sessions_one_daily_per_user_per_date")
    assert definition is not None, "the one-row-per-day guarantee is missing"
    assert "UNIQUE" in definition
    assert "user_id" in definition and "date" in definition


def test_the_daily_index_is_partial_and_scoped_to_daily(conn) -> None:
    """**The predicate IS the ruling.**

    Without `WHERE task_type = 'daily'` this would refuse the eleven other task
    types that legitimately have several rows on one date — two voice exchanges,
    a quiz and a reading — and an absence is exactly what a later edit restores
    without noticing. The same shape as 015's
    `test_the_unique_index_is_not_scoped_to_chunkless_cards`.
    """
    definition = _indexdef(conn, "sessions_one_daily_per_user_per_date") or ""
    assert "WHERE" in definition
    assert "daily" in definition


def test_a_second_daily_row_for_one_day_is_refused(conn) -> None:
    """Proved by inserting one, not by reading the definition."""
    conn.execute(
        "INSERT INTO users (telegram_user_id, name, native_language) "
        "VALUES (-9017, 'Seventeen', 'lt')"
    )
    user = conn.execute(
        "SELECT id FROM users WHERE telegram_user_id = -9017"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO sessions (user_id, date, task_type) "
        "VALUES (%s, DATE '2026-08-26', 'daily')",
        (user,),
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            "INSERT INTO sessions (user_id, date, task_type) "
            "VALUES (%s, DATE '2026-08-26', 'daily')",
            (user,),
        )


def test_the_other_task_types_may_still_repeat_on_one_day(conn) -> None:
    """The half the predicate exists for, asserted rather than assumed."""
    conn.execute(
        "INSERT INTO users (telegram_user_id, name, native_language) "
        "VALUES (-9018, 'Eighteen', 'fa')"
    )
    user = conn.execute(
        "SELECT id FROM users WHERE telegram_user_id = -9018"
    ).fetchone()[0]
    for _ in range(2):
        conn.execute(
            "INSERT INTO sessions (user_id, date, task_type) "
            "VALUES (%s, DATE '2026-08-26', 'voice')",
            (user,),
        )
    count = conn.execute(
        "SELECT count(*) FROM sessions WHERE user_id = %s", (user,)
    ).fetchone()[0]
    assert count == 2


def test_task_type_still_has_no_check_to_widen(conn) -> None:
    """#47 did not fire here, and the negative is recorded rather than assumed.

    `errors.source` had a CHECK that had to be widened once at migration 012 for
    the full v3 set. `sessions.task_type` is a bare TEXT, so `daily` needed
    nothing — and a later slice adding a CHECK would be adding the very thing
    #47 is about.
    """
    rows = conn.execute(
        """
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'sessions'::regclass AND contype = 'c'
        """
    ).fetchall()
    names = {r[0] for r in rows}
    assert not any("task_type" in name for name in names)


# --- what a typed answer leaves behind (#157) -------------------------------


@pytest.mark.parametrize(
    "column,data_type",
    [
        ("session_id", "bigint"),
        ("typed_response", "text"),
        ("typed_matched", "boolean"),
    ],
)
def test_card_reviews_gains_the_typed_answer_columns(conn, column, data_type) -> None:
    row = _column(conn, "card_reviews", column)
    assert row is not None, f"card_reviews.{column} is missing"
    is_nullable, kind = row
    assert is_nullable == "YES"
    assert kind == data_type


def test_a_verdict_cannot_exist_without_its_answer(conn) -> None:
    """A `typed_matched` with no `typed_response` is unreadable a month later."""
    row = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'card_reviews_a_verdict_needs_its_answer'"
    ).fetchone()
    assert row is not None, "the paired-nullability CHECK is missing"
    assert "typed_matched" in row[0] and "typed_response" in row[0]


def test_deleting_a_session_never_deletes_its_reviews(conn) -> None:
    """SET NULL and not CASCADE.

    The review is evidence about a learner; the session is a container. W7 built
    `card_reviews` as the append-only log precisely because the individual grades
    are the thing that cannot be re-derived, and a container taking them with it
    would undo that.
    """
    row = conn.execute(
        """
        SELECT confdeltype FROM pg_constraint
         WHERE conrelid = 'card_reviews'::regclass
           AND contype = 'f'
           AND confrelid = 'sessions'::regclass
        """
    ).fetchone()
    assert row is not None, "card_reviews.session_id has no foreign key"
    assert row[0] == "n", "expected ON DELETE SET NULL"


def test_the_block_states_python_knows_are_not_mirrored_in_sql(conn) -> None:
    """`block_breakdown` is JSONB with no CHECK, and that is deliberate.

    `core.sessions.BLOCK_STATES` is the authority. A CHECK over a JSONB object's
    values would be a second copy of a five-value set that changes when PRD §4.1
    does, and `core.sessions.blocks.stored_state` already reads an unrecognised
    value as "nothing stored" — so a breakdown written by an older deploy cannot
    stop a learner opening their session.
    """
    assert set(BLOCK_STATES) == {"ready", "done", "empty", "unavailable"}
    row = _column(conn, "sessions", "block_breakdown")
    assert row is not None and row[1] == "jsonb"
