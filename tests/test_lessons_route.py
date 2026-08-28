"""`GET /lessons/{unit_number}` **through the ASGI transport** (rule 1).

Not a direct service call. In v2, 161 tests passed while the main feature was
dead because every test called handlers directly, and this route is how two of
the three lessons this slice generates are read at all.
"""

from __future__ import annotations

import asyncio
import hashlib
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
from core.lessons import LESSON_VERSION
from core.lessons.schema import parse_lesson

FIXTURES = Path(__file__).parent / "fixtures" / "lessons"


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
        VALUES (%s, 'W10b Route', 'lt', TRUE, 'B1', %s, %s, 'Europe/Vilnius')
        RETURNING id
        """,
        (telegram_user_id, f"w10b-{abs(telegram_user_id)}@example.test",
         str(uuid.uuid4())),
    ).fetchone()
    user_id = int(row[0])
    db.execute(
        "INSERT INTO access_requests (telegram_user_id, user_id, display_name, "
        "status) VALUES (%s, %s, 'W10b Route', 'approved')",
        (telegram_user_id, user_id),
    )
    raw = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at) "
        "VALUES (%s, %s, %s)",
        (hashlib.sha256(raw.encode()).digest(), user_id,
         datetime.now(timezone.utc) + timedelta(days=30)),
    )
    db.commit()
    yield type("L", (), {"user_id": user_id, "cookie": raw})()
    db.execute("DELETE FROM access_requests WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()


@pytest.fixture
def stored_lesson(db):
    """Unit 1's specimen, written at the CURRENT version, cleaned up after."""
    raw = json.loads((FIXTURES / "specimen.json").read_text())
    lesson = parse_lesson(raw)
    payload = lesson.model_dump(mode="json")
    db.execute("DELETE FROM grammar_lessons WHERE unit_number = 1")
    db.execute(
        "INSERT INTO grammar_lessons (unit_number, sections, diagrams, "
        "verification, lesson_version) VALUES (%s, %s, %s, %s, %s)",
        (1, json.dumps(payload["sections"]), json.dumps(payload["diagrams"]),
         json.dumps({"verdict": "passed"}), LESSON_VERSION),
    )
    db.commit()
    yield lesson
    db.execute("DELETE FROM grammar_lessons WHERE unit_number = 1")
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


def test_an_unauthenticated_read_is_401(app, stored_lesson) -> None:
    """**What "authorise" means for a resource with no owner, asserted.**

    `grammar_lessons` has no `user_id`, so there is no row-level check to make --
    what is left is whether the caller is signed in at all, and an unstated
    answer is how a route quietly serves stored content to anybody. Same 401 the
    deploy uses as its evidence that `english-api` is live.
    """
    response = request(app, "GET", "/lessons/1")
    assert response.status_code == 401


def test_a_signed_in_learner_reads_the_lesson(app, learner, stored_lesson) -> None:
    response = request(app, "GET", "/lessons/1", cookies=_as(learner))
    assert response.status_code == 200
    body = response.json()
    assert body["unit_number"] == 1
    assert len(body["sections"]) == 4
    assert [s["target"] for s in body["sections"]] == [
        s.target for s in stored_lesson.sections
    ]


def test_the_lesson_is_the_same_for_every_learner(app, learner, stored_lesson) -> None:
    """The global line, on the wire. Nothing here is selected by user."""
    first = request(app, "GET", "/lessons/1", cookies=_as(learner)).json()
    second = request(app, "GET", "/lessons/1", cookies=_as(learner)).json()
    assert first == second
    assert "user_id" not in json.dumps(first)


def test_a_unit_with_no_lesson_is_404(app, learner) -> None:
    """A unit nobody has generated for is the correct behaviour, not a bug."""
    response = request(app, "GET", "/lessons/7", cookies=_as(learner))
    assert response.status_code == 404


def test_a_unit_number_outside_the_syllabus_is_404(app, learner) -> None:
    for unit in (0, 25, 999):
        assert request(app, "GET", f"/lessons/{unit}",
                       cookies=_as(learner)).status_code == 404


def test_a_lesson_below_the_current_version_is_not_served(
    app, learner, db, stored_lesson
) -> None:
    """**The `lesson_version` read policy, through the real route.**

    `grammar_lessons_only_verified_rows_exist` keeps passing on a row verified
    under rules that no longer exist -- the CHECK cannot see the version. So the
    service refuses it, exactly as `bank_for_session` refuses a stale
    `validator_version`, and the route 404s rather than serving teaching checked
    by retired checks.
    """
    db.execute("UPDATE grammar_lessons SET lesson_version = %s WHERE unit_number = 1",
               (LESSON_VERSION - 1,))
    db.commit()
    assert request(app, "GET", "/lessons/1", cookies=_as(learner)).status_code == 404


def test_no_murphy_citation_reaches_the_route(app, learner, stored_lesson) -> None:
    """#171's constraint at this surface too. No page number ever reaches a learner."""
    body = request(app, "GET", "/lessons/1", cookies=_as(learner)).text
    assert "murphy" not in body.lower()
