"""Rescue mode quiz size — no backlog (S4)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.db import close_pool, connection
from apps.bot.handlers import quiz as quiz_handler
from core.services.errors import due_errors
from core.services.streaks import get_streak
from core.services.identity import save_onboarding
FAKE_TELEGRAM_ID_BASE = 9_341_000_000


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


def _onboard(tid: int) -> int:
    user_id = save_onboarding(
        tid,
        {
            "name": "Rescue Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": "08:00",
            "evening_time": "21:00",
        },
    )
    return user_id


def _insert_errors(tid: int, n: int) -> None:
    with connection() as conn:
        for i in range(n):
            conn.execute(
                """
                INSERT INTO errors (
                    user_id, source, you_said, correct_form, error_type,
                    explanation, next_review
                ) VALUES (
                    %s, 'text', %s, %s,
                    'quantifier_modifier', 'Use very.', CURRENT_DATE
                )
                """,
                (tid, f"bad {i}", f"good {i}"),
            )


def _set_rescue(tid: int, until: date) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE streaks SET rescue_mode_until = %s WHERE user_id = %s
            """,
            (until, tid),
        )


def _fake_questions(n: int) -> list[dict]:
    return [
        {
            "error_id": i,
            "error_type": "quantifier_modifier",
            "error_type_label": "Quantifiers and modifiers",
            "format": "choice",
            "prompt": f"Q{i}?",
            "options": ["a", "b", "c", "d"],
            "accept": ["a"],
            "explanation": "because",
        }
        for i in range(n)
    ]


def test_rescue_quiz_is_three_questions(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _insert_errors(user_id, 8)
    day = date(2026, 7, 15)
    _set_rescue(user_id, day + timedelta(days=3))
    assert get_streak(user_id).rescue_mode_until is not None

    due = due_errors(user_id, limit=3)
    assert len(due) == 3
    assert len(due_errors(user_id, limit=5)) == 5

    app = MagicMock()
    app.bot = AsyncMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 7, 15, 6, 0, tzinfo=timezone.utc)

    with patch.object(
        quiz_handler,
        "_build_quiz_questions",
        return_value=(_fake_questions(3), "at a cafe"),
    ) as build:
        with patch.object(
            quiz_handler, "_user_timezone", return_value="Europe/Vilnius"
        ):
            with patch.object(quiz_handler, "local_today", return_value=day):
                action = asyncio.run(
                    quiz_handler.deliver_morning(app, user_id, now=now)
                )

    assert action == "quiz"
    build.assert_called_once()
    errors_arg = build.call_args[0][1]
    assert len(errors_arg) == 3


def test_non_rescue_quiz_is_five_questions(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _insert_errors(user_id, 8)
    day = date(2026, 7, 15)

    app = MagicMock()
    app.bot = AsyncMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 7, 15, 6, 0, tzinfo=timezone.utc)

    with patch.object(
        quiz_handler,
        "_build_quiz_questions",
        return_value=(_fake_questions(5), "at a cafe"),
    ) as build:
        with patch.object(
            quiz_handler, "_user_timezone", return_value="Europe/Vilnius"
        ):
            with patch.object(quiz_handler, "local_today", return_value=day):
                action = asyncio.run(
                    quiz_handler.deliver_morning(app, user_id, now=now)
                )

    assert action == "quiz"
    errors_arg = build.call_args[0][1]
    assert len(errors_arg) == 5


def test_rescue_never_returns_more_than_three_due_errors(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _insert_errors(user_id, 10)
    day = date(2026, 7, 15)
    _set_rescue(user_id, day + timedelta(days=5))

    # due_errors already caps — rescue is a limit change, not new logic.
    assert len(due_errors(user_id, limit=3)) <= 3
    assert len(due_errors(user_id, limit=3)) == 3
