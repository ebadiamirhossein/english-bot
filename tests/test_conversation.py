"""S26/S26a text conversation (/talk) — behaviour, close-out, prompts, labels."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, Message, Update, User

from apps.bot import texts
from core.config import Settings
from core.db import close_pool, connection, migrate
from apps.bot.handlers.conversation import (
    build_conversation_close_messages,
    build_conversation_close_prompt,
    build_conversation_system_prompt,
    build_conversation_turn_messages,
    build_topic_pool,
    chunk_topic_label,
    get_picking_conversation_session,
    init_conversation_prompt,
    on_conversation_text,
    on_talk_callback,
    on_talk_command,
    open_conversation_awaits_text,
    rotate_topics,
    s26_button_labels,
    _close_out,
    _safe_exc_msg,
)
from apps.bot.handlers.correction import init_correction_prompt
from apps.bot.handlers.quiz import open_quiz_awaits_gap_answer
from core.llm import LLMError, _to_anthropic_messages, chat
from core.services.sessions import (
    get_open_conversation_session,
    insert_session,
    update_session_payload,
    utc_now_iso,
)
from core.services.identity import save_onboarding
from core.services.users import get_user, set_paused_until
FAKE_TELEGRAM_ID_BASE = 9_480_000_000
_FROZEN = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
_PROMPT_DIR = (
    Path(__file__).resolve().parents[1] / "packages" / "core" / "prompts"
)


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
                "DELETE FROM users WHERE id = %s",
                (fake_telegram_id,),
            )


@pytest.fixture(autouse=True)
def _init_prompts() -> None:
    init_correction_prompt()
    init_conversation_prompt()


def _onboard(tid: int) -> int:
    user_id = save_onboarding(
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
    return user_id


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
    message.message_id = 7001
    message.from_user = MagicMock(id=tid)
    sent = MagicMock()
    sent.message_id = 9001
    message.reply_text = AsyncMock(return_value=sent)
    message.edit_text = AsyncMock()
    message.edit_reply_markup = AsyncMock()
    message.chat = MagicMock()
    message.chat.send_action = AsyncMock()
    bot = MagicMock()
    bot.edit_message_reply_markup = AsyncMock()
    bot.set_message_reaction = AsyncMock()
    message.get_bot = MagicMock(return_value=bot)
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
    user_id = _onboard(tid)
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
                (user_id,),
            )
    assert _error_count(user_id) == 1


def test_s26_button_labels_max_20() -> None:
    for label in s26_button_labels():
        assert len(label) <= 20, f"{label!r} is {len(label)} chars"


def test_prompt_instructs_recast_and_do_not_force() -> None:
    turn_txt = (_PROMPT_DIR / "conversation.txt").read_text(encoding="utf-8")
    assert "only when there is an error" in turn_txt.lower()
    assert "Never restate the whole message" in turn_txt
    assert "Contribute something every turn" in turn_txt
    assert "Do not end every turn with a question" in turn_txt
    assert "Vary length" in turn_txt
    assert "sometimes and naturally" in turn_txt.lower()
    assert "not a checklist" in turn_txt.lower()
    assert "Do NOT stop the conversation to correct" in turn_txt
    assert "do NOT read this list aloud" in turn_txt
    assert "Never repeat an ungrammatical form" in turn_txt
    assert "every reused fragment must be correct English" in turn_txt
    assert "end with a question unless" not in turn_txt.lower()
    assert "short paragraphs" in turn_txt.lower()
    assert "own line" in turn_txt.lower()
    assert "Emoji occasionally" in turn_txt
    close_txt = (_PROMPT_DIR / "conversation_close.txt").read_text(
        encoding="utf-8"
    )
    assert "Maximum 3" in close_txt
    assert "recurring" in close_txt.lower()
    assert "ONE language only" in close_txt
    assert "transliterat" in close_txt.lower()


def test_close_failure_copy_distinct_from_turn_failure() -> None:
    assert texts.TALK_CLOSE_FAILED != texts.TALK_TURN_FAILED
    assert "done chatting" in texts.TALK_CLOSE_FAILED.lower()
    assert "say it again" not in texts.TALK_CLOSE_FAILED.lower()


@pytest.mark.parametrize(
    "entry",
    ["command", "command_topic", "callback_topic", "callback_other"],
)
def test_talk_refuses_every_entry_path_while_gap_open(
    cleanup_user: int, entry: str
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    insert_session(
        user_id,
        "quiz",
        date(2026, 8, 14),
        payload=_quiz_gap_payload(),
        completed=False,
    )
    assert open_quiz_awaits_gap_answer(user_id) is True

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
                (user_id,),
            ).fetchone()
        assert int(row["n"]) == 0

    asyncio.run(_run())


def test_talk_works_while_paused(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    set_paused_until(user_id, date(2099, 1, 1))

    async def _run() -> None:
        update, message = _make_update(tid, "/talk weekend plans")
        context = MagicMock()
        context.args = ["weekend", "plans"]
        with patch(
            "apps.bot.handlers.conversation.datetime"
        ) as mock_dt:
            mock_dt.now = MagicMock(return_value=_FROZEN)
            await on_talk_command(update, context)
        assert message.reply_text.await_count >= 1
        session = get_open_conversation_session(
            user_id,
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
    user_id = _onboard(tid)
    insert_session(
        user_id,
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
            patch("apps.bot.handlers.conversation.datetime") as mock_dt,
            patch(
                "apps.bot.handlers.conversation.load_settings",
                return_value=_settings_mock(),
            ),
            patch(
                "apps.bot.handlers.conversation.asyncio.to_thread",
                side_effect=_to_thread,
            ),
        ):
            mock_dt.now = MagicMock(return_value=_FROZEN)
            await on_conversation_text(update, context)

        assert texts.TALK_TURN_FAILED in message.reply_text.await_args.args[0]
        session = get_open_conversation_session(
            user_id,
            now=_FROZEN,
            active_minutes=30,
            awaiting_topic_minutes=2,
        )
        assert session is not None
        assert int(session.payload["turn_count"]) == 3
        assert _error_count(user_id) == 0

    asyncio.run(_run())


def test_successful_turn_uses_to_thread_no_errors(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    insert_session(
        user_id,
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
            patch("apps.bot.handlers.conversation.datetime") as mock_dt,
            patch(
                "apps.bot.handlers.conversation.load_settings",
                return_value=_settings_mock(),
            ),
            patch(
                "apps.bot.handlers.conversation.asyncio.to_thread",
                side_effect=_to_thread,
            ),
        ):
            mock_dt.now = MagicMock(return_value=_FROZEN)
            await on_conversation_text(update, context)

        assert to_thread_calls
        assert _error_count(user_id) == 0
        session = get_open_conversation_session(
            user_id,
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
    user_id = _onboard(tid)
    insert_session(
        user_id,
        "conversation",
        date(2026, 8, 14),
        payload=_conv_payload(
            turn_count=10,
            messages=[{"role": "assistant", "content": "hi"}],
        ),
        completed=False,
    )

    async def _thread_turn(fn, *a, **kw):
        if getattr(fn, "__name__", "") == "_generate_close_result":
            return {"errors": [], "did_well": "Clear storytelling."}
        return "What else happened?"

    async def _run() -> None:
        update, message = _make_update(tid, "turn eleven")
        context = MagicMock()
        with (
            patch("apps.bot.handlers.conversation.datetime") as mock_dt,
            patch(
                "apps.bot.handlers.conversation.load_settings",
                return_value=_settings_mock(),
            ),
            patch(
                "apps.bot.handlers.conversation.asyncio.to_thread",
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
            user_id,
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
                (user_id,),
            ).fetchone()
        assert bool(row["completed"]) is True

    asyncio.run(_run())


def test_failed_close_send_writes_zero_errors(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    sid = insert_session(
        user_id,
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
        message = _make_message(user_id, "end")
        message.reply_text = AsyncMock(side_effect=RuntimeError("send failed"))
        user = get_user(user_id)
        assert user is not None
        with patch(
            "apps.bot.handlers.conversation.asyncio.to_thread",
            side_effect=_thread,
        ):
            await _close_out(
                message,
                user_id,
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
        assert _error_count(user_id) == 0
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
    user_id = _onboard(tid)
    sid = insert_session(
        user_id,
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
        message = _make_message(user_id, "end")
        user = get_user(user_id)
        assert user is not None
        with patch(
            "apps.bot.handlers.conversation.asyncio.to_thread",
            side_effect=_thread,
        ):
            await _close_out(
                message,
                user_id,
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
        assert _error_count(user_id) == 3
        with connection() as conn:
            row = conn.execute(
                "SELECT completed FROM sessions WHERE id = %s",
                (sid,),
            ).fetchone()
            src = conn.execute(
                "SELECT source FROM errors WHERE user_id = %s LIMIT 1",
                (user_id,),
            ).fetchone()
        assert bool(row["completed"]) is True
        assert src["source"] == "conversation"

    asyncio.run(_run())


def test_abandoned_incomplete_writes_zero_errors(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    insert_session(
        user_id,
        "conversation",
        date(2026, 8, 14),
        payload=_conv_payload(turn_count=2),
        completed=False,
    )
    assert _error_count(user_id) == 0


def test_system_prompt_builds_for_user(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    user = get_user(user_id)
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
        / "apps"
        / "bot"
        / "handlers"
        / "conversation.py"
    ).read_text(encoding="utf-8")
    # Only one call site: inside _close_out after successful send.
    assert src.count("record_errors(") == 1
    assert "record_errors" in src[src.index("async def _close_out") :]


def _realistic_history() -> list[dict[str, str]]:
    """Opener-first transcript ending on assistant — the live shape that broke."""
    return [
        {
            "role": "assistant",
            "content": (
                "Alright — let's talk about weekend plans. "
                "What's on your mind?"
            ),
        },
        {
            "role": "user",
            "content": (
                "I want to after work go home and a little resting "
                "and preparing for drinking alcohol"
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Nice — go home after work, rest a little, and get ready "
                "for a fun night with some drinks. Who are you meeting?"
            ),
        },
        {
            "role": "user",
            "content": "Maybe my friends from university",
        },
        {
            "role": "assistant",
            "content": (
                "Cool — university friends. What do you usually do together?"
            ),
        },
        {
            "role": "user",
            "content": "We talk about job and sometimes play games",
        },
        {
            "role": "assistant",
            "content": (
                "Sounds fun — talking about jobs and playing games. "
                "Any game you love lately?"
            ),
        },
    ]


def _seed_recurring_errors(tid: int) -> None:
    with connection() as conn:
        with conn.transaction():
            for code, said, form in (
                ("verb_tense_past", "I go yesterday", "I went yesterday"),
                ("article_missing", "I saw movie", "I saw a movie"),
                ("preposition", "depend of", "depend on"),
            ):
                conn.execute(
                    """
                    INSERT INTO errors (
                        user_id, source, you_said, correct_form,
                        error_type, next_review, resolved
                    ) VALUES (
                        %s, 'text', %s, %s, %s,
                        CURRENT_DATE + 1, FALSE
                    )
                    """,
                    (tid, said, form, code),
                )


def _llm_settings() -> Settings:
    return Settings(
        database_url="postgresql://x:y@localhost:5433/english_bot",
        telegram_bot_token="token",
        llm_api_key="test-key",
        llm_provider="anthropic",
        llm_model="claude-sonnet-5",
    )


def _mock_llm_response(
    text: str, *, stop_reason: str = "end_turn", output_tokens: int = 5
) -> MagicMock:
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    response.stop_reason = stop_reason
    response.usage = MagicMock(
        input_tokens=10,
        output_tokens=output_tokens,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return response


def test_close_request_constructs_from_realistic_payload(
    cleanup_user: int,
) -> None:
    """Regression: close path must build a valid provider request (S26a).

    Mocks at the Anthropic transport only — prompt render, message shaping,
    and ``chat()`` construction all run for real.
    """
    tid = cleanup_user
    user_id = _onboard(tid)
    _seed_recurring_errors(user_id)
    user = get_user(user_id)
    assert user is not None

    history = _realistic_history()
    assert history[0]["role"] == "assistant"
    assert history[-1]["role"] == "assistant"

    system = build_conversation_close_prompt(user)
    messages = build_conversation_close_messages(history, max_messages=20)
    assert messages[-1]["role"] == "user"
    _to_anthropic_messages(messages)

    close_json = (
        '{"errors":[],"did_well":"You kept the chat going with concrete detail."}'
    )
    with patch("core.llm.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.return_value = _mock_llm_response(close_json)
        result = chat(
            messages,
            system=system,
            json_mode=True,
            max_tokens=2000,
            reject_truncation=True,
            settings=_llm_settings(),
        )
    assert isinstance(result, dict)
    assert client.messages.create.call_count == 1
    sent = client.messages.create.call_args.kwargs["messages"]
    assert sent[-1]["role"] == "user"
    assert sent[0]["role"] == "assistant"


def test_turn_request_constructs_from_realistic_payload(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _seed_recurring_errors(user_id)
    user = get_user(user_id)
    assert user is not None

    history = _realistic_history()
    system = build_conversation_system_prompt(user, topic="weekend plans")
    messages = build_conversation_turn_messages(
        history, "We play chess mostly", max_messages=20
    )
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "We play chess mostly"
    _to_anthropic_messages(messages)

    with patch("core.llm.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.return_value = _mock_llm_response(
            "Chess is great — rated or just for fun?"
        )
        result = chat(
            messages,
            system=system,
            json_mode=False,
            max_tokens=500,
            reject_truncation=True,
            settings=_llm_settings(),
        )
    assert isinstance(result, str)
    assert client.messages.create.call_count == 1
    sent = client.messages.create.call_args.kwargs["messages"]
    assert sent[-1]["role"] == "user"


def test_failed_close_generation_completes_session_zero_errors(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    history = _realistic_history()
    sid = insert_session(
        user_id,
        "conversation",
        date(2026, 8, 14),
        payload=_conv_payload(turn_count=3, messages=history),
        completed=False,
    )

    async def _run() -> None:
        message = _make_message(user_id, "end")
        user = get_user(user_id)
        assert user is not None
        with (
            patch(
                "apps.bot.handlers.conversation.asyncio.to_thread",
                side_effect=LLMError(
                    "Anthropic API error 400: conversation must end "
                    "with a user message"
                ),
            ),
            caplog.at_level(
                logging.WARNING, logger="apps.bot.handlers.conversation"
            ),
        ):
            await _close_out(
                message,
                user_id,
                sid,
                _conv_payload(turn_count=3, messages=history),
                user=user,
            )
        assert message.reply_text.await_count == 1
        assert message.reply_text.await_args.args[0] == texts.TALK_CLOSE_FAILED
        assert _error_count(user_id) == 0
        with connection() as conn:
            row = conn.execute(
                "SELECT completed FROM sessions WHERE id = %s",
                (sid,),
            ).fetchone()
        assert bool(row["completed"]) is True

        joined = " ".join(r.getMessage() for r in caplog.records)
        assert "exc_type=LLMError" in joined
        assert "conversation must end" in joined
        assert "a little resting" not in joined
        assert "drinking alcohol" not in joined

    asyncio.run(_run())


def test_safe_exc_msg_strips_raw_payload() -> None:
    exc = LLMError(
        'Response was not valid JSON: Expecting value; raw=\'{"you_said": '
        '"I want to after work go home and a little resting"}\''
    )
    safe = _safe_exc_msg(exc)
    assert "raw=" not in safe
    assert "a little resting" not in safe


# --- S26b -------------------------------------------------------------------


def test_close_truncation_retries_then_fallback_zero_errors(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    """Close-out truncation → one max-2 retry → S26a fallback; zero errors."""
    tid = cleanup_user
    user_id = _onboard(tid)
    history = _realistic_history()
    sid = insert_session(
        user_id,
        "conversation",
        date(2026, 8, 14),
        payload=_conv_payload(turn_count=5, messages=history),
        completed=False,
    )
    calls: list[str] = []

    def _fake_chat(messages, **kwargs):
        assert kwargs.get("reject_truncation") is True
        assert kwargs.get("max_tokens") == 2000
        cue = messages[-1]["content"]
        calls.append(cue)
        raise LLMError("response truncated stop_reason=max_tokens")

    async def _to_thread(fn, *a, **kw):
        return fn(*a, **kw)

    async def _run() -> None:
        message = _make_message(user_id, "end")
        user = get_user(user_id)
        assert user is not None
        with (
            patch("apps.bot.handlers.conversation.chat", side_effect=_fake_chat),
            patch(
                "apps.bot.handlers.conversation.asyncio.to_thread",
                side_effect=_to_thread,
            ),
            caplog.at_level(logging.INFO, logger="core.llm"),
        ):
            await _close_out(
                message,
                user_id,
                sid,
                _conv_payload(turn_count=5, messages=history),
                user=user,
            )
        assert len(calls) == 2
        assert "max 3" in calls[0]
        assert "at most 2" in calls[1]
        assert message.reply_text.await_args.args[0] == texts.TALK_CLOSE_FAILED
        assert _error_count(user_id) == 0
        with connection() as conn:
            row = conn.execute(
                "SELECT completed FROM sessions WHERE id = %s", (sid,)
            ).fetchone()
        assert bool(row["completed"]) is True

    asyncio.run(_run())


def test_close_stop_reason_logged_on_llm_call(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    user = get_user(user_id)
    assert user is not None
    history = _realistic_history()
    messages = build_conversation_close_messages(history, max_messages=20)
    system = build_conversation_close_prompt(user)
    close_json = '{"errors":[],"did_well":"Concrete detail."}'
    with (
        patch("core.llm.anthropic.Anthropic") as mock_cls,
        caplog.at_level(logging.INFO, logger="core.llm"),
    ):
        client = mock_cls.return_value
        client.messages.create.return_value = _mock_llm_response(
            close_json, stop_reason="end_turn", output_tokens=40
        )
        chat(
            messages,
            system=system,
            json_mode=True,
            max_tokens=2000,
            reject_truncation=True,
            settings=_llm_settings(),
        )
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "stop_reason=end_turn" in joined


def test_truncated_turn_never_sent_warm_failure_no_turn_count(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    insert_session(
        user_id,
        "conversation",
        date(2026, 8, 14),
        payload=_conv_payload(turn_count=2),
        completed=False,
    )

    async def _to_thread(fn, *a, **k):
        raise LLMError("response truncated stop_reason=max_tokens")

    async def _run() -> None:
        update, message = _make_update(tid, "we stayed three days")
        context = MagicMock()
        with (
            patch("apps.bot.handlers.conversation.datetime") as mock_dt,
            patch(
                "apps.bot.handlers.conversation.load_settings",
                return_value=_settings_mock(),
            ),
            patch(
                "apps.bot.handlers.conversation.asyncio.to_thread",
                side_effect=_to_thread,
            ),
        ):
            mock_dt.now = MagicMock(return_value=_FROZEN)
            await on_conversation_text(update, context)

        body = message.reply_text.await_args.args[0]
        assert body == texts.TALK_TURN_FAILED
        assert "we stayed" not in body.lower()
        session = get_open_conversation_session(
            user_id,
            now=_FROZEN,
            active_minutes=30,
            awaiting_topic_minutes=2,
        )
        assert session is not None
        assert int(session.payload["turn_count"]) == 2
        assert _error_count(user_id) == 0

    asyncio.run(_run())


def test_end_chat_answers_before_llm_second_tap_noop(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    history = _realistic_history()
    sid = insert_session(
        user_id,
        "conversation",
        date(2026, 8, 14),
        payload=_conv_payload(turn_count=3, messages=history),
        completed=False,
    )
    order: list[str] = []

    async def _answer(*a, **k):
        order.append("answer")

    async def _edit(*a, **k):
        order.append("edit")

    async def _to_thread(fn, *a, **kw):
        order.append("llm")
        return {"errors": [], "did_well": "Clear detail."}

    async def _run() -> None:
        message = _make_message(user_id, "end")
        message.edit_text = AsyncMock(side_effect=_edit)
        query = MagicMock(spec=CallbackQuery)
        query.from_user = User(id=tid, first_name="A", is_bot=False)
        query.data = "talk:end"
        query.answer = AsyncMock(side_effect=_answer)
        query.message = message
        update = MagicMock(spec=Update)
        update.callback_query = query
        update.message = None
        update.effective_user = query.from_user
        context = MagicMock()
        with (
            patch("apps.bot.handlers.conversation.datetime") as mock_dt,
            patch(
                "apps.bot.handlers.conversation.load_settings",
                return_value=_settings_mock(),
            ),
            patch(
                "apps.bot.handlers.conversation.asyncio.to_thread",
                side_effect=_to_thread,
            ),
        ):
            mock_dt.now = MagicMock(return_value=_FROZEN)
            await on_talk_callback(update, context)
            assert order[0] == "answer"
            assert "edit" in order
            assert order.index("answer") < order.index("llm")
            assert message.edit_text.await_count >= 1
            assert message.edit_text.await_args.kwargs.get("reply_markup") is None
            assert texts.TALK_WRAPPING_UP in message.edit_text.await_args.args[0]

            # Re-open for second-tap idempotency while closing=True.
            update_session_payload(
                sid,
                {
                    **_conv_payload(turn_count=3, messages=history),
                    "closing": True,
                },
            )
            with connection() as conn:
                conn.execute(
                    "UPDATE sessions SET completed = FALSE WHERE id = %s",
                    (sid,),
                )
            llm_before = order.count("llm")
            await on_talk_callback(update, context)
            assert order.count("llm") == llm_before

    asyncio.run(_run())


def test_one_live_end_keyboard_after_turn_reply(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    payload = _conv_payload(turn_count=1)
    payload["end_keyboard_message_id"] = 4242
    insert_session(
        user_id,
        "conversation",
        date(2026, 8, 14),
        payload=payload,
        completed=False,
    )

    async def _to_thread(fn, *a, **k):
        return "Beach towns are great for that vibe."

    async def _run() -> None:
        update, message = _make_update(tid, "it was groove techno")
        context = MagicMock()
        bot = message.get_bot()
        with (
            patch("apps.bot.handlers.conversation.datetime") as mock_dt,
            patch(
                "apps.bot.handlers.conversation.load_settings",
                return_value=_settings_mock(),
            ),
            patch(
                "apps.bot.handlers.conversation.asyncio.to_thread",
                side_effect=_to_thread,
            ),
        ):
            mock_dt.now = MagicMock(return_value=_FROZEN)
            await on_conversation_text(update, context)

        bot.edit_message_reply_markup.assert_awaited()
        call_kw = bot.edit_message_reply_markup.await_args.kwargs
        assert call_kw["message_id"] == 4242
        assert call_kw["reply_markup"] is None
        session = get_open_conversation_session(
            user_id,
            now=_FROZEN,
            active_minutes=30,
            awaiting_topic_minutes=2,
        )
        assert session is not None
        assert session.payload.get("end_keyboard_message_id") == 9001
        assert _error_count(user_id) == 0

    asyncio.run(_run())


def test_chunk_topic_label_english_only_ignores_persian_meaning() -> None:
    from datetime import datetime as dt

    from core.services.chunks import Chunk

    chunk = Chunk(
        id=1,
        user_id=1,
        chunk="a notch above",
        full_sentence="That hotel is a notch above the rest.",
        meaning="یک پله بالاتر (/nɒtʃ/)",
        source="vocabulary",
        track="life",
        exported_to_anki=False,
        next_review=None,
        times_right=0,
        times_wrong=0,
        streak_right=0,
        created_at=dt.now(timezone.utc),
        presented_at=dt.now(timezone.utc),
    )
    label = chunk_topic_label(chunk)
    assert "یک" not in label
    assert "پله" not in label
    assert "/nɒtʃ/" not in label
    assert "یک پله بالاتر" not in label
    assert label == "a notch above"


def test_picking_topic_not_claimed_by_conversation_filter(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    insert_session(
        user_id,
        "conversation",
        date(2026, 8, 14),
        payload={
            "phase": "picking_topic",
            "topic": "",
            "messages": [],
            "turn_count": 0,
            "last_activity": utc_now_iso(_FROZEN),
            "offered_topics": ["travel", "cooking", "space"],
            "closing": False,
        },
        completed=False,
    )
    assert open_conversation_awaits_text(user_id, now=_FROZEN) is False
    assert get_picking_conversation_session(user_id) is not None


def test_topic_picker_persists_offered_and_rotates(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    from core.services.interests import replace_interests

    replace_interests(
        user_id,
        [
            ("travel", "life"),
            ("cooking", "life"),
            ("space", "curiosity"),
            ("sport", "curiosity"),
            ("pricing", "work"),
            ("standups", "work"),
        ],
    )

    async def _run() -> None:
        update, message = _make_update(tid, "/talk")
        context = MagicMock()
        context.args = []
        with patch("apps.bot.handlers.conversation.datetime") as mock_dt:
            mock_dt.now = MagicMock(return_value=_FROZEN)
            await on_talk_command(update, context)
        picking = get_picking_conversation_session(user_id)
        assert picking is not None
        first = list(picking.payload.get("offered_topics") or [])
        assert len(first) == 3
        assert open_conversation_awaits_text(user_id, now=_FROZEN) is False

        # Second /talk without tapping — must rotate away from the same set.
        update2, message2 = _make_update(tid, "/talk")
        with patch("apps.bot.handlers.conversation.datetime") as mock_dt:
            mock_dt.now = MagicMock(return_value=_FROZEN)
            await on_talk_command(update2, context)
        picking2 = get_picking_conversation_session(user_id)
        assert picking2 is not None
        second = list(picking2.payload.get("offered_topics") or [])
        assert len(second) == 3
        assert set(x.casefold() for x in second) != set(
            x.casefold() for x in first
        )

    asyncio.run(_run())


def test_topic_pool_defaults_only_when_all_empty(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    assert build_topic_pool(user_id) == list(texts.TALK_DEFAULT_TOPICS)
    from core.services.interests import replace_interests

    replace_interests(
        user_id, [("travel", "life"), ("cooking", "life")]
    )
    pool = build_topic_pool(user_id)
    assert "travel" in pool
    assert pool != list(texts.TALK_DEFAULT_TOPICS)


def test_rotate_topics_prefers_unoffered() -> None:
    pool = ["a", "b", "c", "d", "e", "f"]
    first = rotate_topics(pool, None, limit=3)
    second = rotate_topics(pool, first, limit=3)
    assert len(first) == 3
    assert len(second) == 3
    assert set(second).isdisjoint(set(first))


def test_reject_truncation_raises_on_max_tokens_stop(
    cleanup_user: int,
) -> None:
    with patch("core.llm.anthropic.Anthropic") as mock_cls:
        client = mock_cls.return_value
        client.messages.create.return_value = _mock_llm_response(
            "partial sentence that got cut",
            stop_reason="max_tokens",
            output_tokens=500,
        )
        with pytest.raises(LLMError, match="truncated"):
            chat(
                [{"role": "user", "content": "hi"}],
                system="sys",
                json_mode=False,
                max_tokens=500,
                reject_truncation=True,
                settings=_llm_settings(),
            )


# --- S26c -------------------------------------------------------------------


def test_reaction_occasional_not_every_turn(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _to_thread(fn, *a, **k):
        return "Nice detail — that tracking layer is a notch above gut feel alone."

    async def _one_turn(*, turn_count: int) -> MagicMock:
        with connection() as conn:
            conn.execute(
                "UPDATE sessions SET completed = TRUE "
                "WHERE user_id = %s AND task_type = 'conversation'",
                (user_id,),
            )
        insert_session(
            user_id,
            "conversation",
            date(2026, 8, 14),
            payload=_conv_payload(turn_count=turn_count),
            completed=False,
        )
        update, message = _make_update(tid, f"turn body {turn_count}")
        context = MagicMock()
        with (
            patch("apps.bot.handlers.conversation.datetime") as mock_dt,
            patch(
                "apps.bot.handlers.conversation.load_settings",
                return_value=_settings_mock(),
            ),
            patch(
                "apps.bot.handlers.conversation.asyncio.to_thread",
                side_effect=_to_thread,
            ),
        ):
            mock_dt.now = MagicMock(return_value=_FROZEN)
            await on_conversation_text(update, context)
        return message

    async def _run() -> None:
        m1 = await _one_turn(turn_count=0)  # next=1 → react
        assert m1.get_bot().set_message_reaction.await_count == 1
        m2 = await _one_turn(turn_count=1)  # next=2 → no react
        assert m2.get_bot().set_message_reaction.await_count == 0

    asyncio.run(_run())


def test_reaction_failure_does_not_break_turn(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    insert_session(
        user_id,
        "conversation",
        date(2026, 8, 14),
        payload=_conv_payload(turn_count=0),
        completed=False,
    )

    async def _to_thread(fn, *a, **k):
        return "Fire 🔥"

    async def _run() -> None:
        update, message = _make_update(tid, "we pressed high all game")
        context = MagicMock()
        bot = message.get_bot()
        bot.set_message_reaction = AsyncMock(
            side_effect=RuntimeError("reactions disabled")
        )
        with (
            patch("apps.bot.handlers.conversation.datetime") as mock_dt,
            patch(
                "apps.bot.handlers.conversation.load_settings",
                return_value=_settings_mock(),
            ),
            patch(
                "apps.bot.handlers.conversation.asyncio.to_thread",
                side_effect=_to_thread,
            ),
        ):
            mock_dt.now = MagicMock(return_value=_FROZEN)
            await on_conversation_text(update, context)
        assert message.reply_text.await_count >= 1
        assert "Fire" in message.reply_text.await_args.args[0]
        session = get_open_conversation_session(
            user_id,
            now=_FROZEN,
            active_minutes=30,
            awaiting_topic_minutes=2,
        )
        assert session is not None
        assert int(session.payload["turn_count"]) == 1
        assert _error_count(user_id) == 0

    asyncio.run(_run())
