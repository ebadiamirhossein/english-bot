"""W24e — *keep going*: an optional next thing once the session is finished.

**The user action:** a learner who has finished today's session (or opened the
app on a Sunday) sees a short choice — watch another video, talk, a few more
cards, write a few lines — offering only what is actually available, with no
count, no score and no backlog. Operator decision 1 of 2026-09-27; rulings R1
(Sunday is watch-only), R2 (only after the session is finished; *watch* is
assigned, never browsed), R4, R7 (cards only when genuinely due).

Service tests take a fixed ``now`` (CLAUDE.md §3 rule 6); the route tests pin
the router's clock the same way. Every learner and row is removed afterwards.

**RED BEFORE THE CODE (2026-09-27):** `core.services.keep_going`,
`core.sessions.blocks.finished`, `/keep-going` and `/keep-going/watch` did not
exist; every test here failed on import or on a 404.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx
import psycopg
import pytest
from fastapi import FastAPI

from apps.api.deps import SESSION_COOKIE_SECURE
from apps.api.main import create_app
from core.config import load_settings
from core.services import cards as cards_svc
from core.services import keep_going
from core.services import video as video_svc
from core.sessions.blocks import Block, finished
from core.video import assign
from core.video.score import Candidate, rank

TUESDAY = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)   # 12:00 in Vilnius
SUNDAY = datetime(2026, 10, 4, 9, 0, tzinfo=timezone.utc)


# ── finished: derived from the blocks, never from `sessions.completed` ──────


def _blocks(review: str, input_: str, focus: str, output: str) -> tuple[Block, ...]:
    states = {"review": review, "input": input_, "focus": focus, "output": output, "close": "ready"}
    return tuple(Block(n=i + 1, kind=k, state=s) for i, (k, s) in enumerate(states.items()))


@pytest.mark.parametrize("states, expected", [
    (("done", "done", "done", "done"), True),
    (("empty", "done", "empty", "done"), True),     # nothing due, no focus items
    (("empty", "empty", "empty", "empty"), False),  # nothing was done at all
    (("done", "done", "done", "ready"), False),     # block 4 still open
    (("done", "unavailable", "done", "done"), False),  # a block we could not read
])
def test_finished_is_every_block_that_served_something_done(states, expected) -> None:
    assert finished(_blocks(*states)) is expected


# ── the options, at the service ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def empty_pool(monkeypatch):
    """**The pool is EMPTY unless a test says otherwise** — pinned, not read
    from whatever the dev database holds, so *no watch* is this file's fact and
    not the database's. Tests that need a candidate patch `rank_for` again."""
    monkeypatch.setattr(assign, "rank_for", lambda conn, user_id, **_: ([], 0))


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as connection:
        yield connection


