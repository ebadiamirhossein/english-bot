"""W7: the deck routes through the real ASGI transport.

CLAUDE.md §3 rule 1 names the card deck alongside the error journal: every route
that writes to it needs an integration test through the real entry point.
Nothing here calls a route function or a service directly; every request goes
through `httpx.ASGITransport` into the app `uvicorn apps.api.main:app` serves.

**The FSRS arithmetic is not re-asserted here** — `tests/test_cards_fsrs.py`
pins it against py-fsrs' own published vectors. What these assert is what the
route does with it: that the number it returns is the number it stored, that the
four grades order as the scheduler says they do, and that the caps and the
ownership rules survive the trip through HTTP.

No model call is made and none is stubbed. Grading a card is arithmetic and
`netguard` would raise if anything reached the network, which is how we know.
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
from core.cards import DAILY_NEW_CARD_CAP
from core.cards.fsrs import CardState, initial_state
from core.config import load_settings
from core.services import cards as svc


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unique rate-limit salt per test, so one test cannot 429 the next."""
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


def _make_learner(db, label: str):
    telegram_user_id = -secrets.randbelow(1_000_000_000) - 1
    row = db.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language, onboarded,
                           cefr_level, explanation_language_fallback,
                           auth_email, auth_user_id, timezone)
        VALUES (%s, %s, 'fa', TRUE, 'B1', TRUE, %s, %s, 'Europe/Vilnius')
        RETURNING id
        """,
        (
            telegram_user_id,
            label,
            f"w7-{abs(telegram_user_id)}@example.test",
            str(uuid.uuid4()),
        ),
    ).fetchone()
    user_id = int(row[0])
    db.execute(
        "INSERT INTO access_requests (telegram_user_id, user_id, display_name, "
        "status) VALUES (%s, %s, %s, 'approved')",
        (telegram_user_id, user_id, label),
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
    return user_id, raw


@pytest.fixture
def learner(db):
    user_id, raw = _make_learner(db, "W7 Learner")
    yield type("L", (), {"user_id": user_id, "cookie": raw})()
    db.execute("DELETE FROM card_reviews WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM cards WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM access_requests WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()


def _mature(due: datetime) -> CardState:
    return CardState(
        fsrs_state="review",
        fsrs_step=None,
        stability=10.0,
        difficulty=5.0,
        due=due,
        last_review=due - timedelta(days=10),
        lapses=0,
        reps=4,
    )


def _seed(db, learner, **over) -> int:
    """A card due yesterday, so it is in the queue whatever today's clock says.

    Relative to `now()` deliberately: the route reads the real clock, and a
    fixed calendar date in a fixture would make this file start failing on a
    date rather than on a change (CLAUDE.md §3 rule 6).
    """
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    spec = dict(
        card_type="cloze",
        front="I _____ to the shops.",
        back="went",
        register="neutral",
        register_source="migration_default",
        meaning="past of go",
        context_sentence="I went to the shops.",
        source_ref="himym_s2e4",
        state=_mature(yesterday),
    )
    spec.update(over)
    card_id = svc.create_card(db, learner.user_id, **spec)
    db.commit()
    assert card_id is not None
    return card_id


def request(app, method, path, *, json_body=None, cookies=None, headers=None):
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as http:
            return await http.request(
                method, path, json=json_body, headers=headers or {}
            )

    return asyncio.run(_go())


def _as(learner, extra=None):
    return (
        {SESSION_COOKIE_SECURE: learner.cookie},
        {"content-type": "application/json", **(extra or {})},
    )


# ── reading the queue ──────────────────────────────────────────────────────


def test_the_queue_requires_a_session(app) -> None:
    assert request(app, "GET", "/review/queue").status_code == 401


def test_the_queue_serves_a_due_card_with_its_whole_face(app, db, learner) -> None:
    """User action: opening /review. PRD §5 and §8.5.4 on the wire."""
    card_id = _seed(db, learner)
    cookies, _ = _as(learner)
    response = request(app, "GET", "/review/queue", cookies=cookies)
    assert response.status_code == 200
    body = response.json()
    assert [c["id"] for c in body["cards"]] == [card_id]
    face = body["cards"][0]
    assert face["front"] == "I _____ to the shops."
    assert face["context_sentence"] == "I went to the shops."
    assert face["source_ref"] == "himym_s2e4"
    assert face["register"] == "neutral"


def test_the_face_carries_an_interval_for_each_of_the_four_grades(
    app, db, learner
) -> None:
    """The client renders these; it has nothing to compute them from."""
    _seed(db, learner)
    cookies, _ = _as(learner)
    face = request(app, "GET", "/review/queue", cookies=cookies).json()["cards"][0]
    assert set(face["intervals"]) == {"again", "hard", "good", "easy"}
    intervals = [face["intervals"][k] for k in ("again", "hard", "good", "easy")]
    assert intervals == sorted(intervals)


def test_a_card_not_yet_due_is_not_served(app, db, learner) -> None:
    tomorrow = datetime.now(timezone.utc) + timedelta(days=3)
    _seed(db, learner, state=_mature(tomorrow))
    cookies, _ = _as(learner)
    body = request(app, "GET", "/review/queue", cookies=cookies).json()
    assert body["cards"] == []


def test_an_empty_deck_is_an_ordinary_response_and_not_an_error(
    app, learner
) -> None:
    cookies, _ = _as(learner)
    response = request(app, "GET", "/review/queue", cookies=cookies)
    assert response.status_code == 200
    assert response.json() == {
        "cards": [],
        "counts": {"new_remaining": 0, "review_remaining": 0, "total_remaining": 0},
        # W10 / #159: the learner's L1 rides on the ENVELOPE, once, read from
        # `users.native_language`. Before this the card face guessed it from the
        # SCRIPT, which is right for Farsi by accident and silently wrong for a
        # Latin-script L1 — no tofu, no direction symptom, nothing in a log.
        "l1_language": "fa",
    }


def test_the_cap_holds_through_the_route(app, db, learner) -> None:
    """PRD §5's daily new-card cap, asserted where a learner meets it."""
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    for i in range(DAILY_NEW_CARD_CAP + 4):
        _seed(db, learner, front=f"new {i}", state=initial_state(due=yesterday))
    cookies, _ = _as(learner)
    body = request(app, "GET", "/review/queue?limit=50", cookies=cookies).json()
    assert len(body["cards"]) == DAILY_NEW_CARD_CAP
    assert body["counts"]["total_remaining"] == DAILY_NEW_CARD_CAP


