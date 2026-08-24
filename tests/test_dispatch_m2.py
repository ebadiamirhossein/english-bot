"""Dispatch-order tests: quiz / book / correction (M2 reachability).

These exercise real handler registration order via Application.process_update.
Unit tests that call handlers directly cannot catch silent OpenQuizFilter swallow.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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
from telegram.ext import ApplicationBuilder, ConversationHandler

from core.config import Settings
from core.db import close_pool, connection
from apps.bot.handlers.book import (
    ASK_BOOK,
    ASK_BOOK_OTHER,
    COLLECT_PAGES,
    CONVERSATION_TIMEOUT_SECONDS,
    after_batch_choice,
    build_book_handler,
    collect_page,
    on_conversation_timeout,
    start,
)
from apps.bot.handlers.book_test import build_book_test_handlers
from apps.bot.handlers.capture import build_capture_handlers
from apps.bot.handlers.correction import build_correction_handler
from apps.bot.handlers.conversation import build_conversation_handlers
from apps.bot.handlers.couple import build_couple_handlers
from apps.bot.handlers.csv_import import build_csv_import_handlers
from apps.bot.handlers.nudge import build_nudge_handler
from apps.bot.handlers.quiz import (
    build_present_handlers,
    build_quiz_handlers,
    open_quiz_awaits_gap_answer,
)
from apps.bot.handlers.reading import build_reading_handler
from apps.bot.handlers.settings import (
    MENU,
    build_settings_editor_handler,
    build_settings_handlers,
    build_settings_orphan_handler,
)
from apps.bot.handlers.voice import build_voice_handler
from apps.bot.alerts import on_error
from core.services.sessions import (
    has_diary_session_on,
    has_reading_session_on,
    has_session_on,
    insert_session,
    local_today,
    save_voice_exchange,
    utc_now_iso,
)
from core.services.identity import save_onboarding
from apps.bot.services.couple import insert_challenge_if_absent, couple_local_today
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


async def _build_app(
    *,
    quiz_spy: AsyncMock,
    correction_spy: AsyncMock,
    capture_spy: AsyncMock | None = None,
    couple_spy: AsyncMock | None = None,
    csv_spy: AsyncMock | None = None,
    non_csv_spy: AsyncMock | None = None,
    conversation_spy: AsyncMock | None = None,
):
    """Application mirroring main.py group 0: quiz → conversation → … → correction."""
    if capture_spy is None:
        capture_spy = AsyncMock()
    if couple_spy is None:
        couple_spy = AsyncMock()
    if csv_spy is None:
        csv_spy = AsyncMock()
    if non_csv_spy is None:
        non_csv_spy = AsyncMock()
    if conversation_spy is None:
        conversation_spy = AsyncMock()
    with (
        patch("apps.bot.handlers.quiz.on_quiz_text", quiz_spy),
        patch("apps.bot.handlers.correction.correct_text", correction_spy),
        patch("apps.bot.handlers.conversation.on_conversation_text", conversation_spy),
        patch("apps.bot.handlers.capture.on_forwarded_capture", capture_spy),
        patch("apps.bot.handlers.capture.on_capture_command", capture_spy),
        patch("apps.bot.handlers.couple.on_couple_answer", couple_spy),
        patch("apps.bot.handlers.csv_import.on_csv_document", csv_spy),
        patch("apps.bot.handlers.csv_import.on_non_csv_document", non_csv_spy),
    ):
        quiz_text, quiz_choice = build_quiz_handlers()
        present_ack, present_orphan = build_present_handlers()
        capture_fwd, capture_cmd = build_capture_handlers()
        talk_cmd, talk_text, talk_cb, talk_orphan = build_conversation_handlers()
        reading = build_reading_handler()
        nudge = build_nudge_handler()
        test_cmd, test_cb = build_book_test_handlers()
        voice = build_voice_handler()
        book = build_book_handler()
        couple_here, couple_answers = build_couple_handlers()
        correction = build_correction_handler()
        csv_doc, non_csv_doc, share_cb, share_orphan = build_csv_import_handlers()

    pause_cmd, stats_cmd, pause_cb = build_settings_handlers()
    settings_editor = build_settings_editor_handler()
    settings_orphan = build_settings_orphan_handler()
    app = ApplicationBuilder().token("1:FAKE-DISPATCH-TEST").build()
    app.add_error_handler(on_error)
    app.add_handler(pause_cmd)
    app.add_handler(stats_cmd)
    app.add_handler(pause_cb)
    app.add_handler(settings_editor)  # tapped-only; no text filter
    app.add_handler(settings_orphan)
    app.add_handler(csv_doc)
    app.add_handler(non_csv_doc)
    app.add_handler(share_cb)
    app.add_handler(share_orphan)
    app.add_handler(quiz_choice)
    app.add_handler(present_ack)
    app.add_handler(present_orphan)
    app.add_handler(capture_fwd)
    app.add_handler(capture_cmd)
    app.add_handler(quiz_text)
    app.add_handler(talk_cmd)
    app.add_handler(talk_cb)
    app.add_handler(talk_orphan)
    app.add_handler(talk_text)  # after quiz gap; before correction — S26
    app.add_handler(reading)  # callbacks only — must not swallow free text
    app.add_handler(nudge)  # nudge: taps only — must not swallow free text
    app.add_handler(test_cb)
    app.add_handler(test_cmd)
    app.add_handler(voice)
    app.add_handler(book)
    app.add_handler(couple_here)
    app.add_handler(couple_answers)
    app.add_handler(correction)

    # Avoid Telegram network: mark initialized without Bot.initialize/get_me.
    me = User(id=1, first_name="Bot", is_bot=True, username="testbot")
    object.__setattr__(app.bot, "_bot_user", me)
    app._initialized = True
    return app, book, settings_editor


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


def test_open_quiz_awaits_gap_only(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 8)
    insert_session(user_id, "quiz", day, payload=_quiz_payload("choice"), completed=False)
    assert open_quiz_awaits_gap_answer(user_id) is False
    assert open_quiz_awaits_gap_answer(user_id + 999) is False

    with connection() as conn:
        with conn.transaction():
            conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
    insert_session(user_id, "quiz", day, payload=_quiz_payload("gap"), completed=False)
    assert open_quiz_awaits_gap_answer(user_id) is True


def test_dispatch_presentation_open_reaches_correction(
    cleanup_user: int,
) -> None:
    """S25: free text while a presentation card is open must reach M2."""
    tid = cleanup_user
    user_id = _onboard(tid)
    payload = _quiz_payload("gap")
    payload["presentations"] = [
        {
            "chunk_id": 1,
            "chunk": "delulu",
            "full_sentence": "She is being delulu.",
            "meaning": "delusional",
        }
    ]
    payload["present_index"] = 0
    insert_session(
        user_id, "quiz", date(2026, 8, 8), payload=payload, completed=False
    )
    assert open_quiz_awaits_gap_answer(user_id) is False

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            update = _text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            quiz_spy.assert_not_awaited()
            correction_spy.assert_awaited_once()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_book_handler_has_conversation_timeout() -> None:
    ch = build_book_handler()
    assert ch.conversation_timeout == CONVERSATION_TIMEOUT_SECONDS
    assert ConversationHandler.TIMEOUT in ch.states


def test_book_timeout_clears_session() -> None:
    async def _run() -> None:
        context = MagicMock()
        context.job_queue = None
        context.user_data = {
            "book": {
                "book": "murphy",
                "collecting": False,
                "pages": [],
            }
        }
        update = MagicMock()
        update.effective_user = MagicMock(id=42)
        result = await on_conversation_timeout(update, context)
        assert result == ConversationHandler.END
        assert "book" not in context.user_data

    asyncio.run(_run())


# --- Application dispatch ----------------------------------------------------


def test_dispatch_gap_quiz_grades_not_correction(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    insert_session(
        user_id, "quiz", date(2026, 8, 8), payload=_quiz_payload("gap"), completed=False
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            update = _text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            quiz_spy.assert_awaited_once()
            correction_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_open_weekly_test_midset_reaches_correction(
    cleanup_user: int,
) -> None:
    """Open 15Q weekly test on a non-gap question must not swallow free text."""
    tid = cleanup_user
    user_id = _onboard(tid)
    questions = []
    for i in range(15):
        fmt = "choice" if i == 3 else "gap"
        questions.append(
            {
                "error_id": i + 1,
                "format": fmt,
                "prompt": "Pick one" if fmt == "choice" else "I ___ yesterday",
                "accept": ["went"],
                "options": ["a", "b", "c", "d"],
                "answer": "a",
            }
        )
    payload = {
        "index": 3,  # mid-set on choice
        "chat_id": tid,
        "message_id": 1,
        "answered": 3,
        "correct_count": 2,
        "weekly_test": True,
        "questions": questions,
    }
    insert_session(
        user_id, "quiz", date(2026, 8, 9), payload=payload, completed=False
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            update = _text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            quiz_spy.assert_not_awaited()
            correction_spy.assert_awaited_once()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_nudged_open_quiz_reaches_correction(cleanup_user: int) -> None:
    """Outstanding nudge (nudges_sent > 0) must not steal free text from M2."""
    tid = cleanup_user
    user_id = _onboard(tid)
    sid = insert_session(
        user_id,
        "quiz",
        date(2026, 8, 8),
        payload=_quiz_payload("choice"),
        completed=False,
    )
    with connection() as conn:
        conn.execute(
            "UPDATE sessions SET nudges_sent = 1 WHERE id = %s",
            (sid,),
        )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            update = _text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            correction_spy.assert_awaited_once()
            quiz_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


@pytest.mark.parametrize("fmt", ["choice", "order", "spot"])
def test_dispatch_nongap_quiz_reaches_correction(
    cleanup_user: int, fmt: str
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    insert_session(
        user_id, "quiz", date(2026, 8, 8), payload=_quiz_payload(fmt), completed=False
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            update = _text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            quiz_spy.assert_not_awaited()
            correction_spy.assert_awaited_once()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_idle_reaches_correction(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        capture_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            capture_spy=capture_spy,
        )
        try:
            update = _text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            quiz_spy.assert_not_awaited()
            capture_spy.assert_not_awaited()
            correction_spy.assert_awaited_once()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_forwarded_reaches_capture_not_correction(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        capture_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            capture_spy=capture_spy,
        )
        try:
            update = _forwarded_text_update(tid, CAPTURE_SAMPLE)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            capture_spy.assert_awaited_once()
            correction_spy.assert_not_awaited()
            quiz_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_capture_command_reaches_capture_not_correction(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        capture_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            capture_spy=capture_spy,
        )
        try:
            update = _command_update(tid, f"/capture {CAPTURE_SAMPLE}")
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            capture_spy.assert_awaited_once()
            correction_spy.assert_not_awaited()
            quiz_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_forwarded_during_gap_quiz_reaches_capture(
    cleanup_user: int,
) -> None:
    """A forward must not be graded as a typed gap answer."""
    tid = cleanup_user
    user_id = _onboard(tid)
    insert_session(
        user_id, "quiz", date(2026, 8, 8), payload=_quiz_payload("gap"), completed=False
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        capture_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            capture_spy=capture_spy,
        )
        try:
            update = _forwarded_text_update(tid, CAPTURE_SAMPLE)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            capture_spy.assert_awaited_once()
            quiz_spy.assert_not_awaited()
            correction_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_open_book_test_reaches_correction(cleanup_user: int) -> None:
    """Open mid-set /test must not swallow free text (tap-only; no text filter)."""
    tid = cleanup_user
    user_id = _onboard(tid)
    insert_session(
        user_id,
        "book_test",
        date(2026, 8, 8),
        payload={
            "index": 0,
            "callback_prefix": "btest",
            "chat_id": tid,
            "message_id": 77,
            "questions": [
                {
                    "source": "book",
                    "format": "choice",
                    "prompt": "Pick one",
                    "options": ["a", "b", "c", "d"],
                    "answer": "a",
                    "accept": ["a"],
                }
            ],
        },
        completed=False,
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            update = _text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            quiz_spy.assert_not_awaited()
            correction_spy.assert_awaited_once()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_book_other_owns_text(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, book, _settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            key = (tid, tid)  # per_chat + per_user private chat
            book._conversations[key] = ASK_BOOK_OTHER
            app.user_data[tid]["book"] = {
                "collecting": False,
                "processing": False,
                "pages": [],
            }
            update = _text_update(tid, "My Custom Grammar Book")
            update._bot = app.bot
            update.message._bot = app.bot
            with patch(
                "apps.bot.handlers.book.is_registered", return_value=True
            ), patch.object(
                Message, "reply_text", new=AsyncMock()
            ):
                await app.process_update(update)
            correction_spy.assert_not_awaited()
            # Book advanced into page collection.
            assert book._conversations.get(key) == COLLECT_PAGES
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_after_summary_reaches_correction_without_done(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, book, _settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            key = (tid, tid)  # per_chat + per_user private chat
            book._conversations[key] = COLLECT_PAGES
            app.user_data[tid]["book"] = {
                "book": "murphy",
                "collecting": False,
                "processing": False,
                "pages": [],
                "over_cap": False,
            }
            update = _text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            correction_spy.assert_awaited_once()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_after_done_reaches_correction(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, book, _settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            key = (tid, tid)  # per_chat + per_user private chat
            book._conversations[key] = COLLECT_PAGES
            app.user_data[tid]["book"] = {
                "book": "murphy",
                "collecting": False,
                "processing": False,
                "pages": [],
            }
            done = _callback_update(tid, "book:after:done")
            done._bot = app.bot
            done.callback_query._bot = app.bot
            done.callback_query.message._bot = app.bot
            with (
                patch.object(CallbackQuery, "answer", new=AsyncMock()),
                patch.object(
                    CallbackQuery, "edit_message_reply_markup", new=AsyncMock()
                ),
            ):
                await app.process_update(done)
            assert key not in book._conversations
            assert "book" not in app.user_data[tid]

            correction_spy.reset_mock()
            text_u = _text_update(tid, SAMPLE_TEXT, update_id=5)
            text_u._bot = app.bot
            text_u.message._bot = app.bot
            await app.process_update(text_u)
            correction_spy.assert_awaited_once()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_add_more_collects_photo(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, book, _settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            key = (tid, tid)  # per_chat + per_user private chat
            book._conversations[key] = COLLECT_PAGES
            app.user_data[tid]["book"] = {
                "book": "murphy",
                "collecting": False,
                "processing": False,
                "pages": [{"batch_index": 1, "file_id": "old"}],
                "over_cap": True,
            }
            more = _callback_update(tid, "book:after:more", update_id=2)
            more._bot = app.bot
            more.callback_query._bot = app.bot
            more.callback_query.message._bot = app.bot
            with (
                patch.object(CallbackQuery, "answer", new=AsyncMock()),
                patch.object(
                    CallbackQuery, "edit_message_reply_markup", new=AsyncMock()
                ),
                patch.object(Message, "reply_text", new=AsyncMock()),
            ):
                await app.process_update(more)

            sess = app.user_data[tid]["book"]
            assert sess["collecting"] is True
            assert sess["pages"] == []
            assert book._conversations.get(key) == COLLECT_PAGES

            photo = _photo_update(tid, update_id=3)
            photo._bot = app.bot
            photo.message._bot = app.bot
            # JobQueue required for debounce; Application may have one after init.
            if app.job_queue is None:
                # Fallback: call collect_page with a context that has FakeJobQueue.
                from tests.test_book import FakeJobQueue

                ctx = MagicMock()
                ctx.user_data = app.user_data[tid]
                ctx.job_queue = FakeJobQueue()
                await collect_page(photo, ctx)
                assert len(ctx.user_data["book"]["pages"]) == 1
            else:
                await app.process_update(photo)
                assert len(app.user_data[tid]["book"]["pages"]) == 1
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_second_book_after_done_starts_clean(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        context = MagicMock()
        context.job_queue = None
        context.user_data = {
            "book": {
                "book": "murphy",
                "collecting": False,
                "pages": [{"batch_index": 1}],
            }
        }
        update = MagicMock()
        update.effective_user = MagicMock(id=tid)
        query = MagicMock()
        query.data = "book:after:done"
        query.answer = AsyncMock()
        query.edit_message_reply_markup = AsyncMock()
        query.message = MagicMock()
        update.callback_query = query
        result = await after_batch_choice(update, context)
        assert result == ConversationHandler.END
        assert "book" not in context.user_data

        start_update = MagicMock()
        start_update.effective_user = MagicMock(id=tid)
        start_update.message = MagicMock()
        start_update.message.reply_text = AsyncMock()
        with patch("apps.bot.handlers.book.is_registered", return_value=True):
            state = await start(start_update, context)
        assert state == ASK_BOOK
        assert context.user_data["book"]["pages"] == []
        assert context.user_data["book"].get("book") is None
        assert context.user_data["book"]["collecting"] is False

    asyncio.run(_run())


def test_dispatch_open_reading_mid_qa_reaches_correction(cleanup_user: int) -> None:
    """S9c: open reading mid-question-set must not swallow free text (M2)."""
    tid = cleanup_user
    user_id = _onboard(tid)
    insert_session(
        user_id,
        "reading",
        date(2026, 8, 8),
        payload={
            "reading_id": 99,
            "chat_id": tid,
            "message_id": 500,
            "phase": "questions",
            "q_index": 2,
            "answers": [0, 1],
            "assessed": True,
            "questions": [
                {
                    "q": f"Q{i}?",
                    "options": ["a", "b", "c", "d"],
                    "answer_index": 0,
                    "why": "Because.",
                }
                for i in range(5)
            ],
        },
        completed=False,
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            update = _text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            quiz_spy.assert_not_awaited()
            correction_spy.assert_awaited_once()
        finally:
            app._initialized = False

    asyncio.run(_run())


# --- Voice / diary / shadow routing (S13 / S16) --------------------------------


def test_dispatch_claimable_shadow_reaches_shadow_not_diary_or_m3(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    now = datetime.now(timezone.utc)
    day = local_today("Europe/Vilnius", now)
    insert_session(
        user_id,
        "shadow",
        day,
        payload={
            "chunk_id": 1,
            "target_sentence": "Hello there",
            "clip_sent_at": now.isoformat(),
            "attempts": 0,
        },
        completed=False,
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        shadow_spy = AsyncMock()
        diary_spy = AsyncMock()
        m3_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            update = _voice_update(tid)
            update._bot = app.bot
            update.message._bot = app.bot
            with (
                patch(
                    "apps.bot.handlers.voice.load_settings",
                    return_value=_voice_settings(),
                ),
                patch("apps.bot.handlers.shadow.handle_shadow_voice", shadow_spy),
                patch("apps.bot.handlers.diary.handle_diary_voice", diary_spy),
                patch("apps.bot.handlers.voice._handle_voice_locked", m3_spy),
            ):
                await app.process_update(update)
            shadow_spy.assert_awaited_once()
            diary_spy.assert_not_awaited()
            m3_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_open_diary_reaches_diary_not_m3(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = local_today("Europe/Vilnius", datetime.now(timezone.utc))
    insert_session(
        user_id, "diary", day, payload={"source": "poll"}, completed=False
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        shadow_spy = AsyncMock()
        diary_spy = AsyncMock()
        m3_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            update = _voice_update(tid)
            update._bot = app.bot
            update.message._bot = app.bot
            with (
                patch(
                    "apps.bot.handlers.voice.load_settings",
                    return_value=_voice_settings(),
                ),
                patch("apps.bot.handlers.shadow.handle_shadow_voice", shadow_spy),
                patch("apps.bot.handlers.diary.handle_diary_voice", diary_spy),
                patch("apps.bot.handlers.voice._handle_voice_locked", m3_spy),
            ):
                await app.process_update(update)
            diary_spy.assert_awaited_once()
            shadow_spy.assert_not_awaited()
            m3_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_no_diary_reaches_m3_not_diary(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        shadow_spy = AsyncMock()
        diary_spy = AsyncMock()
        m3_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            update = _voice_update(tid)
            update._bot = app.bot
            update.message._bot = app.bot
            with (
                patch(
                    "apps.bot.handlers.voice.load_settings",
                    return_value=_voice_settings(),
                ),
                patch("apps.bot.handlers.shadow.handle_shadow_voice", shadow_spy),
                patch("apps.bot.handlers.diary.handle_diary_voice", diary_spy),
                patch("apps.bot.handlers.voice._handle_voice_locked", m3_spy),
            ):
                await app.process_update(update)
            m3_spy.assert_awaited_once()
            shadow_spy.assert_not_awaited()
            diary_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_live_m3_beats_open_diary(cleanup_user: int) -> None:
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
    insert_session(
        user_id, "diary", day, payload={"source": "poll"}, completed=False
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        shadow_spy = AsyncMock()
        diary_spy = AsyncMock()
        m3_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            update = _voice_update(tid)
            update._bot = app.bot
            update.message._bot = app.bot
            with (
                patch(
                    "apps.bot.handlers.voice.load_settings",
                    return_value=_voice_settings(),
                ),
                patch("apps.bot.handlers.shadow.handle_shadow_voice", shadow_spy),
                patch("apps.bot.handlers.diary.handle_diary_voice", diary_spy),
                patch("apps.bot.handlers.voice._handle_voice_locked", m3_spy),
            ):
                await app.process_update(update)
            m3_spy.assert_awaited_once()
            shadow_spy.assert_not_awaited()
            diary_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


# --- S15b CSV document vs /book collision ------------------------------------


def test_dispatch_csv_during_book_reaches_csv_not_book(
    cleanup_user: int,
) -> None:
    """Open /book COLLECT_PAGES only matches IMAGE — CSV must not be swallowed."""
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        csv_spy = AsyncMock()
        app, book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            csv_spy=csv_spy,
        )
        try:
            key = (tid, tid)  # per_chat + per_user private chat
            book._conversations[key] = COLLECT_PAGES
            app.user_data[tid]["book"] = {
                "book": "murphy",
                "collecting": True,
                "processing": False,
                "pages": [],
                "over_cap": False,
            }
            update = _document_update(tid, file_name="export.csv")
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            csv_spy.assert_awaited_once()
            assert book._conversations.get(key) == COLLECT_PAGES
            assert app.user_data[tid]["book"]["pages"] == []
            correction_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_image_document_during_book_reaches_book(
    cleanup_user: int,
) -> None:
    """Image documents mid-/book must still hit collect_page, not non-CSV reply."""
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        csv_spy = AsyncMock()
        non_csv_spy = AsyncMock()
        app, book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            csv_spy=csv_spy,
            non_csv_spy=non_csv_spy,
        )
        try:
            key = (tid, tid)  # per_chat + per_user private chat
            book._conversations[key] = COLLECT_PAGES
            app.user_data[tid]["book"] = {
                "book": "murphy",
                "collecting": True,
                "processing": False,
                "pages": [],
                "over_cap": False,
            }
            update = _document_update(
                tid,
                file_name="page.jpg",
                mime_type="image/jpeg",
                file_id="img-doc-1",
            )
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            assert len(app.user_data[tid]["book"]["pages"]) == 1
            csv_spy.assert_not_awaited()
            non_csv_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_plain_text_still_reaches_correction_with_csv_handlers(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        csv_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            csv_spy=csv_spy,
        )
        try:
            update = _text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            correction_spy.assert_awaited_once()
            csv_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_share_pending_plain_text_reaches_correction(
    cleanup_user: int,
) -> None:
    """S24: Share pending in user_data must not swallow free English (no MessageHandler)."""
    from telegram.ext import CallbackQueryHandler, MessageHandler

    csv_h, non_csv_h, share_h, orphan_h = build_csv_import_handlers()
    assert isinstance(csv_h, MessageHandler)
    assert isinstance(non_csv_h, MessageHandler)
    assert isinstance(share_h, CallbackQueryHandler)
    assert isinstance(orphan_h, CallbackQueryHandler)

    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        csv_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            csv_spy=csv_spy,
        )
        try:
            # Simulate: slang CSV arrived, Share confirmation pending.
            app.user_data[tid]["share_slang_pending"] = {
                "items": [
                    {
                        "chunk": "mid",
                        "full_sentence": "The movie was mid.",
                        "meaning": "average",
                    }
                ],
                "rejected": 0,
                "filename": "slang.csv",
            }
            update = _text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            correction_spy.assert_awaited_once()
            csv_spy.assert_not_awaited()
            quiz_spy.assert_not_awaited()
            # Pending must still be there — free text did not consume it.
            assert "share_slang_pending" in app.user_data[tid]
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_settings_mid_flow_plain_text_reaches_correction(
    cleanup_user: int,
) -> None:
    """Open /settings mid-flow must not swallow plain text (no MessageHandler)."""
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, _book, settings = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            key = (tid, tid)  # per_chat + per_user private chat
            settings._conversations[key] = MENU
            app.user_data[tid]["settings"] = {
                "wizard_chat_id": tid,
                "wizard_message_id": 99,
                "wizard_state": MENU,
            }
            update = _text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            correction_spy.assert_awaited_once()
            quiz_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


# --- Couple challenge dispatch (S8) -------------------------------------------


def test_dispatch_private_text_still_reaches_correction_with_couple_registered(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        couple_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            couple_spy=couple_spy,
        )
        try:
            update = _text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            correction_spy.assert_awaited_once()
            couple_spy.assert_not_awaited()
            quiz_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_group_open_challenge_reaches_couple(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = couple_local_today(datetime.now(timezone.utc))
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM couple_challenges WHERE date = %s", (day,)
            )
    insert_challenge_if_absent(day, "Fill ___", "very")

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        couple_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            couple_spy=couple_spy,
        )
        try:
            update = _group_text_update(tid, "very")
            update._bot = app.bot
            update.message._bot = app.bot
            with patch(
                "apps.bot.handlers.couple.load_settings",
                return_value=_couple_settings(),
            ):
                await app.process_update(update)
            couple_spy.assert_awaited_once()
            correction_spy.assert_not_awaited()
            quiz_spy.assert_not_awaited()
        finally:
            app._initialized = False
            with connection() as conn:
                with conn.transaction():
                    conn.execute(
                        "DELETE FROM couple_challenges WHERE date = %s",
                        (day,),
                    )

    asyncio.run(_run())


def test_dispatch_group_no_open_challenge_reaches_nothing(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = couple_local_today(datetime.now(timezone.utc))
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM couple_challenges WHERE date = %s", (day,)
            )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        couple_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            couple_spy=couple_spy,
        )
        try:
            update = _group_text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            with patch(
                "apps.bot.handlers.couple.load_settings",
                return_value=_couple_settings(),
            ):
                await app.process_update(update)
            couple_spy.assert_not_awaited()
            correction_spy.assert_not_awaited()
            quiz_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_group_unregistered_reaches_nothing(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    stranger = user_id + 777_777
    day = couple_local_today(datetime.now(timezone.utc))
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM couple_challenges WHERE date = %s", (day,)
            )
    insert_challenge_if_absent(day, "Fill ___", "very")

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        couple_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            couple_spy=couple_spy,
        )
        try:
            update = _group_text_update(stranger, "very")
            update._bot = app.bot
            update.message._bot = app.bot
            with patch(
                "apps.bot.handlers.couple.load_settings",
                return_value=_couple_settings(),
            ):
                await app.process_update(update)
            couple_spy.assert_not_awaited()
            correction_spy.assert_not_awaited()
        finally:
            app._initialized = False
            with connection() as conn:
                with conn.transaction():
                    conn.execute(
                        "DELETE FROM couple_challenges WHERE date = %s",
                        (day,),
                    )

    asyncio.run(_run())


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


def test_dispatch_handlers_conversation_and_correction_same_group() -> None:
    """PTB first-match-wins only applies within the same handler group."""
    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        conversation_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            conversation_spy=conversation_spy,
        )
        try:
            group0 = app.handlers.get(0, [])
            from telegram.ext import MessageHandler as MH

            text_handlers = [
                h
                for h in group0
                if isinstance(h, MH) and h.callback is not None
            ]
            # Spied callbacks live on the handlers built under the patch.
            callbacks = {h.callback for h in text_handlers}
            assert conversation_spy in callbacks
            assert correction_spy in callbacks
            assert all(h in group0 for h in text_handlers)
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_open_conversation_captures_correction_spy_zero(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    insert_session(
        user_id,
        "conversation",
        date(2026, 8, 14),
        payload=_conversation_payload(),
        completed=False,
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        conversation_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            conversation_spy=conversation_spy,
        )
        try:
            update = _text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            conversation_spy.assert_awaited_once()
            correction_spy.assert_not_awaited()
            quiz_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_no_conversation_correction_conversation_spy_zero(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        conversation_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            conversation_spy=conversation_spy,
        )
        try:
            update = _text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            correction_spy.assert_awaited_once()
            conversation_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_stale_conversation_falls_through_to_correction(
    cleanup_user: int,
) -> None:
    """Filter-time staleness — no scheduler. Injected last_activity + frozen now."""
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
    frozen = stale + timedelta(minutes=45)

    def _awaits(uid: int, now: datetime | None = None) -> bool:
        return (
            get_open_conversation_session(
                uid,
                now=frozen,
                active_minutes=30,
                awaiting_topic_minutes=2,
            )
            is not None
        )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        conversation_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            conversation_spy=conversation_spy,
        )
        try:
            with patch(
                "apps.bot.handlers.conversation.open_conversation_awaits_text",
                side_effect=_awaits,
            ):
                update = _text_update(tid, SAMPLE_TEXT)
                update._bot = app.bot
                update.message._bot = app.bot
                await app.process_update(update)
            correction_spy.assert_awaited_once()
            conversation_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


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


def test_dispatch_awaiting_topic_stale_after_two_minutes(
    cleanup_user: int,
) -> None:
    from core.services.sessions import get_open_conversation_session

    tid = cleanup_user
    user_id = _onboard(tid)
    start = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
    insert_session(
        user_id,
        "conversation",
        date(2026, 8, 14),
        payload=_conversation_payload(
            phase="awaiting_topic", last_activity=start
        ),
        completed=False,
    )
    assert (
        get_open_conversation_session(
            user_id,
            now=start + timedelta(minutes=1),
            active_minutes=30,
            awaiting_topic_minutes=2,
        )
        is not None
    )
    assert (
        get_open_conversation_session(
            user_id,
            now=start + timedelta(minutes=3),
            active_minutes=30,
            awaiting_topic_minutes=2,
        )
        is None
    )


def test_dispatch_group_chat_never_captured_by_conversation(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    insert_session(
        user_id,
        "conversation",
        date(2026, 8, 14),
        payload=_conversation_payload(),
        completed=False,
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        conversation_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            conversation_spy=conversation_spy,
        )
        try:
            update = _group_text_update(tid, SAMPLE_TEXT)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            conversation_spy.assert_not_awaited()
            correction_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


def test_dispatch_command_mid_conversation_reaches_handler(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    insert_session(
        user_id,
        "conversation",
        date(2026, 8, 14),
        payload=_conversation_payload(),
        completed=False,
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        conversation_spy = AsyncMock()
        app, _book, _settings = await _build_app(
            quiz_spy=quiz_spy,
            correction_spy=correction_spy,
            conversation_spy=conversation_spy,
        )
        try:
            from telegram import MessageEntity

            user = User(id=tid, first_name="A", is_bot=False)
            chat = Chat(id=tid, type="private")
            msg = Message(
                message_id=10,
                date=datetime.now(timezone.utc),
                chat=chat,
                from_user=user,
                text="/stats",
                entities=[
                    MessageEntity(
                        type=MessageEntity.BOT_COMMAND,
                        offset=0,
                        length=6,
                    )
                ],
            )
            update = Update(update_id=1, message=msg)
            update._bot = app.bot
            update.message._bot = app.bot
            await app.process_update(update)
            conversation_spy.assert_not_awaited()
            correction_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())


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
