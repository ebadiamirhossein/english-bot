"""S26 text conversation (/talk) — behaviour, close-out, prompts, labels."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, Message, Update, User

from app import texts
from app.db import close_pool, connection, migrate
from app.handlers.conversation import (
    build_conversation_close_prompt,
    build_conversation_system_prompt,
    init_conversation_prompt,
    on_conversation_text,
    on_talk_callback,
    on_talk_command,
    s26_button_labels,
    _close_out,
)
from app.handlers.correction import init_correction_prompt
from app.handlers.quiz import open_quiz_awaits_gap_answer
from app.llm import LLMError
from app.services.sessions import (
    get_open_conversation_session,
    insert_session,
    utc_now_iso,
)
from app.services.users import get_user, save_onboarding, set_paused_until

FAKE_TELEGRAM_ID_BASE = 9_480_000_000
_FROZEN = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
_PROMPT_DIR = Path(__file__).resolve().parents[1] / "app" / "prompts"


@pytest.fixture
def fake_telegram_id() -> int:
    return FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)


@pytest.fixture(autouse=True)
def _close_pool_after_test() -> None:
    yield
    close_pool()


@pytest.fixture
def cleanup_user(fake_telegram_id: int):
    yield fake_telegram_id
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM users WHERE telegram_user_id = %s",
                (fake_telegram_id,),
            )


@pytest.fixture(autouse=True)
def _init_prompts() -> None:
    init_correction_prompt()
    init_conversation_prompt()


def _onboard(tid: int) -> None:
    save_onboarding(
        tid,
        {
            "name": "Talk Test",
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


def _quiz_gap_payload() -> dict[str, Any]:
    return {
        "index": 0,
        "chat_id": 1,
        "message_id": 1,
        "answered": 0,
        "questions": [
            {
                "error_id": 1,
                "format": "gap",
                "prompt": "I ___ yesterday",
                "accept": ["went"],
            }
        ],
    }


def _conv_payload(
    *,
    phase: str = "active",
    topic: str = "weekend plans",
    turn_count: int = 0,
    messages: list[dict[str, str]] | None = None,
    last_activity: datetime | None = None,
) -> dict[str, Any]:
    when = last_activity or _FROZEN
    return {
        "phase": phase,
        "topic": topic,
        "messages": list(messages or []),
        "turn_count": turn_count,
        "last_activity": utc_now_iso(when),
        "warned_last_turn": False,
    }


def _make_message(tid: int, text: str) -> MagicMock:
    message = MagicMock(spec=Message)
    message.text = text
    message.chat_id = tid
    message.from_user = MagicMock(id=tid)
    message.reply_text = AsyncMock()
    message.chat = MagicMock()
    message.chat.send_action = AsyncMock()
    return message


def _make_update(tid: int, text: str) -> tuple[MagicMock, MagicMock]:
    message = _make_message(tid, text)
    update = MagicMock(spec=Update)
    update.message = message
    update.effective_user = MagicMock(id=tid)
    update.callback_query = None
    return update, message


def _error_count(user_id: int) -> int:
    with connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM errors WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    return int(row["n"])


def _settings_mock() -> MagicMock:
    settings = MagicMock()
    settings.conversation_timeout_minutes = 30
    settings.conversation_awaiting_topic_minutes = 2
    settings.conversation_max_turns = 12
    settings.conversation_history_max_messages = 20
    return settings


def test_migration_008_accepts_conversation_source(cleanup_user: int) -> None:
    assert migrate() == []
    tid = cleanup_user
    _onboard(tid)
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO errors (
                    user_id, source, you_said, correct_form,
                    error_type, next_review
                ) VALUES (
                    %s, 'conversation', 'I go', 'I went',
                    'verb_tense_past', CURRENT_DATE + 1
                )
                """,
                (tid,),
            )
    assert _error_count(tid) == 1


def test_s26_button_labels_max_20() -> None:
    for label in s26_button_labels():
        assert len(label) <= 20, f"{label!r} is {len(label)} chars"


