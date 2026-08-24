"""W2 passkey auth, exercised through the real ASGI transport.

CLAUDE.md §3 rule 1 — v2 shipped 161 green tests over a dead feature because
every one of them called a handler directly. Nothing here calls a route
function; every request goes through ``httpx.ASGITransport`` into the app
``uvicorn apps.api.main:app`` serves.

Two other rules shape this file:

* **Rule 5** — no expected value is computed by the code under test. The
  authenticator is ``tests/support/softauth.py``, which imports nothing from
  ``core.passkeys``; cookie attributes are hardcoded here rather than read from
  ``Settings``; the 30-day figure is written out as ``30 * 86400``.
* **Rule 6** — no test depends on the wall clock. Every service function takes
  an explicit ``now``, so "31 days later" is a parameter, never a sleep and
  never a frozen global.

Every test's docstring names the user action it exercises (rule 4).
"""

from __future__ import annotations

import ast
import asyncio
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import psycopg
import pytest
from fastapi import FastAPI

from apps.api.deps import SESSION_COOKIE_SECURE
from apps.api.main import create_app
from core.config import load_settings
from core.services import auth
from tests.support.softauth import SoftAuthenticator

RP_ID = "foundgrant.com"
ORIGIN = "https://app.foundgrant.com"
API_DIR = Path(__file__).resolve().parents[1] / "apps" / "api"

# Hardcoded, not read from Settings (rule 5): a cookie test that asks the
# session module what the expiry should be proves only that it agrees with
# itself.
EXPECTED_MAX_AGE = 30 * 86400

# A fixed instant in the past. Hardcoded rather than `now - timedelta` so that
# nothing in an expiry test moves when the calendar does (rule 6) — the failure
# `test_vocabulary_due_and_anki` shipped, where a test began failing on a date
# boundary rather than on a code change.
EXPIRED_AT = datetime(2020, 1, 1, tzinfo=timezone.utc)


# --- fixtures -----------------------------------------------------------------


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the variables the way they are really set (rule 3).

    The rate-limit salt is unique per test, which gives every test its own
    bucket keys. Without that, the *global* ceiling would be shared across the
    whole file and later tests would 429 on work earlier tests did — and it
    doubles as proof that the salt actually reaches the bucket key.
    """
    monkeypatch.setenv("WEBAUTHN_RP_ID", RP_ID)
    monkeypatch.setenv("WEBAUTHN_ORIGIN", ORIGIN)
    monkeypatch.setenv("WEBAUTHN_RP_NAME", "Everyday English")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SALT", secrets.token_hex(16))


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def db():
    """A connection of this test's own, never the app's pool."""
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


class Learner:
    """A seeded user row plus the bits a test needs to drive it."""

    def __init__(self, user_id: int, email: str) -> None:
        self.user_id = user_id
        self.email = email


def _make_learner(db, *, status: str = "approved", enrolled: bool = False) -> Learner:
    """Insert a throwaway learner. Negative ids keep them out of real data.

    Since W4b the Telegram id and the internal id are different numbers: the
    first is invented here, the second is assigned by the identity column and
    read back. Nothing may assume they are equal -- that assumption is exactly
    what this slice removed.
    """
    telegram_user_id = -secrets.randbelow(1_000_000_000) - 1
    email = f"w2-test-{abs(telegram_user_id)}@example.test"
    row = db.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language, onboarded,
                           auth_email, auth_user_id)
        VALUES (%s, %s, 'fa', TRUE, %s, %s)
        RETURNING id
        """,
        (
            telegram_user_id,
            "Test Learner",
            email,
            str(uuid.uuid4()) if enrolled else None,
        ),
    ).fetchone()
    user_id = int(row[0])
    db.execute(
        """
        INSERT INTO access_requests (telegram_user_id, user_id, display_name,
                                     status)
        VALUES (%s, %s, %s, %s)
        """,
        (telegram_user_id, user_id, "Test Learner", status),
    )
    db.commit()
    return Learner(user_id, email)


@pytest.fixture
def learner(db):
    """An approved, onboarded, not-yet-enrolled learner. Removed afterwards."""
    made = _make_learner(db)
    yield made
    db.execute(
        "DELETE FROM users WHERE id = %s", (made.user_id,)
    )
    db.execute(
        "DELETE FROM access_requests WHERE user_id = %s", (made.user_id,)
    )
    db.commit()


@pytest.fixture
def cleanup(db):
    """Remove any learner a test made for itself."""
    made: list[int] = []
    yield made
    for user_id in made:
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.execute(
            "DELETE FROM access_requests WHERE user_id = %s", (user_id,)
        )
    db.commit()


