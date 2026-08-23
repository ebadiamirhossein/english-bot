"""Free correction for non-command private text (M2 / S2).

Unregistered users get silence (same access model as S1). Mid-onboarding
users are not registered yet, so ConversationHandler owns their text.
"""

from __future__ import annotations

import logging
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes, MessageHandler, filters

from datetime import datetime, timezone

from app import texts
from app.db import connection
from app.llm import LLMError, chat
from app.services.errors import record_errors
from app.services.sessions import complete_open_free_practice, local_today
from app.services.users import User, get_user, is_registered

logger = logging.getLogger(__name__)

HANDLER_NAME = "correction"

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "correction.txt"
_MIN_CHARS = 10
_MAX_CHARS = 1000

ABSTRACT_ERROR_TYPES = (
    "gerund_vs_infinitive",
    "present_perfect",
    "conditional",
    "modal_verb",
    "article_missing",
    "article_wrong",
)

# Populated by init_correction_prompt() at startup.
_prompt_template: str | None = None
_error_type_list: str = ""
_murphy_by_code: dict[str, str | None] = {}

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


def init_correction_prompt() -> None:
    """Load the prompt template and error taxonomy from the database."""
    global _prompt_template, _error_type_list, _murphy_by_code
    _prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")
    with connection() as conn:
        rows = conn.execute(
            "SELECT code, label, murphy_units FROM error_types ORDER BY code"
        ).fetchall()
    _murphy_by_code = {row["code"]: row["murphy_units"] for row in rows}
    _error_type_list = "\n".join(
        f"- {row['code']}: {row['label']}" for row in rows
    )
    logger.info("Loaded %s error types for correction prompt", len(rows))


def murphy_lookup() -> dict[str, str | None]:
    """Return the cached code → murphy_units map (for tests / rendering)."""
    if not _murphy_by_code:
        init_correction_prompt()
    return dict(_murphy_by_code)


def error_type_list_text() -> str:
    """Return the cached error-type bullet list for prompts."""
    if not _error_type_list:
        init_correction_prompt()
    return _error_type_list


def build_system_prompt(user: User) -> str:
    """Parameterise the correction system prompt for this learner."""
    if _prompt_template is None:
        init_correction_prompt()
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
        error_type_list=_error_type_list,
        explanation_language_rule=explanation_rule,
    )


def wrap_user_text(text: str) -> str:
    return f"<user_text>\n{text}\n</user_text>"


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

    user_id = user_tg.id
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

    system = build_system_prompt(user)
    messages = [{"role": "user", "content": wrap_user_text(text)}]

    result = await _call_llm_with_handler_retry(
        message, messages=messages, system=system
    )
    if result is None:
        return

    await _handle_model_result(message, user_id, result)


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
            raise LLMError("Expected JSON object from correction call")
        return raw
    except LLMError:
        await message.reply_text(texts.LLM_RETRY)
        try:
            raw = chat(messages, system=system, json_mode=True)
            if not isinstance(raw, dict):
                raise LLMError("Expected JSON object from correction call")
            return raw
        except LLMError:
            logger.exception(
                "LLM failed after handler retry user_id=%s handler=%s",
                message.from_user.id if message.from_user else None,
                HANDLER_NAME,
            )
            await message.reply_text(texts.LLM_FAILED)
            return None


def _complete_free_practice_if_open(user_id: int) -> None:
    """S4: a processed correction makes today's free_practice day Active."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT timezone FROM users WHERE telegram_user_id = %s
            """,
            (user_id,),
        ).fetchone()
    tz = str(row["timezone"] or "Europe/Vilnius") if row else "Europe/Vilnius"
    day = local_today(tz, datetime.now(timezone.utc))
    complete_open_free_practice(user_id, day)


async def _handle_model_result(message, user_id: int, result: dict) -> None:
    _complete_free_practice_if_open(user_id)

    if not result.get("is_english", True):
        await message.reply_text(texts.NOT_ENGLISH)
        return

    did_well = str(result.get("did_well") or "").strip()
    if not result.get("has_errors", False):
        await message.reply_text(texts.format_praise(did_well or "Nice."))
        return

    corrections = list(result.get("corrections") or [])
    # Cap at 3 even if the model overshoots.
    corrections = corrections[:3]
    if not corrections:
        await message.reply_text(texts.format_praise(did_well or "Nice."))
        return

    written = record_errors(user_id, "text", corrections)
    # Re-filter to what we would show: drop unknown types the same way writes do.
    valid = murphy_lookup()
    kept = [c for c in corrections if c.get("error_type") in valid]
    if written == 0 or not kept:
        # All dropped as invalid types — still acknowledge the attempt softly.
        await message.reply_text(texts.format_praise(did_well or "Nice."))
        return

    await message.reply_text(render_correction_message(corrections, did_well))


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
    valid = murphy_lookup()
    kept = [c for c in corrections if c.get("error_type") in valid]
    if not kept:
        return texts.format_praise(did)
    return texts.format_correction_reply(kept, did, valid)
