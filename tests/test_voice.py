"""Voice partner tests (S5) — session gate, conversation, errors, TTS fallback."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.bot import texts
from core.config import Settings
from core.db import close_pool, connection
from apps.bot.handlers.correction import init_correction_prompt
from apps.bot.handlers.voice import handle_voice, init_voice_prompt
from apps.bot.scheduler import EligibleUser, is_user_due_for_morning
from core.services.sessions import (
    bot_initiated_count,
    get_continuable_voice_session,
    get_open_quiz_session,
    has_session_on,
    insert_session,
    local_today,
    save_voice_exchange,
)
from core.services.users import save_onboarding
from core.speech import SpeechError
from telegram.error import BadRequest

FAKE_TELEGRAM_ID_BASE = 9_350_000_000


@pytest.fixture
def fake_telegram_id() -> int:
    return FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)


@pytest.fixture(autouse=True)
def _close_pool_after_test() -> None:
    yield
    close_pool()


@pytest.fixture(autouse=True)
def _init_prompts() -> None:
    init_correction_prompt()
    init_voice_prompt()


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


def test_voice_session_does_not_block_quiz_delivery(cleanup_user: int) -> None:
    """Regression: a morning voice message must not cancel that day's quiz."""
    tid = cleanup_user
    _onboard(tid, morning="07:00", tz="Europe/Vilnius")
    now = datetime(2026, 8, 3, 4, 40, tzinfo=timezone.utc)
    day = local_today("Europe/Vilnius", now)
    assert day == date(2026, 8, 3)

    insert_session(
        tid,
        "voice",
        day,
        payload={"messages": [], "turn_count": 1},
        completed=True,
    )

    assert has_session_on(tid, day) is False
    user = EligibleUser(
        telegram_user_id=tid,
        timezone="Europe/Vilnius",
        morning_time=time(7, 0),
        paused_until=None,
    )
    assert is_user_due_for_morning(user, now) is True


def test_completed_quiz_does_not_block_voice(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 8, 3)
    insert_session(tid, "quiz", day, payload={"questions": []}, completed=True)
    now = datetime(2026, 8, 3, 18, 0, tzinfo=timezone.utc)
    assert (
        get_continuable_voice_session(
            tid, now=now, context_minutes=120, max_turns=10
        )
        is None
    )
    sid = save_voice_exchange(
        None,
        tid,
        day,
        {"messages": [{"role": "user", "content": "hi"}], "turn_count": 1},
    )
    assert sid > 0
    row = get_continuable_voice_session(
        tid, now=now, context_minutes=120, max_turns=10
    )
    assert row is not None
    assert row.task_type == "voice"


def test_voice_while_open_quiz_does_not_consume_answers(cleanup_user: int) -> None:
    """Voice must not grade quiz answers; quiz stays open afterwards."""
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 8, 3)
    quiz_payload = {
        "questions": [
            {
                "error_id": 1,
                "format": "gap",
                "prompt": "I ___ yesterday",
                "accept": ["went"],
            }
        ],
        "index": 0,
        "answers": [],
    }
    insert_session(tid, "quiz", day, payload=quiz_payload, completed=False)
    open_before = get_open_quiz_session(tid, day)
    assert open_before is not None
    assert open_before.completed is False
    assert open_before.payload == quiz_payload

    update = _make_voice_update(tid)
    context = _make_context()
    llm_result = _llm_payload(errors=[])

    with (
        patch("apps.bot.handlers.voice.load_settings", return_value=_settings()),
        patch("apps.bot.handlers.voice.transcribe", return_value="I went to the shop"),
        patch("apps.bot.handlers.voice.chat", return_value=llm_result) as mock_chat,
        patch("apps.bot.handlers.voice.synthesize", return_value=b"opus"),
        patch("apps.bot.handlers.quiz.grade_answer") as mock_grade,
        patch("apps.bot.handlers.quiz.on_quiz_text") as mock_quiz_text,
    ):
        asyncio.run(handle_voice(update, context))
        mock_chat.assert_called()
        mock_grade.assert_not_called()
        mock_quiz_text.assert_not_called()

    open_after = get_open_quiz_session(tid, day)
    assert open_after is not None
    assert open_after.completed is False
    assert open_after.payload == quiz_payload
    assert open_after.id == open_before.id


