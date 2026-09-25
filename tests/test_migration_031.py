"""W20 migration 031: `push_subscriptions` and `push_deliveries`.

Read from `information_schema` / `pg_constraint` on a connection this module
opens itself, never compared against a list derived from the code under test
(CLAUDE.md §3 rule 5).

**THE ASSERTION THIS FILE EXISTS FOR IS AN ABSENCE: neither table has a column
that could hold a learner's text or a message body** (CLAUDE.md §5).

**RED DEMONSTRATIONS (2026-09-25):** `test_no_column_holds_a_message` went red
with `ALTER TABLE push_deliveries ADD COLUMN body TEXT` applied to the dev
database (dropped again); `test_one_decision_per_learner_per_day_per_kind` went
red with the primary key dropped (`ALTER TABLE push_deliveries DROP CONSTRAINT
push_deliveries_pkey`, re-added); `test_a_malformed_key_is_refused_by_the_table`
went red with `push_subscriptions_p256dh_check` dropped (re-added from 031).
"""

from __future__ import annotations

import psycopg
import pytest

from core.config import load_settings


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row is not None and int(row[0] or 0) >= 31, (
            "run `python -m core.db migrate` — 031 is not applied to this database"
        )
        yield connection


def _columns(conn, table):
    return {
        r[0]: (r[1], r[2])
        for r in conn.execute(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name = %s",
            (table,),
        ).fetchall()
    }


def test_no_column_holds_a_message(conn) -> None:
    assert _columns(conn, "push_subscriptions") == {
        "id": ("bigint", "NO"),
        "user_id": ("bigint", "NO"),
        "endpoint": ("text", "NO"),
        "p256dh": ("text", "NO"),
        "auth": ("text", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
    }
    assert _columns(conn, "push_deliveries") == {
        "user_id": ("bigint", "NO"),
        "local_date": ("date", "NO"),
        "kind": ("text", "NO"),
        "outcome": ("text", "NO"),
        "decided_at": ("timestamp with time zone", "NO"),
    }


def test_one_decision_per_learner_per_day_per_kind(conn) -> None:
    cols = conn.execute(
        """
        SELECT a.attname
          FROM pg_constraint c
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
         WHERE c.conrelid = 'push_deliveries'::regclass AND c.contype = 'p'
        """
    ).fetchall()
    assert sorted(r[0] for r in cols) == ["kind", "local_date", "user_id"]


def test_both_tables_key_on_users_id_and_cascade(conn) -> None:
    """PRODUCT-PRINCIPLES §2: `users(id)`, never a Telegram id."""
    for table in ("push_subscriptions", "push_deliveries"):
        row = conn.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = %s::regclass AND contype = 'f'",
            (table,),
        ).fetchone()
        assert row[0] == "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE", table


def test_one_browser_is_one_row(conn) -> None:
    row = conn.execute(
        "SELECT count(*) FROM pg_constraint WHERE conrelid = 'push_subscriptions'::regclass "
        "AND contype = 'u' AND pg_get_constraintdef(oid) = 'UNIQUE (endpoint)'"
    ).fetchone()
    assert row[0] == 1


def test_a_malformed_key_is_refused_by_the_table(conn) -> None:
    """Rolled back in `finally`: the red run (CHECK dropped) inserted the row,
    and the fixture's clean exit committed it — which then blocked re-adding
    the CHECK. A failing run must leave nothing behind."""
    uid = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0]
    try:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) "
                "VALUES (%s, 'https://push.example.test/m', 'short', %s)",
                (uid, "A" * 22),
            )
    finally:
        conn.rollback()


def test_the_outcomes_are_the_documented_nine(conn) -> None:
    row = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'push_deliveries'::regclass AND conname = 'push_deliveries_outcome_check'"
    ).fetchone()
    for outcome in ("sending", "sent", "failed", "practised", "ceiling",
                    "bot_ladder", "no_subscription", "no_channel", "late"):
        assert f"'{outcome}'" in row[0]
    assert row[0].count("'::text") == 9