def request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    client: tuple[str, int] = ("127.0.0.1", 51234),
) -> httpx.Response:
    """One request through the ASGI transport, synchronously.

    ``client`` is threaded through so the rate-limit tests can present distinct
    addresses — the thing that separates the per-client bucket from the global
    one.
    """

    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=client)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as http:
            return await http.request(
                method, path, json=json_body, headers=headers or {}
            )

    return asyncio.run(_go())


def _challenge_of(response: httpx.Response) -> bytes:
    """The challenge out of an options response, decoded independently."""
    import base64

    raw = response.json()["challenge"]
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def _handle_of(db, user_id: int) -> bytes:
    row = db.execute(
        "SELECT auth_user_id FROM users WHERE id = %s", (user_id,)
    ).fetchone()
    assert row is not None and row[0] is not None
    return uuid.UUID(str(row[0])).bytes


def _session_cookie(response: httpx.Response) -> str:
    assert SESSION_COOKIE_SECURE in response.cookies, "no session cookie was set"
    return response.cookies[SESSION_COOKIE_SECURE]


def enrol(app, db, learner: Learner) -> tuple[SoftAuthenticator, str]:
    """Drive a full enrolment. Returns the authenticator and the session cookie.

    The user action: the learner opens /enrol, types the address and the code
    the operator handed them, and confirms with Face ID.
    """
    token = auth.issue_claim_token(
        user_id=learner.user_id, now=datetime.now(timezone.utc)
    )
    begin = request(
        app,
        "POST",
        "/auth/register/begin",
        json_body={"email": learner.email, "claim_token": token},
    )
    assert begin.status_code == 200, begin.text
    device = SoftAuthenticator()
    credential = device.register(
        challenge=_challenge_of(begin), origin=ORIGIN, rp_id=RP_ID
    )
    finish = request(
        app,
        "POST",
        "/auth/register/finish",
        json_body={"credential": credential, "claim_token": token},
    )
    assert finish.status_code == 200, finish.text
    return device, _session_cookie(finish)


def sign_in(app, db, learner: Learner, device: SoftAuthenticator) -> httpx.Response:
    """Drive a full sign-in. The user action: tapping Sign in on the phone."""
    begin = request(app, "POST", "/auth/login/begin")
    assert begin.status_code == 200, begin.text
    assertion = device.authenticate(
        challenge=_challenge_of(begin),
        origin=ORIGIN,
        rp_id=RP_ID,
        user_handle=_handle_of(db, learner.user_id),
    )
    return request(
        app, "POST", "/auth/login/finish", json_body={"credential": assertion}
    )


# --- the two ceremonies -------------------------------------------------------


def test_registration_options_are_discoverable_and_verified(app, learner) -> None:
    """The learner opens /enrol with a valid code and the browser is asked
    for a resident, user-verifying credential."""
    token = auth.issue_claim_token(
        user_id=learner.user_id, now=datetime.now(timezone.utc)
    )
    response = request(
        app,
        "POST",
        "/auth/register/begin",
        json_body={"email": learner.email, "claim_token": token},
    )
    assert response.status_code == 200
    options = response.json()
    assert options["rp"]["id"] == RP_ID, "RP ID must be the registrable domain"
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert options["authenticatorSelection"]["userVerification"] == "required"
    assert options["attestation"] == "none"
    # The handle is opaque: not the telegram id, not the email.
    assert options["user"]["id"] not in (str(learner.user_id), learner.email)