def test_another_learners_deck_is_not_visible(app, db, learner) -> None:
    other_id, other_cookie = _make_learner(db, "W7 Other")
    try:
        _seed(db, learner)
        response = request(
            app, "GET", "/review/queue", cookies={SESSION_COOKIE_SECURE: other_cookie}
        )
        assert response.json()["cards"] == []
    finally:
        db.execute("DELETE FROM access_requests WHERE user_id = %s", (other_id,))
        db.execute("DELETE FROM users WHERE id = %s", (other_id,))
        db.commit()


# ── grading ────────────────────────────────────────────────────────────────


def test_grading_requires_a_session(app, db, learner) -> None:
    card_id = _seed(db, learner)
    response = request(
        app,
        "POST",
        f"/review/{card_id}/grade",
        json_body={"rating": "good"},
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 401


def test_grading_refuses_a_non_json_body(app, db, learner) -> None:
    """The CSRF barrier is that every state-changing route is a JSON POST."""
    card_id = _seed(db, learner)
    cookies, _ = _as(learner)
    response = request(
        app,
        "POST",
        f"/review/{card_id}/grade",
        json_body={"rating": "good"},
        cookies=cookies,
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 415


def test_grading_refuses_a_rating_that_is_not_one_of_the_four(
    app, db, learner
) -> None:
    """The rating travels by name. A client cannot invent a fifth grade, and it
    cannot send `3` and have it mean Good by accident."""
    card_id = _seed(db, learner)
    cookies, headers = _as(learner)
    for bad in ("brilliant", "3", "", "AGAIN"):
        response = request(
            app,
            "POST",
            f"/review/{card_id}/grade",
            json_body={"rating": bad},
            cookies=cookies,
            headers=headers,
        )
        assert response.status_code == 422, bad


def test_grading_returns_the_interval_it_actually_stored(app, db, learner) -> None:
    """**The assertion that catches a route returning a number it did not save.**

    Not a check of FSRS's arithmetic — that is pinned by the upstream vectors
    in `test_cards_fsrs.py`. This asserts internal consistency: the days the
    learner is told the card will be away equals the days between the logged
    review and the stored due date.
    """
    card_id = _seed(db, learner)
    cookies, headers = _as(learner)
    response = request(
        app,
        "POST",
        f"/review/{card_id}/grade",
        json_body={"rating": "good", "duration_ms": 3300},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()

    row = db.execute(
        """
        SELECT c.due, r.reviewed_at, r.rating, r.due_after, r.review_duration_ms
          FROM cards c JOIN card_reviews r ON r.card_id = c.id
         WHERE c.id = %s
        """,
        (card_id,),
    ).fetchone()
    due, reviewed_at, rating, due_after, duration = row
    assert rating == 3
    assert due == due_after
    assert duration == 3300
    assert body["interval_days"] == (due - reviewed_at).days
    assert datetime.fromisoformat(body["due"]) == due


def test_the_four_grades_order_as_the_scheduler_says_through_the_route(
    app, db, learner
) -> None:
    """One card each, identical state, four grades. Again … Easy, strictly."""
    cookies, headers = _as(learner)
    dues = []
    for rating in ("again", "hard", "good", "easy"):
        card_id = _seed(db, learner, front=f"card {rating}")
        body = request(
            app,
            "POST",
            f"/review/{card_id}/grade",
            json_body={"rating": rating},
            cookies=cookies,
            headers=headers,
        ).json()
        dues.append(datetime.fromisoformat(body["due"]))
    assert dues == sorted(dues)
    assert len(set(dues)) == 4


def test_a_graded_card_leaves_the_queue(app, db, learner) -> None:
    """User action: grading a card and expecting the next one."""
    card_id = _seed(db, learner)
    cookies, headers = _as(learner)
    request(
        app,
        "POST",
        f"/review/{card_id}/grade",
        json_body={"rating": "good"},
        cookies=cookies,
        headers=headers,
    )
    body = request(app, "GET", "/review/queue", cookies=cookies).json()
    assert body["cards"] == []


def test_grading_appends_exactly_one_review_row(app, db, learner) -> None:
    card_id = _seed(db, learner)
    cookies, headers = _as(learner)
    for _ in range(1):
        request(
            app,
            "POST",
            f"/review/{card_id}/grade",
            json_body={"rating": "hard"},
            cookies=cookies,
            headers=headers,
        )
    count = db.execute(
        "SELECT count(*) FROM card_reviews WHERE card_id = %s", (card_id,)
    ).fetchone()[0]
    assert count == 1


def test_another_learners_card_is_not_found(app, db, learner) -> None:
    """404 rather than 403: an id that exists but is not yours is a fact about
    the other learner."""
    other_id, other_cookie = _make_learner(db, "W7 Other Grade")
    try:
        card_id = _seed(db, learner)
        response = request(
            app,
            "POST",
            f"/review/{card_id}/grade",
            json_body={"rating": "good"},
            cookies={SESSION_COOKIE_SECURE: other_cookie},
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 404
    finally:
        db.execute("DELETE FROM access_requests WHERE user_id = %s", (other_id,))
        db.execute("DELETE FROM users WHERE id = %s", (other_id,))
        db.commit()


# The export's three tests stood here from W7 until 2026-08-25. W8a removed
# `GET /cards/export.tsv`, so they went with it — the route they exercised does
# not exist. What replaces them is not a test of this router at all but a ban:
# `tests/test_web_shell.py::test_no_anki_export_path_in_the_web_app` fails the
# commit that puts the path back into `apps/api` or `apps/web`.


# ── the routes are registered, which is #117's real evidence ───────────────


def test_the_deck_routes_answer_401_and_not_404_without_a_session(app) -> None:
    """**#117's evidence, in the same shape the deployment step now cites.**

    A `401` proves the route is registered *and* gated; a `404` would mean the
    router never loaded. The step used to cite a start-up log line that did not
    appear in `journalctl` — the cause was that `apps/api` never configured
    logging at all, so every INFO record fell through to `logging.lastResort`
    (WARNING and above). That is fixed in `core.logging.configure_console_logging`
    and the step now cites this, which is a fact a reader can reproduce.
    """
    assert request(app, "GET", "/review/queue").status_code == 401
    assert (
        request(
            app,
            "POST",
            "/review/1/grade",
            json_body={"rating": "good"},
            headers={"content-type": "application/json"},
        ).status_code
        == 401
    )


def test_the_startup_line_naming_the_routes_is_emitted(caplog) -> None:
    """#117's other half: the line the runbook used to cite must actually exist.

    Asserted at INFO through the root logger, which is the level and the handler
    that were missing under systemd.
    """
    import logging

    with caplog.at_level(logging.INFO, logger="apps.api.main"):
        create_app()
    built = [r for r in caplog.records if r.getMessage().startswith("API built")]
    assert built, "the `API built origins=… routes=…` line was not emitted"
    assert "/review/queue" in built[-1].getMessage()
    assert "/review/{card_id}/grade" in built[-1].getMessage()
