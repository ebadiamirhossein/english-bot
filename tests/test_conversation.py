"""S26/S26a text conversation (/talk) — behaviour, close-out, prompts, labels."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Message, Update

from core.config import Settings
from core.db import close_pool, connection, migrate
from core.llm import LLMError, chat
from core.services.sessions import insert_session, utc_now_iso
from core.services.identity import save_onboarding
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
    # #448: keyed on `telegram_user_id`. This read `WHERE id = %s` with the
    # Telegram id -- `id` has been the internal key since W4b (migration 011),
    # so the DELETE matched nothing, succeeded, and left every `Talk Test`
    # user behind: 7,802 of the dev database's 8,125 users on 2026-09-25.
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM users WHERE telegram_user_id = %s",
                (fake_telegram_id,),
            )


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


# --- S26b -------------------------------------------------------------------


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


