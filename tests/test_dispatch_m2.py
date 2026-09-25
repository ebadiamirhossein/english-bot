"""Dispatch-order tests: quiz / book / correction (M2 reachability).

These exercise real handler registration order via Application.process_update.
Unit tests that call handlers directly cannot catch silent OpenQuizFilter swallow.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

import pytest
from telegram import (
    CallbackQuery,
    Chat,
    Document,
    Message,
    MessageEntity,
    MessageOriginUser,
    PhotoSize,
    Update,
    User,
    Voice,
)

from core.config import Settings
from core.db import close_pool, connection
from core.services.sessions import (
    has_diary_session_on,
    has_reading_session_on,
    has_session_on,
    insert_session,
    utc_now_iso,
)
from core.services.identity import save_onboarding
from datetime import timedelta
FAKE_TELEGRAM_ID_BASE = 9_470_000_000
SAMPLE_TEXT = "her english is not so much good"
CAPTURE_SAMPLE = "Could you circle back on this by Friday please?"
COUPLE_CHAT_ID = -100555666777


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
            "name": "Dispatch Test",
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


def _quiz_payload(fmt: str, *, index: int = 0) -> dict[str, Any]:
    questions = [
        {
            "error_id": 1,
            "format": fmt,
            "prompt": "I ___ yesterday" if fmt == "gap" else "Pick one",
            "accept": ["went"],
            "options": ["a", "b", "c", "d"],
            "tiles": ["a", "b", "c"],
            "answer": "a",
        }
    ]
    return {
        "index": index,
        "chat_id": 1,
        "message_id": 1,
        "answered": 0,
        "questions": questions,
    }


def _voice_settings() -> Settings:
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


def _text_update(
    user_id: int,
    text: str,
    *,
    update_id: int = 1,
    message_id: int = 10,
) -> Update:
    user = User(id=user_id, first_name="A", is_bot=False)
    chat = Chat(id=user_id, type="private")
    msg = Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=user,
        text=text,
    )
    return Update(update_id=update_id, message=msg)


def _group_text_update(
    user_id: int,
    text: str,
    *,
    chat_id: int = COUPLE_CHAT_ID,
    update_id: int = 1,
    message_id: int = 20,
) -> Update:
    user = User(id=user_id, first_name="A", is_bot=False)
    chat = Chat(id=chat_id, type="supergroup", title="Couple")
    msg = Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=user,
        text=text,
    )
    return Update(update_id=update_id, message=msg)


def _couple_settings() -> Settings:
    return Settings(
        database_url="postgresql://x:y@localhost:5433/english_bot",
        telegram_bot_token="token",
        llm_api_key="test-key",
        couple_chat_id=COUPLE_CHAT_ID,
    )


def _voice_update(
    user_id: int,
    *,
    duration: int = 20,
    update_id: int = 50,
    message_id: int = 50,
) -> Update:
    user = User(id=user_id, first_name="A", is_bot=False)
    chat = Chat(id=user_id, type="private")
    voice = Voice(
        file_id="voice-dispatch-1",
        file_unique_id="voice-unique-1",
        duration=duration,
    )
    msg = Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=user,
        voice=voice,
    )
    return Update(update_id=update_id, message=msg)


def _forwarded_text_update(
    user_id: int,
    text: str,
    *,
    update_id: int = 1,
    message_id: int = 11,
) -> Update:
    user = User(id=user_id, first_name="A", is_bot=False)
    origin_user = User(id=user_id + 1, first_name="Client", is_bot=False)
    chat = Chat(id=user_id, type="private")
    origin = MessageOriginUser(
        date=datetime.now(timezone.utc),
        sender_user=origin_user,
    )
    msg = Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=user,
        text=text,
        forward_origin=origin,
    )
    return Update(update_id=update_id, message=msg)


def _command_update(
    user_id: int,
    text: str,
    *,
    update_id: int = 1,
    message_id: int = 12,
) -> Update:
    """Build a private command update with a bot_command entity."""
    user = User(id=user_id, first_name="A", is_bot=False)
    chat = Chat(id=user_id, type="private")
    cmd = text.split()[0]
    cmd_len = len(cmd)
    msg = Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=user,
        text=text,
        entities=(
            MessageEntity(
                type=MessageEntity.BOT_COMMAND,
                offset=0,
                length=cmd_len,
            ),
        ),
    )
    return Update(update_id=update_id, message=msg)


def _callback_update(
    user_id: int,
    data: str,
    *,
    update_id: int = 2,
    message_id: int = 99,
) -> Update:
    user = User(id=user_id, first_name="A", is_bot=False)
    chat = Chat(id=user_id, type="private")
    msg = Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=user,
        text="summary",
    )
    cq = CallbackQuery(
        id="cq1",
        from_user=user,
        chat_instance="x",
        data=data,
        message=msg,
    )
    return Update(update_id=update_id, callback_query=cq)


def _photo_update(
    user_id: int,
    *,
    update_id: int = 3,
    message_id: int = 50,
    file_id: str = "photo1",
) -> Update:
    user = User(id=user_id, first_name="A", is_bot=False)
    chat = Chat(id=user_id, type="private")
    photo = PhotoSize(
        file_id=file_id, file_unique_id=f"u-{file_id}", width=10, height=10
    )
    msg = Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=user,
        photo=(photo,),
    )
    return Update(update_id=update_id, message=msg)


def _document_update(
    user_id: int,
    *,
    file_name: str,
    mime_type: str = "text/csv",
    update_id: int = 40,
    message_id: int = 80,
    file_id: str = "doc-1",
) -> Update:
    user = User(id=user_id, first_name="A", is_bot=False)
    chat = Chat(id=user_id, type="private")
    doc = Document(
        file_id=file_id,
        file_unique_id=f"u-{file_id}",
        file_name=file_name,
        mime_type=mime_type,
        file_size=100,
    )
    msg = Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=user,
        document=doc,
    )
    return Update(update_id=update_id, message=msg)


# --- Unit helpers ------------------------------------------------------------


# --- Application dispatch ----------------------------------------------------


# --- Voice / diary / shadow routing (S13 / S16) --------------------------------


# --- S15b CSV document vs /book collision ------------------------------------


# --- Couple challenge dispatch (S8) -------------------------------------------


# --- S26 conversation dispatch -----------------------------------------------


def _conversation_payload(
    *,
    phase: str = "active",
    topic: str = "weekend plans",
    last_activity: datetime | None = None,
    turn_count: int = 0,
) -> dict[str, Any]:
    when = last_activity or datetime.now(timezone.utc)
    return {
        "phase": phase,
        "topic": topic,
        "messages": [],
        "turn_count": turn_count,
        "last_activity": utc_now_iso(when),
        "warned_last_turn": False,
    }


def test_dispatch_stale_via_get_open_returns_none(cleanup_user: int) -> None:
    """Staleness evaluated in get_open_conversation_session with injected now."""
    from core.services.sessions import get_open_conversation_session

    tid = cleanup_user
    user_id = _onboard(tid)
    stale = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
    insert_session(
        user_id,
        "conversation",
        date(2026, 8, 14),
        payload=_conversation_payload(last_activity=stale),
        completed=False,
    )
    now = stale + timedelta(minutes=45)
    assert (
        get_open_conversation_session(
            user_id, now=now, active_minutes=30, awaiting_topic_minutes=2
        )
        is None
    )
    assert (
        get_open_conversation_session(
            user_id, now=stale + timedelta(minutes=5), active_minutes=30, awaiting_topic_minutes=2
        )
        is not None
    )


def test_open_conversation_does_not_change_eligibility(
    cleanup_user: int,
) -> None:
    """S7a lesson: open conversation must not affect quiz/reading/diary gates."""
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 14)
    before_quiz = has_session_on(user_id, day)
    before_reading = has_reading_session_on(user_id, day)
    before_diary = has_diary_session_on(user_id, day)
    insert_session(
        user_id,
        "conversation",
        day,
        payload=_conversation_payload(),
        completed=False,
    )
    assert has_session_on(user_id, day) is before_quiz
    assert has_reading_session_on(user_id, day) is before_reading
    assert has_diary_session_on(user_id, day) is before_diary
    assert before_quiz is False
    assert before_reading is False
    assert before_diary is False
