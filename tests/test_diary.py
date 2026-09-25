"""Voice diary (S13 / M9) — schedule, /diary, processing, privacy, streaks."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config import Settings
from core.db import connection
from core.services.sessions import complete_session, insert_session
from core.services.streaks import get_streak, roll_over_day
from core.services.identity import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_480_000_000
_TG_ADDRESS_BASE = 9_000_000_000

# Personal detail that must not appear unquoted in logs / session payload.
PERSONAL_FIXTURE = (
    "Today I told my therapist about my divorce from Alex "
    "at 14 Rotušės street and the bank account ending 8821"
)

# Tuesday 2026-08-04 21:05 Vilnius
_TUESDAY_EVENING_UTC = datetime(2026, 8, 4, 18, 5, tzinfo=timezone.utc)
# Thursday
_THURSDAY_EVENING_UTC = datetime(2026, 8, 6, 18, 5, tzinfo=timezone.utc)
# Monday reading evening
_MONDAY_EVENING_UTC = datetime(2026, 8, 3, 18, 5, tzinfo=timezone.utc)


@pytest.fixture
def fake_telegram_id() -> int:
    return FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)


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
) -> int:
    user_id = save_onboarding(
        tid,
        {
            "name": "Diary Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": morning,
            "evening_time": evening,
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
        diary_max_seconds=90,
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _mock_app(tid: int, message_id: int = 500) -> MagicMock:
    app = MagicMock()
    msg = MagicMock()
    msg.chat_id = tid
    msg.message_id = message_id
    app.bot.send_message = AsyncMock(return_value=msg)
    return app


def _make_voice_update(
    tid: int,
    *,
    duration: int = 30,
    file_id: str = "diary-voice-1",
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


def _diary_llm(
    *,
    errors: list | None = None,
    did_well: str = "Clear past tense on went.",
) -> dict:
    return {
        "errors": errors if errors is not None else [],
        "did_well": did_well,
    }


def _chunk_count(tid: int) -> int:
    with connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE user_id = %s",
            (tid,),
        ).fetchone()
    assert row is not None
    return int(row["n"])


def _error_count(tid: int, *, source: str = "diary") -> int:
    with connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM errors WHERE user_id = %s AND source = %s",
            (tid, source),
        ).fetchone()
    assert row is not None
    return int(row["n"])


def _session_payload(tid: int, day: date) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT payload FROM sessions
             WHERE user_id = %s AND date = %s AND task_type = 'diary'
             ORDER BY id DESC LIMIT 1
            """,
            (tid, day),
        ).fetchone()
    if row is None:
        return None
    payload = row["payload"]
    if payload is not None and not isinstance(payload, dict):
        payload = dict(payload)
    return payload


# --- Schedule -----------------------------------------------------------------


# --- /diary command -----------------------------------------------------------


# --- Processing ---------------------------------------------------------------


def test_completed_diary_makes_day_active(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 4)
    with connection() as conn:
        conn.execute(
            """
            UPDATE streaks
               SET current_streak = 3,
                   longest_streak = 3,
                   freeze_tokens = 2,
                   total_active_days = 3,
                   last_active_date = %s,
                   last_evaluated_date = %s
             WHERE user_id = %s
            """,
            (date(2026, 8, 3), date(2026, 8, 3), user_id),
        )
    sid = insert_session(
        user_id, "diary", day, payload={"source": "poll"}, completed=False
    )
    complete_session(sid, None)
    result = roll_over_day(user_id, day)
    streak = get_streak(user_id)
    assert result.outcome == "active"
    assert streak.last_active_date == day


def test_incomplete_diary_alone_is_neutral(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 4)
    with connection() as conn:
        conn.execute(
            """
            UPDATE streaks
               SET current_streak = 3,
                   longest_streak = 3,
                   freeze_tokens = 2,
                   total_active_days = 3,
                   last_active_date = %s,
                   last_evaluated_date = %s
             WHERE user_id = %s
            """,
            (date(2026, 8, 3), date(2026, 8, 3), user_id),
        )
    insert_session(user_id, "diary", day, payload={"source": "poll"}, completed=False)
    result = roll_over_day(user_id, day)
    streak = get_streak(user_id)
    assert result.outcome == "neutral"
    assert streak.current_streak == 3


