"""Correction flow + record_errors tests (live Postgres :5433, mocked LLM)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.db import close_pool, connection
from core.services.errors import record_errors
from core.services.identity import save_onboarding


FAKE_TELEGRAM_ID_BASE = 9_100_000_000


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
            "name": "Corr Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Talk to clients without freezing",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": "08:00",
            "evening_time": "21:00",
        },
    )
    return user_id


def _set_fallback(user_id: int, value: bool) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE users
               SET explanation_language_fallback = %s
             WHERE id = %s
            """,
            (value, user_id),
        )


def _count_errors(tid: int) -> int:
    with connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM errors WHERE user_id = %s",
            (tid,),
        ).fetchone()
    return int(row["n"])


def _fetch_errors(tid: int) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT you_said, correct_form, error_type, source, next_review
              FROM errors
             WHERE user_id = %s
             ORDER BY id
            """,
            (tid,),
        ).fetchall()
    return list(rows)


def _make_update(tid: int, text: str) -> MagicMock:
    update = MagicMock()
    update.effective_user = MagicMock(id=tid)
    update.message = MagicMock()
    update.message.text = text
    update.message.chat_id = tid
    update.message.from_user = MagicMock(id=tid)
    update.message.reply_text = AsyncMock()
    return update


def _make_context() -> MagicMock:
    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    return context


def test_record_two_corrections_writes_two_rows(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    corrections = [
        {
            "you_said": "her english is not so much good",
            "correct_form": "her English isn't very good",
            "error_type": "quantifier_modifier",
            "explanation": '"so much" doesn\'t go before adjectives.',
        },
        {
            "you_said": "I go yesterday",
            "correct_form": "I went yesterday",
            "error_type": "verb_tense_past",
            "explanation": "Use the past form for yesterday.",
        },
    ]
    written = record_errors(user_id, "text", corrections)
    assert written == 2
    rows = _fetch_errors(user_id)
    assert len(rows) == 2
    assert all(r["source"] == "text" for r in rows)
    tomorrow = date.today() + timedelta(days=1)
    assert all(r["next_review"] == tomorrow for r in rows)


def test_invalid_error_type_dropped(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    corrections = [
        {
            "you_said": "bad invent",
            "correct_form": "ok",
            "error_type": "not_a_real_type",
            "explanation": "x",
        },
        {
            "you_said": "I go yesterday",
            "correct_form": "I went yesterday",
            "error_type": "verb_tense_past",
            "explanation": "Past form.",
        },
    ]
    written = record_errors(user_id, "text", corrections)
    assert written == 1
    rows = _fetch_errors(user_id)
    assert len(rows) == 1
    assert rows[0]["error_type"] == "verb_tense_past"


