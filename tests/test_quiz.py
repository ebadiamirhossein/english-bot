"""Quiz grading, mark_result once, abandon, free_practice idempotency (S3)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db import close_pool, connection
from app.handlers import quiz as quiz_handler
from app.handlers.quiz import grade_answer, normalize_answer
from app.services.errors import mark_result
from app.services.users import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_310_000_000


@pytest.fixture
def fake_telegram_id() -> int:
    return FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)


@pytest.fixture(autouse=True)
def _close_pool_after_test() -> None:
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


def _onboard(tid: int, *, morning: str = "07:00", tz: str = "Europe/Vilnius") -> None:
    save_onboarding(
        tid,
        {
            "name": "Quiz Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": morning,
            "evening_time": "21:00",
        },
    )
    with connection() as conn:
        conn.execute(
            "UPDATE users SET timezone = %s WHERE telegram_user_id = %s",
            (tz, tid),
        )


def _insert_error(tid: int, *, next_review: date | None = None) -> int:
    review = next_review if next_review is not None else date.today()
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO errors (
                user_id, source, you_said, correct_form, error_type,
                explanation, next_review
            ) VALUES (
                %s, 'text', 'so much good', 'very good',
                'quantifier_modifier', 'Use very.', %s
            )
            RETURNING id
            """,
            (tid, review),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _sessions(tid: int) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT task_type, completed, date
              FROM sessions WHERE user_id = %s ORDER BY id
            """,
            (tid,),
        ).fetchall()
    return [dict(r) for r in rows]


def _next_review(error_id: int) -> date:
    with connection() as conn:
        row = conn.execute(
            "SELECT next_review FROM errors WHERE id = %s",
            (error_id,),
        ).fetchone()
    assert row is not None
    return row["next_review"]


def test_grading_normalisation() -> None:
    accept = ["isn't", "is not", "isnt"]
    assert grade_answer("Isn't", accept)
    assert grade_answer("isn't ", accept)
    assert grade_answer("isnt", accept)
    assert grade_answer("is not", accept)
    assert grade_answer("Isn't.", accept)
    assert grade_answer("isn\u2019t", accept)  # curly apostrophe
    assert not grade_answer("aren't", accept)
    assert normalize_answer("  Is NOT  ") == "is not"


def test_answer_calls_mark_result_once(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    eid = _insert_error(tid, next_review=date.today())
    today = date.today()
    payload = {
        "index": 0,
        "correct_count": 0,
        "answered": 0,
        "questions": [
            {
                "error_id": eid,
                "format": "gap",
                "prompt": "It ___ very good.",
                "accept": ["isn't", "is not"],
                "answer": "isn't",
                "error_type": "quantifier_modifier",
                "explanation": "Use very.",
            }
        ],
        "chat_id": tid,
        "message_id": 1,
        "session_id": 0,
    }
    from psycopg.types.json import Jsonb

    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO sessions (
                user_id, date, task_type, delivered_at, completed, payload
            ) VALUES (%s, %s, 'quiz', NOW(), FALSE, %s)
            RETURNING id
            """,
            (tid, today, Jsonb(payload)),
        ).fetchone()
    assert row is not None
    session_id = int(row["id"])
    payload["session_id"] = session_id
    with connection() as conn:
        conn.execute(
            "UPDATE sessions SET payload = %s WHERE id = %s",
            (Jsonb(payload), session_id),
        )

    context = MagicMock()
    context.bot.edit_message_text = AsyncMock()

    with patch.object(quiz_handler, "mark_result", wraps=mark_result) as mocked:
        asyncio.run(
            quiz_handler._advance_after_answer(
                context,
                tid,
                session_id,
                payload,
                correct=True,
                question=payload["questions"][0],
            )
        )
        assert mocked.call_count == 1
        mocked.assert_called_with(eid, True)


def test_abandon_leaves_remaining_untouched(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    today = date.today()
    ids = [_insert_error(tid, next_review=today) for _ in range(5)]
    reviews_before = {eid: _next_review(eid) for eid in ids}

    # Answer only first two via mark_result (simulate); leave 3–5 alone.
    mark_result(ids[0], True)
    mark_result(ids[1], False)

    for eid in ids[2:]:
        assert _next_review(eid) == reviews_before[eid]


def test_zero_due_errors_free_practice_once(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid, morning="00:00", tz="UTC")
    # Future review only — nothing due
    _insert_error(tid, next_review=date.today() + timedelta(days=10))

    app = MagicMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)

    action1 = asyncio.run(quiz_handler.deliver_morning(app, tid, now=now))
    assert action1 == "free_practice"
    assert app.bot.send_message.await_count == 1

    sessions = _sessions(tid)
    assert len(sessions) == 1
    assert sessions[0]["task_type"] == "free_practice"
    assert sessions[0]["completed"] is False
    assert not any(s["task_type"] == "quiz" for s in sessions)

    # Next poll five minutes later must not send again
    action2 = asyncio.run(
        quiz_handler.deliver_morning(app, tid, now=now + timedelta(minutes=5))
    )
    assert action2 == "skipped_existing"
    assert app.bot.send_message.await_count == 1
    assert len(_sessions(tid)) == 1

    # And eligibility must exclude the user
    from app.scheduler import users_due_for_morning

    due_ids = [u.telegram_user_id for u in users_due_for_morning(now + timedelta(minutes=5))]
    assert tid not in due_ids
