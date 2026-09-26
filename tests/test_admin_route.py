"""W23: `GET /admin/activity` — the bot's `/admin`, ported — through the real ASGI transport.

TASKS' W23 row: *"`/admin` ported (activity never content)"*; CLAUDE.md §5:
*"The admin panel shows activity, never content."* Every assertion goes through
`create_app()` (§3 rule 1), against the dev database.

**RED DEMONSTRATIONS (2026-09-25):**
* `test_a_learner_who_is_not_the_operator_gets_404` — red with
  `is_operator` returning `True` unconditionally (200 for a learner).
* `test_unset_operator_means_nobody` — red with `is_operator` written
  `user_id in admin_user_ids or not admin_user_ids` (200 with the variable
  unset: an empty allowlist read as *everybody*).

**THE OPERATOR IS `ADMIN_USER_IDS`, NOT THE TELEGRAM ID, AND A TEST DECIDED
IT.** The first build compared `OPERATOR_TELEGRAM_ID` with
`users.telegram_user_id`; the full suite's `test_the_api_never_names_a_telegram_id`
refused `apps/api/routers/admin.py` (W4b: the API must not know Telegram
exists). The rule was right and the design moved.
* `test_the_panel_is_activity_and_never_content` — red with a
  `last_error: str | None = None` field added to `AdminUserOut` (the key set
  grew: a field that could carry a sentence is refused before it is ever filled).
* `test_the_operator_reads_every_learners_activity` — red with `admin_out`
  passing `current_streak=0` (hardcoded 3 expected, §3 rule 5).
"""

from __future__ import annotations

import asyncio
import secrets

import httpx
import psycopg
import pytest

from apps.api.deps import SESSION_COOKIE_SECURE
from apps.api.main import create_app
from core.config import load_settings
from tests.support import progress_seed as seed

SECRET_SENTENCE = "AdminGuard: my boss say me I am late every day"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBAUTHN_RP_ID", "foundgrant.com")
    monkeypatch.setenv("WEBAUTHN_ORIGIN", "https://app.foundgrant.com")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SALT", secrets.token_hex(16))


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def learners(db):
    made: list = []

    def _make(label: str):
        learner = seed.make_learner(db, label)
        made.append(learner)
        return learner

    yield _make
    for learner in made:
        db.rollback()
        db.execute("DELETE FROM errors WHERE user_id = %s", (learner.user_id,))
        db.commit()
        seed.drop_learner(db, learner.user_id)


@pytest.fixture
def operator(learners, monkeypatch: pytest.MonkeyPatch):
    """A learner on ``ADMIN_USER_IDS``, as the operator's own row will be on the host."""
    learner = learners("W23 operator")
    monkeypatch.setenv("ADMIN_USER_IDS", str(learner.user_id))
    return learner


def _get(learner=None) -> httpx.Response:
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(), client=("127.0.0.1", 51234))
        cookies = {SESSION_COOKIE_SECURE: learner.cookie} if learner else None
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as http:
            return await http.get("/admin/activity")

    return asyncio.run(_go())


def _row(body: dict, user_id: int) -> dict:
    (row,) = [u for u in body["users"] if u["id"] == user_id]
    return row


def test_the_panel_requires_a_session() -> None:
    assert _get().status_code == 401


def test_a_learner_who_is_not_the_operator_gets_404(operator, learners) -> None:
    """User action: the second learner types `/admin` into the address bar.

    404, the answer an unknown path gets — the route does not announce itself.
    """
    other = learners("W23 learner")
    response = _get(other)
    assert response.status_code == 404
    assert response.json() == {"detail": "not_found"}


def test_unset_operator_means_nobody(db, learners, monkeypatch) -> None:
    """Silence is never the default (#31's shape): no variable, no panel — for anyone."""
    learner = learners("W23 unset")
    monkeypatch.setenv("ADMIN_USER_IDS", "")
    assert _get(learner).status_code == 404


def test_the_operator_reads_every_learners_activity(db, operator, learners) -> None:
    """User action: the operator opens `/admin` on their phone."""
    other = learners("W23 second learner")
    db.execute(
        "UPDATE streaks SET current_streak = 3 WHERE user_id = %s", (other.user_id,)
    )
    db.commit()
    response = _get(operator)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["weekly_goal_days"] == 5
    assert body["lookback_days"] == 7
    row = _row(body, other.user_id)
    assert row["name"] == "W23 second learner"
    assert row["cefr_level"] == "B1"
    assert row["current_streak"] == 3
    assert row["paused"] is False
    assert row["revoked"] is False
    _row(body, operator.user_id)


def test_the_panel_is_activity_and_never_content(db, operator, learners) -> None:
    """CLAUDE.md §5. The key set is exact, and a journal sentence never reaches it."""
    other = learners("W23 writer")
    db.execute(
        """
        INSERT INTO errors (user_id, source, you_said, correct_form, error_type,
                            explanation, next_review)
        VALUES (%s, 'text', %s, 'my boss tells me', 'verb_tense_past', 'x', CURRENT_DATE)
        """,
        (other.user_id, SECRET_SENTENCE),
    )
    db.commit()
    response = _get(operator)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"pending_requests", "weekly_goal_days", "lookback_days", "users"}
    assert set(_row(body, other.user_id)) == {
        "id", "name", "cefr_level", "current_streak", "active_days",
        "last_active", "paused", "revoked",
    }
    assert "AdminGuard" not in response.text
    assert "boss" not in response.text


def test_a_web_practice_day_is_counted_by_the_panel(db, operator, learners) -> None:
    """Launch 2026-09-26, B3 — *is the activity true?* All three learners read
    **0 active days in the last 7** on the operator's `/admin`. This pins that
    the panel's count reads the WEB logs (`core.services.activity`, #259's one
    signal), so a 0 there is the data, not a panel that cannot see the web.

    User action: a learner answers block 3 on the web one day and talks on
    `/talk` another; the operator opens `/admin`. The window is the route's own
    — today in the learner's timezone, computed here the way the route computes
    it (§3 rule 6), and the days are placed relative to it.

    **RED DEMONSTRATION (2026-09-26):** `count_active_days` without its
    `practised_dates` union (v2's `completed = TRUE` only, #259's defect) → red,
    0 active days.
    """
    from datetime import datetime, timedelta, timezone

    from core.services.sessions import local_today

    other = learners("W23 web learner")
    today = local_today("Europe/Vilnius", datetime.now(timezone.utc))
    seed.attempt(db, other.user_id, "cloze_cued", seed.at(today - timedelta(days=1), 12))
    seed.turns(db, other.user_id, today - timedelta(days=3), typed=4)
    seed.turns(db, other.user_id, today - timedelta(days=9), typed=4)  # outside the 7
    response = _get(operator)
    assert response.status_code == 200, response.text
    assert _row(response.json(), other.user_id)["active_days"] == 2
