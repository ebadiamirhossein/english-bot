"""Reading engine delivery + chunks (S9a)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db import close_pool, connection
from app.handlers.reading import deliver_evening, init_reading_prompt
from app.scheduler import (
    EligibleUser,
    is_user_due_for_evening,
    is_user_due_for_morning,
)
from app.services.interests import list_interests, replace_interests, select_topic
from app.services.reading import (
    ReadingValidationError,
    normalize_for_match,
    validate_reading_payload,
)
from app.services.sessions import (
    bot_initiated_count,
    has_reading_session_on,
    has_session_on,
    increment_bot_messages,
    insert_session,
    local_today,
)
from app.services.users import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_460_000_000

# Monday 2026-08-03 — a reading day.
_MONDAY_EVENING_UTC = datetime(2026, 8, 3, 18, 5, tzinfo=timezone.utc)  # 21:05 Vilnius
# Tuesday — not a reading day.
_TUESDAY_EVENING_UTC = datetime(2026, 8, 4, 18, 5, tzinfo=timezone.utc)


@pytest.fixture
def fake_telegram_id() -> int:
    return FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)


@pytest.fixture(autouse=True)
def _close_pool_after_test() -> None:
    init_reading_prompt()
    yield
    close_pool()


def _delete_user(telegram_user_id: int) -> None:
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM users WHERE telegram_user_id = %s",
                (telegram_user_id,),
            )


@pytest.fixture
def cleanup_user(fake_telegram_id: int):
    yield fake_telegram_id
    _delete_user(fake_telegram_id)


def _onboard(
    tid: int,
    *,
    evening: str = "21:00",
    morning: str = "07:00",
    tz: str = "Europe/Vilnius",
    track_weights: dict[str, int] | None = None,
) -> None:
    save_onboarding(
        tid,
        {
            "name": "Reading Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": track_weights
            or {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": morning,
            "evening_time": evening,
        },
    )
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE users SET timezone = %s WHERE telegram_user_id = %s",
                (tz, tid),
            )


def _seed_interests(tid: int, rows: list[tuple[str, str]]) -> None:
    replace_interests(tid, rows)


def _set_interest_meta(
    tid: int,
    topic: str,
    *,
    weight: float,
    last_used: date | None,
) -> None:
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                UPDATE interests
                   SET weight = %s, last_used = %s
                 WHERE user_id = %s AND topic = %s
                """,
                (weight, last_used, tid, topic),
            )


def _eligible(
    tid: int,
    *,
    tz: str = "Europe/Vilnius",
    evening: str = "21:00",
    morning: str = "07:00",
) -> EligibleUser:
    eh, em = map(int, evening.split(":"))
    mh, mm = map(int, morning.split(":"))
    return EligibleUser(
        telegram_user_id=tid,
        timezone=tz,
        morning_time=time(mh, mm),
        paused_until=None,
        evening_time=time(eh, em),
    )


def _words(n: int, seed: str = "word") -> str:
    return " ".join(f"{seed}{i}" for i in range(n))


def _valid_llm_payload(
    *,
    chunks: list[dict[str, str]] | None = None,
    body_override: str | None = None,
) -> dict[str, Any]:
    """Build a valid ~300-word body containing five known chunks."""
    phrases = [
        "market research cycle",
        "client email thread",
        "pricing negotiation room",
        "campaign launch window",
        "brand positioning work",
    ]
    if chunks is None:
        chunks = [
            {
                "chunk": phrases[i],
                "full_sentence": f"They discussed the {phrases[i]}.",
                "meaning": f"gloss {i}",
            }
            for i in range(5)
        ]
    filler = _words(280, "alpha")
    body = (
        f"The team opened with the {phrases[0]}. "
        f"Next came a {phrases[1]} that ran late. "
        f"In the {phrases[2]} they settled terms. "
        f"Then the {phrases[3]} closed. "
        f"Finally {phrases[4]} wrapped the week. "
        f"{filler}"
    )
    if body_override is not None:
        body = body_override
    return {
        "title": "A week in marketing",
        "body": body,
        "questions": [
            {
                "question": f"Q{i}?",
                "answer": f"A{i}",
                "distractors": ["x", "y", "z"],
            }
            for i in range(5)
        ],
        "chunks": chunks,
    }


