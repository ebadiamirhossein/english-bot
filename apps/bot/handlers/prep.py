"""Load-up mode (M10 / S14).

``/prep <topic>`` → 10 chunks + 3 sentence frames for a real upcoming
situation. Command only — no MessageHandler. Never writes ``errors`` or
``sessions``. Chunks persist for Anki; frames are reply-only.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import CommandHandler, ContextTypes

from app import texts
from app.llm import LLMError, chat
from app.services.prep import (
    EXPECTED_CHUNKS,
    PrepValidationError,
    format_prep_reply,
    persist_and_send,
    validate_prep_payload,
)
from app.services.users import User, get_user, is_registered

logger = logging.getLogger(__name__)

HANDLER_NAME = "prep"

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "prep.txt"
_MIN_TOPIC_CHARS = 3
_MAX_TOPIC_CHARS = 200
_MAX_TOKENS = 2500
_RAW_LOG_LIMIT = 300

_prompt_template: str | None = None


def init_prep_prompt() -> None:
    """Load the prep system prompt from disk (call once at boot)."""
    global _prompt_template
    _prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")


def build_system_prompt(user: User) -> str:
    if _prompt_template is None:
        init_prep_prompt()
    assert _prompt_template is not None

    domain = (user.work_domain or "").strip() or "general"
    return _prompt_template.format(
        cefr_level=user.cefr_level,
        work_domain=domain,
    )


def wrap_topic(topic: str) -> str:
    return f"<topic>\n{topic}\n</topic>"


def build_prep_handler() -> CommandHandler:
    """Return the ``/prep`` command handler for main registration."""
    return CommandHandler("prep", on_prep_command)


async def on_prep_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    user_tg = update.effective_user
    if message is None or user_tg is None:
        return

    user_id = user_tg.id
    if not is_registered(user_id):
        return

    args = context.args or []
    topic = " ".join(args).strip()
    if len(topic) < _MIN_TOPIC_CHARS:
        await message.reply_text(texts.PREP_USAGE)
        return
    if len(topic) > _MAX_TOPIC_CHARS:
        await message.reply_text(texts.PREP_TOO_LONG)
        return

    await _run_prep(update, context, topic)


async def _run_prep(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    topic: str,
) -> None:
    message = update.message
    user_tg = update.effective_user
    if message is None or user_tg is None:
        return

    user_id = user_tg.id
    user = get_user(user_id)
    if user is None:
        return

    # Topic may name a real client or colleague — never log it (PRD §10).
    logger.info("handler=%s user_id=%s", HANDLER_NAME, user_id)

    await context.bot.send_chat_action(
        chat_id=message.chat_id, action=ChatAction.TYPING
    )

    system = build_system_prompt(user)
    messages = [{"role": "user", "content": wrap_topic(topic)}]

    try:
        raw = await asyncio.to_thread(
            chat,
            messages,
            system=system,
            json_mode=True,
            max_tokens=_MAX_TOKENS,
        )
    except LLMError:
        logger.exception(
            "handler=%s user_id=%s reason=llm_error",
            HANDLER_NAME,
            user_id,
        )
        await message.reply_text(texts.LLM_FAILED)
        return

    if not isinstance(raw, dict):
        logger.warning(
            "handler=%s user_id=%s reason=non_dict raw=%s",
            HANDLER_NAME,
            user_id,
            repr(raw)[:_RAW_LOG_LIMIT],
        )
        await message.reply_text(texts.PREP_FAILED)
        return

    try:
        payload = validate_prep_payload(raw, topic=topic)
    except PrepValidationError as exc:
        logger.warning(
            "handler=%s user_id=%s reason=%s raw=%s",
            HANDLER_NAME,
            user_id,
            exc,
            repr(raw)[:_RAW_LOG_LIMIT],
        )
        await message.reply_text(texts.PREP_FAILED)
        return

    if len(payload.chunks) < EXPECTED_CHUNKS:
        logger.warning(
            "handler=%s user_id=%s reason=partial_chunks count=%s",
            HANDLER_NAME,
            user_id,
            len(payload.chunks),
        )

    reply = format_prep_reply(
        topic=topic,
        chunks=payload.chunks,
        frames=payload.frames,
    )

    async def _send() -> None:
        await message.reply_text(reply)

    try:
        n = await persist_and_send(
            user_id=user_id,
            payload=payload,
            send=_send,
        )
    except Exception:
        logger.exception(
            "handler=%s user_id=%s reason=persist_or_send",
            HANDLER_NAME,
            user_id,
        )
        await message.reply_text(texts.PREP_FAILED)
        return

    logger.info(
        "handler=%s user_id=%s chunks=%s",
        HANDLER_NAME,
        user_id,
        n,
    )
