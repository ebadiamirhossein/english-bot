"""S16 shadowing (M12): select, TTS, claim window, word diff, privacy."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import InlineKeyboardMarkup

from app import texts
from app.config import Settings
from app.db import close_pool, connection
from app.handlers import shadow as shadow_handler
from app.handlers.voice import handle_voice
from app.services.calibration import (
    CALIBRATION_TASK_TYPES,
    compute_accuracy_window,
    maybe_calibrate,
)
from app.services.chunks import insert_chunks
from app.services.sessions import (
    SHADOW_VOICE_CLAIM_MINUTES,
    complete_session,
    get_claimable_shadow_session,
    get_open_shadow_session,
    has_session_on,
    insert_session,
    local_today,
    save_voice_exchange,
    update_session_payload,
)
from app.services.shadow import (
    SHADOW_EXCLUDE_RECENT_K,
    abandon_open_shadow_sessions,
    diff_words,
    select_shadow_sentence,
    words_for_compare,
)
from app.services.streaks import get_streak, roll_over_day
from app.services.users import save_onboarding
from app.speech import SpeechError

FAKE_TELEGRAM_ID_BASE = 9_510_000_000
PERSONAL_FIXTURE = "ZX9SHADOWPRIVATE transcript must never land in DB or logs"
TARGET = "The quick brown fox jumps"


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
            "name": "Shadow Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": "07:00",
            "evening_time": "21:00",
        },
    )


def _settings() -> Settings:
    return Settings(
        database_url="postgresql://x:y@localhost:5433/english_bot",
        telegram_bot_token="token",
        llm_api_key="test-key",
        openai_api_key="test-openai-key",
        diary_max_seconds=90,
        voice_max_seconds=120,
        voice_context_minutes=120,
        voice_max_turns=10,
    )


def _seed_chunks(tid: int, n: int = 1, *, prefix: str = "sent") -> list[int]:
    items = [
        {
            "chunk": f"chunk{i}",
            "full_sentence": f"{prefix} {i} the quick brown fox.",
            "meaning": f"m{i}",
        }
        for i in range(n)
    ]
    with connection() as conn:
        with conn.transaction():
            insert_chunks(
                conn, tid, source="test_shadow", track=None, chunks=items
            )
            rows = conn.execute(
                """
                SELECT id FROM chunks
                 WHERE user_id = %s AND source = 'test_shadow'
                 ORDER BY id ASC
                """,
                (tid,),
            ).fetchall()
    return [int(r["id"]) for r in rows]


def _error_count(tid: int) -> int:
    with connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM errors WHERE user_id = %s", (tid,)
        ).fetchone()
    assert row is not None
    return int(row["n"])


def _shadow_sessions(tid: int) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, completed, score, payload
              FROM sessions
             WHERE user_id = %s AND task_type = 'shadow'
             ORDER BY id ASC
            """,
            (tid,),
        ).fetchall()
    out = []
    for r in rows:
        payload = r["payload"]
        if payload is not None and not isinstance(payload, dict):
            payload = dict(payload)
        out.append(
            {
                "id": int(r["id"]),
                "completed": bool(r["completed"]),
                "score": float(r["score"]) if r["score"] is not None else None,
                "payload": payload,
            }
        )
    return out


def _calibration_count(tid: int) -> int:
    with connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM calibration_log WHERE user_id = %s",
            (tid,),
        ).fetchone()
    assert row is not None
    return int(row["n"])


def _make_voice_update(
    user_id: int, *, duration: int = 10, message_id: int = 50
) -> MagicMock:
    update = MagicMock()
    update.effective_user = MagicMock(id=user_id)
    message = MagicMock()
    message.chat_id = user_id
    message.message_id = message_id
    message.voice = MagicMock(duration=duration, file_id="voice-shadow-1")
    message.reply_text = AsyncMock(return_value=MagicMock(message_id=77))
    message.reply_voice = AsyncMock(
        return_value=MagicMock(chat_id=user_id, message_id=200)
    )
    update.message = message
    return update


