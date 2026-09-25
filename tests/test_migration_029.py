"""W19 migration 029: `progress_snapshots`, and `sessions.xp` documented as reserved.

Read from `information_schema` / `pg_constraint` on a connection this module
opens itself, never compared against a list derived from the code under test
(CLAUDE.md §3 rule 5).

**THE ASSERTION THIS FILE EXISTS FOR IS AN ABSENCE: the table holds numbers and
a date, and no column that could hold a learner's text** (CLAUDE.md §5).

**RED DEMONSTRATIONS (2026-09-25):** `test_the_table_holds_numbers_and_a_date_only`
went red with `ALTER TABLE progress_snapshots ADD COLUMN note TEXT` applied to
the dev database (reverted); `test_one_row_per_learner_per_day` went red with the
primary key dropped (`ALTER TABLE progress_snapshots DROP CONSTRAINT
progress_snapshots_pkey`, re-added); `test_sessions_xp_says_it_has_no_writer` went
red with `COMMENT ON COLUMN sessions.xp IS NULL` (re-applied from 029).
"""

from __future__ import annotations

import psycopg
import pytest

from core.config import load_settings


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row is not None and int(row[0] or 0) >= 29, (
            "run `python -m core.db migrate` — 029 is not applied to this database"
        )
        yield connection


def test_the_table_holds_numbers_and_a_date_only(conn) -> None:
    rows = conn.execute(
        """
        SELECT column_name, data_type, is_nullable
          FROM information_schema.columns
         WHERE table_name = 'progress_snapshots'
        """
    ).fetchall()
    assert {r[0]: (r[1], r[2]) for r in rows} == {
        "user_id": ("bigint", "NO"),
        "local_date": ("date", "NO"),
        "known_words": ("integer", "NO"),
        "xp": ("integer", "NO"),
        "recorded_at": ("timestamp with time zone", "NO"),
    }


def test_one_row_per_learner_per_day(conn) -> None:
    cols = conn.execute(
        """
        SELECT a.attname
          FROM pg_constraint c
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
         WHERE c.conrelid = 'progress_snapshots'::regclass AND c.contype = 'p'
        """
    ).fetchall()
    assert sorted(r[0] for r in cols) == ["local_date", "user_id"]


def test_the_table_keys_on_users_id_and_cascades(conn) -> None:
    """PRODUCT-PRINCIPLES §2: `users(id)`, never a Telegram id."""
    row = conn.execute(
        """
        SELECT pg_get_constraintdef(oid)
          FROM pg_constraint
         WHERE conrelid = 'progress_snapshots'::regclass AND contype = 'f'
        """
    ).fetchone()
    assert row is not None
    assert row[0] == "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"


def test_neither_number_can_go_negative(conn) -> None:
    defs = [
        r[0]
        for r in conn.execute(
            """
            SELECT pg_get_constraintdef(oid)
              FROM pg_constraint
             WHERE conrelid = 'progress_snapshots'::regclass AND contype = 'c'
            """
        ).fetchall()
    ]
    assert "CHECK ((known_words >= 0))" in defs
    assert "CHECK ((xp >= 0))" in defs


def test_sessions_xp_says_it_has_no_writer(conn) -> None:
    """#349's shape: a column nothing writes says so where a schema reader looks."""
    row = conn.execute(
        "SELECT col_description('sessions'::regclass, attnum) FROM pg_attribute "
        "WHERE attrelid = 'sessions'::regclass AND attname = 'xp'"
    ).fetchone()
    assert row is not None and row[0] is not None
    assert row[0].startswith("RESERVED, NO WRITER.")
