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
    Message,
    MessageEntity,
    MessageOriginUser,
    PhotoSize,
    Update,
    User,
    Voice,
)
from telegram.ext import ApplicationBuilder, ConversationHandler

from app.config import Settings
from app.db import close_pool, connection
from app.handlers.book import (
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
from app.handlers.book_test import build_book_test_handlers
from app.handlers.capture import build_capture_handlers
from app.handlers.correction import build_correction_handler
from app.handlers.nudge import build_nudge_handler
from app.handlers.quiz import (
    build_quiz_handlers,
    open_quiz_awaits_gap_answer,
)
from app.handlers.reading import build_reading_handler
from app.handlers.settings import build_settings_handlers
from app.handlers.voice import build_voice_handler
from app.services.alerts import on_error
from app.services.sessions import insert_session, local_today, save_voice_exchange
from app.services.users import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_470_000_000
SAMPLE_TEXT = "her english is not so much good"
CAPTURE_SAMPLE = "Could you circle back on this by Friday please?"


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
):
    """Application mirroring main.py: capture → quiz text → voice → correction."""
    if capture_spy is None:
        capture_spy = AsyncMock()
    with (
        patch("app.handlers.quiz.on_quiz_text", quiz_spy),
        patch("app.handlers.correction.correct_text", correction_spy),
        patch("app.handlers.capture.on_forwarded_capture", capture_spy),
        patch("app.handlers.capture.on_capture_command", capture_spy),
    ):
        quiz_text, quiz_choice = build_quiz_handlers()
        capture_fwd, capture_cmd = build_capture_handlers()
        reading = build_reading_handler()
        nudge = build_nudge_handler()
        test_cmd, test_cb = build_book_test_handlers()
        voice = build_voice_handler()
        book = build_book_handler()
        correction = build_correction_handler()

    pause_cmd, stats_cmd, pause_cb = build_settings_handlers()
    app = ApplicationBuilder().token("1:FAKE-DISPATCH-TEST").build()
    app.add_error_handler(on_error)
    app.add_handler(pause_cmd)
    app.add_handler(stats_cmd)
    app.add_handler(pause_cb)
    app.add_handler(quiz_choice)
    app.add_handler(capture_fwd)
    app.add_handler(capture_cmd)
    app.add_handler(quiz_text)
    app.add_handler(reading)  # callbacks only — must not swallow free text
    app.add_handler(nudge)  # nudge: taps only — must not swallow free text
    app.add_handler(test_cb)
    app.add_handler(test_cmd)
    app.add_handler(voice)
    app.add_handler(book)
    app.add_handler(correction)

    # Avoid Telegram network: mark initialized without Bot.initialize/get_me.
    me = User(id=1, first_name="Bot", is_bot=True, username="testbot")
    object.__setattr__(app.bot, "_bot_user", me)
    app._initialized = True
    return app, book


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


# --- Unit helpers ------------------------------------------------------------