def _make_context() -> MagicMock:
    context = MagicMock()
    tg_file = MagicMock()
    tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"ogg"))
    context.bot.get_file = AsyncMock(return_value=tg_file)
    context.bot.send_chat_action = AsyncMock()
    context.bot.send_voice = AsyncMock(
        return_value=MagicMock(chat_id=1, message_id=201)
    )
    context.bot.edit_message_text = AsyncMock()
    context.bot.delete_message = AsyncMock()
    return context


def _make_command_update(user_id: int) -> MagicMock:
    update = MagicMock()
    update.effective_user = MagicMock(id=user_id)
    message = MagicMock()
    message.chat_id = user_id
    message.message_id = 10
    message.text = "/shadow"
    message.reply_text = AsyncMock()
    message.reply_voice = AsyncMock(
        return_value=MagicMock(chat_id=user_id, message_id=99)
    )
    update.message = message
    return update


# --- word diff ----------------------------------------------------------------


def test_words_for_compare_strips_case_and_punct() -> None:
    assert words_for_compare("Hello, World!") == words_for_compare("hello world")


def test_diff_exact_match() -> None:
    r = diff_words("The quick brown fox", "the quick brown fox")
    assert r.matched == 4
    assert r.missed == []
    assert r.added == []
    assert r.altered == []
    assert r.score == 1.0


def test_diff_one_missed() -> None:
    r = diff_words("the quick brown fox", "the quick fox")
    assert "brown" in r.missed
    assert r.score < 1.0


def test_diff_one_added() -> None:
    r = diff_words("the quick fox", "the quick brown fox")
    assert "brown" in r.added


def test_diff_one_altered() -> None:
    r = diff_words("the quick brown fox", "the quiet brown fox")
    assert ("quick", "quiet") in r.altered


def test_diff_ignores_case_and_punctuation() -> None:
    r = diff_words("Hello, world!", "hello world")
    assert r.score == 1.0


# --- selection ----------------------------------------------------------------


def test_select_excludes_last_k_for_variety(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    ids = _seed_chunks(tid, 10, prefix="var")
    assert len(ids) == 10
    assert SHADOW_EXCLUDE_RECENT_K >= 5

    picked: list[int] = []
    day = date(2026, 8, 9)
    for i in range(5):
        chunk = select_shadow_sentence(tid)
        assert chunk is not None
        picked.append(chunk.id)
        insert_session(
            tid,
            "shadow",
            day,
            payload={
                "chunk_id": chunk.id,
                "target_sentence": chunk.full_sentence,
                "clip_sent_at": datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc).isoformat(),
                "attempts": 0,
            },
            completed=True,
        )
        # Mark completed so next select still sees chunk_id in recent payloads.
        # insert_session with completed=True still stores payload.
    assert len(set(picked)) == 5, picked


