"""Shadowing (M12 / S16).

``/shadow`` → TTS a sentence from the user's chunks → user repeats by voice →
deterministic word-level intelligibility feedback. One retry, then complete.
Never writes ``errors``. Attempt transcript is never persisted.
"""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.constants import ChatAction
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from app import texts
from app.config import load_settings
from app.handlers.voice import (
    _delete_status,
    _edit_status,
    _repeat_record_voice,
)
from app.services.sessions import (
    complete_session,
    get_open_shadow_session,
    get_session_by_id,
    insert_session,
    local_today,
    update_session_payload,
)
from app.services.shadow import (
    abandon_open_shadow_sessions,
    diff_words,
    format_shadow_feedback,
    select_shadow_sentence,
    utc_now_iso,
)
from app.services.users import is_registered
from app.speech import SpeechError, synthesize, transcribe

logger = logging.getLogger(__name__)

HANDLER_NAME = "shadow"
CALLBACK_PREFIX = "shadow:again:"


def build_shadow_handlers() -> tuple[CommandHandler, CallbackQueryHandler]:
    return (
        CommandHandler("shadow", on_shadow_command),
        CallbackQueryHandler(on_shadow_retry, pattern=r"^shadow:again:\d+$"),
    )


def _user_timezone(user_id: int) -> str:
    from app.db import connection

    with connection() as conn:
        row = conn.execute(
            "SELECT timezone FROM users WHERE telegram_user_id = %s",
            (user_id,),
        ).fetchone()
    if row is None:
        return "Europe/Vilnius"
    return str(row["timezone"] or "Europe/Vilnius")


def _retry_keyboard(session_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    texts.BTN_SHADOW_AGAIN,
                    callback_data=f"{CALLBACK_PREFIX}{session_id}",
                )
            ]
        ]
    )


async def on_shadow_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """User-initiated /shadow — no ceiling, no bot_message_counts."""
    message = update.message
    user_tg = update.effective_user
    if message is None or user_tg is None:
        return
    user_id = user_tg.id
    if not is_registered(user_id):
        return

    now = datetime.now(timezone.utc)
    tz = _user_timezone(user_id)
    day = local_today(tz, now)

    chunk = select_shadow_sentence(user_id)
    if chunk is None:
        await message.reply_text(texts.SHADOW_EMPTY_POOL)
        return

    settings = load_settings()
    await context.bot.send_chat_action(
        chat_id=message.chat_id, action=ChatAction.RECORD_VOICE
    )

    try:
        audio = await asyncio.to_thread(
            synthesize, chunk.full_sentence, settings=settings
        )
    except SpeechError:
        logger.warning(
            "TTS failed user_id=%s handler=%s", user_id, HANDLER_NAME
        )
        await message.reply_text(texts.SHADOW_FAILED_TTS)
        return

    abandon_open_shadow_sessions(user_id)

    await message.reply_text(texts.SHADOW_INTRO)
    try:
        sent = await message.reply_voice(
            voice=InputFile(io.BytesIO(audio), filename="shadow.ogg")
        )
    except Exception:
        logger.exception(
            "shadow send failed user_id=%s handler=%s", user_id, HANDLER_NAME
        )
        await message.reply_text(texts.SHADOW_FAILED_TTS)
        return

    clip_sent_at = utc_now_iso(now)
    insert_session(
        user_id,
        "shadow",
        day,
        payload={
            "chunk_id": chunk.id,
            "target_sentence": chunk.full_sentence,
            "chat_id": int(sent.chat_id),
            "clip_message_id": int(sent.message_id),
            "clip_sent_at": clip_sent_at,
            "attempts": 0,
        },
        completed=False,
    )
    logger.info("shadow opened user_id=%s day=%s", user_id, day)