@pytest.fixture
def learner(db):
    telegram_user_id = -secrets.randbelow(1_000_000_000) - 1
    user_id = db.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language, onboarded,
                           cefr_level, auth_email, auth_user_id, timezone)
        VALUES (%s, 'W24e Keep Going', 'fa', TRUE, 'B1', %s, %s, 'Europe/Vilnius')
        RETURNING id
        """,
        (telegram_user_id, f"w24e-{abs(telegram_user_id)}@example.test", str(uuid.uuid4())),
    ).fetchone()[0]
    db.execute(
        "INSERT INTO access_requests (telegram_user_id, user_id, display_name, status) "
        "VALUES (%s, %s, 'W24e', 'approved')",
        (telegram_user_id, user_id),
    )
    raw = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (hashlib.sha256(raw.encode()).digest(), user_id,
         datetime.now(timezone.utc) + timedelta(days=30)),
    )
    db.commit()
    yield type("L", (), {"user_id": user_id, "cookie": raw})()
    db.rollback()
    for table in ("card_reviews", "cards", "conversation_usage", "writing_submissions",
                  "video_assignments", "video_coverage", "access_requests"):
        db.execute(f"DELETE FROM {table} WHERE user_id = %s", (user_id,))
    db.execute("DELETE FROM videos WHERE youtube_id LIKE 'w24ekg%%'")
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()


def _due_card(db, learner, now: datetime) -> None:
    cards_svc.create_card(
        db, learner.user_id, card_type="production", front="to eat quickly",
        back="devour", register="neutral", register_source="import_default",
        meaning="to eat quickly",
        state=cards_svc.CardState(
            fsrs_state="review", fsrs_step=None, stability=10.0, difficulty=5.0,
            due=now - timedelta(days=1), last_review=now - timedelta(days=11),
            lapses=0, reps=4,
        ),
    )
    db.commit()


def test_a_tuesday_with_nothing_due_offers_talk_and_write(learner) -> None:
    """The pool is empty (pinned above), no card is due: no *watch*, no
    *cards* — an option that would open onto nothing is not offered."""
    assert keep_going.options(learner.user_id, now=TUESDAY) == ("talk", "write")


def test_a_due_card_adds_cards(db, learner) -> None:
    _due_card(db, learner, TUESDAY)
    assert keep_going.options(learner.user_id, now=TUESDAY) == ("talk", "cards", "write")


def test_sunday_offers_nothing_but_watch(db, learner) -> None:
    """R1. A due card and open caps change nothing on a Sunday: the only thing
    Sunday may offer is free input — and here the pool is empty, so nothing."""
    _due_card(db, learner, SUNDAY)
    assert keep_going.options(learner.user_id, now=SUNDAY) == ()


def test_a_reached_cap_removes_its_option_silently(db, learner) -> None:
    cfg = load_settings()
    local = date(2026, 9, 29)
    db.execute(
        "INSERT INTO conversation_usage (user_id, local_date, turns_learner) VALUES (%s, %s, %s)",
        (learner.user_id, local, cfg.conversation_max_turns_per_day),
    )
    for _ in range(cfg.writing_max_submissions_per_day):
        db.execute(
            "INSERT INTO writing_submissions (user_id, day_kind, local_date, is_english, "
            "llm_input_tokens, llm_output_tokens, llm_cache_creation_input_tokens, "
            "llm_cache_read_input_tokens) VALUES (%s, 'journal', %s, TRUE, 0, 0, 0, 0)",
            (learner.user_id, local),
        )
    db.commit()
    assert keep_going.options(learner.user_id, now=TUESDAY) == ()


def _in_band_video(db, youtube_id: str) -> int:
    video = video_svc.upsert_video(
        db, youtube_id=youtube_id, channel_id="UCw24e000000000000000000",
        accent="british", track="life", title="A W24e probe", duration_s=300,
        published_at=TUESDAY, now=TUESDAY,
    )
    db.commit()
    return video


def _ranked_with(video: int, youtube_id: str):
    return rank([Candidate(video_id=video, youtube_id=youtube_id, track="life",
                           accent="british", duration_s=300, coverage=0.955,
                           proper_nouns_detected=True)],
                track_weights={"life": 50, "curiosity": 30, "work": 20},
                accent_exposure={}, targets=frozenset())


def test_watch_assigns_one_extra_and_then_reopens_it(db, learner, monkeypatch) -> None:
    """R2: *watch another* is assigned by the selection score. A second tap
    reopens the same extra — at most one a day (migration 034) — and once it is
    finished, *watch* is no longer offered."""
    video = _in_band_video(db, "w24ekg0001")
    monkeypatch.setattr(assign, "rank_for", lambda conn, user_id, **_: (_ranked_with(video, "w24ekg0001"), 1))
    assert "watch" in keep_going.options(learner.user_id, now=TUESDAY)
    first = keep_going.watch(learner.user_id, now=TUESDAY)
    assert first is not None and first.video["video_id"] == video
    assert first.l1_language == "fa"
    again = keep_going.watch(learner.user_id, now=TUESDAY)
    assert again.video["video_id"] == video
    assert db.execute(
        "SELECT count(*) FROM video_assignments WHERE user_id = %s AND kind = 'extra'",
        (learner.user_id,),
    ).fetchone()[0] == 1
    db.execute("UPDATE video_assignments SET completed_at = %s WHERE user_id = %s",
               (TUESDAY, learner.user_id))
    db.commit()
    assert "watch" not in keep_going.options(learner.user_id, now=TUESDAY)
    assert keep_going.watch(learner.user_id, now=TUESDAY) is None


def test_sundays_watch_is_the_days_own_video_first(db, learner, monkeypatch) -> None:
    """R3: Sunday's video is assigned by the worker and reachable only here and
    through *practise anyway* — so Sunday's *watch* opens it before any extra."""
    daily = _in_band_video(db, "w24ekg0002")
    video_svc.assign_video(db, user_id=learner.user_id, video_id=daily,
                           assigned_for=date(2026, 10, 4), score_breakdown={})
    db.commit()
    monkeypatch.setattr(assign, "rank_for", lambda *a, **k: pytest.fail("ranked on Sunday"))
    assert keep_going.options(learner.user_id, now=SUNDAY) == ("watch",)
    assert keep_going.watch(learner.user_id, now=SUNDAY).video["video_id"] == daily


