"""Voice partner (M3 / S5) + diary/shadow voice router (M9 / S13 / S16).

Voice in → Whisper → conversational reply as voice + correction as text.
Conversation state lives in sessions.payload. Never bot_data.

S5a: repeating chat action + in-place status message through three stages.

S16 routing (ordered): claimable open shadow (30-min clip window) wins; else
live M3; else open diary for local today; else M3.
"""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from telegram import InputFile, Update
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import ContextTypes, MessageHandler, filters

from apps.bot import texts
from core import PROMPTS_DIR
from core.config import load_settings
from apps.bot.handlers.correction import (
    ABSTRACT_ERROR_TYPES,
    error_type_list_text,
    render_correction_message,
)
from core.llm import LLMError, chat
from core.services.errors import record_errors
from core.services.sessions import (
    get_claimable_shadow_session,
    get_continuable_voice_session,
    get_open_diary_session,
    local_today,
    save_voice_exchange,
)
from core.services.users import User, get_user, is_registered
from core.speech import SpeechError, synthesize, transcribe

logger = logging.getLogger(__name__)

HANDLER_NAME = "voice"
_CHAT_ACTION_INTERVAL_SECONDS = 4.0

_PROMPT_PATH = PROMPTS_DIR / "voice.txt"
_user_locks: dict[int, asyncio.Lock] = {}

_prompt_template: str | None = None

_FALLBACK_RULE_TRUE = (
    "BUT when the error type is abstract grammar "
    f"({', '.join(ABSTRACT_ERROR_TYPES)}) AND the user's "
    "explanation_language_fallback is enabled, write that explanation in "
    "their native language ({native_language}) instead. Concrete error types "
    "stay English regardless."
)

_FALLBACK_RULE_FALSE = (
    "Write every explanation in English, including abstract grammar types."
)


def init_voice_prompt() -> None:
    """Load the voice prompt template; error taxonomy comes from correction."""
    global _prompt_template
    _prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")
    error_type_list_text()  # warm the shared taxonomy cache
    logger.info("Loaded voice prompt template")


def build_voice_handler() -> MessageHandler:
    return MessageHandler(filters.VOICE, handle_voice)


def _lock_for(user_id: int) -> asyncio.Lock:
    lock = _user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _user_locks[user_id] = lock
    return lock


def build_voice_system_prompt(user: User, *, final_turn: bool) -> str:
    if _prompt_template is None:
        init_voice_prompt()
    assert _prompt_template is not None

    if user.explanation_language_fallback:
        explanation_rule = _FALLBACK_RULE_TRUE.format(
            native_language=user.native_language
        )
    else:
        explanation_rule = _FALLBACK_RULE_FALSE

    return _prompt_template.format(
        cefr_level=user.cefr_level,
        native_language=user.native_language,
        work_domain=user.work_domain or "general",
        error_type_list=error_type_list_text(),
        explanation_language_rule=explanation_rule,
        final_turn="true" if final_turn else "false",
    )


