"""W11b: `GET /week`, through the real ASGI transport.

CLAUDE.md §3 rule 1. Nothing here calls the route function or the service
directly; every request goes through `httpx.ASGITransport` into the app
`uvicorn apps.api.main:app` serves.

**The route is a read and nothing else.** No model call, no speech call, no
write — `tests/support/netguard.py` is armed session-wide by `conftest.py`, so a
provider call inside the request would raise rather than pass silently.

**The assertions this file exists for are the two negatives.** A weekly report
is the single most likely place in this product to smuggle in guilt: it is the
app speaking, it is retrospective, and the natural way to write one is to say
what did not happen. So the payload is asserted to carry no backlog key
(#160, and the tuple is imported from `test_session_route` rather than copied)
and no field for the four columns nothing writes.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import psycopg
import pytest
from fastapi import FastAPI

from apps.api.deps import SESSION_COOKIE_SECURE
from apps.api.main import create_app
from core.config import load_settings
from tests.test_session_route import BACKLOG_KEYS


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBAUTHN_RP_ID", "foundgrant.com")
    monkeypatch.setenv("WEBAUTHN_ORIGIN", "https://app.foundgrant.com")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SALT", secrets.token_hex(16))


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def learner(db):
    telegram_user_id = -secrets.randbelow(1_000_000_000) - 1
    row = db.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language, onboarded,
                           cefr_level, auth_email, auth_user_id, timezone)
        VALUES (%s, 'W11b Route', 'lt', TRUE, 'B1', %s, %s, 'Europe/Vilnius')
        RETURNING id
        """,
        (
            telegram_user_id,
            f"w11b-{abs(telegram_user_id)}@example.test",
            str(uuid.uuid4()),
        ),
    ).fetchone()
    user_id = int(row[0])
    db.execute(
        "INSERT INTO access_requests (telegram_user_id, user_id, display_name, "
        "status) VALUES (%s, %s, 'W11b Route', 'approved')",
        (telegram_user_id, user_id),
    )
    raw = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at) "
        "VALUES (%s, %s, %s)",
        (
            hashlib.sha256(raw.encode()).digest(),
            user_id,
            datetime.now(timezone.utc) + timedelta(days=30),
        ),
    )
    db.commit()
    yield type("L", (), {"user_id": user_id, "cookie": raw})()
    db.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM access_requests WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()


def request(app, method, path, *, cookies=None):
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as http:
            return await http.request(method, path)

    return asyncio.run(_go())


def _as(learner):
    return {SESSION_COOKIE_SECURE: learner.cookie}


# ── the route ───────────────────────────────────────────────────────────────


def test_the_week_requires_a_session(app) -> None:
    assert request(app, "GET", "/week").status_code == 401


def test_the_week_serves_a_report(app, db, learner) -> None:
    """User action: it is Sunday and the learner opens the app."""
    response = request(app, "GET", "/week", cookies=_as(learner))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "week_ending",
        "sunday",
        "days_with_a_session",
        "items_answered",
        "items_right",
        "cards_reviewed",
        "words_now_known",
        "units_passed",
        "empty",
    }


def test_a_learner_with_no_week_yet_gets_a_report_that_says_it_is_empty(
    app, db, learner
) -> None:
    """Week one is both learners' state, and it is a 200 rather than a 404.

    An empty week is a fact about the week, not a missing resource; a 404 here
    would make the client render an error for the ordinary first Sunday.
    """
    body = request(app, "GET", "/week", cookies=_as(learner)).json()
    assert body["empty"] is True
    assert body["days_with_a_session"] == 0


def test_nothing_is_generated_while_the_learner_waits(app, db, learner) -> None:
    """The netguard is armed for the whole session; this route makes no
    outbound call at all, and a later slice that adds one fails here."""
    assert request(app, "GET", "/week", cookies=_as(learner)).status_code == 200


# ── the two negatives ───────────────────────────────────────────────────────


def test_the_report_carries_no_backlog_key(app, db, learner) -> None:
    """#160, and the tuple is `test_session_route`'s own — not a fifth copy."""
    response = request(app, "GET", "/week", cookies=_as(learner))
    # **The 200 is part of the assertion, not scaffolding (#345).** A scan for
    # absent keys over a 404 body passes whether the rule holds or the route is
    # gone, which is an assertion that admits its own failure mode.
    assert response.status_code == 200
    assert BACKLOG_KEYS, "the imported tuple is empty; this scan reads nothing"
    for banned in BACKLOG_KEYS:
        assert banned not in response.text


def test_the_report_carries_no_field_for_what_nothing_writes(
    app, db, learner
) -> None:
    """**#258 / #259 at the HTTP boundary.**

    `minutes`, `completed_at` and `xp` have no writer — `complete_block` was
    the only one and W11 removed it, and W19 owns the weighting — so a field for
    any of them would be a number that is always zero. A zero on a report is a
    score, and a score of zero on a week nobody promised anything about is guilt
    with no banned word in it.

    Asserted over the whole response text, because a surface cannot render what
    never arrived.
    """
    response = request(app, "GET", "/week", cookies=_as(learner))
    assert response.status_code == 200  # #345, as above
    for absent in ("minutes", "xp", "block_breakdown", "completed_at"):
        assert absent not in response.text


def test_the_report_names_the_week_it_covers(app, db, learner) -> None:
    """A report with no date on it is a report about no particular week."""
    body = request(app, "GET", "/week", cookies=_as(learner)).json()
    from datetime import date

    ending = date.fromisoformat(body["week_ending"])
    assert ending.weekday() == 6, "PRD §4.2's week runs Mon → Sun"