# ── the routes, through the ASGI transport (CLAUDE.md §3 rule 1) ────────────


@pytest.fixture(autouse=True)
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_ORIGINS", "http://localhost:3000")


@pytest.fixture
def app(monkeypatch) -> FastAPI:
    import apps.api.routers.keep_going as router

    monkeypatch.setattr(router, "_now", lambda: TUESDAY)
    return create_app()


def _request(app, method, path, *, cookies=None):
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver",
                                     cookies=cookies) as http:
            return await http.request(method, path)

    return asyncio.run(_go())


def test_both_routes_need_a_session(app) -> None:
    assert _request(app, "GET", "/keep-going").status_code == 401
    assert _request(app, "POST", "/keep-going/watch").status_code == 401


def test_the_options_route_carries_kinds_and_no_number(app, learner) -> None:
    response = _request(app, "GET", "/keep-going", cookies={SESSION_COOKIE_SECURE: learner.cookie})
    assert response.status_code == 200
    body = response.json()
    assert body == {"options": ["talk", "write"]}
    assert all(isinstance(v, str) for v in body["options"]), "no count may cross the wire"


def test_nothing_to_watch_is_a_404_and_writes_nothing(app, db, learner) -> None:
    response = _request(app, "POST", "/keep-going/watch",
                        cookies={SESSION_COOKIE_SECURE: learner.cookie})
    assert response.status_code == 404
    assert response.json() == {"detail": "nothing_to_watch"}
    assert db.execute("SELECT count(*) FROM video_assignments WHERE user_id = %s",
                      (learner.user_id,)).fetchone()[0] == 0


def test_the_session_says_finished_and_never_writes_completed(app, db, learner) -> None:
    """`finished` is on the wire; `sessions.completed` stays unwritten (#259,
    #361 are not touched by W24e)."""
    import apps.api.routers.session  # noqa: F401  (the session route's own clock is real)

    response = _request(app, "GET", "/session/today", cookies={SESSION_COOKIE_SECURE: learner.cookie})
    assert response.status_code == 200
    assert response.json()["finished"] is False
    assert db.execute(
        "SELECT bool_or(completed) FROM sessions WHERE user_id = %s", (learner.user_id,)
    ).fetchone()[0] is False
    db.execute("DELETE FROM sessions WHERE user_id = %s", (learner.user_id,))
    db.commit()


# ── #462: a conversation counts as block 4 (operator ruling, 2026-09-27) ────
#
# **The user action:** a learner talks on `/talk` instead of writing. With three
# or more learner turns (typed or voice) on their local day, block 4 is done for
# that day exactly as a writing submission makes it, so the session can read
# finished and keep going appears. Derived from `conversation_usage.turns_learner`
# — the metering row the conversation already writes — and **no journal write
# is added.**
#
# **RED BEFORE THE CODE (2026-09-27):** `_derive_done`'s output branch read only
# `writing_submissions`, so the 3-turn cases below read `ready` / `finished is
# False`; the 2-turn case and the Sunday case were green before and are shown
# red by mutation (recorded in the decisions log, W24r (B)).

TUESDAY_LOCAL = date(2026, 9, 29)
SUNDAY_LOCAL = date(2026, 10, 4)


def _talked(db, learner, local: date, turns: int) -> None:
    db.execute(
        "INSERT INTO conversation_usage (user_id, local_date, turns_learner, turns_app) "
        "VALUES (%s, %s, %s, %s)",
        (learner.user_id, local, turns, turns),
    )
    db.commit()


def _clear_sessions(db, learner) -> None:
    db.execute("DELETE FROM sessions WHERE user_id = %s", (learner.user_id,))
    db.commit()


def _state(session, kind: str) -> str:
    return next(b.state for b in session.blocks if b.kind == kind)


