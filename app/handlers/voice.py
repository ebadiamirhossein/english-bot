"""Voice partner (M3 / S5).

Voice in → Whisper → conversational reply as voice + correction as text.
Conversation state lives in sessions.payload. Never bot_data.
"""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime, timezone
from pathlib import Path

from telegram import InputFile, Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes, MessageHandler, filters

from app import texts
from app.config import load_settings
from app.handlers.correction import (
    ABSTRACT_ERROR_TYPES,
    error_type_list_text,
    render_correction_message,
)
from app.llm import LLMError, chat
from app.services.errors import record_errors
from app.services.sessions import (
    get_continuable_voice_session,
    local_today,
    save_voice_exchange,
)
from app.services.users import User, get_user, is_registered
from app.speech import SpeechError, synthesize, transcribe

logger = logging.getLogger(__name__)

HANDLER_NAME = "voice"

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "voice.txt"
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
    if message.voice.duration > settings.voice_max_seconds:
        await message.reply_text(texts.VOICE_TOO_LONG)
        return

    async with _lock_for(user_id):
        await _handle_voice_locked(update, context, settings)


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

    await context.bot.send_chat_action(
        chat_id=message.chat_id, action=ChatAction.RECORD_VOICE
    )

    try:
        tg_file = await context.bot.get_file(message.voice.file_id)
        audio_buf = await tg_file.download_as_bytearray()
        audio = bytes(audio_buf)
    except Exception:
        logger.exception(
            "Voice download failed user_id=%s handler=%s",
            user_id,
            HANDLER_NAME,
        )
        await message.reply_text(texts.LLM_FAILED)
        return

    try:
        transcript = transcribe(audio, settings=settings)
    except SpeechError:
        await message.reply_text(texts.LLM_RETRY)
        try:
            transcript = transcribe(audio, settings=settings)
        except SpeechError:
            logger.exception(
                "STT failed after retry user_id=%s handler=%s",
                user_id,
                HANDLER_NAME,
            )
            await message.reply_text(texts.LLM_FAILED)
            return

    if not transcript or len(transcript.strip()) < 2:
        await message.reply_text(texts.VOICE_DIDNT_CATCH)
        return

    transcript = transcript.strip()
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
        messages = list(payload.get("messages") or [])
        turn_count = int(payload.get("turn_count") or 0)
        session_id: int | None = existing.id
    else:
        payload = {"messages": [], "turn_count": 0}
        messages = []
        turn_count = 0
        session_id = None

    next_turn = turn_count + 1
    final_turn = next_turn >= settings.voice_max_turns

    history_for_llm = list(messages) + [
        {"role": "user", "content": transcript}
    ]
    system = build_voice_system_prompt(user, final_turn=final_turn)

    result = await _call_llm_with_handler_retry(
        message, messages=history_for_llm, system=system
    )
    if result is None:
        return

    reply_text = str(result.get("reply") or "").strip()
    if not reply_text:
        reply_text = "Nice — tell me more?"
    errors = list(result.get("errors") or [])[:3]
    did_well = str(result.get("did_well") or "").strip()

    await context.bot.send_chat_action(
        chat_id=message.chat_id, action=ChatAction.RECORD_VOICE
    )

    voice_sent_as_audio = False
    try:
        audio_out = synthesize(reply_text, settings=settings)
        voice_file = InputFile(io.BytesIO(audio_out), filename="voice.ogg")
        if settings.tts_format == "opus":
            await message.reply_voice(voice=voice_file)
        else:
            await message.reply_audio(audio=voice_file)
        voice_sent_as_audio = True
    except SpeechError:
        logger.warning(
            "TTS failed; falling back to text user_id=%s", user_id
        )
        await message.reply_text(reply_text)

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


async def _call_llm_with_handler_retry(
    message,
    *,
    messages: list[dict],
    system: str,
) -> dict | None:
    """Call llm.chat; on first LLMError reply LLM_RETRY and try once more."""
    try:
        raw = chat(messages, system=system, json_mode=True)
        if not isinstance(raw, dict):
            raise LLMError("Expected JSON object from voice call")
        return raw
    except LLMError:
        await message.reply_text(texts.LLM_RETRY)
        try:
            raw = chat(messages, system=system, json_mode=True)
            if not isinstance(raw, dict):
                raise LLMError("Expected JSON object from voice call")
            return raw
        except LLMError:
            logger.exception(
                "LLM failed after handler retry user_id=%s handler=%s",
                message.from_user.id if message.from_user else None,
                HANDLER_NAME,
            )
            await message.reply_text(texts.LLM_FAILED)
            return None