def test_open_quiz_awaits_gap_only(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 8, 8)
    insert_session(tid, "quiz", day, payload=_quiz_payload("choice"), completed=False)
    assert open_quiz_awaits_gap_answer(tid) is False
    assert open_quiz_awaits_gap_answer(tid + 999) is False

    with connection() as conn:
        with conn.transaction():
            conn.execute("DELETE FROM sessions WHERE user_id = %s", (tid,))
    insert_session(tid, "quiz", day, payload=_quiz_payload("gap"), completed=False)
    assert open_quiz_awaits_gap_answer(tid) is True


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
    _onboard(tid)
    insert_session(
        tid, "quiz", date(2026, 8, 8), payload=_quiz_payload("gap"), completed=False
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, _book = await _build_app(
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
    _onboard(tid)
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
        tid, "quiz", date(2026, 8, 9), payload=payload, completed=False
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, _book = await _build_app(
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
    _onboard(tid)
    sid = insert_session(
        tid,
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
        app, _book = await _build_app(
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
    _onboard(tid)
    insert_session(
        tid, "quiz", date(2026, 8, 8), payload=_quiz_payload(fmt), completed=False
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, _book = await _build_app(
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
    _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        capture_spy = AsyncMock()
        app, _book = await _build_app(
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
    _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        capture_spy = AsyncMock()
        app, _book = await _build_app(
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
    _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        capture_spy = AsyncMock()
        app, _book = await _build_app(
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
    _onboard(tid)
    insert_session(
        tid, "quiz", date(2026, 8, 8), payload=_quiz_payload("gap"), completed=False
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        capture_spy = AsyncMock()
        app, _book = await _build_app(
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
    _onboard(tid)
    insert_session(
        tid,
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
        app, _book = await _build_app(
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
    _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, book = await _build_app(
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
                "app.handlers.book.is_registered", return_value=True
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
    _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, book = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            key = (tid, tid)
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
    _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, book = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            key = (tid, tid)
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
    _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        app, book = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            key = (tid, tid)
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
    _onboard(tid)

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
        with patch("app.handlers.book.is_registered", return_value=True):
            state = await start(start_update, context)
        assert state == ASK_BOOK
        assert context.user_data["book"]["pages"] == []
        assert context.user_data["book"].get("book") is None
        assert context.user_data["book"]["collecting"] is False

    asyncio.run(_run())


def test_dispatch_open_reading_mid_qa_reaches_correction(cleanup_user: int) -> None:
    """S9c: open reading mid-question-set must not swallow free text (M2)."""
    tid = cleanup_user
    _onboard(tid)
    insert_session(
        tid,
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
        app, _book = await _build_app(
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
    _onboard(tid)
    now = datetime.now(timezone.utc)
    day = local_today("Europe/Vilnius", now)
    insert_session(
        tid,
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
        app, _book = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            update = _voice_update(tid)
            update._bot = app.bot
            update.message._bot = app.bot
            with (
                patch(
                    "app.handlers.voice.load_settings",
                    return_value=_voice_settings(),
                ),
                patch("app.handlers.shadow.handle_shadow_voice", shadow_spy),
                patch("app.handlers.diary.handle_diary_voice", diary_spy),
                patch("app.handlers.voice._handle_voice_locked", m3_spy),
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
    _onboard(tid)
    day = local_today("Europe/Vilnius", datetime.now(timezone.utc))
    insert_session(
        tid, "diary", day, payload={"source": "poll"}, completed=False
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        shadow_spy = AsyncMock()
        diary_spy = AsyncMock()
        m3_spy = AsyncMock()
        app, _book = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            update = _voice_update(tid)
            update._bot = app.bot
            update.message._bot = app.bot
            with (
                patch(
                    "app.handlers.voice.load_settings",
                    return_value=_voice_settings(),
                ),
                patch("app.handlers.shadow.handle_shadow_voice", shadow_spy),
                patch("app.handlers.diary.handle_diary_voice", diary_spy),
                patch("app.handlers.voice._handle_voice_locked", m3_spy),
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
    _onboard(tid)

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        shadow_spy = AsyncMock()
        diary_spy = AsyncMock()
        m3_spy = AsyncMock()
        app, _book = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            update = _voice_update(tid)
            update._bot = app.bot
            update.message._bot = app.bot
            with (
                patch(
                    "app.handlers.voice.load_settings",
                    return_value=_voice_settings(),
                ),
                patch("app.handlers.shadow.handle_shadow_voice", shadow_spy),
                patch("app.handlers.diary.handle_diary_voice", diary_spy),
                patch("app.handlers.voice._handle_voice_locked", m3_spy),
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
    _onboard(tid)
    day = local_today("Europe/Vilnius", datetime.now(timezone.utc))
    save_voice_exchange(
        None,
        tid,
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
        tid, "diary", day, payload={"source": "poll"}, completed=False
    )

    async def _run() -> None:
        quiz_spy = AsyncMock()
        correction_spy = AsyncMock()
        shadow_spy = AsyncMock()
        diary_spy = AsyncMock()
        m3_spy = AsyncMock()
        app, _book = await _build_app(
            quiz_spy=quiz_spy, correction_spy=correction_spy
        )
        try:
            update = _voice_update(tid)
            update._bot = app.bot
            update.message._bot = app.bot
            with (
                patch(
                    "app.handlers.voice.load_settings",
                    return_value=_voice_settings(),
                ),
                patch("app.handlers.shadow.handle_shadow_voice", shadow_spy),
                patch("app.handlers.diary.handle_diary_voice", diary_spy),
                patch("app.handlers.voice._handle_voice_locked", m3_spy),
            ):
                await app.process_update(update)
            m3_spy.assert_awaited_once()
            shadow_spy.assert_not_awaited()
            diary_spy.assert_not_awaited()
        finally:
            app._initialized = False

    asyncio.run(_run())