def _block_three_done(db, learner) -> None:
    """The dev database holds no items, so block 3 serves the unit's teaching
    and stays `ready`. A learner who finished it has `focus: done` in the stored
    breakdown — the resume state `today` honours (a stored `done` wins) — so
    that is what is written, rather than a builder being stubbed."""
    db.execute(
        "UPDATE sessions SET block_breakdown = COALESCE(block_breakdown, '{}'::jsonb) "
        "|| '{\"focus\": \"done\"}'::jsonb WHERE user_id = %s AND task_type = 'daily'",
        (learner.user_id,),
    )
    db.commit()


def test_two_learner_turns_do_not_finish_block_four(db, learner) -> None:
    from core.services import sessions as sessions_svc

    _talked(db, learner, TUESDAY_LOCAL, 2)
    try:
        session = sessions_svc.today(learner.user_id, now=TUESDAY)
        assert _state(session, "output") == "ready"
        assert session.finished is False
    finally:
        _clear_sessions(db, learner)


def test_three_learner_turns_finish_block_four_and_the_session(db, learner) -> None:
    """No card is due, no video is assigned and block 3 is done, so block 4 is
    the only block still open: three turns make it `done` and the session
    `finished`."""
    from core.services import sessions as sessions_svc

    sessions_svc.today(learner.user_id, now=TUESDAY)
    _block_three_done(db, learner)
    before = sessions_svc.today(learner.user_id, now=TUESDAY)
    assert [(b.kind, b.state) for b in before.blocks if b.kind != "close"] == [
        ("review", "empty"), ("input", "empty"), ("focus", "done"), ("output", "ready"),
    ], "the premise: block 4 is the only block still open"
    assert before.finished is False
    _talked(db, learner, TUESDAY_LOCAL, 3)
    try:
        session = sessions_svc.today(learner.user_id, now=TUESDAY)
        assert _state(session, "output") == "done"
        assert session.finished is True
    finally:
        _clear_sessions(db, learner)


def test_turns_on_another_day_do_not_count(db, learner) -> None:
    """The learner's LOCAL date keys both tables: yesterday's conversation is
    not today's block 4."""
    from core.services import sessions as sessions_svc

    _talked(db, learner, TUESDAY_LOCAL - timedelta(days=1), 5)
    try:
        assert _state(sessions_svc.today(learner.user_id, now=TUESDAY), "output") == "ready"
    finally:
        _clear_sessions(db, learner)


def test_talking_writes_no_journal_row(db, learner) -> None:
    """Deriving block 4 from the conversation adds no writer: `errors` and
    `writing_submissions` are untouched by the hydration."""
    from core.services import sessions as sessions_svc

    _talked(db, learner, TUESDAY_LOCAL, 3)
    try:
        sessions_svc.today(learner.user_id, now=TUESDAY)
        for table in ("errors", "writing_submissions"):
            assert db.execute(f"SELECT count(*) FROM {table} WHERE user_id = %s",
                              (learner.user_id,)).fetchone()[0] == 0, table
    finally:
        _clear_sessions(db, learner)


def test_after_three_turns_the_route_says_finished_and_keep_going_appears(
    app, db, learner, monkeypatch
) -> None:
    """Through the ASGI transport: `/session/today` carries `finished: true`
    (the client's gate for the done state and keep going, W24e R2) and
    `/keep-going` offers the choices for that same day."""
    import apps.api.routers.session as session_router

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return TUESDAY

    monkeypatch.setattr(session_router, "datetime", _Clock)
    cookies = {SESSION_COOKIE_SECURE: learner.cookie}
    try:
        _request(app, "GET", "/session/today", cookies=cookies)
        _block_three_done(db, learner)
        assert _request(app, "GET", "/session/today", cookies=cookies).json()["finished"] is False
        _talked(db, learner, TUESDAY_LOCAL, 3)
        body = _request(app, "GET", "/session/today", cookies=cookies).json()
        assert body["finished"] is True
        output = next(b for b in body["blocks"] if b["kind"] == "output")
        assert output["state"] == "done"
        options = _request(app, "GET", "/keep-going", cookies=cookies).json()["options"]
        assert options == ["talk", "write"]
    finally:
        _clear_sessions(db, learner)


def test_sunday_is_unaffected_by_a_conversation(db, learner) -> None:
    """R1 stands: however much the learner talked, Sunday offers nothing but
    *watch* (and the pool is empty here, so nothing)."""
    _talked(db, learner, SUNDAY_LOCAL, 3)
    assert keep_going.options(learner.user_id, now=SUNDAY) == ()
