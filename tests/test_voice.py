"""Voice partner tests (S5) — session gate, conversation, errors, TTS fallback."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config import Settings
from core.db import close_pool, connection
from core.services.sessions import (
    get_continuable_voice_session,
    insert_session,
    local_today,
    save_voice_exchange,
)
from core.services.identity import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_350_000_000
_TG_ADDRESS_BASE = 9_000_000_000


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


def _onboard(tid: int, *, morning: str = "07:00", tz: str = "Europe/Vilnius") -> int:
    user_id = save_onboarding(
        tid,
        {
            "name": "Voice Test",
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
    return user_id


def _settings(**overrides: object) -> Settings:
    base = dict(
        database_url="postgresql://x:y@localhost:5433/english_bot",
        telegram_bot_token="token",
        llm_api_key="test-key",
        openai_api_key="test-openai-key",
        stt_provider="openai",
        tts_provider="openai",
        whisper_model="whisper-1",
        tts_model="tts-1",
        tts_voice="alloy",
        tts_format="opus",
        voice_max_seconds=120,
        voice_context_minutes=120,
        voice_max_turns=10,
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _make_voice_update(
    tid: int,
    *,
    duration: int = 5,
    file_id: str = "voice-file-1",
) -> MagicMock:
    update = MagicMock()
    update.effective_user = MagicMock(id=tid)
    message = MagicMock()
    message.chat_id = tid
    message.from_user = MagicMock(id=tid)
    message.voice = MagicMock(duration=duration, file_id=file_id)
    status = MagicMock()
    status.message_id = 9001
    message.reply_text = AsyncMock(return_value=status)
    message.reply_voice = AsyncMock()
    message.reply_audio = AsyncMock()
    update.message = message
    return update


def _make_context() -> MagicMock:
    context = MagicMock()
    context.bot = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.delete_message = AsyncMock()
    tg_file = MagicMock()
    tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"ogg"))
    context.bot.get_file = AsyncMock(return_value=tg_file)
    return context


def _llm_payload(*, reply: str = "How was your day?", errors: list | None = None) -> dict:
    return {
        "reply": reply,
        "errors": errors
        if errors is not None
        else [
            {
                "you_said": "I go",
                "correct_form": "I went",
                "error_type": "verb_tense_past",
                "explanation": "Past needs went.",
            }
        ],
        "did_well": "Clear topic.",
    }


# --- Session gate (write first) ----------------------------------------------


def test_completed_quiz_does_not_block_voice(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 3)
    insert_session(user_id, "quiz", day, payload={"questions": []}, completed=True)
    now = datetime(2026, 8, 3, 18, 0, tzinfo=timezone.utc)
    assert (
        get_continuable_voice_session(
            user_id, now=now, context_minutes=120, max_turns=10
        )
        is None
    )
    sid = save_voice_exchange(
        None,
        user_id,
        day,
        {"messages": [{"role": "user", "content": "hi"}], "turn_count": 1},
    )
    assert sid > 0
    row = get_continuable_voice_session(
        user_id, now=now, context_minutes=120, max_turns=10
    )
    assert row is not None
    assert row.task_type == "voice"


def test_conversation_continues_inside_window(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    now = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    day = local_today("Europe/Vilnius", now)
    save_voice_exchange(
        None,
        user_id,
        day,
        {
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hey"},
            ],
            "turn_count": 1,
        },
    )
    row = get_continuable_voice_session(
        user_id, now=now, context_minutes=120, max_turns=10
    )
    assert row is not None
    assert row.payload is not None
    assert row.payload["turn_count"] == 1


def test_conversation_starts_fresh_outside_window(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 3)
    sid = save_voice_exchange(
        None,
        user_id,
        day,
        {"messages": [{"role": "user", "content": "hi"}], "turn_count": 1},
    )
    # Force completed_at into the past beyond the window.
    with connection() as conn:
        conn.execute(
            """
            UPDATE sessions
               SET completed_at = NOW() - INTERVAL '3 hours'
             WHERE id = %s
            """,
            (sid,),
        )
    now = datetime.now(timezone.utc)
    assert (
        get_continuable_voice_session(
            user_id, now=now, context_minutes=120, max_turns=10
        )
        is None
    )


# --- S5a: processing status + repeating chat action --------------------------


