"""W4b migration 011: identity stops being a Telegram id.

Everything is read from ``information_schema`` / ``pg_constraint`` on a
connection this module opens itself, never compared against a hand-written
column list -- a hand-written list is what drifts (CLAUDE.md §3 rule 5).

The migration's own row-count assertions are not repeated here. They live inside
011 because they must abort the transaction, and a test that re-derived them
from the same code would prove nothing (rule 5 again). What this file proves is
the *shape* 011 leaves behind, and the two behaviours the shape exists for: a
learner with no Telegram account can exist, and the learners who already existed
did not lose their session or their passkey.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from core.config import load_settings
from core.services import auth, identity

# Every child column that pointed at users(telegram_user_id) before 011.
USER_FK_TABLES = {
    "errors": "user_id",
    "chunks": "user_id",
    "book_units": "user_id",
    "sessions": "user_id",
    "streaks": "user_id",
    "interests": "user_id",
    "readings": "user_id",
    "couple_challenges": "winner_user_id",
    "couple_scores": "user_id",
    "calibration_log": "user_id",
    "bot_message_counts": "user_id",
    "shared_content_deliveries": "user_id",
    "auth_credentials": "user_id",
    "auth_sessions": "user_id",
    "auth_claim_tokens": "user_id",
    "auth_challenges": "user_id",
    "user_lexemes": "user_id",
}


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row is not None and int(row[0] or 0) >= 11, (
            "run `python -m core.db migrate` — 011 is not applied to this database"
        )
        try:
            yield connection
        finally:
            connection.rollback()


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


def _constraints(conn, relation: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT pg_get_constraintdef(c.oid)
          FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
         WHERE t.relname = %s
        """,
        (relation,),
    ).fetchall()
    return [r[0] for r in rows]


# ── the shape ────────────────────────────────────────────────────────────────


def test_users_is_keyed_on_a_surrogate_id(conn) -> None:
    assert "PRIMARY KEY (id)" in _constraints(conn, "users")


def test_a_telegram_id_is_now_optional_and_unique(conn) -> None:
    """Nullable so a web learner can exist; unique so it still resolves one."""
    row = conn.execute(
        """
        SELECT is_nullable FROM information_schema.columns
         WHERE table_name = 'users' AND column_name = 'telegram_user_id'
        """
    ).fetchone()
    assert row is not None and row[0] == "YES"
    assert "UNIQUE (telegram_user_id)" in _constraints(conn, "users")


def test_every_row_stays_reachable_by_something(conn) -> None:
    """A learner with neither a Telegram id nor an email could not be found."""
    clauses = " ".join(_constraints(conn, "users"))
    assert "telegram_user_id IS NOT NULL" in clauses
    assert "auth_email IS NOT NULL" in clauses


@pytest.mark.parametrize("table,column", sorted(USER_FK_TABLES.items()))
def test_every_child_points_at_the_surrogate_key(conn, table, column) -> None:
    clauses = _constraints(conn, table)
    assert f"FOREIGN KEY ({column}) REFERENCES users(id)" in " ".join(clauses)


def test_the_one_non_cascading_key_stays_non_cascading(conn) -> None:
    """``couple_challenges.winner_user_id`` has always been NO ACTION.

    It is why ``DELETE FROM users`` errors today instead of quietly taking the
    challenge history with it. Re-adding the seventeen keys uniformly would have
    lost that, silently, which is the only reason this test exists.
    """
    clause = next(
        c for c in _constraints(conn, "couple_challenges") if "winner_user_id" in c
    )
    assert "ON DELETE CASCADE" not in clause


def test_access_requests_kept_its_telegram_column(conn) -> None:
    """A pending request exists before any users row -- 005's whole purpose.

    Its primary key had to move off ``telegram_user_id`` (a PK column cannot be
    made nullable), but the column itself stays: dropping it would have thrown
    away every request from somebody who never finished onboarding.
    """
    names = {n for n, _ in _columns(conn, "access_requests")}
    assert {"id", "user_id", "telegram_user_id"} <= names
    clauses = _constraints(conn, "access_requests")
    assert "PRIMARY KEY (id)" in clauses
    assert "UNIQUE (telegram_user_id)" in clauses
    assert "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE" in clauses


