"""Voice diary (S13 / M9) — schedule, /diary, processing, privacy, streaks."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.bot import texts
from core.config import Settings
from core.db import close_pool, connection
from apps.bot.handlers.correction import init_correction_prompt
from apps.bot.handlers.diary import (
    deliver_diary,
    handle_diary_voice,
    init_diary_prompt,
    on_diary_command,
)
from apps.bot.handlers.voice import handle_voice, init_voice_prompt
from apps.bot.scheduler import (
    DIARY_WEEKDAYS,
    READING_WEEKDAYS,
    EligibleUser,
    is_user_due_for_diary,
    is_user_due_for_evening,
    is_user_due_for_morning,
)
from core.services.sessions import (
    bot_initiated_count,
    complete_session,
    get_open_diary_session,
    has_completed_diary_on,
    has_diary_session_on,
    has_session_on,
    increment_bot_messages,
    insert_session,
    local_today,
    save_voice_exchange,
)
from core.services.streaks import get_streak, roll_over_day
from core.services.identity import save_onboarding
from core.services.users import set_paused_until
from core.speech import SpeechError

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


@pytest.fixture(autouse=True)
def _close_pool_after_test() -> None:
    init_correction_prompt()
    init_voice_prompt()
    init_diary_prompt()
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


def _eligible(
    user_id: int,
    *,
    tz: str = "Europe/Vilnius",
    evening: str = "21:00",
    morning: str = "07:00",
    paused_until: date | None = None,
) -> EligibleUser:
    eh, em = map(int, evening.split(":"))
    mh, mm = map(int, morning.split(":"))
    return EligibleUser(
        id=user_id,
        # Deliberately not equal to `id`.
        telegram_address=_TG_ADDRESS_BASE + user_id,
        timezone=tz,
        morning_time=time(mh, mm),
        paused_until=paused_until,
        evening_time=time(eh, em),
    )


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


def test_diary_weekdays_disjoint_from_reading() -> None:
    assert DIARY_WEEKDAYS.isdisjoint(READING_WEEKDAYS)
    assert DIARY_WEEKDAYS == frozenset({1, 3})


def test_eligibility_tue_thu_not_reading_evenings(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    user = _eligible(user_id)
    assert is_user_due_for_diary(user, _TUESDAY_EVENING_UTC) is True
    assert is_user_due_for_evening(user, _TUESDAY_EVENING_UTC) is False
    assert is_user_due_for_diary(user, _THURSDAY_EVENING_UTC) is True
    assert is_user_due_for_evening(user, _THURSDAY_EVENING_UTC) is False
    assert is_user_due_for_diary(user, _MONDAY_EVENING_UTC) is False
    assert is_user_due_for_evening(user, _MONDAY_EVENING_UTC) is True


def test_eligibility_once_per_day(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    user = _eligible(user_id)
    day = local_today("Europe/Vilnius", _TUESDAY_EVENING_UTC)
    assert is_user_due_for_diary(user, _TUESDAY_EVENING_UTC) is True
    insert_session(user_id, "diary", day, payload={"source": "poll"}, completed=False)
    assert has_diary_session_on(user_id, day) is True
    assert is_user_due_for_diary(user, _TUESDAY_EVENING_UTC) is False


def test_ceiling_reached_skips_prompt_no_session(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = local_today("Europe/Vilnius", _TUESDAY_EVENING_UTC)
    for _ in range(3):
        increment_bot_messages(user_id, day)
    app = _mock_app(user_id)
    with caplog.at_level(logging.WARNING):
        action = asyncio.run(
            deliver_diary(app, user_id, now=_TUESDAY_EVENING_UTC)
        )
    assert action == "skipped_ceiling"
    assert has_diary_session_on(user_id, day) is False
    app.bot.send_message.assert_not_awaited()
    assert any("ceiling" in r.message for r in caplog.records)


def test_paused_user_not_due(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = local_today("Europe/Vilnius", _TUESDAY_EVENING_UTC)
    set_paused_until(user_id, day)
    user = _eligible(user_id, paused_until=day)
    assert is_user_due_for_diary(user, _TUESDAY_EVENING_UTC) is False


def test_deliver_increments_ceiling(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = local_today("Europe/Vilnius", _TUESDAY_EVENING_UTC)
    app = _mock_app(user_id)
    action = asyncio.run(deliver_diary(app, user_id, now=_TUESDAY_EVENING_UTC))
    assert action == "diary"
    assert bot_initiated_count(user_id, day) == 1
    assert get_open_diary_session(user_id, day) is not None
    sent = app.bot.send_message.await_args.kwargs["text"]
    assert len(sent) < 400
    assert sent in texts.DIARY_PROMPTS


# --- /diary command -----------------------------------------------------------


def test_diary_command_opens_session_no_ceiling(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 3)
    for _ in range(3):
        increment_bot_messages(user_id, day)
    update = MagicMock()
    update.effective_user = MagicMock(id=tid)
    message = MagicMock()
    message.reply_text = AsyncMock(
        return_value=MagicMock(chat_id=tid, message_id=77)
    )
    update.message = message
    with patch("apps.bot.handlers.diary.local_today", return_value=day):
        asyncio.run(on_diary_command(update, MagicMock()))
    assert get_open_diary_session(user_id, day) is not None
    assert bot_initiated_count(user_id, day) == 3  # unchanged


def test_diary_command_reuses_open(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 4)
    insert_session(user_id, "diary", day, payload={"source": "poll"}, completed=False)
    update = MagicMock()
    update.effective_user = MagicMock(id=tid)
    message = MagicMock()
    message.reply_text = AsyncMock()
    update.message = message
    with patch("apps.bot.handlers.diary.local_today", return_value=day):
        asyncio.run(on_diary_command(update, MagicMock()))
    message.reply_text.assert_awaited_once_with(texts.DIARY_ALREADY_OPEN)
    with connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE user_id = %s AND task_type = 'diary'",
            (user_id,),
        ).fetchone()
    assert int(row["n"]) == 1


def test_diary_command_already_done(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 4)
    sid = insert_session(
        user_id, "diary", day, payload={"source": "command"}, completed=False
    )
    complete_session(sid, None)
    assert has_completed_diary_on(user_id, day) is True
    update = MagicMock()
    update.effective_user = MagicMock(id=tid)
    message = MagicMock()
    message.reply_text = AsyncMock()
    update.message = message
    with patch("apps.bot.handlers.diary.local_today", return_value=day):
        asyncio.run(on_diary_command(update, MagicMock()))
    message.reply_text.assert_awaited_once_with(texts.DIARY_ALREADY_DONE)


# --- Processing ---------------------------------------------------------------


def test_six_corrections_become_two_diary_errors(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 4)
    insert_session(user_id, "diary", day, payload={"source": "poll"}, completed=False)
    six = [
        {
            "you_said": f"err{i}",
            "correct_form": f"ok{i}",
            "error_type": "verb_tense_past",
            "explanation": "Past needs went.",
        }
        for i in range(6)
    ]
    update = _make_voice_update(tid)
    context = _make_context()
    with (
        patch(
            "apps.bot.handlers.voice.load_settings",
            return_value=_settings(),
        ),
        patch("apps.bot.handlers.voice.local_today", return_value=day),
        patch("apps.bot.handlers.diary.local_today", return_value=day),
        patch(
            "apps.bot.handlers.diary.transcribe", return_value="I go to work yesterday"
        ),
        patch(
            "apps.bot.handlers.diary.chat",
            return_value=_diary_llm(errors=six),
        ),
        patch("core.speech.synthesize") as synth,
    ):
        asyncio.run(handle_voice(update, context))
    assert _error_count(user_id) == 2
    assert has_completed_diary_on(user_id, day) is True
    synth.assert_not_called()
    update.message.reply_voice.assert_not_awaited()


def test_zero_corrections_still_names_did_well(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 4)
    insert_session(user_id, "diary", day, payload={"source": "poll"}, completed=False)
    update = _make_voice_update(tid)
    context = _make_context()
    with (
        patch(
            "apps.bot.handlers.voice.load_settings",
            return_value=_settings(),
        ),
        patch("apps.bot.handlers.voice.local_today", return_value=day),
        patch("apps.bot.handlers.diary.local_today", return_value=day),
        patch("apps.bot.handlers.diary.transcribe", return_value="I went home early."),
        patch(
            "apps.bot.handlers.diary.chat",
            return_value=_diary_llm(
                errors=[], did_well="Natural past tense on went."
            ),
        ),
    ):
        asyncio.run(handle_voice(update, context))
    assert _error_count(user_id) == 0
    replies = [
        c.args[0] for c in update.message.reply_text.await_args_list if c.args
    ]
    assert any("Natural past tense on went." in r for r in replies)


def test_full_transcript_absent_from_payload_and_logs(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 4)
    insert_session(user_id, "diary", day, payload={"source": "poll"}, completed=False)
    update = _make_voice_update(tid)
    context = _make_context()
    with (
        caplog.at_level(logging.DEBUG),
        patch(
            "apps.bot.handlers.voice.load_settings",
            return_value=_settings(),
        ),
        patch("apps.bot.handlers.voice.local_today", return_value=day),
        patch("apps.bot.handlers.diary.local_today", return_value=day),
        patch("apps.bot.handlers.diary.transcribe", return_value=PERSONAL_FIXTURE),
        patch(
            "apps.bot.handlers.diary.chat",
            return_value=_diary_llm(
                errors=[
                    {
                        "you_said": "I go",
                        "correct_form": "I went",
                        "error_type": "verb_tense_past",
                        "explanation": "Past needs went.",
                    }
                ]
            ),
        ),
    ):
        asyncio.run(handle_voice(update, context))
    payload = _session_payload(user_id, day)
    assert payload is not None
    assert PERSONAL_FIXTURE not in str(payload)
    for record in caplog.records:
        assert PERSONAL_FIXTURE not in record.getMessage()
    # Journal may retain a short you_said fragment — not the full diary.
    with connection() as conn:
        rows = conn.execute(
            "SELECT you_said FROM errors WHERE user_id = %s AND source = 'diary'",
            (user_id,),
        ).fetchall()
    for row in rows:
        assert PERSONAL_FIXTURE not in str(row["you_said"])


def test_no_chunks_from_diary(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 4)
    insert_session(user_id, "diary", day, payload={"source": "poll"}, completed=False)
    before = _chunk_count(user_id)
    update = _make_voice_update(tid)
    context = _make_context()
    with (
        patch(
            "apps.bot.handlers.voice.load_settings",
            return_value=_settings(),
        ),
        patch("apps.bot.handlers.voice.local_today", return_value=day),
        patch("apps.bot.handlers.diary.local_today", return_value=day),
        patch("apps.bot.handlers.diary.transcribe", return_value="I cooked dinner."),
        patch(
            "apps.bot.handlers.diary.chat",
            return_value=_diary_llm(errors=[]),
        ),
    ):
        asyncio.run(handle_voice(update, context))
    assert _chunk_count(user_id) == before


def test_over_length_declined_before_download(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 4)
    insert_session(user_id, "diary", day, payload={"source": "poll"}, completed=False)
    update = _make_voice_update(tid, duration=91)
    context = _make_context()
    with (
        patch(
            "apps.bot.handlers.voice.load_settings",
            return_value=_settings(),
        ),
        patch("apps.bot.handlers.voice.local_today", return_value=day),
        patch("apps.bot.handlers.diary.transcribe") as tr,
    ):
        asyncio.run(handle_voice(update, context))
    tr.assert_not_called()
    context.bot.get_file.assert_not_awaited()
    update.message.reply_text.assert_awaited_once_with(texts.DIARY_TOO_LONG)


def test_stt_failure_warm_degrade(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 4)
    insert_session(user_id, "diary", day, payload={"source": "poll"}, completed=False)
    update = _make_voice_update(tid)
    context = _make_context()
    with (
        caplog.at_level(logging.WARNING),
        patch(
            "apps.bot.handlers.voice.load_settings",
            return_value=_settings(),
        ),
        patch("apps.bot.handlers.voice.local_today", return_value=day),
        patch("apps.bot.handlers.diary.local_today", return_value=day),
        patch(
            "apps.bot.handlers.diary.transcribe",
            side_effect=SpeechError("fail"),
        ),
    ):
        asyncio.run(handle_voice(update, context))
    assert get_open_diary_session(user_id, day) is not None  # still open
    assert has_completed_diary_on(user_id, day) is False
    assert any("STT failed" in r.message for r in caplog.records)


def test_diary_does_not_block_morning_quiz(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, morning="07:00")
    now = datetime(2026, 8, 5, 4, 10, tzinfo=timezone.utc)  # Wed morning
    day = local_today("Europe/Vilnius", now)
    insert_session(user_id, "diary", day, payload={"source": "command"}, completed=True)
    assert has_session_on(user_id, day) is False
    user = _eligible(user_id)
    assert is_user_due_for_morning(user, now) is True


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


def test_s13_button_labels_max_20() -> None:
    # Diary has no buttons today; keep the audit loop for any future BTN_DIARY_*.
    labels = [
        getattr(texts, name)
        for name in dir(texts)
        if name.startswith("BTN_") and "DIARY" in name
    ]
    for label in labels:
        assert len(label) <= 20, label
    for prompt in texts.DIARY_PROMPTS:
        assert len(prompt) < 400


def test_live_m3_wins_over_open_diary_unit(cleanup_user: int) -> None:
    """Unit pin: with live M3 + open diary, M3 path runs (not diary)."""
    tid = cleanup_user
    user_id = _onboard(tid)
    day = local_today("Europe/Vilnius", datetime.now(timezone.utc))
    save_voice_exchange(
        None,
        user_id,
        day,
        {
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hey"},
            ],
            "turn_count": 2,
        },
    )
    insert_session(user_id, "diary", day, payload={"source": "poll"}, completed=False)
    update = _make_voice_update(tid)
    context = _make_context()
    diary_spy = AsyncMock()
    m3_spy = AsyncMock()
    with (
        patch(
            "apps.bot.handlers.voice.load_settings",
            return_value=_settings(),
        ),
        patch("apps.bot.handlers.diary.handle_diary_voice", diary_spy),
        patch("apps.bot.handlers.voice._handle_voice_locked", m3_spy),
    ):
        asyncio.run(handle_voice(update, context))
    m3_spy.assert_awaited_once()
    diary_spy.assert_not_awaited()
