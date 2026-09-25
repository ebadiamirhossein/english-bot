"""W20: the `/push/*` routes, through the real ASGI transport, against the dev database.

CLAUDE.md §3 rule 1: every route that writes goes through `httpx.ASGITransport`
into `create_app()`. `POST /push/subscribe` writes `push_subscriptions`; the
assertions read the table on a separate connection.

**RED DEMONSTRATIONS (2026-09-25):**
* `test_subscribe_stores_this_browser_and_state_reads_it_back` — red with
  `save_subscription` writing nothing (no row: `None == <the learner's id>`).
* `test_a_shared_device_moves_to_the_learner_who_turned_it_on` — red with the
  upsert's `SET user_id = EXCLUDED.user_id` removed (the row stayed the first
  learner's).
* `test_unsubscribe_removes_only_your_own_row` — red with `delete_subscription`'s
  `user_id = %s` removed (the other learner's row was deleted).
* `test_the_key_is_null_until_the_pair_matches` — red with `public_key`
  returning `vapid.public_key` without `check()` (the mismatched key was served).
"""

from __future__ import annotations

import asyncio
import base64
import os
import secrets

import httpx
import psycopg
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from apps.api.deps import SESSION_COOKIE_SECURE
from apps.api.main import create_app
from core.config import load_settings
from core.push import generate_vapid_keys
from tests.support import progress_seed as seed


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBAUTHN_RP_ID", "foundgrant.com")
    monkeypatch.setenv("WEBAUTHN_ORIGIN", "https://app.foundgrant.com")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SALT", secrets.token_hex(16))


@pytest.fixture
def keys(monkeypatch):
    private, public = generate_vapid_keys()
    monkeypatch.setenv("VAPID_PRIVATE_KEY", private)
    monkeypatch.setenv("VAPID_PUBLIC_KEY", public)
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:op@example.invalid")
    return public


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def learners(db):
    made: list[int] = []

    def _make():
        learner = seed.make_learner(db, "W20 route")
        made.append(learner.user_id)
        return learner

    yield _make
    for user_id in made:
        seed.drop_learner(db, user_id)


def call(method, path, *, learner=None, body=None, headers=None):
    app = create_app()

    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        cookies = {SESSION_COOKIE_SECURE: learner.cookie} if learner else None
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as http:
            return await http.request(method, path, json=body, headers=headers or {})

    return asyncio.run(_go())


def browser(endpoint: str | None = None) -> dict:
    key = ec.generate_private_key(ec.SECP256R1())
    point = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    b64 = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=").decode()  # noqa: E731
    return {
        "endpoint": endpoint or f"https://push.example.test/{secrets.token_hex(12)}",
        "expirationTime": None,
        "keys": {"p256dh": b64(point), "auth": b64(os.urandom(16))},
    }


def owner(db, endpoint):
    db.rollback()
    row = db.execute("SELECT user_id FROM push_subscriptions WHERE endpoint = %s", (endpoint,)).fetchone()
    return None if row is None else row[0]


def test_every_route_needs_a_session(keys) -> None:
    assert call("GET", "/push/key").status_code == 401
    for path in ("/push/subscribe", "/push/unsubscribe", "/push/state"):
        assert call("POST", path, body=browser()).status_code == 401, path


def test_the_key_is_null_until_the_pair_matches(learners, monkeypatch) -> None:
    me = learners()
    for key in ("VAPID_PRIVATE_KEY", "VAPID_PUBLIC_KEY", "VAPID_SUBJECT"):
        monkeypatch.setenv(key, "")
    assert call("GET", "/push/key", learner=me).json() == {"public_key": None}
    a, b = generate_vapid_keys(), generate_vapid_keys()
    monkeypatch.setenv("VAPID_PRIVATE_KEY", a[0])
    monkeypatch.setenv("VAPID_PUBLIC_KEY", b[1])
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:op@example.invalid")
    assert call("GET", "/push/key", learner=me).json() == {"public_key": None}
    monkeypatch.setenv("VAPID_PUBLIC_KEY", a[1])
    assert call("GET", "/push/key", learner=me).json() == {"public_key": a[1]}


def test_subscribe_stores_this_browser_and_state_reads_it_back(learners, keys, db) -> None:
    me = learners()
    sub = browser()
    ask = {"endpoint": sub["endpoint"]}
    assert call("POST", "/push/state", learner=me, body=ask).json() == {"on": False}
    response = call("POST", "/push/subscribe", learner=me, body=sub)
    assert response.status_code == 200, response.text
    assert response.json() == {"on": True}
    assert owner(db, sub["endpoint"]) == me.user_id
    assert call("POST", "/push/state", learner=me, body=ask).json() == {"on": True}
    # Idempotent: a second subscribe of the same browser is one row.
    call("POST", "/push/subscribe", learner=me, body=sub)
    db.rollback()
    assert db.execute(
        "SELECT count(*) FROM push_subscriptions WHERE user_id = %s", (me.user_id,)
    ).fetchone()[0] == 1


def test_a_shared_device_moves_to_the_learner_who_turned_it_on(learners, keys, db) -> None:
    a, b = learners(), learners()
    sub = browser()
    call("POST", "/push/subscribe", learner=a, body=sub)
    call("POST", "/push/subscribe", learner=b, body=sub)
    assert owner(db, sub["endpoint"]) == b.user_id
    assert call("POST", "/push/state", learner=a, body={"endpoint": sub["endpoint"]}).json() == {"on": False}


def test_unsubscribe_removes_only_your_own_row(learners, keys, db) -> None:
    a, b = learners(), learners()
    mine, theirs = browser(), browser()
    call("POST", "/push/subscribe", learner=a, body=mine)
    call("POST", "/push/subscribe", learner=b, body=theirs)
    assert call("POST", "/push/unsubscribe", learner=a, body={"endpoint": theirs["endpoint"]}).json() == {"on": False}
    assert owner(db, theirs["endpoint"]) == b.user_id
    call("POST", "/push/unsubscribe", learner=a, body={"endpoint": mine["endpoint"]})
    assert owner(db, mine["endpoint"]) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.update(endpoint="http://push.example.test/x"),
        lambda s: s["keys"].update(p256dh="short"),
        lambda s: s["keys"].update(auth="A" * 21 + "!"),
        lambda s: s.pop("keys"),
    ],
)
def test_a_malformed_subscription_is_a_422_and_writes_nothing(learners, keys, db, mutate) -> None:
    me = learners()
    sub = browser()
    mutate(sub)
    assert call("POST", "/push/subscribe", learner=me, body=sub).status_code == 422
    db.rollback()
    assert db.execute(
        "SELECT count(*) FROM push_subscriptions WHERE user_id = %s", (me.user_id,)
    ).fetchone()[0] == 0


def test_a_non_json_body_is_refused(learners, keys) -> None:
    """A form post would be a simple request with no CORS preflight."""
    me = learners()
    app = create_app()

    async def _go():
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            cookies={SESSION_COOKIE_SECURE: me.cookie},
        ) as http:
            return await http.post("/push/subscribe", data={"endpoint": "https://x.test/a"})

    assert asyncio.run(_go()).status_code == 415


def test_no_route_sends_a_push(learners, keys, monkeypatch) -> None:
    """Sending is the worker's. A subscribe must never reach a push service."""

    def _no(*_a, **_k):
        raise AssertionError("a route reached a push service")

    monkeypatch.setattr("core.push_api.httpx.post", _no)
    me = learners()
    assert call("POST", "/push/subscribe", learner=me, body=browser()).status_code == 200
