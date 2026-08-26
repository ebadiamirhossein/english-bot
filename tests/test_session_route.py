"""W10: `GET /session/today` and the block-complete route, through the real
ASGI transport.

Nothing here calls a route function or a service directly; every request goes
through `httpx.ASGITransport` into the app `uvicorn apps.api.main:app` serves —
CLAUDE.md §3 rule 1, and the descendant of v2's most expensive lesson.

**The assertion this file exists for is `test_nothing_is_generated_while_the_
learner_waits`.** ARCHITECTURE §7: items are produced and gated the night
before, never in the request path. W10 generates nothing at all, so the property
is trivially true today — and it is asserted anyway, because it stops being
trivial the moment the generation slice lands, and because a session that opens
in under a second is the criterion the whole design is arranged around.

`tests/support/netguard.py` is armed session-wide by `conftest.py`, so a
provider call inside a request would raise rather than pass silently. That is
how we know, rather than by reading the router.
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
from core.sessions import BLOCK_KINDS
from core.services import cards as cards_svc


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
        VALUES (%s, 'W10 Route', 'lt', TRUE, 'B1', %s, %s, 'Europe/Vilnius')
        RETURNING id
        """,
        (
            telegram_user_id,
            f"w10r-{abs(telegram_user_id)}@example.test",
            str(uuid.uuid4()),
        ),
    ).fetchone()
    user_id = int(row[0])
    db.execute(
        "INSERT INTO access_requests (telegram_user_id, user_id, display_name, "
        "status) VALUES (%s, %s, 'W10 Route', 'approved')",
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
    db.execute("DELETE FROM card_reviews WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM cards WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM access_requests WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()


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


def _as(learner):
    return {SESSION_COOKIE_SECURE: learner.cookie}


def _seed_due_card(db, learner, **over) -> int:
    now = datetime.now(timezone.utc)
    spec = dict(
        card_type="production",
        front="to eat quickly",
        back="devour",
        register="neutral",
        register_source="import_default",
        meaning="to eat quickly",
        state=cards_svc.CardState(
            fsrs_state="review",
            fsrs_step=None,
            stability=10.0,
            difficulty=5.0,
            due=now - timedelta(days=1),
            last_review=now - timedelta(days=11),
            lapses=0,
            reps=4,
        ),
    )
    spec.update(over)
    card_id = cards_svc.create_card(db, learner.user_id, **spec)
    db.commit()
    assert card_id is not None
    return card_id


# ── the route ───────────────────────────────────────────────────────────────


def test_the_session_requires_a_session(app) -> None:
    assert request(app, "GET", "/session/today").status_code == 401


def test_the_session_serves_prd_4_1s_five_blocks(app, db, learner) -> None:
    """User action: tapping *Start today's session* on home."""
    response = request(app, "GET", "/session/today", cookies=_as(learner))
    assert response.status_code == 200
    body = response.json()
    assert [b["kind"] for b in body["blocks"]] == list(BLOCK_KINDS)
    assert [b["n"] for b in body["blocks"]] == [1, 2, 3, 4, 5]


def test_nothing_is_generated_while_the_learner_waits(app, db, learner) -> None:
    """ARCHITECTURE §7, asserted rather than described.

    `tests/support/netguard.py` is armed for the whole session by `conftest.py`,
    so any outbound call — a model, a speech provider, anything — raises inside
    the request. This test passes because the route makes none, not because
    nobody looked.
    """
    assert request(app, "GET", "/session/today", cookies=_as(learner)).status_code == 200


def test_the_l1_is_on_the_envelope_and_is_the_learners_own(app, db, learner) -> None:
    """#159. This learner is `lt`, and before W10 a Lithuanian gloss would have
    been labelled English by a script test with no visible symptom."""
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    assert body["l1_language"] == "lt"


def test_no_murphy_citation_reaches_the_wire(app, db, learner) -> None:
    """#171 as extended by #183, at the HTTP boundary.

    Block 3 serialises a unit's grammar targets and every one of them carries a
    `murphy_units` in the database. The whole response is searched, not just the
    focus block, because a payload is the thing a surface renders and a surface
    cannot render what never arrived.
    """
    raw = request(app, "GET", "/session/today", cookies=_as(learner)).text
    assert "murphy" not in raw.lower()


def test_block_one_is_empty_and_says_so_distinctly(app, db, learner) -> None:
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    review = body["blocks"][0]
    assert review["state"] == "empty"
    # `empty` is a fact, and it carries nothing. `unavailable` is a different
    # answer entirely and no block returns it here.
    assert review["payload"] == {}
    assert all(b["state"] != "unavailable" for b in body["blocks"])


def test_a_due_card_arrives_inside_block_one(app, db, learner) -> None:
    """#160: the deck lives in the session, not behind a tab with a counter."""
    card_id = _seed_due_card(db, learner)
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    review = body["blocks"][0]
    assert review["state"] == "ready"
    assert [c["id"] for c in review["payload"]["cards"]] == [card_id]
    assert review["payload"]["cards"][0]["typed"] is True


def test_the_session_carries_no_backlog_number_anywhere(app, db, learner) -> None:
    """CLAUDE.md §4. Nothing in this payload counts what was not done."""
    _seed_due_card(db, learner)
    body = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    assert "counts" not in body
    for block in body["blocks"]:
        for banned in ("total_remaining", "due_now", "overdue", "carried"):
            assert banned not in block["payload"]


# ── resume ──────────────────────────────────────────────────────────────────


def test_completing_a_block_survives_a_new_request(app, db, learner) -> None:
    """The phone-lock check, in the suite. Resume state is on the SERVER."""
    session_id = request(
        app, "GET", "/session/today", cookies=_as(learner)
    ).json()["session_id"]

    done = request(
        app, "POST", f"/session/{session_id}/block/2/complete", cookies=_as(learner)
    )
    assert done.status_code == 200
    assert done.json()["blocks"][1]["state"] == "done"

    again = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    assert again["session_id"] == session_id
    assert again["blocks"][1]["state"] == "done"


def test_opening_the_session_twice_returns_the_same_row(app, db, learner) -> None:
    first = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    second = request(app, "GET", "/session/today", cookies=_as(learner)).json()
    assert first["session_id"] == second["session_id"]


def test_a_block_outside_the_five_is_refused(app, db, learner) -> None:
    session_id = request(
        app, "GET", "/session/today", cookies=_as(learner)
    ).json()["session_id"]
    for n in (0, 6, 99):
        response = request(
            app, "POST", f"/session/{session_id}/block/{n}/complete",
            cookies=_as(learner),
        )
        assert response.status_code == 422


def test_someone_elses_session_is_a_404(app, db, learner) -> None:
    """404 covers "no such session", "not yours" and "not a daily session" —
    telling a caller that an id exists but belongs to someone else is a fact
    about the other learner."""
    response = request(
        app, "POST", "/session/999999999/block/1/complete", cookies=_as(learner)
    )
    assert response.status_code == 404


def test_the_block_route_requires_a_session(app) -> None:
    assert request(app, "POST", "/session/1/block/1/complete").status_code == 401


# ── #157 through the route ──────────────────────────────────────────────────


def test_a_typed_attempt_is_graded_on_the_server(app, db, learner) -> None:
    card_id = _seed_due_card(db, learner)
    headers = {"content-type": "application/json"}
    right = request(
        app, "POST", f"/review/{card_id}/attempt",
        json_body={"text": "Devour."}, cookies=_as(learner), headers=headers,
    )
    assert right.status_code == 200
    assert right.json() == {"matched": True}

    wrong = request(
        app, "POST", f"/review/{card_id}/attempt",
        json_body={"text": "eat"}, cookies=_as(learner), headers=headers,
    )
    assert wrong.json() == {"matched": False}


def test_the_attempt_route_writes_nothing(app, db, learner) -> None:
    """It is a read. The attempt is recorded by the grade call, which recomputes
    the verdict rather than trusting one the client carries back."""
    card_id = _seed_due_card(db, learner)
    request(
        app, "POST", f"/review/{card_id}/attempt",
        json_body={"text": "devour"}, cookies=_as(learner),
        headers={"content-type": "application/json"},
    )
    reviews = db.execute(
        "SELECT count(*) FROM card_reviews WHERE card_id = %s", (card_id,)
    ).fetchone()[0]
    assert reviews == 0


def test_the_attempt_route_refuses_a_form_body(app, db, learner) -> None:
    """The CSRF barrier is that a state-changing route is a JSON POST, which
    always preflights, and the preflight is answered only for the two allowed
    origins. Making the refusal the route's own decision is what survives
    someone later adding a `Form(...)` parameter."""
    card_id = _seed_due_card(db, learner)
    response = request(
        app, "POST", f"/review/{card_id}/attempt",
        json_body={"text": "devour"}, cookies=_as(learner),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 415


def test_a_grade_from_inside_the_session_carries_both(app, db, learner) -> None:
    card_id = _seed_due_card(db, learner)
    session_id = request(
        app, "GET", "/session/today", cookies=_as(learner)
    ).json()["session_id"]

    response = request(
        app, "POST", f"/review/{card_id}/grade",
        json_body={
            "rating": "good",
            "session_id": session_id,
            "typed_response": "Devour",
        },
        cookies=_as(learner),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200

    row = db.execute(
        "SELECT session_id, typed_response, typed_matched FROM card_reviews "
        "WHERE card_id = %s",
        (card_id,),
    ).fetchone()
    assert row[0] == session_id
    assert row[1] == "Devour"
    # Recomputed here, never taken from the client.
    assert row[2] is True


def test_a_grade_from_review_carries_no_session(app, db, learner) -> None:
    """#160 keeps `/review` reachable outside the session, which is why
    `card_reviews.session_id` is nullable — the same reason
    `item_attempts.session_id` is."""
    card_id = _seed_due_card(db, learner)
    request(
        app, "POST", f"/review/{card_id}/grade",
        json_body={"rating": "good"},
        cookies=_as(learner),
        headers={"content-type": "application/json"},
    )
    stored = db.execute(
        "SELECT session_id FROM card_reviews WHERE card_id = %s", (card_id,)
    ).fetchone()[0]
    assert stored is None


def test_an_attempt_on_someone_elses_card_is_a_404(app, db, learner) -> None:
    response = request(
        app, "POST", "/review/999999999/attempt",
        json_body={"text": "devour"}, cookies=_as(learner),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 404
