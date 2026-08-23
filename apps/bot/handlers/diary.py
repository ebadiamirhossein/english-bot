"""Voice diary (M9 / S13).

Bot-initiated Tue/Thu prompt + user-initiated /diary. Voice reply → Whisper →
light-touch corrections (max 2) as text. No TTS. Full transcript discarded;
quoted fragments may land in errors.you_said via record_errors.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from apps.bot import texts
from core import PROMPTS_DIR
from core.config import load_settings
from apps.bot.handlers.correction import (
    ABSTRACT_ERROR_TYPES,
    error_type_list_text,
    render_correction_message,
)
from apps.bot.handlers.voice import (
    _delete_status,
    _edit_status,
    _repeat_record_voice,
)
from core.llm import LLMError, chat
from core.services.errors import record_errors
from core.services.sessions import (
    complete_session,
    get_open_diary_session,
    has_completed_diary_on,
    has_diary_session_on,
    increment_bot_messages,
    insert_session,
    local_today,
    under_message_ceiling,
)
from core.services.users import User, get_user, is_registered
from core.speech import SpeechError, transcribe

logger = logging.getLogger(__name__)

HANDLER_NAME = "diary"
MAX_DIARY_ERRORS = 2

_PROMPT_PATH = PROMPTS_DIR / "diary.txt"
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


def init_diary_prompt() -> None:
    """Load the diary prompt template; error taxonomy from correction."""
    global _prompt_template
    _prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")
    error_type_list_text()
    logger.info("Loaded diary prompt template")


def build_diary_handlers() -> CommandHandler:
    return CommandHandler("diary", on_diary_command)


def diary_prompt_for(local_date: date) -> str:
    """Rotate concrete diary prompts by calendar day."""
    prompts = texts.DIARY_PROMPTS
    index = local_date.toordinal() % len(prompts)
    return prompts[index]


def build_diary_system_prompt(user: User) -> str:
    if _prompt_template is None:
        init_diary_prompt()
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
    )


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


async def deliver_diary(
    app: Any,
    user_id: int,
    *,
    now: datetime,
) -> str:
    """Bot-initiated diary prompt. Counts toward the 3-message ceiling."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    tz = _user_timezone(user_id)
    day = local_today(tz, now)

    if has_diary_session_on(user_id, day):
        return "skipped_existing"

    if not under_message_ceiling(user_id, day):
        logger.warning(
            "diary skip user_id=%s reason=ceiling_reached day=%s",
            user_id,
            day,
        )
        return "skipped_ceiling"

    user = get_user(user_id)
    if user is None:
        logger.warning("diary skip user_id=%s reason=user_not_found", user_id)
        return "skipped_no_user"

    prompt = diary_prompt_for(day)
    try:
        msg = await app.bot.send_message(chat_id=user_id, text=prompt)
    except Exception:
        logger.exception("diary send failed user_id=%s", user_id)
        return "skipped_send_failed"

    insert_session(
        user_id,
        "diary",
        day,
        payload={
            "source": "poll",
            "prompt_index": day.toordinal() % len(texts.DIARY_PROMPTS),
            "chat_id": int(msg.chat_id),
            "message_id": int(msg.message_id),
        },
        completed=False,
    )
    increment_bot_messages(user_id, day)
    logger.info("diary delivered user_id=%s day=%s", user_id, day)
    return "diary"


async def on_diary_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """User-initiated /diary — no ceiling, no bot_message_counts."""
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

    open_session = get_open_diary_session(user_id, day)
    if open_session is not None:
        await message.reply_text(texts.DIARY_ALREADY_OPEN)
        return

    if has_completed_diary_on(user_id, day):
        await message.reply_text(texts.DIARY_ALREADY_DONE)
        return

    prompt = diary_prompt_for(day)
    sent = await message.reply_text(prompt)
    insert_session(
        user_id,
        "diary",
        day,
        payload={
            "source": "command",
            "prompt_index": day.toordinal() % len(texts.DIARY_PROMPTS),
            "chat_id": int(sent.chat_id),
            "message_id": int(sent.message_id),
        },
        completed=False,
    )
    logger.info("diary command opened user_id=%s day=%s", user_id, day)


async def handle_diary_voice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    settings: Any,
) -> None:
    """Process one diary voice note. Caller holds the per-user voice lock."""
    message = update.message
    assert message is not None and message.voice is not None
    user_tg = update.effective_user
    assert user_tg is not None
    user_id = user_tg.id

    user = get_user(user_id)
    if user is None:
        return

    now = datetime.now(timezone.utc)
    tz = _user_timezone(user_id)
    day = local_today(tz, now)
    session = get_open_diary_session(user_id, day)
    if session is None:
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
            name=f"diary-action-{user_id}",
        )

        try:
            tg_file = await bot.get_file(message.voice.file_id)
            audio_buf = await tg_file.download_as_bytearray()
            audio = bytes(audio_buf)
        except Exception:
            logger.exception(
                "Diary download failed user_id=%s handler=%s",
                user_id,
                HANDLER_NAME,
            )
            await finish_as(texts.LLM_FAILED)
            return

        try:
            transcript = await asyncio.to_thread(
                transcribe, audio, settings=settings
            )
        except SpeechError:
            await edit_stage(texts.LLM_RETRY)
            try:
                transcript = await asyncio.to_thread(
                    transcribe, audio, settings=settings
                )
            except SpeechError:
                logger.warning(
                    "STT failed after retry user_id=%s handler=%s",
                    user_id,
                    HANDLER_NAME,
                )
                await finish_as(texts.LLM_FAILED)
                return

        if not transcript or len(transcript.strip()) < 2:
            await finish_as(texts.DIARY_DIDNT_CATCH)
            return

        transcript = transcript.strip()
        # Drop reference as soon as we hand off to LLM — never persist full text.
        await edit_stage(texts.VOICE_STATUS_THINKING)

        system = build_diary_system_prompt(user)
        messages = [{"role": "user", "content": transcript}]
        # Clear local binding before awaiting so we do not accidentally log it.
        del transcript

        result = await _call_diary_llm(
            messages=messages,
            system=system,
            on_retry=edit_stage,
            on_failed=finish_as,
        )
        if result is None:
            return

        errors = list(result.get("errors") or [])[:MAX_DIARY_ERRORS]
        did_well = str(result.get("did_well") or "").strip()

        await clear_status()
        correction_text = render_correction_message(errors, did_well)
        await message.reply_text(correction_text)

        if errors:
            record_errors(user_id, "diary", errors)

        complete_session(session.id, None)
        logger.info(
            "diary completed user_id=%s session_id=%s errors=%s",
            user_id,
            session.id,
            len(errors),
        )
    except Exception:
        logger.exception(
            "Diary handler failed user_id=%s handler=%s",
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


async def _call_diary_llm(
    *,
    messages: list[dict],
    system: str,
    on_retry: Callable[[str], Awaitable[None]] | None = None,
    on_failed: Callable[[str], Awaitable[None]] | None = None,
) -> dict | None:
    """json_mode chat off the event loop; soft fail after one retry."""

    def _once() -> dict:
        raw = chat(messages, system=system, json_mode=True)
        if not isinstance(raw, dict):
            raise LLMError("Expected JSON object from diary call")
        return raw

    try:
        return await asyncio.to_thread(_once)
    except LLMError:
        if on_retry is not None:
            await on_retry(texts.LLM_RETRY)
        try:
            return await asyncio.to_thread(_once)
        except LLMError:
            logger.warning(
                "LLM failed after handler retry handler=%s",
                HANDLER_NAME,
            )
            if on_failed is not None:
                await on_failed(texts.LLM_FAILED)
            return None
