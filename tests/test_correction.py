"""Correction flow + record_errors tests (live Postgres :5433, mocked LLM)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db import close_pool, connection
from app.handlers import correction as correction_handler
from app.handlers.correction import (
    ABSTRACT_ERROR_TYPES,
    build_system_prompt,
    init_correction_prompt,
    murphy_lookup,
)
from app.services.errors import record_errors
from app.services.users import get_user, save_onboarding
from app import texts


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


def _onboard(tid: int) -> None:
    save_onboarding(
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


def _set_fallback(tid: int, value: bool) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE users
               SET explanation_language_fallback = %s
             WHERE telegram_user_id = %s
            """,
            (value, tid),
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


@pytest.fixture(autouse=True)
def _init_prompt() -> None:
    init_correction_prompt()


def test_record_two_corrections_writes_two_rows(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
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
    written = record_errors(tid, "text", corrections)
    assert written == 2
    rows = _fetch_errors(tid)
    assert len(rows) == 2
    assert all(r["source"] == "text" for r in rows)
    tomorrow = date.today() + timedelta(days=1)
    assert all(r["next_review"] == tomorrow for r in rows)


def test_invalid_error_type_dropped(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
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
    written = record_errors(tid, "text", corrections)
    assert written == 1
    rows = _fetch_errors(tid)
    assert len(rows) == 1
    assert rows[0]["error_type"] == "verb_tense_past"


def test_has_errors_false_writes_zero_rows(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    update = _make_update(tid, "This sentence is perfectly fine.")
    context = _make_context()
    payload = {
        "is_english": True,
        "has_errors": False,
        "corrections": [],
        "did_well": "Natural word order.",
    }
    with patch("app.handlers.correction.chat", return_value=payload):
        asyncio.run(correction_handler.correct_text(update, context))
    assert _count_errors(tid) == 0
    update.message.reply_text.assert_awaited_with("Natural word order.")


def test_is_english_false_writes_zero_rows(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    update = _make_update(tid, "این یک جمله فارسی است حتما")
    context = _make_context()
    payload = {
        "is_english": False,
        "has_errors": False,
        "corrections": [],
        "did_well": "",
    }
    with patch("app.handlers.correction.chat", return_value=payload):
        asyncio.run(correction_handler.correct_text(update, context))
    assert _count_errors(tid) == 0
    update.message.reply_text.assert_awaited_with(texts.NOT_ENGLISH)


def test_rendered_message_matches_prd_shape(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    update = _make_update(tid, "her english is not so much good today")
    context = _make_context()
    payload = {
        "is_english": True,
        "has_errors": True,
        "corrections": [
            {
                "you_said": "her english is not so much good",
                "correct_form": "her English isn't very good",
                "error_type": "quantifier_modifier",
                "explanation": (
                    '"so much" doesn\'t go before adjectives. Use "very".'
                ),
            },
            {
                "you_said": "collocation fail",
                "correct_form": "make a decision",
                "error_type": "collocation",
                "explanation": 'Say "make a decision", not "do a decision".',
            },
        ],
        "did_well": "Clean word order in the whole sentence.",
    }
    with patch("app.handlers.correction.chat", return_value=payload):
        asyncio.run(correction_handler.correct_text(update, context))

    assert _count_errors(tid) == 2
    reply = update.message.reply_text.await_args.args[0]
    expected_first = texts.format_correction_block(
        you_said="her english is not so much good",
        correct_form="her English isn't very good",
        explanation='"so much" doesn\'t go before adjectives. Use "very".',
        murphy_units=murphy_lookup()["quantifier_modifier"],
    )
    expected_second = texts.format_correction_block(
        you_said="collocation fail",
        correct_form="make a decision",
        explanation='Say "make a decision", not "do a decision".',
        murphy_units=None,  # collocation has NULL murphy_units
    )
    assert "📗" in expected_first
    assert "📗" not in expected_second
    assert reply == (
        expected_first
        + "\n\n"
        + expected_second
        + "\nClean word order in the whole sentence."
    )


def test_system_prompt_fallback_true_includes_native_rule(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    _set_fallback(tid, True)
    user = get_user(tid)
    assert user is not None
    assert user.explanation_language_fallback is True
    prompt = build_system_prompt(user)
    assert "write that explanation in their native language" in prompt
    assert ", ".join(ABSTRACT_ERROR_TYPES) in prompt
    assert user.native_language in prompt


def test_system_prompt_fallback_false_omits_native_rule(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    _set_fallback(tid, False)
    user = get_user(tid)
    assert user is not None
    assert user.explanation_language_fallback is False
    prompt = build_system_prompt(user)
    assert "write that explanation in their native language" not in prompt
    assert ", ".join(ABSTRACT_ERROR_TYPES) not in prompt
    assert "Write every explanation in English" in prompt


def test_format_correction_block_no_murphy_when_null() -> None:
    block = texts.format_correction_block(
        you_said="do a decision",
        correct_form="make a decision",
        explanation='Use "make" with decision.',
        murphy_units=None,
    )
    assert "📗" not in block
    assert block == (
        '✏️ "do a decision"\n'
        "→ make a decision\n"
        '💡 Use "make" with decision.'
    )
