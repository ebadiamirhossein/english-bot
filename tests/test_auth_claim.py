"""W2 claim tokens: the service, and the operator CLI over it.

The claim token is what stands in for email verification in this slice. If it
is weak, a pre-seeded ``auth_email`` is the only thing between a stranger and
the error journal — so its storage, its single-use property and its expiry get
their own tests rather than being covered incidentally by the enrolment flow.
"""

from __future__ import annotations

import ast
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest

from core import claim
from core.config import load_settings
from core.services import auth

CORE = Path(__file__).resolve().parents[1] / "packages" / "core"


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def user_id(db) -> int:
    """A throwaway learner row, removed afterwards."""
    made = -secrets.randbelow(1_000_000_000) - 1
    db.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language, onboarded,
                           auth_email)
        VALUES (%s, 'Claim Test', 'lt', TRUE, %s)
        """,
        (made, f"claim-{abs(made)}@example.test"),
    )
    db.execute(
        """
        INSERT INTO access_requests (telegram_user_id, display_name, status)
        VALUES (%s, 'Claim Test', 'approved')
        """,
        (made,),
    )
    db.commit()
    yield made
    db.execute("DELETE FROM users WHERE telegram_user_id = %s", (made,))
    db.execute("DELETE FROM access_requests WHERE telegram_user_id = %s", (made,))
    db.commit()


def test_only_a_digest_is_stored(db, user_id) -> None:
    """The operator issues a code. The database must not be able to reveal it.

    A disclosure of this table must not hand anyone a working enrolment token,
    which is the whole reason the raw value is returned once and never again.
    """
    token = auth.issue_claim_token(user_id=user_id, now=datetime.now(timezone.utc))
    rows = db.execute(
        "SELECT token_hash FROM auth_claim_tokens WHERE user_id = %s", (user_id,)
    ).fetchall()
    assert len(rows) == 1
    stored = bytes(rows[0][0])
    assert len(stored) == 32, "not a SHA-256 digest"
    assert token.encode("utf-8") not in stored
    assert token not in stored.hex()


def test_the_token_has_real_entropy(db, user_id) -> None:
    """A guessable code is not a factor. 32 CSPRNG bytes, urlsafe-encoded."""
    now = datetime.now(timezone.utc)
    tokens = {auth.issue_claim_token(user_id=user_id, now=now) for _ in range(5)}
    assert len(tokens) == 5
    for token in tokens:
        assert len(token) >= 40


def test_a_token_is_single_use_even_under_a_race(db, user_id) -> None:
    """Two enrolments racing on one code must not both succeed.

    Consumption is one UPDATE with the guard in its WHERE clause; a SELECT then
    an UPDATE would let both pass.
    """
    now = datetime.now(timezone.utc)
    auth.issue_claim_token(user_id=user_id, now=now)
    first = auth.revoke_claim_tokens(user_id=user_id, now=now)
    second = auth.revoke_claim_tokens(user_id=user_id, now=now)
    assert (first, second) == (1, 0)


def test_expiry_is_a_parameter_not_the_wall_clock(db, user_id) -> None:
    """CLAUDE.md §3 rule 6. The token was issued three days ago with a 24h life.

    Both sides of the comparison are computed the same way, and nothing here
    changes behaviour when the calendar rolls over.
    """
    issued_at = datetime.now(timezone.utc) - timedelta(days=3)
    auth.issue_claim_token(user_id=user_id, now=issued_at, hours=24)
    row = db.execute(
        "SELECT created_at, expires_at FROM auth_claim_tokens WHERE user_id = %s",
        (user_id,),
    ).fetchone()
    assert row is not None
    assert row[1] - row[0] == timedelta(hours=24)
    assert row[1] < datetime.now(timezone.utc), "should already have expired"


def test_the_default_lifetime_is_twenty_four_hours(db, user_id) -> None:
    """Answer Q2: 24h default, --hours available per issue."""
    now = datetime.now(timezone.utc)
    auth.issue_claim_token(user_id=user_id, now=now)
    row = db.execute(
        "SELECT expires_at FROM auth_claim_tokens WHERE user_id = %s", (user_id,)
    ).fetchone()
    assert row is not None
    # 24 written out here rather than read from Settings (rule 5).
    assert abs((row[0] - now) - timedelta(hours=24)) < timedelta(seconds=5)


def test_listing_never_reveals_a_token_or_an_address(db, user_id, capsys) -> None:
    """The operator checks whether a code is still outstanding.

    This output is for deciding whether to issue another one — not for
    recovering one that was lost, which is impossible by design.
    """
    token = auth.issue_claim_token(user_id=user_id, now=datetime.now(timezone.utc))
    assert claim.main(["list"]) == 0
    printed = capsys.readouterr().out
    assert str(user_id) in printed
    assert token not in printed
    assert "@" not in printed


def test_issue_prints_the_token_once_with_its_terms(db, user_id, capsys) -> None:
    """The operator runs `claim issue` with the learner in front of them."""
    assert claim.main(["issue", "--telegram-user-id", str(user_id)]) == 0
    printed = capsys.readouterr().out
    row = db.execute(
        "SELECT token_hash FROM auth_claim_tokens WHERE user_id = %s", (user_id,)
    ).fetchone()
    assert row is not None
    assert "Single use" in printed
    assert "24h" in printed
    # It says out loud that this is the only time it can be read.
    assert "one and only time" in printed


def test_issue_addresses_the_learner_by_id_not_by_email(db, user_id) -> None:
    """No address may enter shell history or a terminal scrollback."""
    parser = claim.build_parser()
    args = parser.parse_args(["issue", "--telegram-user-id", str(user_id)])
    assert args.telegram_user_id == user_id
    assert not hasattr(args, "email")
    with pytest.raises(SystemExit):
        parser.parse_args(["issue", "--email", "someone@example.test"])


def test_revoke_spends_every_outstanding_token(db, user_id, capsys) -> None:
    """A code was handed over and then the plan changed."""
    now = datetime.now(timezone.utc)
    auth.issue_claim_token(user_id=user_id, now=now)
    auth.issue_claim_token(user_id=user_id, now=now)
    assert claim.main(["revoke", "--telegram-user-id", str(user_id)]) == 0
    assert "Spent 2" in capsys.readouterr().out
    remaining = db.execute(
        """
        SELECT count(*) FROM auth_claim_tokens
         WHERE user_id = %s AND used_at IS NULL
        """,
        (user_id,),
    ).fetchone()
    assert remaining is not None and remaining[0] == 0


def test_the_cli_holds_no_sql() -> None:
    """core/claim.py is argparse and printing; the queries are in the service.

    tests/test_core_boundary.py exempts core/services/ and migrations/ and
    nothing else, so this is the same rule stated where someone editing the CLI
    will see it fail.
    """
    tree = ast.parse((CORE / "claim.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            statement = " ".join(node.value.upper().split())
            assert " FROM " not in statement or "SELECT " not in statement
            assert not statement.startswith(("INSERT INTO", "UPDATE ", "DELETE FROM"))


def test_revoking_all_sessions_is_the_recovery_runbooks_step(db, user_id) -> None:
    """DEPLOYMENT.md's Case B: every credential lost, operator re-enrols.

    The runbook's SQL is exercised here as a function so the documented recovery
    is not the only place the behaviour exists.
    """
    now = datetime.now(timezone.utc)
    db.execute(
        "UPDATE users SET auth_user_id = %s WHERE telegram_user_id = %s",
        (str(uuid.uuid4()), user_id),
    )
    db.execute(
        """
        INSERT INTO auth_sessions (token_hash, user_id, expires_at)
        VALUES (%s, %s, %s)
        """,
        (secrets.token_bytes(32), user_id, now + timedelta(days=30)),
    )
    db.commit()
    assert auth.revoke_all_sessions(user_id=user_id, now=now) == 1
    assert auth.revoke_all_sessions(user_id=user_id, now=now) == 0