def test_voice_exchange_does_not_increment_bot_message_counts(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = local_today(
        "Europe/Vilnius", datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    )
    update = _make_voice_update(tid)
    context = _make_context()

    with (
        patch(
            "apps.bot.handlers.voice.load_settings",
            return_value=_settings(),
        ),
        patch(
            "apps.bot.handlers.voice.local_today",
            return_value=day,
        ),
        patch("apps.bot.handlers.voice.transcribe", return_value="Hello friend"),
        patch("apps.bot.handlers.voice.chat", return_value=_llm_payload(errors=[])),
        patch("apps.bot.handlers.voice.synthesize", return_value=b"opus"),
    ):
        asyncio.run(handle_voice(update, context))

    assert bot_initiated_count(tid, day) == 0


def test_conversation_continues_inside_window(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    now = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    day = local_today("Europe/Vilnius", now)
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
    row = get_continuable_voice_session(
        tid, now=now, context_minutes=120, max_turns=10
    )
    assert row is not None
    assert row.payload is not None
    assert row.payload["turn_count"] == 1


def test_conversation_starts_fresh_outside_window(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 8, 3)
    sid = save_voice_exchange(
        None,
        tid,
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
            tid, now=now, context_minutes=120, max_turns=10
        )
        is None
    )


def test_turn_10_final_then_next_opens_new_session(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 8, 3)
    messages: list[dict] = []
    for i in range(9):
        messages.append({"role": "user", "content": f"u{i}"})
        messages.append({"role": "assistant", "content": f"a{i}"})
    save_voice_exchange(
        None, tid, day, {"messages": messages, "turn_count": 9}
    )

    update = _make_voice_update(tid)
    context = _make_context()
    captured: dict = {}

    def _chat(messages_arg, **kwargs):
        system = kwargs.get("system") or ""
        captured["final_turn"] = "final_turn: true" in system
        return _llm_payload(errors=[])

    with (
        patch("apps.bot.handlers.voice.load_settings", return_value=_settings()),
        patch("apps.bot.handlers.voice.local_today", return_value=day),
        patch("apps.bot.handlers.voice.transcribe", return_value="Last turn here"),
        patch("apps.bot.handlers.voice.chat", side_effect=_chat),
        patch("apps.bot.handlers.voice.synthesize", return_value=b"opus"),
    ):
        asyncio.run(handle_voice(update, context))

    assert captured.get("final_turn") is True
    now = datetime.now(timezone.utc)
    # After turn 10, continuable session is exhausted.
    assert (
        get_continuable_voice_session(
            tid, now=now, context_minutes=120, max_turns=10
        )
        is None
    )
    # Next exchange creates a new session id.
    with (
        patch("apps.bot.handlers.voice.load_settings", return_value=_settings()),
        patch("apps.bot.handlers.voice.local_today", return_value=day),
        patch("apps.bot.handlers.voice.transcribe", return_value="Fresh start"),
        patch("apps.bot.handlers.voice.chat", return_value=_llm_payload(errors=[])),
        patch("apps.bot.handlers.voice.synthesize", return_value=b"opus"),
    ):
        asyncio.run(handle_voice(update, context))

    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, payload FROM sessions
             WHERE user_id = %s AND task_type = 'voice'
             ORDER BY id
            """,
            (tid,),
        ).fetchall()
    assert len(rows) == 2
    assert int(rows[0]["payload"]["turn_count"]) == 10
    assert int(rows[1]["payload"]["turn_count"]) == 1


def test_errors_written_with_source_voice_capped_at_3(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 8, 3)
    update = _make_voice_update(tid)
    context = _make_context()
    errors = [
        {
            "you_said": f"err{i}",
            "correct_form": f"ok{i}",
            "error_type": "verb_tense_past",
            "explanation": "Past tense.",
        }
        for i in range(5)
    ]

    with (
        patch("apps.bot.handlers.voice.load_settings", return_value=_settings()),
        patch("apps.bot.handlers.voice.local_today", return_value=day),
        patch("apps.bot.handlers.voice.transcribe", return_value="I go yesterday shop"),
        patch(
            "apps.bot.handlers.voice.chat",
            return_value=_llm_payload(errors=errors),
        ),
        patch("apps.bot.handlers.voice.synthesize", return_value=b"opus"),
    ):
        asyncio.run(handle_voice(update, context))

    with connection() as conn:
        rows = conn.execute(
            """
            SELECT source FROM errors WHERE user_id = %s ORDER BY id
            """,
            (tid,),
        ).fetchall()
    assert len(rows) == 3
    assert all(r["source"] == "voice" for r in rows)


def test_over_length_voice_declined_without_transcribe(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    update = _make_voice_update(tid, duration=180)
    context = _make_context()

    with (
        patch("apps.bot.handlers.voice.load_settings", return_value=_settings()),
        patch("apps.bot.handlers.voice.transcribe") as mock_stt,
    ):
        asyncio.run(handle_voice(update, context))
        mock_stt.assert_not_called()

    update.message.reply_text.assert_awaited_with(texts.VOICE_TOO_LONG)
    context.bot.get_file.assert_not_called()


def test_tts_failure_delivers_text_and_records_errors(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 8, 3)
    update = _make_voice_update(tid)
    context = _make_context()
    err = {
        "you_said": "I go",
        "correct_form": "I went",
        "error_type": "verb_tense_past",
        "explanation": "Past needs went.",
    }

    with (
        patch("apps.bot.handlers.voice.load_settings", return_value=_settings()),
        patch("apps.bot.handlers.voice.local_today", return_value=day),
        patch("apps.bot.handlers.voice.transcribe", return_value="I go to park"),
        patch(
            "apps.bot.handlers.voice.chat",
            return_value=_llm_payload(reply="What did you see?", errors=[err]),
        ),
        patch(
            "apps.bot.handlers.voice.synthesize",
            side_effect=SpeechError("tts down"),
        ),
    ):
        asyncio.run(handle_voice(update, context))

    update.message.reply_voice.assert_not_awaited()
    # First text reply is the spoken fallback; second is the correction block.
    text_calls = [c.args[0] for c in update.message.reply_text.await_args_list]
    assert "What did you see?" in text_calls
    assert any("I go" in t for t in text_calls)

    with connection() as conn:
        rows = conn.execute(
            "SELECT source FROM errors WHERE user_id = %s",
            (tid,),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["source"] == "voice"


# --- S5a: processing status + repeating chat action --------------------------


def test_s5a_happy_path_status_order(cleanup_user: int) -> None:
    """Status created once, edited twice, deleted before voice send."""
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 8, 3)
    update = _make_voice_update(tid)
    context = _make_context()
    order: list[str] = []

    async def _reply_text(text: str, **_kwargs: object) -> MagicMock:
        order.append(f"reply:{text}")
        msg = MagicMock()
        msg.message_id = 9001
        return msg

    async def _edit(*, chat_id: int, message_id: int, text: str) -> None:
        order.append(f"edit:{text}")

    async def _delete(*, chat_id: int, message_id: int) -> None:
        order.append("delete")

    async def _reply_voice(**_kwargs: object) -> None:
        order.append("voice")

    update.message.reply_text = AsyncMock(side_effect=_reply_text)
    update.message.reply_voice = AsyncMock(side_effect=_reply_voice)
    context.bot.edit_message_text = AsyncMock(side_effect=_edit)
    context.bot.delete_message = AsyncMock(side_effect=_delete)

    with (
        patch("apps.bot.handlers.voice.load_settings", return_value=_settings()),
        patch("apps.bot.handlers.voice.local_today", return_value=day),
        patch("apps.bot.handlers.voice.transcribe", return_value="Hello there friend"),
        patch("apps.bot.handlers.voice.chat", return_value=_llm_payload(errors=[])),
        patch("apps.bot.handlers.voice.synthesize", return_value=b"opus"),
    ):
        asyncio.run(handle_voice(update, context))

    # First reply_text is status; later reply_text is correction (after voice).
    assert order[0] == f"reply:{texts.VOICE_STATUS_LISTENING}"
    assert order[1] == f"edit:{texts.VOICE_STATUS_THINKING}"
    assert order[2] == f"edit:{texts.VOICE_STATUS_RECORDING}"
    assert order[3] == "delete"
    assert order[4] == "voice"
    assert any(s.startswith("reply:") and "👍" in s for s in order[5:])


def test_s5a_empty_transcript_edits_status(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    update = _make_voice_update(tid)
    context = _make_context()

    with (
        patch("apps.bot.handlers.voice.load_settings", return_value=_settings()),
        patch("apps.bot.handlers.voice.transcribe", return_value=" "),
    ):
        asyncio.run(handle_voice(update, context))

    context.bot.edit_message_text.assert_awaited()
    edit_texts = [
        c.kwargs.get("text") or (c.args[0] if c.args else None)
        for c in context.bot.edit_message_text.await_args_list
    ]
    # edit_message_text is called with keyword text=
    edit_texts = [
        c.kwargs["text"] for c in context.bot.edit_message_text.await_args_list
    ]
    assert texts.VOICE_DIDNT_CATCH in edit_texts
    # No separate user-facing message beyond the initial status create.
    assert update.message.reply_text.await_count == 1
    update.message.reply_text.assert_awaited_with(texts.VOICE_STATUS_LISTENING)
    context.bot.delete_message.assert_not_awaited()


def test_s5a_llm_failure_ends_as_failure_text(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 8, 3)
    update = _make_voice_update(tid)
    context = _make_context()

    from core.llm import LLMError

    with (
        patch("apps.bot.handlers.voice.load_settings", return_value=_settings()),
        patch("apps.bot.handlers.voice.local_today", return_value=day),
        patch("apps.bot.handlers.voice.transcribe", return_value="Hello there friend"),
        patch(
            "apps.bot.handlers.voice.chat",
            side_effect=LLMError("down"),
        ),
    ):
        asyncio.run(handle_voice(update, context))

    edit_texts = [
        c.kwargs["text"] for c in context.bot.edit_message_text.await_args_list
    ]
    assert texts.VOICE_STATUS_THINKING in edit_texts
    assert texts.LLM_RETRY in edit_texts
    assert texts.LLM_FAILED in edit_texts
    assert edit_texts[-1] == texts.LLM_FAILED
    assert texts.VOICE_STATUS_THINKING != edit_texts[-1]
    context.bot.delete_message.assert_not_awaited()
    update.message.reply_voice.assert_not_awaited()


def test_s5a_exception_clears_status_and_cancels_action(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    update = _make_voice_update(tid)
    context = _make_context()
    cancelled: dict[str, bool] = {"seen": False}

    real_create = asyncio.create_task

    def _tracking_create(coro, **kwargs):  # type: ignore[no-untyped-def]
        task = real_create(coro, **kwargs)

        def _on_done(t: asyncio.Task) -> None:
            if t.cancelled():
                cancelled["seen"] = True

        task.add_done_callback(_on_done)
        return task

    with (
        patch("apps.bot.handlers.voice.load_settings", return_value=_settings()),
        patch("apps.bot.handlers.voice.asyncio.create_task", side_effect=_tracking_create),
        patch(
            "apps.bot.handlers.voice.transcribe",
            side_effect=RuntimeError("boom"),
        ),
    ):
        asyncio.run(handle_voice(update, context))

    edit_texts = [
        c.kwargs["text"] for c in context.bot.edit_message_text.await_args_list
    ]
    assert texts.LLM_FAILED in edit_texts
    assert cancelled["seen"] is True


def test_s5a_over_length_no_status_no_chat_action(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    update = _make_voice_update(tid, duration=180)
    context = _make_context()

    with (
        patch("apps.bot.handlers.voice.load_settings", return_value=_settings()),
        patch("apps.bot.handlers.voice.transcribe") as mock_stt,
    ):
        asyncio.run(handle_voice(update, context))
        mock_stt.assert_not_called()

    update.message.reply_text.assert_awaited_once_with(texts.VOICE_TOO_LONG)
    context.bot.send_chat_action.assert_not_awaited()
    context.bot.edit_message_text.assert_not_awaited()
    context.bot.get_file.assert_not_called()


def test_s5a_status_does_not_increment_bot_message_counts(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 8, 3)
    update = _make_voice_update(tid)
    context = _make_context()

    with (
        patch("apps.bot.handlers.voice.load_settings", return_value=_settings()),
        patch("apps.bot.handlers.voice.local_today", return_value=day),
        patch("apps.bot.handlers.voice.transcribe", return_value="Hello there friend"),
        patch("apps.bot.handlers.voice.chat", return_value=_llm_payload(errors=[])),
        patch("apps.bot.handlers.voice.synthesize", return_value=b"opus"),
    ):
        asyncio.run(handle_voice(update, context))

    assert bot_initiated_count(tid, day) == 0


def test_s5a_failed_delete_still_sends_voice(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 8, 3)
    update = _make_voice_update(tid)
    context = _make_context()
    context.bot.delete_message = AsyncMock(
        side_effect=BadRequest("message to delete not found")
    )

    with (
        patch("apps.bot.handlers.voice.load_settings", return_value=_settings()),
        patch("apps.bot.handlers.voice.local_today", return_value=day),
        patch("apps.bot.handlers.voice.transcribe", return_value="Hello there friend"),
        patch("apps.bot.handlers.voice.chat", return_value=_llm_payload(errors=[])),
        patch("apps.bot.handlers.voice.synthesize", return_value=b"opus"),
    ):
        asyncio.run(handle_voice(update, context))

    update.message.reply_voice.assert_awaited()