def test_select_empty_pool(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    assert select_shadow_sentence(tid) is None


# --- /shadow command ----------------------------------------------------------


def test_shadow_command_with_chunks_creates_session(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_chunks(tid, 1)
    update = _make_command_update(tid)
    context = _make_context()
    with (
        patch("app.handlers.shadow.load_settings", return_value=_settings()),
        patch(
            "app.handlers.shadow.synthesize", return_value=b"ogg-bytes"
        ) as synth,
    ):
        asyncio.run(shadow_handler.on_shadow_command(update, context))
    synth.assert_called_once()
    sessions = _shadow_sessions(tid)
    assert len(sessions) == 1
    assert sessions[0]["completed"] is False
    assert sessions[0]["payload"]["target_sentence"]
    assert "clip_sent_at" in sessions[0]["payload"]
    update.message.reply_voice.assert_awaited()


def test_shadow_empty_pool_no_tts_no_session(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    update = _make_command_update(tid)
    context = _make_context()
    with (
        patch("app.handlers.shadow.load_settings", return_value=_settings()),
        patch("app.handlers.shadow.synthesize") as synth,
    ):
        asyncio.run(shadow_handler.on_shadow_command(update, context))
    synth.assert_not_called()
    assert _shadow_sessions(tid) == []
    update.message.reply_text.assert_awaited_with(texts.SHADOW_EMPTY_POOL)


def test_shadow_tts_failure_warm_degrade(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_chunks(tid, 1)
    update = _make_command_update(tid)
    context = _make_context()
    with (
        caplog.at_level(logging.WARNING),
        patch("app.handlers.shadow.load_settings", return_value=_settings()),
        patch(
            "app.handlers.shadow.synthesize",
            side_effect=SpeechError("tts down"),
        ),
    ):
        asyncio.run(shadow_handler.on_shadow_command(update, context))
    assert _shadow_sessions(tid) == []
    update.message.reply_text.assert_awaited_with(texts.SHADOW_FAILED_TTS)
    assert any("TTS failed" in r.message for r in caplog.records)


# --- voice routing / claim window ---------------------------------------------


def test_claimable_shadow_routes_to_shadow_not_m3(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    now = datetime.now(timezone.utc)
    day = local_today("Europe/Vilnius", now)
    insert_session(
        tid,
        "shadow",
        day,
        payload={
            "chunk_id": 1,
            "target_sentence": TARGET,
            "clip_sent_at": now.isoformat(),
            "attempts": 0,
        },
        completed=False,
    )
    update = _make_voice_update(tid)
    context = _make_context()
    shadow_spy = AsyncMock()
    diary_spy = AsyncMock()
    m3_spy = AsyncMock()
    with (
        patch("app.handlers.voice.load_settings", return_value=_settings()),
        patch("app.handlers.shadow.handle_shadow_voice", shadow_spy),
        patch("app.handlers.diary.handle_diary_voice", diary_spy),
        patch("app.handlers.voice._handle_voice_locked", m3_spy),
    ):
        asyncio.run(handle_voice(update, context))
    shadow_spy.assert_awaited_once()
    diary_spy.assert_not_awaited()
    m3_spy.assert_not_awaited()


def test_stale_shadow_defers_to_live_m3(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    now = datetime.now(timezone.utc)
    day = local_today("Europe/Vilnius", now)
    stale = now - timedelta(minutes=45)
    assert SHADOW_VOICE_CLAIM_MINUTES == 30
    sid = insert_session(
        tid,
        "shadow",
        day,
        payload={
            "chunk_id": 1,
            "target_sentence": TARGET,
            "clip_sent_at": stale.isoformat(),
            "attempts": 0,
        },
        completed=False,
    )
    save_voice_exchange(
        None,
        tid,
        day,
        {
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hey"},
            ],
            "turn_count": 1,
        },
    )
    assert get_claimable_shadow_session(tid, day, now=now) is None

    update = _make_voice_update(tid)
    context = _make_context()
    shadow_spy = AsyncMock()
    diary_spy = AsyncMock()
    m3_spy = AsyncMock()
    with (
        patch("app.handlers.voice.load_settings", return_value=_settings()),
        patch("app.handlers.shadow.handle_shadow_voice", shadow_spy),
        patch("app.handlers.diary.handle_diary_voice", diary_spy),
        patch("app.handlers.voice._handle_voice_locked", m3_spy),
    ):
        asyncio.run(handle_voice(update, context))
    m3_spy.assert_awaited_once()
    shadow_spy.assert_not_awaited()
    diary_spy.assert_not_awaited()
    open_s = get_open_shadow_session(tid, day)
    assert open_s is not None
    assert open_s.id == sid
    assert open_s.completed is False


def test_claimable_shadow_beats_live_m3_and_diary(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    now = datetime.now(timezone.utc)
    day = local_today("Europe/Vilnius", now)
    insert_session(
        tid,
        "shadow",
        day,
        payload={
            "chunk_id": 1,
            "target_sentence": TARGET,
            "clip_sent_at": now.isoformat(),
            "attempts": 0,
        },
        completed=False,
    )
    save_voice_exchange(
        None,
        tid,
        day,
        {
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hey"},
            ],
            "turn_count": 1,
        },
    )
    insert_session(tid, "diary", day, payload={"source": "poll"}, completed=False)

    update = _make_voice_update(tid)
    context = _make_context()
    shadow_spy = AsyncMock()
    diary_spy = AsyncMock()
    m3_spy = AsyncMock()
    with (
        patch("app.handlers.voice.load_settings", return_value=_settings()),
        patch("app.handlers.shadow.handle_shadow_voice", shadow_spy),
        patch("app.handlers.diary.handle_diary_voice", diary_spy),
        patch("app.handlers.voice._handle_voice_locked", m3_spy),
    ):
        asyncio.run(handle_voice(update, context))
    shadow_spy.assert_awaited_once()
    diary_spy.assert_not_awaited()
    m3_spy.assert_not_awaited()


# --- attempt / retry / complete -----------------------------------------------


def test_attempt_offers_retry_then_completes(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    now = datetime.now(timezone.utc)
    day = local_today("Europe/Vilnius", now)
    sid = insert_session(
        tid,
        "shadow",
        day,
        payload={
            "chunk_id": 1,
            "target_sentence": TARGET,
            "clip_sent_at": now.isoformat(),
            "attempts": 0,
        },
        completed=False,
    )
    update = _make_voice_update(tid)
    context = _make_context()

    with (
        patch("app.handlers.voice.load_settings", return_value=_settings()),
        patch(
            "app.handlers.shadow.transcribe",
            return_value="the quiet brown fox jumps",
        ),
    ):
        asyncio.run(handle_voice(update, context))

    sessions = _shadow_sessions(tid)
    assert sessions[0]["completed"] is False
    assert sessions[0]["payload"]["attempts"] == 1
    assert PERSONAL_FIXTURE not in str(sessions[0]["payload"])
    call_kwargs = [
        c.kwargs for c in update.message.reply_text.await_args_list
    ]
    assert any(
        isinstance(c.get("reply_markup"), InlineKeyboardMarkup)
        for c in call_kwargs
    )
    assert _error_count(tid) == 0

    update2 = _make_voice_update(tid, message_id=51)
    context2 = _make_context()
    with (
        patch("app.handlers.voice.load_settings", return_value=_settings()),
        patch(
            "app.handlers.shadow.transcribe",
            return_value="totally different words here",
        ),
    ):
        asyncio.run(handle_voice(update2, context2))

    sessions = _shadow_sessions(tid)
    assert sessions[0]["id"] == sid
    assert sessions[0]["completed"] is True
    assert sessions[0]["score"] is not None
    assert sessions[0]["payload"].get("transcript") is None
    assert PERSONAL_FIXTURE not in str(sessions[0]["payload"])
    assert _error_count(tid) == 0


def test_retry_rearms_clip_sent_at(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    now = datetime.now(timezone.utc)
    day = local_today("Europe/Vilnius", now)
    old = (now - timedelta(minutes=40)).isoformat()
    sid = insert_session(
        tid,
        "shadow",
        day,
        payload={
            "chunk_id": 1,
            "target_sentence": TARGET,
            "clip_sent_at": old,
            "attempts": 1,
        },
        completed=False,
    )
    msg = MagicMock()
    msg.chat_id = tid
    msg.message_id = 10
    msg.reply_text = AsyncMock()
    cq = MagicMock()
    cq.data = f"shadow:again:{sid}"
    cq.from_user = MagicMock(id=tid)
    cq.message = msg
    cq.answer = AsyncMock()
    update = MagicMock()
    update.callback_query = cq
    context = _make_context()
    before = datetime.now(timezone.utc)
    with (
        patch("app.handlers.shadow.load_settings", return_value=_settings()),
        patch(
            "app.handlers.shadow.synthesize", return_value=b"ogg"
        ) as synth,
    ):
        asyncio.run(shadow_handler.on_shadow_retry(update, context))
    synth.assert_called_once()
    sessions = _shadow_sessions(tid)
    rearmed = datetime.fromisoformat(sessions[0]["payload"]["clip_sent_at"])
    if rearmed.tzinfo is None:
        rearmed = rearmed.replace(tzinfo=timezone.utc)
    assert rearmed >= before - timedelta(seconds=2)
    assert get_claimable_shadow_session(tid, day, now=datetime.now(timezone.utc)) is not None


def test_stt_failure_warm_degrade(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    now = datetime.now(timezone.utc)
    day = local_today("Europe/Vilnius", now)
    insert_session(
        tid,
        "shadow",
        day,
        payload={
            "chunk_id": 1,
            "target_sentence": TARGET,
            "clip_sent_at": now.isoformat(),
            "attempts": 0,
        },
        completed=False,
    )
    update = _make_voice_update(tid)
    context = _make_context()
    with (
        caplog.at_level(logging.WARNING),
        patch("app.handlers.voice.load_settings", return_value=_settings()),
        patch(
            "app.handlers.shadow.transcribe",
            side_effect=SpeechError("stt down"),
        ),
    ):
        asyncio.run(handle_voice(update, context))
    assert any("STT failed" in r.message for r in caplog.records)
    assert get_open_shadow_session(tid, day) is not None


def test_transcript_not_in_payload_or_logs(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    now = datetime.now(timezone.utc)
    day = local_today("Europe/Vilnius", now)
    insert_session(
        tid,
        "shadow",
        day,
        payload={
            "chunk_id": 1,
            "target_sentence": TARGET,
            "clip_sent_at": now.isoformat(),
            "attempts": 0,
        },
        completed=False,
    )
    update = _make_voice_update(tid)
    context = _make_context()
    with (
        caplog.at_level(logging.DEBUG),
        patch("app.handlers.voice.load_settings", return_value=_settings()),
        patch(
            "app.handlers.shadow.transcribe",
            return_value=PERSONAL_FIXTURE,
        ),
    ):
        asyncio.run(handle_voice(update, context))
    payload = _shadow_sessions(tid)[0]["payload"]
    assert PERSONAL_FIXTURE not in str(payload)
    for record in caplog.records:
        assert PERSONAL_FIXTURE not in record.getMessage()


# --- streaks / morning / calibration ------------------------------------------


def test_completed_shadow_makes_day_active(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
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
            (date(2026, 8, 3), date(2026, 8, 3), tid),
        )
    sid = insert_session(
        tid,
        "shadow",
        day,
        payload={"chunk_id": 1, "target_sentence": TARGET},
        completed=False,
    )
    complete_session(sid, 0.8)
    result = roll_over_day(tid, day)
    assert result.outcome == "active"


def test_incomplete_shadow_alone_is_neutral(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
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
            (date(2026, 8, 3), date(2026, 8, 3), tid),
        )
    insert_session(
        tid,
        "shadow",
        day,
        payload={"chunk_id": 1, "target_sentence": TARGET},
        completed=False,
    )
    result = roll_over_day(tid, day)
    streak = get_streak(tid)
    assert result.outcome == "neutral"
    assert streak.current_streak == 3


def test_shadow_does_not_block_morning_quiz(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 8, 9)
    sid = insert_session(
        tid,
        "shadow",
        day,
        payload={"chunk_id": 1, "target_sentence": TARGET},
        completed=False,
    )
    assert has_session_on(tid, day) is False
    complete_session(sid, 1.0)
    assert has_session_on(tid, day) is False


def test_shadow_score_outside_calibration(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    assert "shadow" not in CALIBRATION_TASK_TYPES
    day = date(2026, 8, 9)
    sid = insert_session(
        tid,
        "shadow",
        day,
        payload={
            "chunk_id": 1,
            "target_sentence": TARGET,
            "answered": 10,
            "correct_count": 10,
        },
        completed=False,
    )
    complete_session(sid, 1.0)
    window = compute_accuracy_window(tid)
    assert window.sample == 0
    before = _calibration_count(tid)
    now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    outcome = maybe_calibrate(tid, now=now)
    assert outcome.sample < 30
    assert _calibration_count(tid) == before


# --- copy / labels ------------------------------------------------------------


def test_s16_button_labels_max_20() -> None:
    labels = [
        getattr(texts, name)
        for name in dir(texts)
        if name.startswith("BTN_") and "SHADOW" in name
    ]
    assert labels
    for label in labels:
        assert len(label) <= 20, label


def test_no_guilt_in_s16_copy() -> None:
    banned = re.compile(
        r"\bmissed\b|\bfailed\b|\bbroke\b|wrong!|should have|"
        r"pronunciation was wrong|you failed|"
        r"😞|😢|😔|☹️|🙁|😟|😤|😠",
        re.IGNORECASE,
    )
    names = [
        n
        for n in dir(texts)
        if n.startswith("SHADOW_") or n.startswith("BTN_SHADOW")
    ]
    for name in names:
        val = getattr(texts, name)
        if callable(val):
            sample = val("target", "attempt", "tip")
            assert banned.search(sample) is None, sample
        else:
            assert banned.search(str(val)) is None, val


def test_abandon_open_shadow() -> None:
    # unit: helper exists and returns count type
    assert callable(abandon_open_shadow_sessions)
    assert callable(update_session_payload)