def _count_rows(tid: int) -> tuple[int, int, int]:
    with connection() as conn:
        readings = conn.execute(
            "SELECT COUNT(*) AS n FROM readings WHERE user_id = %s",
            (tid,),
        ).fetchone()["n"]
        chunks = conn.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE user_id = %s",
            (tid,),
        ).fetchone()["n"]
        sessions = conn.execute(
            """
            SELECT COUNT(*) AS n FROM sessions
             WHERE user_id = %s AND task_type = 'reading'
            """,
            (tid,),
        ).fetchone()["n"]
    return int(readings), int(chunks), int(sessions)


def _mock_app(send_side_effect: Exception | None = None) -> MagicMock:
    app = MagicMock()
    send = AsyncMock()
    if send_side_effect is not None:
        send.side_effect = send_side_effect
    app.bot.send_message = send
    return app


# --- Eligibility --------------------------------------------------------------


def test_eligibility_only_mon_wed_fri(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    user = _eligible(tid)
    assert is_user_due_for_evening(user, _MONDAY_EVENING_UTC) is True
    assert is_user_due_for_evening(user, _TUESDAY_EVENING_UTC) is False
    wed = datetime(2026, 8, 5, 18, 5, tzinfo=timezone.utc)
    assert is_user_due_for_evening(user, wed) is True
    fri = datetime(2026, 8, 7, 18, 5, tzinfo=timezone.utc)
    assert is_user_due_for_evening(user, fri) is True
    sun = datetime(2026, 8, 9, 18, 5, tzinfo=timezone.utc)
    assert is_user_due_for_evening(user, sun) is False


def test_eligibility_only_at_or_after_evening_time(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid, evening="21:00")
    user = _eligible(tid, evening="21:00")
    before = datetime(2026, 8, 3, 17, 59, tzinfo=timezone.utc)  # 20:59 Vilnius
    assert is_user_due_for_evening(user, before) is False
    assert is_user_due_for_evening(user, _MONDAY_EVENING_UTC) is True


def test_eligibility_once_per_day(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    user = _eligible(tid)
    day = local_today("Europe/Vilnius", _MONDAY_EVENING_UTC)
    assert is_user_due_for_evening(user, _MONDAY_EVENING_UTC) is True
    insert_session(tid, "reading", day, payload={"reading_id": 1}, completed=False)
    assert has_reading_session_on(tid, day) is True
    assert is_user_due_for_evening(user, _MONDAY_EVENING_UTC) is False


# --- Topic selection ----------------------------------------------------------


def test_topic_selection_prefers_weight_and_older_last_used(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_interests(
        tid,
        [
            ("alpha topic", "work"),
            ("beta topic", "work"),
            ("gamma topic", "life"),
        ],
    )
    today = date(2026, 8, 3)
    _set_interest_meta(
        tid, "alpha topic", weight=1.0, last_used=today - timedelta(days=2)
    )
    _set_interest_meta(
        tid, "beta topic", weight=3.0, last_used=today - timedelta(days=2)
    )
    _set_interest_meta(
        tid, "gamma topic", weight=1.0, last_used=today - timedelta(days=2)
    )

    chosen = select_topic(tid, {"work": 40, "life": 40, "curiosity": 20}, today)
    assert chosen is not None
    assert chosen.topic == "beta topic"


def test_topic_selection_higher_track_weight_wins(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_interests(
        tid,
        [
            ("work topic", "work"),
            ("life topic", "life"),
        ],
    )
    today = date(2026, 8, 3)
    chosen = select_topic(tid, {"work": 60, "life": 25, "curiosity": 15}, today)
    assert chosen is not None
    assert chosen.topic == "work topic"


def test_topic_selection_alpha_tiebreak_stable(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_interests(
        tid,
        [
            ("zebra", "work"),
            ("apple", "work"),
        ],
    )
    today = date(2026, 8, 3)
    weights = {"work": 40, "life": 40, "curiosity": 20}
    first = select_topic(tid, weights, today)
    second = select_topic(tid, weights, today)
    assert first is not None and second is not None
    assert first.topic == "apple"
    assert second.topic == "apple"


def test_last_used_set_on_successful_delivery(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_interests(tid, [("campaigns", "work"), ("travel", "life")])
    app = _mock_app()
    action = asyncio.run(
        deliver_evening(
            app,
            tid,
            now=_MONDAY_EVENING_UTC,
            chat_fn=lambda *a, **k: _valid_llm_payload(),
        )
    )
    assert action == "reading"
    day = local_today("Europe/Vilnius", _MONDAY_EVENING_UTC)
    used = [r for r in list_interests(tid) if r.last_used == day]
    assert len(used) == 1


# --- Validation ---------------------------------------------------------------


def test_chunk_capital_and_apostrophe_normalise() -> None:
    phrases_body = (
        "Market research cycle sits at the centre of every brief. "
        "The client's email thread ran for three days. "
        "A pricing negotiation room held the tension. "
        "The campaign launch window finally opened. "
        "Brand positioning work closed the loop. "
    )
    filler = _words(280)
    body = phrases_body + filler

    raw = {
        "title": "T",
        "body": body,
        "questions": [
            {"question": "q", "answer": "a", "distractors": ["x", "y", "z"]}
            for _ in range(5)
        ],
        "chunks": [
            {
                "chunk": "market research cycle",
                "full_sentence": "Market research cycle sits at the centre.",
                "meaning": "m1",
            },
            {
                "chunk": "client\u2019s email thread",
                "full_sentence": "The client's email thread ran.",
                "meaning": "m2",
            },
            {
                "chunk": "pricing negotiation room",
                "full_sentence": "s",
                "meaning": "m3",
            },
            {
                "chunk": "campaign launch window",
                "full_sentence": "s",
                "meaning": "m4",
            },
            {
                "chunk": "brand positioning work",
                "full_sentence": "s",
                "meaning": "m5",
            },
        ],
    }
    validated = validate_reading_payload(raw)
    assert validated.chunks[0]["chunk"] == "market research cycle"
    assert validated.chunks[1]["chunk"] == "client\u2019s email thread"


def test_normalize_for_match_basics() -> None:
    assert normalize_for_match("Hello  World") == normalize_for_match("hello world")
    assert "don" in normalize_for_match("don\u2019t")


def test_validate_rejects_four_chunks() -> None:
    raw = _valid_llm_payload()
    raw["chunks"] = raw["chunks"][:4]
    with pytest.raises(ReadingValidationError):
        validate_reading_payload(raw)


# --- Delivery paths -----------------------------------------------------------


def test_ceiling_reached_nothing_written(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_interests(tid, [("campaigns", "work"), ("travel", "life")])
    day = local_today("Europe/Vilnius", _MONDAY_EVENING_UTC)
    for _ in range(3):
        increment_bot_messages(tid, day)
    app = _mock_app()
    chat_calls: list[int] = []

    def chat_fn(*a: Any, **k: Any) -> dict:
        chat_calls.append(1)
        return _valid_llm_payload()

    with caplog.at_level(logging.WARNING):
        action = asyncio.run(
            deliver_evening(app, tid, now=_MONDAY_EVENING_UTC, chat_fn=chat_fn)
        )
    assert action == "skipped_ceiling"
    assert chat_calls == []
    assert _count_rows(tid) == (0, 0, 0)
    assert app.bot.send_message.await_count == 0
    assert any("ceiling_reached" in r.message for r in caplog.records)


def test_sending_increments_bot_message_counts(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_interests(tid, [("campaigns", "work"), ("travel", "life")])
    day = local_today("Europe/Vilnius", _MONDAY_EVENING_UTC)
    assert bot_initiated_count(tid, day) == 0
    app = _mock_app()
    action = asyncio.run(
        deliver_evening(
            app,
            tid,
            now=_MONDAY_EVENING_UTC,
            chat_fn=lambda *a, **k: _valid_llm_payload(),
        )
    )
    assert action == "reading"
    assert bot_initiated_count(tid, day) == 1
    assert app.bot.send_message.await_count == 1


def test_reading_session_does_not_block_morning_quiz(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid, morning="07:00")
    day = local_today("Europe/Vilnius", _MONDAY_EVENING_UTC)
    insert_session(
        tid, "reading", day, payload={"reading_id": 99}, completed=False
    )
    assert has_session_on(tid, day) is False
    morning_now = datetime(2026, 8, 3, 4, 15, tzinfo=timezone.utc)  # 07:15 Vilnius
    user = _eligible(tid, morning="07:00")
    assert is_user_due_for_morning(user, morning_now) is True


def test_no_interests_skips_without_llm(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    app = _mock_app()
    calls: list[int] = []

    def chat_fn(*a: Any, **k: Any) -> dict:
        calls.append(1)
        return _valid_llm_payload()

    with caplog.at_level(logging.WARNING):
        action = asyncio.run(
            deliver_evening(app, tid, now=_MONDAY_EVENING_UTC, chat_fn=chat_fn)
        )
    assert action == "skipped_no_interests"
    assert calls == []
    assert _count_rows(tid) == (0, 0, 0)
    assert any("no_interests" in r.message for r in caplog.records)


def test_validation_failure_writes_nothing(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_interests(tid, [("campaigns", "work"), ("travel", "life")])
    app = _mock_app()
    calls = {"n": 0}

    def chat_fn(*a: Any, **k: Any) -> dict:
        calls["n"] += 1
        bad = _valid_llm_payload()
        bad["chunks"] = bad["chunks"][:4]
        return bad

    with caplog.at_level(logging.WARNING):
        action = asyncio.run(
            deliver_evening(app, tid, now=_MONDAY_EVENING_UTC, chat_fn=chat_fn)
        )
    assert action == "skipped_validation_failure"
    assert calls["n"] == 2
    assert _count_rows(tid) == (0, 0, 0)
    assert any("validation" in r.message for r in caplog.records)


def test_chunk_not_in_body_and_body_too_short_write_nothing(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_interests(tid, [("campaigns", "work"), ("travel", "life")])

    bad_chunk = _valid_llm_payload()
    bad_chunk["chunks"][0]["chunk"] = "this phrase is nowhere in the body at all"
    action = asyncio.run(
        deliver_evening(
            _mock_app(),
            tid,
            now=_MONDAY_EVENING_UTC,
            chat_fn=lambda *a, **k: bad_chunk,
        )
    )
    assert action == "skipped_validation_failure"
    assert _count_rows(tid) == (0, 0, 0)

    short = _valid_llm_payload()
    short["body"] = "Too short " + " ".join(c["chunk"] for c in short["chunks"])
    action = asyncio.run(
        deliver_evening(
            _mock_app(),
            tid,
            now=_MONDAY_EVENING_UTC,
            chat_fn=lambda *a, **k: short,
        )
    )
    assert action == "skipped_validation_failure"
    assert _count_rows(tid) == (0, 0, 0)


def test_send_failure_rolls_back_and_stays_eligible(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_interests(tid, [("campaigns", "work"), ("travel", "life")])
    app = _mock_app(send_side_effect=RuntimeError("telegram down"))
    action = asyncio.run(
        deliver_evening(
            app,
            tid,
            now=_MONDAY_EVENING_UTC,
            chat_fn=lambda *a, **k: _valid_llm_payload(),
        )
    )
    assert action == "skipped_send_failed"
    assert _count_rows(tid) == (0, 0, 0)
    assert all(r.last_used is None for r in list_interests(tid))
    user = _eligible(tid)
    assert is_user_due_for_evening(user, _MONDAY_EVENING_UTC) is True


def test_successful_run_writes_exact_rows(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_interests(tid, [("campaigns", "work"), ("travel", "life")])
    app = _mock_app()
    action = asyncio.run(
        deliver_evening(
            app,
            tid,
            now=_MONDAY_EVENING_UTC,
            chat_fn=lambda *a, **k: _valid_llm_payload(),
        )
    )
    assert action == "reading"
    readings, chunks, sessions = _count_rows(tid)
    assert readings == 1
    assert chunks == 5
    assert sessions == 1

    with connection() as conn:
        reading = conn.execute(
            "SELECT title, completed, questions FROM readings WHERE user_id = %s",
            (tid,),
        ).fetchone()
        assert reading["completed"] is False
        assert reading["title"] == "A week in marketing"
        assert len(reading["questions"]) == 5

        chunk_rows = conn.execute(
            "SELECT source, track, exported_to_anki FROM chunks WHERE user_id = %s",
            (tid,),
        ).fetchall()
        assert all(r["exported_to_anki"] is False for r in chunk_rows)
        assert all(str(r["source"]).startswith("reading_") for r in chunk_rows)

        session = conn.execute(
            """
            SELECT payload, completed FROM sessions
             WHERE user_id = %s AND task_type = 'reading'
            """,
            (tid,),
        ).fetchone()
        assert session["completed"] is False
        assert "reading_id" in session["payload"]