async def handle_voice(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    user_tg = update.effective_user
    if message is None or user_tg is None or message.voice is None:
        return

    user_id = user_tg.id
    if not is_registered(user_id):
        return

    settings = load_settings()
    now = datetime.now(timezone.utc)
    tz = _user_timezone(user_id)
    day = local_today(tz, now)

    # Ordered: claimable shadow → live M3 → open diary → M3 (S16/S13).
    claimable_shadow = get_claimable_shadow_session(user_id, day, now=now)
    live_m3 = (
        None
        if claimable_shadow is not None
        else get_continuable_voice_session(
            user_id,
            now=now,
            context_minutes=settings.voice_context_minutes,
            max_turns=settings.voice_max_turns,
        )
    )
    open_diary = (
        None
        if claimable_shadow is not None or live_m3 is not None
        else get_open_diary_session(user_id, day)
    )
    route_shadow = claimable_shadow is not None
    route_diary = open_diary is not None

    # Over-length decline happens before status or chat action exist.
    max_seconds = (
        settings.diary_max_seconds
        if route_diary
        else settings.voice_max_seconds
    )
    if message.voice.duration > max_seconds:
        await message.reply_text(
            texts.DIARY_TOO_LONG if route_diary else texts.VOICE_TOO_LONG
        )
        return

    async with _lock_for(user_id):
        if route_shadow:
            from apps.bot.handlers.shadow import handle_shadow_voice

            await handle_shadow_voice(update, context, settings)
        elif route_diary:
            from apps.bot.handlers.diary import handle_diary_voice

            await handle_diary_voice(update, context, settings)
        else:
            await _handle_voice_locked(update, context, settings)


async def _repeat_record_voice(bot: Any, chat_id: int) -> None:
    """Re-send RECORD_VOICE every 4s — Telegram actions expire after ~5s."""
    try:
        while True:
            await bot.send_chat_action(
                chat_id=chat_id, action=ChatAction.RECORD_VOICE
            )
            await asyncio.sleep(_CHAT_ACTION_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        raise


async def _edit_status(
    bot: Any, chat_id: int, message_id: int, text: str
) -> None:
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text
        )
    except BadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        raise


async def _delete_status(bot: Any, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        logger.debug(
            "status delete failed chat_id=%s message_id=%s",
            chat_id,
            message_id,
            exc_info=True,
        )


async def _handle_voice_locked(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    settings,
) -> None:
    message = update.message
    assert message is not None and message.voice is not None
    user_tg = update.effective_user
    assert user_tg is not None
    user_id = user_tg.id

    user = get_user(user_id)
    if user is None:
        return

    chat_id = message.chat_id
    bot = context.bot
    status_id: int | None = None
    status_resolved = False
    action_task: asyncio.Task[None] | None = None

    async def edit_stage(text: str) -> None:
        if status_id is None:
            return
        await _edit_status(bot, chat_id, status_id, text)

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
            name=f"voice-action-{user_id}",
        )

        try:
            tg_file = await bot.get_file(message.voice.file_id)
            audio_buf = await tg_file.download_as_bytearray()
            audio = bytes(audio_buf)
        except Exception:
            logger.exception(
                "Voice download failed user_id=%s handler=%s",
                user_id,
                HANDLER_NAME,
            )
            await finish_as(texts.LLM_FAILED)
            return

        try:
            transcript = transcribe(audio, settings=settings)
        except SpeechError:
            await edit_stage(texts.LLM_RETRY)
            try:
                transcript = transcribe(audio, settings=settings)
            except SpeechError:
                logger.exception(
                    "STT failed after retry user_id=%s handler=%s",
                    user_id,
                    HANDLER_NAME,
                )
                await finish_as(texts.LLM_FAILED)
                return

        if not transcript or len(transcript.strip()) < 2:
            await finish_as(texts.VOICE_DIDNT_CATCH)
            return

        transcript = transcript.strip()
        await edit_stage(texts.VOICE_STATUS_THINKING)

        now = datetime.now(timezone.utc)
        tz = _user_timezone(user_id)
        day = local_today(tz, now)

        existing = get_continuable_voice_session(
            user_id,
            now=now,
            context_minutes=settings.voice_context_minutes,
            max_turns=settings.voice_max_turns,
        )
        if existing is not None and existing.payload is not None:
            payload = dict(existing.payload)
            history = list(payload.get("messages") or [])
            turn_count = int(payload.get("turn_count") or 0)
            session_id: int | None = existing.id
        else:
            history = []
            turn_count = 0
            session_id = None

        next_turn = turn_count + 1
        final_turn = next_turn >= settings.voice_max_turns

        history_for_llm = list(history) + [
            {"role": "user", "content": transcript}
        ]
        system = build_voice_system_prompt(user, final_turn=final_turn)

        result = await _call_llm_with_handler_retry(
            messages=history_for_llm,
            system=system,
            on_retry=edit_stage,
            on_failed=finish_as,
        )
        if result is None:
            return

        reply_text = str(result.get("reply") or "").strip()
        if not reply_text:
            reply_text = "Nice — tell me more?"
        errors = list(result.get("errors") or [])[:3]
        did_well = str(result.get("did_well") or "").strip()

        await edit_stage(texts.VOICE_STATUS_RECORDING)

        voice_sent_as_audio = False
        try:
            audio_out = synthesize(reply_text, settings=settings)
        except SpeechError:
            logger.warning(
                "TTS failed; falling back to text user_id=%s", user_id
            )
            await clear_status()
            await message.reply_text(reply_text)
            audio_out = None
        else:
            await clear_status()
            voice_file = InputFile(io.BytesIO(audio_out), filename="voice.ogg")
            if settings.tts_format == "opus":
                await message.reply_voice(voice=voice_file)
            else:
                await message.reply_audio(audio=voice_file)
            voice_sent_as_audio = True

        correction_text = render_correction_message(errors, did_well)
        await message.reply_text(correction_text)

        if errors:
            record_errors(user_id, "voice", errors)

        new_messages = history_for_llm + [
            {"role": "assistant", "content": reply_text}
        ]
        new_payload = {
            "messages": new_messages,
            "turn_count": next_turn,
        }
        save_voice_exchange(session_id, user_id, day, new_payload)
        logger.info(
            "voice exchange user_id=%s turn=%s audio=%s",
            user_id,
            next_turn,
            voice_sent_as_audio,
        )
    except Exception:
        logger.exception(
            "Voice handler failed user_id=%s handler=%s",
            user_id,
            HANDLER_NAME,
        )
        await finish_as(texts.LLM_FAILED)
    finally:
        if action_task is not None:
            action_task.cancel()
            try:
                await action_task
            except asyncio.CancelledError:
                pass
        if status_id is not None and not status_resolved:
            await finish_as(texts.LLM_FAILED)


def _user_timezone(user_id: int) -> str:
    from core.db import connection

    with connection() as conn:
        row = conn.execute(
            "SELECT timezone FROM users WHERE telegram_user_id = %s",
            (user_id,),
        ).fetchone()
    if row is None:
        return "Europe/Vilnius"
    return str(row["timezone"] or "Europe/Vilnius")


async def _call_llm_with_handler_retry(
    *,
    messages: list[dict],
    system: str,
    on_retry: Callable[[str], Awaitable[None]] | None = None,
    on_failed: Callable[[str], Awaitable[None]] | None = None,
) -> dict | None:
    """Call llm.chat; on first LLMError signal retry, then fail soft."""
    try:
        raw = chat(messages, system=system, json_mode=True)
        if not isinstance(raw, dict):
            raise LLMError("Expected JSON object from voice call")
        return raw
    except LLMError:
        if on_retry is not None:
            await on_retry(texts.LLM_RETRY)
        try:
            raw = chat(messages, system=system, json_mode=True)
            if not isinstance(raw, dict):
                raise LLMError("Expected JSON object from voice call")
            return raw
        except LLMError:
            logger.exception(
                "LLM failed after handler retry handler=%s",
                HANDLER_NAME,
            )
            if on_failed is not None:
                await on_failed(texts.LLM_FAILED)
            return None