def test_a_full_enrolment_binds_the_account_and_starts_a_session(
    app, db, learner
) -> None:
    """The learner completes /enrol; the account is claimed and they are in."""
    _, cookie = enrol(app, db, learner)
    row = db.execute(
        "SELECT auth_user_id FROM users WHERE id = %s",
        (learner.user_id,),
    ).fetchone()
    assert row is not None and row[0] is not None, "auth_user_id was not bound"
    credentials = db.execute(
        "SELECT count(*) FROM auth_credentials WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()
    assert credentials is not None and credentials[0] == 1
    me = request(
        app, "GET", "/health/auth", cookies={SESSION_COOKIE_SECURE: cookie}
    )
    assert me.json()["user_id"] == learner.user_id


def test_a_full_sign_in_works_without_typing_an_identifier(app, db, learner) -> None:
    """The learner taps Sign in; the browser offers the passkey and Face ID
    succeeds. No email is typed anywhere in this flow."""
    device, _ = enrol(app, db, learner)
    response = sign_in(app, db, learner, device)
    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == learner.user_id
    assert _session_cookie(response)


def test_the_sign_count_is_written_back(app, db, learner) -> None:
    """Each sign-in advances the authenticator's counter; the row follows."""
    device, _ = enrol(app, db, learner)
    sign_in(app, db, learner, device)
    row = db.execute(
        "SELECT sign_count FROM auth_credentials WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()
    assert row is not None and int(row[0]) == 1


def test_login_begin_reveals_nothing_about_any_user(app) -> None:
    """An anonymous visitor hits the sign-in screen: the options must not name
    a credential, or the route becomes an enumeration oracle."""
    response = request(app, "POST", "/auth/login/begin")
    assert response.status_code == 200
    assert response.json()["allowCredentials"] == []
    assert response.json()["rpId"] == RP_ID


# --- rejection paths ----------------------------------------------------------


def test_an_unknown_email_is_refused_identically_to_a_missing_token(
    app, learner
) -> None:
    """Someone guesses an address. The answer must not tell them whether it
    exists — cases 1 and 2, asserted against each other."""
    unknown = request(
        app,
        "POST",
        "/auth/register/begin",
        json_body={"email": "nobody@example.test", "claim_token": "x" * 20},
    )
    no_token = request(
        app,
        "POST",
        "/auth/register/begin",
        json_body={"email": learner.email, "claim_token": "x" * 20},
    )
    assert unknown.status_code == no_token.status_code == 400
    assert unknown.text == no_token.text


def test_a_used_claim_token_is_refused(app, db, learner) -> None:
    """The code was already spent by a successful enrolment; a second attempt
    with the same code must fail."""
    now = datetime.now(timezone.utc)
    token = auth.issue_claim_token(user_id=learner.user_id, now=now)
    auth.revoke_claim_tokens(user_id=learner.user_id, now=now)
    response = request(
        app,
        "POST",
        "/auth/register/begin",
        json_body={"email": learner.email, "claim_token": token},
    )
    assert response.status_code == 400


def test_an_expired_claim_token_is_refused(app, learner) -> None:
    """The operator issued a code yesterday. Time is a parameter, not a sleep
    and not the wall clock (rule 6)."""
    issued_at = datetime.now(timezone.utc) - timedelta(days=3)
    token = auth.issue_claim_token(
        user_id=learner.user_id, now=issued_at, hours=24
    )
    response = request(
        app,
        "POST",
        "/auth/register/begin",
        json_body={"email": learner.email, "claim_token": token},
    )
    assert response.status_code == 400


def test_an_already_enrolled_account_cannot_be_claimed_again(
    app, db, cleanup
) -> None:
    """Someone with a valid code tries to claim an account that is already in
    use — the second claim must not produce a credential."""
    enrolled = _make_learner(db, enrolled=True)
    cleanup.append(enrolled.user_id)
    token = auth.issue_claim_token(
        user_id=enrolled.user_id, now=datetime.now(timezone.utc)
    )
    response = request(
        app,
        "POST",
        "/auth/register/begin",
        json_body={"email": enrolled.email, "claim_token": token},
    )
    assert response.status_code == 400


def test_a_revoked_user_cannot_enrol(app, db, cleanup) -> None:
    """The gate that only existed at sign-in in the first draft of the plan.

    A revoked learner with a valid code must be turned away *before* a
    credential is written and the single-use token burned — otherwise the
    failure surfaces at their first sign-in, with state already left behind.
    """
    revoked = _make_learner(db, status="revoked")
    cleanup.append(revoked.user_id)
    token = auth.issue_claim_token(
        user_id=revoked.user_id, now=datetime.now(timezone.utc)
    )
    response = request(
        app,
        "POST",
        "/auth/register/begin",
        json_body={"email": revoked.email, "claim_token": token},
    )
    assert response.status_code == 400
    credentials = db.execute(
        "SELECT count(*) FROM auth_credentials WHERE user_id = %s",
        (revoked.user_id,),
    ).fetchone()
    assert credentials is not None and credentials[0] == 0
    spent = db.execute(
        "SELECT used_at FROM auth_claim_tokens WHERE user_id = %s",
        (revoked.user_id,),
    ).fetchone()
    assert spent is not None and spent[0] is None, "the token was burned anyway"


def test_a_never_approved_user_cannot_enrol(app, db, cleanup) -> None:
    """A pending access request is not an account yet."""
    pending = _make_learner(db, status="pending")
    cleanup.append(pending.user_id)
    token = auth.issue_claim_token(
        user_id=pending.user_id, now=datetime.now(timezone.utc)
    )
    response = request(
        app,
        "POST",
        "/auth/register/begin",
        json_body={"email": pending.email, "claim_token": token},
    )
    assert response.status_code == 400


def test_a_sign_count_regression_is_refused(app, db, learner) -> None:
    """A cloned authenticator replays an old counter. Hard failure, no session."""
    device, _ = enrol(app, db, learner)
    sign_in(app, db, learner, device)  # counter is now 1

    begin = request(app, "POST", "/auth/login/begin")
    replayed = device.authenticate(
        challenge=_challenge_of(begin),
        origin=ORIGIN,
        rp_id=RP_ID,
        user_handle=_handle_of(db, learner.user_id),
        sign_count=1,  # not greater than the stored 1
    )
    response = request(
        app, "POST", "/auth/login/finish", json_body={"credential": replayed}
    )
    assert response.status_code == 401
    assert SESSION_COOKIE_SECURE not in response.cookies


def test_a_zero_sign_count_is_not_a_regression(app, db, learner) -> None:
    """Apple passkeys always report 0. If 0-then-0 were treated as a
    regression, both learners would be locked out on day one."""
    device, _ = enrol(app, db, learner)
    begin = request(app, "POST", "/auth/login/begin")
    assertion = device.authenticate(
        challenge=_challenge_of(begin),
        origin=ORIGIN,
        rp_id=RP_ID,
        user_handle=_handle_of(db, learner.user_id),
        sign_count=0,
    )
    response = request(
        app, "POST", "/auth/login/finish", json_body={"credential": assertion}
    )
    assert response.status_code == 200, response.text


def test_a_tampered_assertion_is_refused(app, db, learner) -> None:
    """One bit of the signature is flipped in transit."""
    device, _ = enrol(app, db, learner)
    begin = request(app, "POST", "/auth/login/begin")
    assertion = device.authenticate(
        challenge=_challenge_of(begin),
        origin=ORIGIN,
        rp_id=RP_ID,
        user_handle=_handle_of(db, learner.user_id),
        tamper_signature=True,
    )
    response = request(
        app, "POST", "/auth/login/finish", json_body={"credential": assertion}
    )
    assert response.status_code == 401


def test_a_replayed_challenge_is_refused(app, db, learner) -> None:
    """A captured assertion is submitted a second time."""
    device, _ = enrol(app, db, learner)
    begin = request(app, "POST", "/auth/login/begin")
    assertion = device.authenticate(
        challenge=_challenge_of(begin),
        origin=ORIGIN,
        rp_id=RP_ID,
        user_handle=_handle_of(db, learner.user_id),
    )
    first = request(
        app, "POST", "/auth/login/finish", json_body={"credential": assertion}
    )
    assert first.status_code == 200
    second = request(
        app, "POST", "/auth/login/finish", json_body={"credential": assertion}
    )
    assert second.status_code == 401, "a challenge must be single-use"


def test_a_challenge_is_spent_even_when_verification_fails(
    app, db, learner
) -> None:
    """A bad response must still burn its challenge.

    Otherwise a failed attempt leaves the challenge live for the rest of its
    five minutes and an attacker gets unlimited tries against one nonce. This
    is why the consume commits before verification rather than sharing its
    transaction.
    """
    device, _ = enrol(app, db, learner)
    begin = request(app, "POST", "/auth/login/begin")
    challenge = _challenge_of(begin)
    handle = _handle_of(db, learner.user_id)

    bad = device.authenticate(
        challenge=challenge,
        origin=ORIGIN,
        rp_id=RP_ID,
        user_handle=handle,
        tamper_signature=True,
    )
    assert (
        request(app, "POST", "/auth/login/finish", json_body={"credential": bad})
    ).status_code == 401

    good = device.authenticate(
        challenge=challenge, origin=ORIGIN, rp_id=RP_ID, user_handle=handle
    )
    retried = request(
        app, "POST", "/auth/login/finish", json_body={"credential": good}
    )
    assert retried.status_code == 401, "the challenge survived a failed attempt"


def test_a_wrong_origin_is_refused(app, db, learner) -> None:
    """A phishing page on another domain relays a real assertion."""
    device, _ = enrol(app, db, learner)
    begin = request(app, "POST", "/auth/login/begin")
    assertion = device.authenticate(
        challenge=_challenge_of(begin),
        origin="https://evil.example",
        rp_id=RP_ID,
        user_handle=_handle_of(db, learner.user_id),
    )
    response = request(
        app, "POST", "/auth/login/finish", json_body={"credential": assertion}
    )
    assert response.status_code == 401


def test_a_wrong_rp_id_is_refused(app, db, learner) -> None:
    """The RP ID hash in the authenticator data names a different domain."""
    device, _ = enrol(app, db, learner)
    begin = request(app, "POST", "/auth/login/begin")
    assertion = device.authenticate(
        challenge=_challenge_of(begin),
        origin=ORIGIN,
        rp_id="evil.example",
        user_handle=_handle_of(db, learner.user_id),
    )
    response = request(
        app, "POST", "/auth/login/finish", json_body={"credential": assertion}
    )
    assert response.status_code == 401


def test_an_assertion_without_a_user_handle_is_refused(app, db, learner) -> None:
    """A discoverable credential always carries one; its absence means the
    authenticator did something this app does not support."""
    device, _ = enrol(app, db, learner)
    begin = request(app, "POST", "/auth/login/begin")
    assertion = device.authenticate(
        challenge=_challenge_of(begin),
        origin=ORIGIN,
        rp_id=RP_ID,
        user_handle=None,
    )
    response = request(
        app, "POST", "/auth/login/finish", json_body={"credential": assertion}
    )
    assert response.status_code == 401


# --- sessions -----------------------------------------------------------------


def test_the_session_cookie_carries_every_attribute(app, db, learner) -> None:
    """The failure this catches is invisible on localhost: a cookie that is
    set but never sent back from a phone.

    Values are hardcoded here, never read from Settings (rule 5).
    """
    token = auth.issue_claim_token(
        user_id=learner.user_id, now=datetime.now(timezone.utc)
    )
    begin = request(
        app,
        "POST",
        "/auth/register/begin",
        json_body={"email": learner.email, "claim_token": token},
    )
    device = SoftAuthenticator()
    credential = device.register(
        challenge=_challenge_of(begin), origin=ORIGIN, rp_id=RP_ID
    )
    finish = request(
        app,
        "POST",
        "/auth/register/finish",
        json_body={"credential": credential, "claim_token": token},
    )
    header = finish.headers["set-cookie"]
    assert header.startswith(f"{SESSION_COOKIE_SECURE}=")
    lowered = header.lower()
    assert "httponly" in lowered
    assert "secure" in lowered
    assert "samesite=lax" in lowered
    assert "path=/" in lowered
    assert f"max-age={EXPECTED_MAX_AGE}" in lowered
    # __Host- requires the absence of Domain; a Domain here would hand the
    # session to the Vercel edge and every sibling subdomain.
    assert "domain=" not in lowered


def test_no_cookie_means_no_session(app) -> None:
    """An anonymous visitor gets an explicit null, not a 401 — the frontend
    guard distinguishes the two by body, not by status."""
    response = request(app, "GET", "/health/auth")
    assert response.status_code == 200
    assert response.json() is None


def test_an_expired_session_does_not_resolve(app, db, learner) -> None:
    """The learner comes back after a month away. Expiry is written directly,
    never waited for (rule 6)."""
    _, cookie = enrol(app, db, learner)
    db.execute(
        """
        UPDATE auth_sessions SET expires_at = %s WHERE user_id = %s
        """,
        (datetime.now(timezone.utc) - timedelta(days=1), learner.user_id),
    )
    db.commit()
    response = request(
        app, "GET", "/health/auth", cookies={SESSION_COOKIE_SECURE: cookie}
    )
    assert response.json() is None


def test_an_expired_session_is_refused_by_a_gated_route(app, db, learner) -> None:
    """The learner comes back after a month and opens a page that needs a session.

    Deliberately a *different code path* from
    ``test_listing_passkeys_needs_a_session``, which is why both exist:

    * **no cookie** — ``get_current_user`` returns ``None`` before
      ``resolve_session`` is ever called;
    * **expired cookie** — ``resolve_session`` runs, finds a real row for a real
      user, and has to reject it on ``expires_at``.

    Without this, the slice that introduces session expiry ships without a test
    that expiry is enforced where enforcement actually matters.

    The expiry instant is a hardcoded date in the past, so nothing here moves
    when the calendar does (CLAUDE.md §3 rule 6).
    """
    _, cookie = enrol(app, db, learner)
    jar = {SESSION_COOKIE_SECURE: cookie}

    # The same route, with the same cookie, works right up until it does not.
    assert request(app, "GET", "/auth/passkeys", cookies=jar).status_code == 200

    db.execute(
        "UPDATE auth_sessions SET expires_at = %s WHERE user_id = %s",
        (EXPIRED_AT, learner.user_id),
    )
    db.commit()

    assert request(app, "GET", "/auth/passkeys", cookies=jar).status_code == 401


def test_revoking_a_user_ends_their_session_on_the_next_request(
    app, db, learner
) -> None:
    """The operator revokes access while the learner is signed in.

    This is the behaviour that re-checking approval per request buys: no logout,
    no session-table edit and no restart is needed for it to take effect.
    """
    _, cookie = enrol(app, db, learner)
    assert (
        request(
            app, "GET", "/health/auth", cookies={SESSION_COOKIE_SECURE: cookie}
        ).json()
        is not None
    )
    db.execute(
        "UPDATE access_requests SET status = 'revoked' WHERE user_id = %s",
        (learner.user_id,),
    )
    db.commit()
    after = request(
        app, "GET", "/health/auth", cookies={SESSION_COOKIE_SECURE: cookie}
    )
    assert after.json() is None


def test_logout_invalidates_the_session_server_side(app, db, learner) -> None:
    """The learner signs out, and the cookie value that leaked is now useless.

    Replaying the raw value is the only way to see that the server revoked it
    rather than merely asking the browser to forget it.
    """
    _, cookie = enrol(app, db, learner)
    out = request(
        app, "POST", "/auth/logout", cookies={SESSION_COOKIE_SECURE: cookie}
    )
    assert out.status_code == 204
    replayed = request(
        app, "GET", "/health/auth", cookies={SESSION_COOKIE_SECURE: cookie}
    )
    assert replayed.json() is None


def test_logout_without_a_session_is_not_an_error(app) -> None:
    """Signing out twice, or from a stale tab, must not 500."""
    assert request(app, "POST", "/auth/logout").status_code == 204


def test_the_session_slides_when_it_nears_expiry(app, db, learner) -> None:
    """The learner uses the app after three weeks; the clock restarts.

    A 30-day *absolute* window would sign a daily user out on day 31, which is
    the wrong behaviour for a daily-habit app.
    """
    _, cookie = enrol(app, db, learner)
    near = datetime.now(timezone.utc) + timedelta(days=1)
    db.execute(
        "UPDATE auth_sessions SET expires_at = %s WHERE user_id = %s",
        (near, learner.user_id),
    )
    db.commit()
    response = request(
        app, "GET", "/health/auth", cookies={SESSION_COOKIE_SECURE: cookie}
    )
    assert response.json() is not None
    row = db.execute(
        "SELECT expires_at FROM auth_sessions WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()
    assert row is not None
    # Computed here, independently of the service (rule 5).
    assert row[0] > datetime.now(timezone.utc) + timedelta(days=29)
    assert "set-cookie" in response.headers, "the browser must learn the new expiry"


def test_a_session_well_inside_its_window_is_not_rewritten(
    app, db, learner
) -> None:
    """A write on every request would be one UPDATE per page view for nothing."""
    _, cookie = enrol(app, db, learner)
    before = db.execute(
        "SELECT expires_at FROM auth_sessions WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()
    request(app, "GET", "/health/auth", cookies={SESSION_COOKIE_SECURE: cookie})
    after = db.execute(
        "SELECT expires_at FROM auth_sessions WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()
    assert before is not None and after is not None
    assert before[0] == after[0]


# --- managing passkeys --------------------------------------------------------


def test_a_second_passkey_needs_a_session_not_a_claim_token(
    app, db, learner
) -> None:
    """The learner adds their laptop while signed in on their phone."""
    device, cookie = enrol(app, db, learner)
    jar = {SESSION_COOKIE_SECURE: cookie}

    anonymous = request(app, "POST", "/auth/passkeys/begin")
    assert anonymous.status_code == 401

    begin = request(app, "POST", "/auth/passkeys/begin", cookies=jar)
    assert begin.status_code == 200
    existing = {c["id"] for c in begin.json()["excludeCredentials"]}
    assert existing, "the device already enrolled must be excluded"

    laptop = SoftAuthenticator()
    credential = laptop.register(
        challenge=_challenge_of(begin), origin=ORIGIN, rp_id=RP_ID
    )
    finish = request(
        app,
        "POST",
        "/auth/passkeys/finish",
        json_body={"credential": credential},
        cookies=jar,
    )
    assert finish.status_code == 200, finish.text
    listed = request(app, "GET", "/auth/passkeys", cookies=jar).json()
    assert len(listed) == 2


def test_a_new_passkey_attaches_to_the_session_user_only(
    app, db, learner, cleanup
) -> None:
    """Two learners are signed in at once; one adds a device.

    The new credential must land on the session's user, taken from the cookie,
    and never on anyone named in the request.
    """
    device, cookie = enrol(app, db, learner)
    other = _make_learner(db)
    cleanup.append(other.user_id)

    begin = request(
        app,
        "POST",
        "/auth/passkeys/begin",
        cookies={SESSION_COOKIE_SECURE: cookie},
    )
    laptop = SoftAuthenticator()
    credential = laptop.register(
        challenge=_challenge_of(begin), origin=ORIGIN, rp_id=RP_ID
    )
    request(
        app,
        "POST",
        "/auth/passkeys/finish",
        json_body={"credential": credential},
        cookies={SESSION_COOKIE_SECURE: cookie},
    )
    owner = db.execute(
        "SELECT user_id FROM auth_credentials WHERE credential_id = %s",
        (laptop.credential_id,),
    ).fetchone()
    assert owner is not None and int(owner[0]) == learner.user_id


def test_deleting_the_last_passkey_is_refused(app, db, learner) -> None:
    """Removing the only credential is self-lockout, and this slice has no
    email reset to recover from it."""
    device, cookie = enrol(app, db, learner)
    jar = {SESSION_COOKIE_SECURE: cookie}
    listed = request(app, "GET", "/auth/passkeys", cookies=jar).json()
    response = request(
        app, "DELETE", f"/auth/passkeys/{listed[0]['id']}", cookies=jar
    )
    assert response.status_code == 409
    still = db.execute(
        "SELECT count(*) FROM auth_credentials WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()
    assert still is not None and still[0] == 1


def test_deleting_someone_elses_passkey_is_a_404(app, db, learner, cleanup) -> None:
    """404 and not 403: a 403 confirms the credential exists and turns an
    opaque id into something enumerable."""
    device, cookie = enrol(app, db, learner)
    other = _make_learner(db)
    cleanup.append(other.user_id)
    other_device, _ = enrol(app, db, other)

    from core.passkeys import b64url_encode

    response = request(
        app,
        "DELETE",
        f"/auth/passkeys/{b64url_encode(other_device.credential_id)}",
        cookies={SESSION_COOKIE_SECURE: cookie},
    )
    assert response.status_code == 404
    survives = db.execute(
        "SELECT count(*) FROM auth_credentials WHERE credential_id = %s",
        (other_device.credential_id,),
    ).fetchone()
    assert survives is not None and survives[0] == 1


def test_an_undecodable_credential_id_is_a_404_not_a_500(
    app, db, learner
) -> None:
    """A typo in a URL is not a server fault."""
    _, cookie = enrol(app, db, learner)
    response = request(
        app,
        "DELETE",
        "/auth/passkeys/not%21base64",
        cookies={SESSION_COOKIE_SECURE: cookie},
    )
    assert response.status_code == 404


def test_a_second_passkey_can_be_deleted(app, db, learner) -> None:
    """The learner loses one of two devices and removes it themselves —
    the case that would otherwise be an operator SQL task."""
    device, cookie = enrol(app, db, learner)
    jar = {SESSION_COOKIE_SECURE: cookie}
    begin = request(app, "POST", "/auth/passkeys/begin", cookies=jar)
    laptop = SoftAuthenticator()
    request(
        app,
        "POST",
        "/auth/passkeys/finish",
        json_body={
            "credential": laptop.register(
                challenge=_challenge_of(begin), origin=ORIGIN, rp_id=RP_ID
            )
        },
        cookies=jar,
    )
    from core.passkeys import b64url_encode

    response = request(
        app,
        "DELETE",
        f"/auth/passkeys/{b64url_encode(laptop.credential_id)}",
        cookies=jar,
    )
    assert response.status_code == 204
    remaining = db.execute(
        "SELECT count(*) FROM auth_credentials WHERE user_id = %s",
        (learner.user_id,),
    ).fetchone()
    assert remaining is not None and remaining[0] == 1


def test_listing_passkeys_needs_a_session(app) -> None:
    """An anonymous caller must not learn that any credential exists."""
    assert request(app, "GET", "/auth/passkeys").status_code == 401


# --- rate limiting ------------------------------------------------------------


def test_one_client_is_limited_on_enrolment(app, learner) -> None:
    """Someone hammers /enrol with guessed codes from one address."""
    body = {"email": learner.email, "claim_token": "x" * 20}
    statuses = [
        request(app, "POST", "/auth/register/begin", json_body=body).status_code
        for _ in range(7)
    ]
    assert 429 in statuses, statuses
    assert statuses[0] == 400, "the first attempts are refused on their merits"


def test_the_global_ceiling_is_a_second_bucket(app, learner) -> None:
    """The same attack from many addresses.

    A per-client limit alone is evaded from a botnet, so the global key has to
    be a real second row rather than a description in a comment. Each address
    stays under its own limit of 5; the global limit of 20 is what stops it.
    """
    body = {"email": learner.email, "claim_token": "x" * 20}
    statuses = []
    for host in range(8):
        for _ in range(4):
            statuses.append(
                request(
                    app,
                    "POST",
                    "/auth/register/begin",
                    json_body=body,
                    client=(f"10.0.0.{host}", 4000 + host),
                ).status_code
            )
    assert 429 in statuses, "the global ceiling never engaged"
    assert statuses[:4] == [400, 400, 400, 400], "one client stayed under its own limit"


# --- structural ---------------------------------------------------------------


def _api_sources() -> list[Path]:
    return [
        p
        for p in sorted(API_DIR.rglob("*.py"))
        if "__pycache__" not in p.parts
    ]


def test_only_the_dependency_resolves_a_session() -> None:
    """No route may re-implement session lookup.

    ``get_current_user`` is the one place a cookie becomes a user. A route that
    grows its own ``resolve_session`` call fails on the commit that adds it.
    """
    offenders: list[str] = []
    for path in _api_sources():
        if path.name == "deps.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr in {"resolve_session", "revoke_all_sessions"}:
                offenders.append(f"{path.name}:{node.lineno} {node.attr}")
    assert offenders == [], (
        "session lookup belongs to apps/api/deps.py::get_current_user alone: "
        + "; ".join(offenders)
    )


def test_the_auth_modules_hold_no_module_level_mutable_state() -> None:
    """The --workers 2 hazard, caught structurally.

    A module-level dict is how a challenge cache gets reintroduced: it works
    perfectly on one laptop process and fails about half of all real ceremonies
    behind two uvicorn workers, intermittently, only in production.
    """
    repo = Path(__file__).resolve().parents[1]
    targets = [
        repo / "packages" / "core" / "services" / "auth.py",
        repo / "packages" / "core" / "passkeys.py",
    ]
    offenders: list[str] = []
    for path in targets:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if isinstance(value, (ast.Dict, ast.List, ast.Set)):
                offenders.append(f"{path.name}:{node.lineno}")
            elif isinstance(value, ast.Call):
                func = value.func
                name = getattr(func, "id", getattr(func, "attr", ""))
                if name in {"dict", "list", "set", "defaultdict"}:
                    offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], (
        "no module-level mutable state in the auth modules — the API runs "
        "uvicorn --workers 2: " + "; ".join(offenders)
    )


def test_no_new_code_rewrites_the_approval_predicate() -> None:
    """The seventh-copy guard.

    The W0 log names three predicates that drifted once they were copied
    (`spacing_step`, `approved_onboarded_users`, `CHUNK_PRESENTED_AND_DUE_SQL`),
    and S18d's decision row says the view exists because "six hand-rolled JOINs
    drift; a missed site silently keeps delivering to a revoked user". The
    module deciding who gets a session is the worst place for another copy, so
    it calls ``access_control.is_approved`` and nothing else does the query.
    """
    repo = Path(__file__).resolve().parents[1]
    added = [
        repo / "packages" / "core" / "services" / "auth.py",
        repo / "packages" / "core" / "passkeys.py",
        repo / "packages" / "core" / "claim.py",
    ] + _api_sources()
    offenders: list[str] = []
    for path in added:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            if not isinstance(node.value, str):
                continue
            statement = " ".join(node.value.lower().split())
            if "from access_requests" in statement:
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], (
        "approval is answered by core.services.access_control.is_approved, "
        "never by a fresh query: " + "; ".join(offenders)
    )


def test_the_software_authenticator_can_produce_a_bad_assertion(
    app, db, learner
) -> None:
    """Rule 4 applied to the fixture itself.

    A fixture that can only produce valid input proves nothing about the
    rejection paths built on it, so this asserts both directions in one place:
    the same device signs an acceptable assertion and an unacceptable one.
    """
    device, _ = enrol(app, db, learner)
    handle = _handle_of(db, learner.user_id)

    good_begin = request(app, "POST", "/auth/login/begin")
    good = request(
        app,
        "POST",
        "/auth/login/finish",
        json_body={
            "credential": device.authenticate(
                challenge=_challenge_of(good_begin),
                origin=ORIGIN,
                rp_id=RP_ID,
                user_handle=handle,
            )
        },
    )
    bad_begin = request(app, "POST", "/auth/login/begin")
    bad = request(
        app,
        "POST",
        "/auth/login/finish",
        json_body={
            "credential": device.authenticate(
                challenge=_challenge_of(bad_begin),
                origin=ORIGIN,
                rp_id=RP_ID,
                user_handle=handle,
                tamper_signature=True,
            )
        },
    )
    assert (good.status_code, bad.status_code) == (200, 401)


def test_the_softauth_fixture_does_not_import_the_code_under_test() -> None:
    """CLAUDE.md §3 rule 5, enforced rather than promised.

    If the authenticator borrowed ``core.passkeys``'s encoders, every
    verification test in this file would only prove the module agrees with
    itself.
    """
    source = (
        Path(__file__).resolve().parent / "support" / "softauth.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "core" not in imported and "apps" not in imported, (
        f"softauth must build its own CBOR/COSE; it imports {sorted(imported)}"
    )


def test_the_session_json_is_the_shape_the_frontend_expects(
    app, db, learner
) -> None:
    """apps/web reads these three keys; a rename here must be visible."""
    _, cookie = enrol(app, db, learner)
    body = request(
        app, "GET", "/health/auth", cookies={SESSION_COOKIE_SECURE: cookie}
    ).json()
    assert set(body) == {"user_id", "name", "expires_at"}
    assert isinstance(body["user_id"], int)
    json.dumps(body)  # must be serialisable as-is