def test_prompt_instructs_recast_and_do_not_force() -> None:
    turn_txt = (_PROMPT_DIR / "conversation.txt").read_text(encoding="utf-8")
    assert "corrected form" in turn_txt.lower()
    assert "not a checklist" in turn_txt.lower()
    assert "Do NOT stop the conversation to correct" in turn_txt
    assert "do NOT read this list aloud" in turn_txt
    close_txt = (_PROMPT_DIR / "conversation_close.txt").read_text(
        encoding="utf-8"
    )
    assert "Maximum 3" in close_txt
    assert "recurring" in close_txt.lower()


@pytest.mark.parametrize(
    "entry",
    ["command", "command_topic", "callback_topic", "callback_other"],
)
def test_talk_refuses_every_entry_path_while_gap_open(
    cleanup_user: int, entry: str
) -> None:
    tid = cleanup_user
    _onboard(tid)
    insert_session(
        tid,
        "quiz",
        date(2026, 8, 14),
        payload=_quiz_gap_payload(),
        completed=False,
    )
    assert open_quiz_awaits_gap_answer(tid) is True

    async def _run() -> None:
        context = MagicMock()
        context.args = []

        if entry == "command":
            update, message = _make_update(tid, "/talk")
            await on_talk_command(update, context)
            assert texts.TALK_GAP_QUIZ_WAITING in message.reply_text.await_args.args[0]
        elif entry == "command_topic":
            update, message = _make_update(tid, "/talk weekend")
            context.args = ["weekend"]
            await on_talk_command(update, context)
            assert texts.TALK_GAP_QUIZ_WAITING in message.reply_text.await_args.args[0]
        elif entry == "callback_topic":
            update, message = _make_update(tid, "x")
            query = MagicMock(spec=CallbackQuery)
            query.from_user = User(id=tid, first_name="A", is_bot=False)
            query.data = "talk:topic:0"
            query.answer = AsyncMock()
            query.message = message
            update.callback_query = query
            update.message = None
            update.effective_user = query.from_user
            await on_talk_callback(update, context)
            assert any(
                texts.TALK_GAP_QUIZ_WAITING in str(c.args)
                for c in message.reply_text.await_args_list
            )
        else:
            update, message = _make_update(tid, "x")
            query = MagicMock(spec=CallbackQuery)
            query.from_user = User(id=tid, first_name="A", is_bot=False)
            query.data = "talk:other"
            query.answer = AsyncMock()
            query.message = message
            update.callback_query = query
            update.message = None
            update.effective_user = query.from_user
            await on_talk_callback(update, context)
            assert any(
                texts.TALK_GAP_QUIZ_WAITING in str(c.args)
                for c in message.reply_text.await_args_list
            )

        with connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM sessions
                 WHERE user_id = %s AND task_type = 'conversation'
                """,
                (tid,),
            ).fetchone()
        assert int(row["n"]) == 0

    asyncio.run(_run())


def test_talk_works_while_paused(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    set_paused_until(tid, date(2099, 1, 1))

    async def _run() -> None:
        update, message = _make_update(tid, "/talk weekend plans")
        context = MagicMock()
        context.args = ["weekend", "plans"]
        with patch(
            "app.handlers.conversation.datetime"
        ) as mock_dt:
            mock_dt.now = MagicMock(return_value=_FROZEN)
            await on_talk_command(update, context)
        assert message.reply_text.await_count >= 1
        session = get_open_conversation_session(
            tid,
            now=_FROZEN,
            active_minutes=30,
            awaiting_topic_minutes=2,
        )
        assert session is not None

    asyncio.run(_run())


def test_turn_llm_failure_keeps_session_open_no_turn_count(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    insert_session(
        tid,
        "conversation",
        date(2026, 8, 14),
        payload=_conv_payload(turn_count=3),
        completed=False,
    )

    async def _to_thread(fn, *a, **k):
        raise LLMError("boom")

    async def _run() -> None:
        update, message = _make_update(tid, "I go to the shop yesterday")
        context = MagicMock()
        with (
            patch("app.handlers.conversation.datetime") as mock_dt,
            patch(
                "app.handlers.conversation.load_settings",
                return_value=_settings_mock(),
            ),
            patch(
                "app.handlers.conversation.asyncio.to_thread",
                side_effect=_to_thread,
            ),
        ):
            mock_dt.now = MagicMock(return_value=_FROZEN)
            await on_conversation_text(update, context)

        assert texts.TALK_TURN_FAILED in message.reply_text.await_args.args[0]
        session = get_open_conversation_session(
            tid,
            now=_FROZEN,
            active_minutes=30,
            awaiting_topic_minutes=2,
        )
        assert session is not None
        assert int(session.payload["turn_count"]) == 3
        assert _error_count(tid) == 0

    asyncio.run(_run())


def test_successful_turn_uses_to_thread_no_errors(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    insert_session(
        tid,
        "conversation",
        date(2026, 8, 14),
        payload=_conv_payload(turn_count=1),
        completed=False,
    )
    to_thread_calls: list[Any] = []

    async def _to_thread(fn, *a, **k):
        to_thread_calls.append(fn)
        return "Nice — you went there yesterday. What happened next?"

    async def _run() -> None:
        update, message = _make_update(tid, "I go there yesterday")
        context = MagicMock()
        with (
            patch("app.handlers.conversation.datetime") as mock_dt,
            patch(
                "app.handlers.conversation.load_settings",
                return_value=_settings_mock(),
            ),
            patch(
                "app.handlers.conversation.asyncio.to_thread",
                side_effect=_to_thread,
            ),
        ):
            mock_dt.now = MagicMock(return_value=_FROZEN)
            await on_conversation_text(update, context)

        assert to_thread_calls
        assert _error_count(tid) == 0
        session = get_open_conversation_session(
            tid,
            now=_FROZEN,
            active_minutes=30,
            awaiting_topic_minutes=2,
        )
        assert session is not None
        assert int(session.payload["turn_count"]) == 2
        assert session.completed is False

    asyncio.run(_run())


def test_turn_cap_warns_then_closes(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    insert_session(
        tid,
        "conversation",
        date(2026, 8, 14),
        payload=_conv_payload(
            turn_count=10,
            messages=[{"role": "assistant", "content": "hi"}],
        ),
        completed=False,
    )

    async def _thread_turn(fn, *a, **kw):
        if kw.get("json_mode"):
            return {"errors": [], "did_well": "Clear storytelling."}
        return "What else happened?"

    async def _run() -> None:
        update, message = _make_update(tid, "turn eleven")
        context = MagicMock()
        with (
            patch("app.handlers.conversation.datetime") as mock_dt,
            patch(
                "app.handlers.conversation.load_settings",
                return_value=_settings_mock(),
            ),
            patch(
                "app.handlers.conversation.asyncio.to_thread",
                side_effect=_thread_turn,
            ),
        ):
            mock_dt.now = MagicMock(return_value=_FROZEN)
            await on_conversation_text(update, context)
            warn_body = message.reply_text.await_args.args[0]
            assert texts.TALK_LAST_TURN_WARN.strip() in warn_body

            update2, message2 = _make_update(tid, "turn twelve")
            await on_conversation_text(update2, context)
            assert any(
                texts.TALK_CLOSING in str(c.args)
                for c in message2.reply_text.await_args_list
            )

        session = get_open_conversation_session(
            tid,
            now=_FROZEN,
            active_minutes=30,
            awaiting_topic_minutes=2,
        )
        assert session is None
        with connection() as conn:
            row = conn.execute(
                """
                SELECT completed FROM sessions
                 WHERE user_id = %s AND task_type = 'conversation'
                 ORDER BY id DESC LIMIT 1
                """,
                (tid,),
            ).fetchone()
        assert bool(row["completed"]) is True

    asyncio.run(_run())


def test_failed_close_send_writes_zero_errors(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    sid = insert_session(
        tid,
        "conversation",
        date(2026, 8, 14),
        payload=_conv_payload(
            turn_count=2,
            messages=[
                {"role": "user", "content": "I go yesterday"},
                {"role": "assistant", "content": "You went yesterday?"},
            ],
        ),
        completed=False,
    )

    async def _thread(fn, *a, **kw):
        return {
            "errors": [
                {
                    "you_said": "I go",
                    "correct_form": "I went",
                    "error_type": "verb_tense_past",
                    "explanation": "Past tense for finished time.",
                }
            ],
            "did_well": "Clear detail.",
        }

    async def _run() -> None:
        message = _make_message(tid, "end")
        message.reply_text = AsyncMock(side_effect=RuntimeError("send failed"))
        user = get_user(tid)
        assert user is not None
        with patch(
            "app.handlers.conversation.asyncio.to_thread",
            side_effect=_thread,
        ):
            await _close_out(
                message,
                tid,
                sid,
                _conv_payload(
                    turn_count=2,
                    messages=[
                        {"role": "user", "content": "I go yesterday"},
                        {"role": "assistant", "content": "You went?"},
                    ],
                ),
                user=user,
            )
        assert _error_count(tid) == 0
        with connection() as conn:
            row = conn.execute(
                "SELECT completed FROM sessions WHERE id = %s",
                (sid,),
            ).fetchone()
        assert bool(row["completed"]) is False

    asyncio.run(_run())


def test_successful_close_writes_at_most_three_errors(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    sid = insert_session(
        tid,
        "conversation",
        date(2026, 8, 14),
        payload=_conv_payload(
            turn_count=4,
            messages=[
                {"role": "user", "content": "I go yesterday"},
                {"role": "assistant", "content": "You went?"},
            ],
        ),
        completed=False,
    )

    async def _thread(fn, *a, **kw):
        return {
            "errors": [
                {
                    "you_said": f"bad{i}",
                    "correct_form": f"good{i}",
                    "error_type": "verb_tense_past",
                    "explanation": "Past tense.",
                }
                for i in range(5)
            ],
            "did_well": "Clear detail.",
        }

    async def _run() -> None:
        message = _make_message(tid, "end")
        user = get_user(tid)
        assert user is not None
        with patch(
            "app.handlers.conversation.asyncio.to_thread",
            side_effect=_thread,
        ):
            await _close_out(
                message,
                tid,
                sid,
                _conv_payload(
                    turn_count=4,
                    messages=[
                        {"role": "user", "content": "I go yesterday"},
                        {"role": "assistant", "content": "You went?"},
                    ],
                ),
                user=user,
            )
        assert _error_count(tid) == 3
        with connection() as conn:
            row = conn.execute(
                "SELECT completed FROM sessions WHERE id = %s",
                (sid,),
            ).fetchone()
            src = conn.execute(
                "SELECT source FROM errors WHERE user_id = %s LIMIT 1",
                (tid,),
            ).fetchone()
        assert bool(row["completed"]) is True
        assert src["source"] == "conversation"

    asyncio.run(_run())


def test_abandoned_incomplete_writes_zero_errors(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    insert_session(
        tid,
        "conversation",
        date(2026, 8, 14),
        payload=_conv_payload(turn_count=2),
        completed=False,
    )
    assert _error_count(tid) == 0


def test_system_prompt_builds_for_user(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    user = get_user(tid)
    assert user is not None
    prompt = build_conversation_system_prompt(user, topic="weekend")
    assert "weekend" in prompt
    assert "checklist" in prompt.lower()
    close = build_conversation_close_prompt(user)
    assert "Maximum 3" in close


def test_grep_no_mid_conversation_record_errors() -> None:
    """Handler must not call record_errors except inside _close_out."""
    src = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "handlers"
        / "conversation.py"
    ).read_text(encoding="utf-8")
    # Only one call site: inside _close_out after successful send.
    assert src.count("record_errors(") == 1
    assert "record_errors" in src[src.index("async def _close_out") :]
