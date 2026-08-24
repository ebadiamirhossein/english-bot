"""Real-life capture (M11 / S15).

Routes only on forwarded private text or ``/capture <text>``. Plain typed
text must continue to reach free correction (M2). Never writes to ``errors``.
"""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from apps.bot import texts
from core import PROMPTS_DIR
from core.prompt_rules import ENGLISH_ONLY_RULE, SINGLE_LANGUAGE_RULE
from core.llm import LLMError, chat
from core.services.capture import (
    CaptureValidationError,
    format_capture_reply,
    persist_and_send,
    validate_capture_payload,
)
from core.services.users import User, get_user, is_registered
from apps.bot import identity as bot_identity

logger = logging.getLogger(__name__)

HANDLER_NAME = "capture"

_PROMPT_PATH = PROMPTS_DIR / "capture.txt"
_MIN_CHARS = 20
_MAX_CHARS = 4000
_MAX_TOKENS = 1500
_RAW_LOG_LIMIT = 300

_prompt_template: str | None = None

_FALLBACK_RULE_TRUE = (
    "Explanations are in English (max 25 words). When an opaque point is "
    "abstract grammar AND explanation_language_fallback is enabled, you may "
    "drop that gloss into the learner's native language ({native_language}). "
    "Concrete idioms and register stay English. " + SINGLE_LANGUAGE_RULE
)

_FALLBACK_RULE_FALSE = (
    "Write every explanation and gloss in English (max 25 words each). "
    + ENGLISH_ONLY_RULE
)


def init_capture_prompt() -> None:
    """Load the capture system prompt from disk (call once at boot)."""
    global _prompt_template
    _prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")


def build_system_prompt(user: User) -> str:
    if _prompt_template is None:
        init_capture_prompt()
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
        explanation_language_rule=explanation_rule,
    )


def wrap_passage(text: str) -> str:
    return f"<passage>\n{text}\n</passage>"


def build_capture_handlers() -> tuple[MessageHandler, CommandHandler]:
    """Return (forwarded-text handler, /capture command) for main registration."""
    forwarded = MessageHandler(
        filters.FORWARDED
        & filters.TEXT
        & ~filters.COMMAND
        & filters.ChatType.PRIVATE,
        on_forwarded_capture,
    )
    command = CommandHandler("capture", on_capture_command)
    return forwarded, command


async def on_forwarded_capture(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    user_tg = update.effective_user
    if message is None or user_tg is None or not message.text:
        return

    user_id = bot_identity.bot_user_id(update, context)
    if user_id is None:
        return
    if not is_registered(user_id):
        return

    text = message.text.strip()
    if not text:
        return
    if len(text) < _MIN_CHARS:
        await message.reply_text(texts.CAPTURE_TOO_SHORT)
        return
    if len(text) > _MAX_CHARS:
        await message.reply_text(texts.CAPTURE_TOO_LONG)
        return

    await _run_capture(update, context, text)


async def on_capture_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    user_tg = update.effective_user
    if message is None or user_tg is None:
        return

    user_id = bot_identity.bot_user_id(update, context)
    if user_id is None:
        return
    if not is_registered(user_id):
        return

    args = context.args or []
    text = " ".join(args).strip()
    if not text:
        await message.reply_text(texts.CAPTURE_USAGE)
        return
    if len(text) < _MIN_CHARS:
        await message.reply_text(texts.CAPTURE_TOO_SHORT)
        return
    if len(text) > _MAX_CHARS:
        await message.reply_text(texts.CAPTURE_TOO_LONG)
        return

    await _run_capture(update, context, text)


async def _run_capture(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    message = update.message
    user_tg = update.effective_user
    if message is None or user_tg is None:
        return

    user_id = bot_identity.bot_user_id(update, context)
    if user_id is None:
        return
    user = get_user(user_id)
    if user is None:
        return

    logger.info("handler=%s user_id=%s", HANDLER_NAME, user_id)

    await context.bot.send_chat_action(
        chat_id=message.chat_id, action=ChatAction.TYPING
    )

    system = build_system_prompt(user)
    messages = [{"role": "user", "content": wrap_passage(text)}]

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
        await message.reply_text(texts.CAPTURE_FAILED)
        return

    try:
        payload = validate_capture_payload(raw)
    except CaptureValidationError as exc:
        logger.warning(
            "handler=%s user_id=%s reason=%s raw=%s",
            HANDLER_NAME,
            user_id,
            exc,
            repr(raw)[:_RAW_LOG_LIMIT],
        )
        await message.reply_text(texts.CAPTURE_NOTHING_USEFUL)
        return

    reply = format_capture_reply(
        explanation=payload.explanation,
        chunks=payload.chunks,
        hint=texts.CAPTURE_SELF_HINT,
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
        await message.reply_text(texts.CAPTURE_FAILED)
        return

    logger.info(
        "handler=%s user_id=%s chunks=%s",
        HANDLER_NAME,
        user_id,
        n,
    )


