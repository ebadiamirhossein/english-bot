"""W2 migration 009: the users auth columns, the view recreate, the auth tables.

Every expectation here is read from ``information_schema`` on a connection this
module opens itself. Nothing is compared against a hand-written column list —
a hand-written list is exactly what drifts, and drift is the failure mode
known issue #48 exists to prevent (CLAUDE.md §3 rule 5).
"""

from __future__ import annotations

import psycopg
import pytest

from core.config import load_settings

AUTH_TABLES = (
    "auth_challenges",
    "auth_claim_tokens",
    "auth_credentials",
    "auth_rate_limits",
    "auth_sessions",
)


@pytest.fixture
def conn():
    """A connection of this test's own, not the app's pool."""
    with psycopg.connect(load_settings().database_url) as connection:
        yield connection


def _columns(conn, relation: str) -> list[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT column_name, data_type
          FROM information_schema.columns
         WHERE table_schema = 'public' AND table_name = %s
         ORDER BY ordinal_position
        """,
        (relation,),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def test_migration_009_is_applied(conn) -> None:
    """A guard for everything below: an unmigrated DB passes empty checks."""
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    assert row is not None and int(row[0] or 0) >= 9, (
        "run `python -m core.db migrate` — 009 is not applied to this database"
    )


def test_users_has_the_three_auth_columns(conn) -> None:
    columns = dict(_columns(conn, "users"))
    assert columns["auth_user_id"] == "uuid"
    assert columns["auth_email"] == "text"
    assert columns["l1_pronunciation_seed"] == "jsonb"


def test_the_auth_columns_are_nullable(conn) -> None:
    """A row with neither is a Telegram-era user who has not enrolled."""
    rows = conn.execute(
        """
        SELECT column_name, is_nullable
          FROM information_schema.columns
         WHERE table_schema = 'public' AND table_name = 'users'
           AND column_name IN
               ('auth_user_id', 'auth_email', 'l1_pronunciation_seed')
        """
    ).fetchall()
    assert {r[0]: r[1] for r in rows} == {
        "auth_user_id": "YES",
        "auth_email": "YES",
        "l1_pronunciation_seed": "YES",
    }


def test_both_identifiers_are_unique(conn) -> None:
    rows = conn.execute(
        """
        SELECT tc.constraint_name, kcu.column_name
          FROM information_schema.table_constraints tc
          JOIN information_schema.key_column_usage kcu
            ON kcu.constraint_name = tc.constraint_name
         WHERE tc.table_name = 'users' AND tc.constraint_type = 'UNIQUE'
        """
    ).fetchall()
    unique_columns = {r[1] for r in rows}
    assert {"auth_user_id", "auth_email"} <= unique_columns


def test_a_mixed_case_auth_email_is_refused(conn) -> None:
    """The operator sets this by hand; the database has to catch a capital.

    The service lowercases on write and on lookup, so an address stored with a
    capital letter would be an account nobody could ever sign in to — a silent
    failure discovered on a phone. This makes it a loud one at UPDATE time.
    """
    user_id = _seed_user(conn, name="Case Test")
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "UPDATE users SET auth_email = %s WHERE telegram_user_id = %s",
            ("Mixed.Case@example.test", user_id),
        )
    conn.rollback()


def test_every_auth_table_exists(conn) -> None:
    rows = conn.execute(
        """
        SELECT table_name FROM information_schema.tables
         WHERE table_schema = 'public' AND table_name LIKE 'auth\\_%'
        """
    ).fetchall()
    assert sorted(r[0] for r in rows) == list(AUTH_TABLES)


def test_auth_credentials_stores_what_the_library_actually_reports(conn) -> None:
    """The column names py_webauthn 2.8.0 dictates, pinned.

    The plan predicted `backup_eligible` from memory. The installed library has
    no such field: it reports ``credential_device_type``
    (`single_device`/`multi_device`) and ``credential_backed_up``. The schema
    follows the library, and this asserts the rename actually landed in the DDL
    rather than only in the code that writes to it — an insert naming a column
    that does not exist fails at the first enrolment, not at import.

    Expected set hardcoded, never derived from the migration (rule 5).
    """
    columns = {name for name, _ in _columns(conn, "auth_credentials")}
    assert columns == {
        "credential_id",
        "user_id",
        "public_key",
        "sign_count",
        "transports",
        "aaguid",
        "credential_device_type",
        "backed_up",
        "nickname",
        "created_at",
        "last_used_at",
    }
    assert "backup_eligible" not in columns, (
        "backup_eligible is the name the plan guessed; py_webauthn 2.8.0 does "
        "not report it"
    )


def test_the_rollback_runbook_drops_exactly_what_009_creates(conn) -> None:
    """A table added to 009 but missing from the rollback is a rollback that
    fails at the one moment it is needed.

    Both sides are read independently: the live schema from
    ``information_schema``, the runbook from the markdown. Nothing here parses
    the migration file, so a rename in the DDL that reached neither is still
    caught by the test above.
    """
    import re
    from pathlib import Path

    runbook = (
        Path(__file__).resolve().parents[1] / "docs" / "DEPLOYMENT.md"
    ).read_text(encoding="utf-8")
    match = re.search(
        r"DROP TABLE IF EXISTS ([a-z_,\s]+);", runbook, re.MULTILINE
    )
    assert match, "docs/DEPLOYMENT.md has no 009 rollback DROP TABLE block"
    dropped = {name.strip() for name in match.group(1).split(",")}
    assert dropped == set(AUTH_TABLES)


def test_the_learning_sessions_table_is_untouched(conn) -> None:
    """`sessions` holds learning sessions. The auth table is `auth_sessions`.

    Namespacing was the point; this fails if a later change collapses them.
    """
    assert _columns(conn, "sessions"), "the learning sessions table vanished"
    assert "token_hash" not in dict(_columns(conn, "sessions"))


def test_the_view_column_set_equals_the_table(conn) -> None:
    """Known issue #48, and W2's stated acceptance criterion.

    `approved_onboarded_users` is `SELECT u.*`, which freezes its column list at
    creation. If 009 had added columns without the recreate in the same file,
    six delivery call sites would silently miss them.

    Compared as an ordered sequence, not a set: set equality would pass a view
    whose columns came back in a different order, and every consumer reads
    `u.*` positionally when it reads a whole row.
    """
    assert _columns(conn, "users") == _columns(conn, "approved_onboarded_users")


def test_the_view_carries_the_new_columns(conn) -> None:
    """The specific thing the recreate exists to achieve, stated directly."""
    view_columns = {name for name, _ in _columns(conn, "approved_onboarded_users")}
    assert {"auth_user_id", "auth_email", "l1_pronunciation_seed"} <= view_columns


def test_the_view_still_filters_on_approval_and_onboarding(conn) -> None:
    """Recreating a view is a chance to change its meaning by accident."""
    row = conn.execute(
        "SELECT pg_get_viewdef('approved_onboarded_users'::regclass, true)"
    ).fetchone()
    assert row is not None
    definition = " ".join(row[0].split()).lower()
    assert "onboarded" in definition
    assert "'approved'" in definition
    assert "access_requests" in definition


def _seed_user(conn, *, name: str) -> int:
    """A throwaway users row. Callers roll back."""
    row = conn.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language)
        VALUES (%s, %s, 'fa')
        RETURNING telegram_user_id
        """,
        (-abs(hash(name)) % 1_000_000_000, name),
    ).fetchone()
    assert row is not None
    return int(row[0])
