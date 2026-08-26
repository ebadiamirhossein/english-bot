"""Free correction for non-command private text (M2 / S2).

Unregistered users get silence (same access model as S1). Mid-onboarding
users are not registered yet, so ConversationHandler owns their text.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes, MessageHandler, filters

from apps.bot import texts
from core.llm import LLMError
from core.services.correction import (
    ABSTRACT_ERROR_TYPES,
    MAX_CHARS as _MAX_CHARS,
    MIN_CHARS as _MIN_CHARS,
    apply_result,
    build_system_prompt,
    call_model,
    error_type_list_text,
    init_correction_prompt,
    murphy_lookup,
    wrap_user_text,
)
from core.services.users import get_user, is_registered
from apps.bot import identity as bot_identity

logger = logging.getLogger(__name__)

HANDLER_NAME = "correction"

# The prompt, the taxonomy cache, build_system_prompt, wrap_user_text and the
# journal write all live in core.services.correction from W3 — `apps/api` needs
# them too and may not import this package. These names are re-exported because
# eight modules and five test files already import them from here; moving the
# logic without moving the imports is what keeps that a move rather than a
# rewrite.
__all__ = [
    "ABSTRACT_ERROR_TYPES",
    "build_correction_handler",
    "build_system_prompt",
    "correct_text",
    "error_type_list_text",
    "init_correction_prompt",
    "murphy_lookup",
    "render_correction_message",
    "wrap_user_text",
]


def build_correction_handler() -> MessageHandler:
    return MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        correct_text,
    )


async def correct_text(
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
    if len(text) < _MIN_CHARS:
        return
    if len(text) > _MAX_CHARS:
        await message.reply_text(texts.TEXT_TOO_LONG)
        return

    user = get_user(user_id)
    if user is None:
        return

    await context.bot.send_chat_action(
        chat_id=message.chat_id, action=ChatAction.TYPING
    )

    result = await _call_llm_with_handler_retry(message, user=user, text=text)
    if result is None:
        return

    await _handle_model_result(message, user_id, result)


async def _call_llm_with_handler_retry(
    message,
    *,
    user,
    text: str,
) -> dict | None:
    """One correction call; on first LLMError tell the learner and try once more.

    The retry lives here and not in `core` because it *speaks*: LLM_RETRY goes
    to the learner between the two attempts, and a service has no channel to
    say anything. The call itself is `core.services.correction.call_model`, so
    the prompt this sends is byte-for-byte the prompt `POST /correct` sends.
    """
    try:
        return call_model(user, text)
    except LLMError:
        await message.reply_text(texts.LLM_RETRY)
        try:
            return call_model(user, text)
        except LLMError:
            logger.exception(
                "LLM failed after handler retry user_id=%s handler=%s",
                message.from_user.id if message.from_user else None,
                HANDLER_NAME,
            )
            await message.reply_text(texts.LLM_FAILED)
            return None


async def _handle_model_result(message, user_id: int, result: dict) -> None:
    """Render what the shared service decided. One correction path, two skins.

    Every branch below mirrors an ``CorrectionOutcome`` field rather than
    re-deriving it: the cap, the unknown-type drop and the journal write all
    happened in ``core.services.correction.apply_result``, which the web route
    calls too. Re-deriving any of it here is how the two front ends would start
    disagreeing about what a correction is.
    """
    outcome = apply_result(user_id, result, source="text")

    if not outcome.is_english:
        await message.reply_text(texts.NOT_ENGLISH)
        return

    if not outcome.has_errors:
        await message.reply_text(texts.format_praise(outcome.did_well))
        return

    await message.reply_text(
        render_correction_message(outcome.corrections, outcome.did_well)
    )


def render_correction_message(
    corrections: list[dict],
    did_well: str,
) -> str:
    """Shared PRD §8 correction text. Cap 3; drop unknown types; praise if empty.

    Pure formatting move for voice (S5) and text (S2) — no behaviour change.
    """
    corrections = list(corrections or [])[:3]
    did = (did_well or "").strip() or "Nice."
    if not corrections:
        return texts.format_praise(did)
    # `murphy_lookup()` is the code -> units map and doubles as the VALID
    # ERROR-CODE SET, which is the only thing it is used for here. The map is no
    # longer passed to the formatter: #183's ruling took the citation off the
    # correction block, so there is nothing to look up for rendering. One
    # argument removed, no logic changed.
    valid = murphy_lookup()
    kept = [c for c in corrections if c.get("error_type") in valid]
    if not kept:
        return texts.format_praise(did)
    return texts.format_correction_reply(kept, did)
