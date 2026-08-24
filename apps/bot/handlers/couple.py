"""Couple challenge group surface (M8 / S8).

Daily question at 18:00 Vilnius in the configured group. First correct
answer wins. Sunday leaderboard. Private learning paths untouched.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from telegram import Message, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from apps.bot import texts
from core.config import Settings, load_settings
from apps.bot.handlers.quiz import grade_answer
from core.llm import LLMError, chat
from apps.bot.services.couple import (
    SCHEDULED_MAX_CHARS,
    add_point,
    claim_sunday_leaderboard,
    claim_win,
    couple_local_today,
    couple_time_reached,
    feature_ready,
    get_challenge_for_date,
    get_open_challenge,
    insert_challenge_if_absent,
    is_couple_sunday,
    pick_source_error,
    registered_user_ids,
    scores_for_week,
    week_start,
)
from core.services.errors import Error
from core.services.users import get_user, is_registered
from apps.bot import identity as bot_identity
from core.services import identity

logger = logging.getLogger(__name__)

HANDLER_NAME = "couple"

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "couple.txt"
_MAX_TOKENS = 400
_prompt_template: str | None = None


def init_couple_prompt() -> None:
    """Load the couple question prompt from disk (call once at boot)."""
    global _prompt_template
    _prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")


def _settings() -> Settings:
    return load_settings()


def build_system_prompt(*, cefr_level: str) -> str:
    if _prompt_template is None:
        init_couple_prompt()
    assert _prompt_template is not None
    return _prompt_template.format(cefr_level=cefr_level)


def wrap_error_row(err: Error) -> str:
    payload = {
        "you_said": err.you_said,
        "correct_form": err.correct_form,
        "error_type": err.error_type,
        "explanation": err.explanation,
    }
    return f"<error_row>\n{json.dumps(payload, ensure_ascii=False)}\n</error_row>"


class OpenCoupleChallengeFilter(filters.MessageFilter):
    """Match group text only for the couple chat with an open challenge.

    Registration is checked here so the handler never runs for strangers.
    """

    def filter(self, message: Message) -> bool:
        chat = message.chat
        user = message.from_user
        if chat is None or user is None:
            return False
        if chat.type not in ("group", "supergroup"):
            return False
        settings = _settings()
        if settings.couple_chat_id is None:
            return False
        if int(chat.id) != int(settings.couple_chat_id):
            return False
        # A PTB filter has no `context` to read the gate's stash from, so it
        # resolves through the core resolver directly. Still one translation
        # module, which is what the rule is about.
        resolved = identity.user_id_for_telegram(user.id)
        if resolved is None or not is_registered(resolved):
            return False
        try:
            # Filter has no injected clock; use UTC now → Vilnius local today.
            from datetime import timezone

            day = couple_local_today(datetime.now(timezone.utc))
            return get_open_challenge(day) is not None
        except Exception:
            logger.exception(
                "OpenCoupleChallengeFilter failed chat_id=%s telegram_user_id=%s",
                chat.id,
                user.id,
            )
            return False


def build_couple_handlers() -> tuple[CommandHandler, MessageHandler]:
    """Return (/here, group answer) for registration before correction."""
    here = CommandHandler("here", on_here_command)
    answers = MessageHandler(
        filters.TEXT
        & ~filters.COMMAND
        & filters.ChatType.GROUPS
        & OpenCoupleChallengeFilter(),
        on_couple_answer,
    )
    return here, answers


async def on_here_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    user_tg = update.effective_user
    if message is None or user_tg is None:
        return
    user_id = bot_identity.bot_user_id(update, context)
    if user_id is None or not is_registered(user_id):
        return

    chat = message.chat
    if chat.type not in ("group", "supergroup"):
        await message.reply_text(texts.COUPLE_HERE_PRIVATE)
        return

    settings = _settings()
    chat_id = int(chat.id)
    if (
        settings.couple_chat_id is not None
        and int(settings.couple_chat_id) == chat_id
    ):
        await message.reply_text(texts.COUPLE_HERE_ALREADY)
        return

    await message.reply_text(
        texts.COUPLE_HERE_SET.format(chat_id=chat_id)
    )


async def on_couple_answer(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    user_tg = update.effective_user
    if message is None or user_tg is None or not message.text:
        return

    user_id = bot_identity.bot_user_id(update, context)
    if user_id is None:
        return
    # Filter already checked registration; belt-and-suspenders.
    if not is_registered(user_id):
        return

    from datetime import timezone

    day = couple_local_today(datetime.now(timezone.utc))
    challenge = get_open_challenge(day)
    if challenge is None:
        return

    raw = message.text.strip()
    if not grade_answer(raw, [challenge.answer]):
        await message.reply_text(texts.COUPLE_TRY_AGAIN)
        return

    if not claim_win(challenge.id, user_id):
        await message.reply_text(texts.COUPLE_ALREADY_CLAIMED)
        return

    add_point(user_id, week_start(day))
    name = _display_name(user_id, user_tg.first_name)
    await message.reply_text(texts.COUPLE_WIN.format(name=name))


def _display_name(user_id: int, fallback: str | None) -> str:
    user = get_user(user_id)
    if user is not None and (user.name or "").strip():
        return user.name.strip()
    return (fallback or "friend").strip() or "friend"


async def generate_question_from_error(err: Error) -> tuple[str, str] | None:
    """One LLM call → (question, answer). Off the event loop."""
    owner = get_user(err.user_id)
    cefr = owner.cefr_level if owner is not None else "B1"
    system = build_system_prompt(cefr_level=cefr)
    try:
        raw = await asyncio.to_thread(
            chat,
            [{"role": "user", "content": wrap_error_row(err)}],
            system=system,
            json_mode=True,
            max_tokens=_MAX_TOKENS,
        )
    except LLMError:
        logger.exception(
            "couple LLM failed source_error_id=%s user_id=%s",
            err.id,
            err.user_id,
        )
        return None

    if not isinstance(raw, dict):
        logger.warning("couple LLM non-object response")
        return None

    question = str(raw.get("question") or "").strip()
    answer = str(raw.get("answer") or "").strip()
    if not question or not answer:
        logger.warning("couple LLM missing question/answer")
        return None
    if len(question) > SCHEDULED_MAX_CHARS - 40:
        question = question[: SCHEDULED_MAX_CHARS - 40].rstrip()
    return question, answer


async def run_couple_poll(
    application: Any,
    *,
    now: datetime,
    settings: Settings | None = None,
) -> list[str]:
    """Daily question + Sunday leaderboard. Returns action tags."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    cfg = settings if settings is not None else _settings()
    actions: list[str] = []

    if not feature_ready(cfg):
        return ["inert"]

    if not couple_time_reached(now):
        return ["before_slot"]

    day = couple_local_today(now)
    q_action = await _deliver_daily_question(application, day, cfg)
    actions.append(q_action)

    if is_couple_sunday(now):
        lb_action = await _deliver_sunday_leaderboard(application, day, cfg)
        actions.append(lb_action)

    return actions