def test_on_conflict_targets_still_exist(conn) -> None:
    """``request_access`` and ``save_onboarding`` both use ON CONFLICT.

    Without the unique constraint 011 added, they would not fail at migration
    time -- they would fail at RUNTIME, on a green deploy, the first time a
    stranger tapped Request access.
    """
    clauses = _constraints(conn, "access_requests")
    assert any(c.startswith("UNIQUE (telegram_user_id)") for c in clauses)


def test_the_view_still_matches_the_table(conn) -> None:
    """#48, restated after a second ALTER TABLE users."""
    assert _columns(conn, "users") == _columns(conn, "approved_onboarded_users")


def test_the_view_joins_on_the_internal_id(conn) -> None:
    """Otherwise a Telegram-less learner is approved and invisible."""
    row = conn.execute(
        "SELECT pg_get_viewdef('approved_onboarded_users'::regclass, true)"
    ).fetchone()
    assert row is not None
    body = " ".join(row[0].split())
    assert "ar.user_id = u.id" in body
    assert "onboarded" in body
    assert "approved" in body


# ── the two behaviours the shape exists for ──────────────────────────────────


def test_a_learner_can_exist_without_telegram(conn) -> None:
    """W4b's acceptance criterion 3, end to end and without a route.

    A user with ``telegram_user_id NULL`` who holds a passkey, a live session
    and a ledger row -- the thing the pre-011 schema made impossible.
    """
    email = f"w4b-{uuid.uuid4().hex[:12]}@example.test"
    user_id = identity.create_web_user(
        email=email, name="Web Learner", native_language="lt"
    )
    try:
        row = conn.execute(
            "SELECT telegram_user_id FROM users WHERE id = %s", (user_id,)
        ).fetchone()
        assert row is not None and row[0] is None

        # Approved, or enrolment would refuse them at begin_registration.
        from core.services.access_control import is_approved

        assert is_approved(user_id)

        # A passkey, a session and a ledger row all attach.
        conn.execute(
            """
            INSERT INTO auth_credentials (credential_id, user_id, public_key,
                                          sign_count)
            VALUES (%s, %s, %s, 0)
            """,
            (secrets.token_bytes(16), user_id, b"pk"),
        )
        conn.execute(
            """
            INSERT INTO auth_sessions (token_hash, user_id, expires_at)
            VALUES (%s, %s, %s)
            """,
            (
                secrets.token_bytes(32),
                user_id,
                datetime.now(timezone.utc) + timedelta(days=30),
            ),
        )
        lex = conn.execute(
            """
            INSERT INTO lexemes (lemma, freq_rank, origin)
            VALUES (%s, 999999, 'seed')
            ON CONFLICT (lemma) DO UPDATE SET lemma = EXCLUDED.lemma
            RETURNING id
            """,
            (f"w4btest{uuid.uuid4().hex[:8]}",),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO user_lexemes (user_id, lexeme_id, state, source,
                                      source_rank)
            VALUES (%s, %s, 'known', 'assumption', 0)
            """,
            (user_id, lex[0]),
        )
        conn.commit()

        # And no Telegram channel at all, which delivery must handle.
        assert identity.telegram_address_for_user(user_id) is None
    finally:
        conn.rollback()
        with psycopg.connect(load_settings().database_url) as cleanup:
            cleanup.execute("DELETE FROM users WHERE id = %s", (user_id,))
            cleanup.commit()


def test_an_existing_session_and_passkey_survive_the_rekey() -> None:
    """W4b's acceptance criterion 11 — nobody re-enrols after the migration.

    The reasoning says they must not have to: ``auth_sessions.token_hash`` and
    ``auth_credentials.credential_id`` are untouched by 011, and
    ``users.auth_user_id`` -- the WebAuthn handle actually stored on the phone --
    is never written by it. So the session join and the credential lookup both
    still resolve.

    That is an "almost certainly", and an "almost certainly" here costs an
    evening of re-enrolling passkeys on two phones, one of them another
    person's. This asserts it instead: the **same** raw cookie and the **same**
    handle still resolve to the same learner under their new ``id``.
    """
    settings = load_settings()
    raw_token = secrets.token_urlsafe(32)
    handle = uuid.uuid4()
    telegram_user_id = -secrets.randbelow(1_000_000_000) - 1
    now = datetime.now(timezone.utc)

    with psycopg.connect(settings.database_url) as db:
        row = db.execute(
            """
            INSERT INTO users (telegram_user_id, name, native_language,
                               onboarded, auth_email, auth_user_id)
            VALUES (%s, 'Survivor', 'fa', TRUE, %s, %s)
            RETURNING id
            """,
            (
                telegram_user_id,
                f"survivor-{abs(telegram_user_id)}@example.test",
                str(handle),
            ),
        ).fetchone()
        user_id = int(row[0])
        db.execute(
            """
            INSERT INTO access_requests (telegram_user_id, user_id,
                                         display_name, status)
            VALUES (%s, %s, 'Survivor', 'approved')
            """,
            (telegram_user_id, user_id),
        )
        db.execute(
            """
            INSERT INTO auth_credentials (credential_id, user_id, public_key,
                                          sign_count)
            VALUES (%s, %s, %s, 0)
            """,
            (b"survivor-cred", user_id, b"pk"),
        )
        db.execute(
            """
            INSERT INTO auth_sessions (token_hash, user_id, expires_at)
            VALUES (%s, %s, %s)
            """,
            (
                hashlib.sha256(raw_token.encode()).digest(),
                user_id,
                now + timedelta(days=30),
            ),
        )
        db.commit()

    try:
        # The cookie the phone is still holding.
        resolved = auth.resolve_session(raw_token=raw_token, now=now)
        assert resolved is not None
        assert resolved.id == user_id
        assert resolved.name == "Survivor"

        # The handle the phone's passkey is bound to still finds the same row,
        # and finds it by `users.id` now.
        with psycopg.connect(settings.database_url) as db:
            row = db.execute(
                """
                SELECT u.id
                  FROM users u
                  INNER JOIN auth_credentials c ON c.user_id = u.id
                 WHERE u.auth_user_id = %s AND c.credential_id = %s
                """,
                (str(handle), b"survivor-cred"),
            ).fetchone()
        assert row is not None and int(row[0]) == user_id

        # And the Telegram id still resolves the same learner.
        assert identity.user_id_for_telegram(telegram_user_id) == user_id
    finally:
        with psycopg.connect(settings.database_url) as db:
            db.execute("DELETE FROM users WHERE id = %s", (user_id,))
            db.execute(
                "DELETE FROM access_requests WHERE telegram_user_id = %s",
                (telegram_user_id,),
            )
            db.commit()


def test_no_orphans_in_any_child_table(conn) -> None:
    """Acceptance criterion 7, asserted against the live database."""
    for table, column in sorted(USER_FK_TABLES.items()):
        row = conn.execute(
            f"""
            SELECT count(*) FROM {table} t
             LEFT JOIN users u ON u.id = t.{column}
             WHERE t.{column} IS NOT NULL AND u.id IS NULL
            """
        ).fetchone()
        assert row is not None and int(row[0]) == 0, f"orphans in {table}"


def test_the_migration_recreates_the_view_in_the_same_file() -> None:
    """#48's standing rule: an ALTER TABLE users pays for a view recreate."""
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[1] / "migrations" / "011_identity.sql"
    ).read_text(encoding="utf-8")
    assert "ALTER TABLE users ADD COLUMN id" in sql
    assert "CREATE OR REPLACE VIEW approved_onboarded_users" in sql


def test_the_migration_deletes_nothing() -> None:
    """The error journal is the product. 011 may not remove a row or a column.

    Stated as a test rather than a comment because it is the property the whole
    slice was designed around: no DELETE, no DROP TABLE, no DROP COLUMN, so the
    ON DELETE CASCADE on sixteen keys is never armed while they are in flight.
    """
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[1] / "migrations" / "011_identity.sql"
    ).read_text(encoding="utf-8")
    body = "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    ).upper()
    assert "DELETE FROM" not in body
    assert "DROP TABLE" not in body
    assert "DROP COLUMN" not in body