async def on_shadow_retry(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Re-send the same clip and re-arm the 30-min voice claim."""
    query = update.callback_query
    if query is None or query.data is None or query.from_user is None:
        return
    await query.answer()

    user_id = query.from_user.id
    if not is_registered(user_id):
        return

    try:
        session_id = int(query.data.split(":")[-1])
    except ValueError:
        return

    session = get_session_by_id(user_id, session_id)
    if session is None or session.task_type != "shadow" or session.completed:
        return

    payload = dict(session.payload or {})
    target = str(payload.get("target_sentence") or "").strip()
    if not target:
        return

    settings = load_settings()
    chat_id = query.message.chat_id if query.message else user_id
    await context.bot.send_chat_action(
        chat_id=chat_id, action=ChatAction.RECORD_VOICE
    )

    try:
        audio = await asyncio.to_thread(synthesize, target, settings=settings)
    except SpeechError:
        logger.warning(
            "TTS failed on retry user_id=%s handler=%s", user_id, HANDLER_NAME
        )
        if query.message is not None:
            await query.message.reply_text(texts.SHADOW_FAILED_TTS)
        return

    now = datetime.now(timezone.utc)
    try:
        sent = await context.bot.send_voice(
            chat_id=chat_id,
            voice=InputFile(io.BytesIO(audio), filename="shadow.ogg"),
        )
    except Exception:
        logger.exception(
            "shadow retry send failed user_id=%s handler=%s",
            user_id,
            HANDLER_NAME,
        )
        if query.message is not None:
            await query.message.reply_text(texts.SHADOW_FAILED_TTS)
        return

    payload["clip_message_id"] = int(sent.message_id)
    payload["chat_id"] = int(sent.chat_id)
    payload["clip_sent_at"] = utc_now_iso(now)
    update_session_payload(session_id, payload)


async def handle_shadow_voice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    settings: object,
) -> None:
    """Process one shadow voice note. Caller holds the per-user voice lock."""
    message = update.message
    assert message is not None and message.voice is not None
    user_tg = update.effective_user
    assert user_tg is not None
    user_id = user_tg.id

    now = datetime.now(timezone.utc)
    tz = _user_timezone(user_id)
    day = local_today(tz, now)
    session = get_open_shadow_session(user_id, day)
    if session is None:
        return

    payload = dict(session.payload or {})
    target = str(payload.get("target_sentence") or "").strip()
    if not target:
        return

    attempts = int(payload.get("attempts") or 0)
    chat_id = message.chat_id
    bot = context.bot
    status_id: int | None = None
    status_resolved = False
    action_task: asyncio.Task[None] | None = None

    async def finish_as(text: str) -> None:
        nonlocal status_resolved
        if status_id is not None and not status_resolved:
            await _edit_status(bot, chat_id, status_id, text)
            status_resolved = True

    async def clear_status() -> None:
        nonlocal status_resolved
        if status_id is not None and not status_resolved:
            await _delete_status(bot, chat_id, status_id)
            status_resolved = True

    try:
        status_msg = await message.reply_text(texts.VOICE_STATUS_LISTENING)
        status_id = int(status_msg.message_id)
        action_task = asyncio.create_task(
            _repeat_record_voice(bot, chat_id),
            name=f"shadow-action-{user_id}",
        )

        try:
            tg_file = await bot.get_file(message.voice.file_id)
            audio_buf = await tg_file.download_as_bytearray()
            audio = bytes(audio_buf)
        except Exception:
            logger.exception(
                "Shadow download failed user_id=%s handler=%s",
                user_id,
                HANDLER_NAME,
            )
            await finish_as(texts.SHADOW_FAILED_STT)
            return

        try:
            transcript = await asyncio.to_thread(
                transcribe, audio, settings=settings
            )
        except SpeechError:
            logger.warning(
                "STT failed user_id=%s handler=%s", user_id, HANDLER_NAME
            )
            await finish_as(texts.SHADOW_FAILED_STT)
            return

        # Audio discarded with ``audio`` going out of scope; transcript stays
        # local for the reply only — never written to payload or logs.
        result = diff_words(target, transcript)
        feedback = format_shadow_feedback(target, transcript, result)
        attempts += 1
        payload["attempts"] = attempts
        # Do not store transcript.
        update_session_payload(session.id, payload)

        await clear_status()

        if attempts < 2:
            await message.reply_text(
                feedback, reply_markup=_retry_keyboard(session.id)
            )
        else:
            complete_session(session.id, result.score)
            await message.reply_text(feedback)
            await message.reply_text(texts.SHADOW_DONE)
            logger.info(
                "shadow completed user_id=%s session_id=%s",
                user_id,
                session.id,
            )
    finally:
        if action_task is not None:
            action_task.cancel()
            try:
                await action_task
            except asyncio.CancelledError:
                pass
        if status_id is not None and not status_resolved:
            await _delete_status(bot, chat_id, status_id)