async def _deliver_daily_question(
    application: Any,
    day,
    settings: Settings,
) -> str:
    existing = get_challenge_for_date(day)
    if existing is not None:
        return "skipped_existing"

    err = pick_source_error(day)
    if err is None:
        logger.info("couple skip day=%s reason=no_source_error", day)
        return "skipped_no_error"

    generated = await generate_question_from_error(err)
    if generated is None:
        return "skipped_llm"

    question, answer = generated
    body = texts.COUPLE_QUESTION.format(question=question)
    if len(body) > SCHEDULED_MAX_CHARS:
        body = body[:SCHEDULED_MAX_CHARS].rstrip()

    challenge_id = insert_challenge_if_absent(day, question, answer)
    if challenge_id is None:
        return "skipped_race"

    assert settings.couple_chat_id is not None
    try:
        await application.bot.send_message(
            chat_id=int(settings.couple_chat_id),
            text=body,
        )
    except Exception:
        logger.exception(
            "couple question send failed chat_id=%s day=%s",
            settings.couple_chat_id,
            day,
        )
        return "skipped_send_failed"

    logger.info(
        "couple question delivered day=%s challenge_id=%s source_error_id=%s",
        day,
        challenge_id,
        err.id,
    )
    return "question"


async def _deliver_sunday_leaderboard(
    application: Any,
    sunday,
    settings: Settings,
) -> str:
    ids = registered_user_ids()
    if len(ids) < 2:
        return "skipped_one_user"

    marker_user_id = ids[0]
    if not claim_sunday_leaderboard(sunday, marker_user_id):
        return "skipped_existing_leaderboard"

    week = week_start(sunday)
    scores = scores_for_week(week)
    a_id, b_id = ids[0], ids[1]
    a_pts = scores.get(a_id, 0)
    b_pts = scores.get(b_id, 0)
    a_name = _display_name(a_id, None)
    b_name = _display_name(b_id, None)

    lines = [
        texts.COUPLE_LEADERBOARD_HEADER,
        texts.COUPLE_LEADERBOARD_SCORE.format(name=a_name, points=a_pts),
        texts.COUPLE_LEADERBOARD_SCORE.format(name=b_name, points=b_pts),
    ]
    if a_pts == b_pts:
        lines.append(texts.COUPLE_LEADERBOARD_TIE)
    elif a_pts > b_pts:
        lines.append(texts.COUPLE_LEADERBOARD_AHEAD.format(name=a_name))
    else:
        lines.append(texts.COUPLE_LEADERBOARD_AHEAD.format(name=b_name))
    lines.append(texts.COUPLE_LEADERBOARD_STAKE)
    body = "\n".join(lines)
    if len(body) > SCHEDULED_MAX_CHARS:
        body = body[:SCHEDULED_MAX_CHARS].rstrip()

    assert settings.couple_chat_id is not None
    try:
        await application.bot.send_message(
            chat_id=int(settings.couple_chat_id),
            text=body,
        )
    except Exception:
        logger.exception(
            "couple leaderboard send failed chat_id=%s sunday=%s",
            settings.couple_chat_id,
            sunday,
        )
        return "skipped_send_failed"

    logger.info("couple leaderboard delivered sunday=%s week=%s", sunday, week)
    return "leaderboard"


# Re-export for tests that patch the answer path.
__all__ = [
    "OpenCoupleChallengeFilter",
    "build_couple_handlers",
    "init_couple_prompt",
    "on_couple_answer",
    "on_here_command",
    "run_couple_poll",
    "generate_question_from_error",
    "wrap_error_row",
]
