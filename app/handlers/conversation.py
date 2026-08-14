"""Text conversation mode (/talk, S26).

Session-backed filter (not a ConversationHandler free-text state). Implicit
recasts mid-chat; explicit corrections only at close-out. Never widens
OpenQuizFilter; never edits correction.py or streaks.py.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ChatAction, ChatType
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app import texts
from app.config import load_settings
from app.handlers.correction import (
    ABSTRACT_ERROR_TYPES,
    error_type_list_text,
    render_correction_message,
)
from app.handlers.quiz import open_quiz_awaits_gap_answer
from app.llm import LLMError, chat
from app.services.books import list_units_for_user
from app.services.chunks import sample_chunks_for_conversation
from app.services.errors import record_errors, top_error_types
from app.services.interests import list_interests
from app.services.sessions import (
    complete_session,
    get_open_conversation_session,
    insert_session,
    local_today,
    update_session_payload,
    utc_now_iso,
)
from app.services.users import User, get_user, is_registered

logger = logging.getLogger(__name__)

HANDLER_NAME = "conversation"
MAX_CLOSE_ERRORS = 3
_MAX_TOPIC_BUTTONS = 8
_TURN_MAX_TOKENS = 300
_CLOSE_MAX_TOKENS = 800

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "conversation.txt"
_CLOSE_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "conversation_close.txt"
)

_prompt_template: str | None = None
_close_prompt_template: str | None = None

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


def init_conversation_prompt() -> None:
    """Load turn + close prompt templates; warm the shared taxonomy cache."""
    global _prompt_template, _close_prompt_template
    _prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")
    _close_prompt_template = _CLOSE_PROMPT_PATH.read_text(encoding="utf-8")
    error_type_list_text()
    logger.info("Loaded conversation prompt templates")


def _settings_timeouts() -> tuple[int, int, int, int]:
    settings = load_settings()
    return (
        settings.conversation_timeout_minutes,
        settings.conversation_awaiting_topic_minutes,
        settings.conversation_max_turns,
        settings.conversation_history_max_messages,
    )


def open_conversation_awaits_text(user_id: int, *, now: datetime | None = None) -> bool:
    """True when a non-stale private conversation session should own free text."""
    instant = now if now is not None else datetime.now(timezone.utc)
    active_m, await_m, _, _ = _settings_timeouts()
    try:
        session = get_open_conversation_session(
            user_id,
            now=instant,
            active_minutes=active_m,
            awaiting_topic_minutes=await_m,
        )
    except Exception:
        logger.exception("open_conversation_awaits_text failed user_id=%s", user_id)
        return False
    return session is not None


class OpenConversationFilter(filters.MessageFilter):
    """Match private text only when an open non-stale conversation exists.

    Fail-open: any uncertainty → False so M2 correction still runs.
    """

    def filter(self, message: Message) -> bool:
        user = message.from_user
        if user is None:
            return False
        chat = message.chat
        if chat is None or chat.type != ChatType.PRIVATE:
            return False
        try:
            return open_conversation_awaits_text(user.id)
        except Exception:
            logger.exception(
                "OpenConversationFilter failed user_id=%s",
                user.id,
            )
            return False


def _end_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    texts.BTN_TALK_END, callback_data="talk:end"
                )
            ]
        ]
    )


def _topic_keyboard(n_topics: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i in range(n_topics):
        row.append(
            InlineKeyboardButton(str(i + 1), callback_data=f"talk:topic:{i}")
        )
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [InlineKeyboardButton(texts.BTN_TALK_OTHER, callback_data="talk:other")]
    )
    return InlineKeyboardMarkup(rows)


def _topic_choices(user_id: int) -> list[str]:
    interests = list_interests(user_id)
    topics = [item.topic for item in interests if item.topic.strip()]
    if not topics:
        topics = list(texts.TALK_DEFAULT_TOPICS)
    return topics[:_MAX_TOPIC_BUTTONS]


def _gap_blocks_talk(user_id: int) -> bool:
    try:
        return open_quiz_awaits_gap_answer(user_id)
    except Exception:
        logger.exception("gap check failed user_id=%s", user_id)
        return False


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


def _chunks_blurb(user_id: int) -> str:
    rows = sample_chunks_for_conversation(user_id, limit=8)
    if not rows:
        return "(none yet)"
    parts: list[str] = []
    for row in rows:
        bit = row.chunk
        if row.full_sentence:
            bit = f"{row.chunk} — {row.full_sentence}"
        parts.append(bit)
    return "; ".join(parts)


def _book_units_blurb(user_id: int) -> str:
    units = list_units_for_user(user_id)[:6]
    if not units:
        return "(none yet)"
    parts = []
    for u in units:
        title = u.get("unit_title") or ""
        parts.append(f"{u.get('book')} unit {u.get('unit_number')} {title}".strip())
    return "; ".join(parts)


def build_conversation_system_prompt(user: User, *, topic: str) -> str:
    if _prompt_template is None:
        init_conversation_prompt()
    assert _prompt_template is not None
    labels = top_error_types(user.telegram_user_id, n=5)
    return _prompt_template.format(
        cefr_level=user.cefr_level,
        native_language=user.native_language,
        topic=topic,
        work_domain=user.work_domain or "general",
        why_statement=user.why_statement or "(not set)",
        recurring_error_labels=", ".join(labels) if labels else "(none yet)",
        chunks_blurb=_chunks_blurb(user.telegram_user_id),
        book_units_blurb=_book_units_blurb(user.telegram_user_id),
    )


def build_conversation_close_prompt(user: User) -> str:
    if _close_prompt_template is None:
        init_conversation_prompt()
    assert _close_prompt_template is not None
    if user.explanation_language_fallback:
        explanation_rule = _FALLBACK_RULE_TRUE.format(
            native_language=user.native_language
        )
    else:
        explanation_rule = _FALLBACK_RULE_FALSE
    labels = top_error_types(user.telegram_user_id, n=5)
    return _close_prompt_template.format(
        cefr_level=user.cefr_level,
        native_language=user.native_language,
        work_domain=user.work_domain or "general",
        error_type_list=error_type_list_text(),
        recurring_error_labels=", ".join(labels) if labels else "(none yet)",
        explanation_language_rule=explanation_rule,
    )


def _trim_history(
    messages: list[dict[str, str]], *, max_messages: int
) -> list[dict[str, str]]:
    if max_messages < 2 or len(messages) <= max_messages:
        return list(messages)
    return list(messages[-max_messages:])


def _new_payload(
    *,
    topic: str | None,
    phase: str,
    now: datetime,
) -> dict[str, Any]:
    return {
        "topic": topic or "",
        "phase": phase,
        "messages": [],
        "turn_count": 0,
        "last_activity": utc_now_iso(now),
        "warned_last_turn": False,
    }


async def on_talk_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """``/talk`` or ``/talk <topic>``. Works while paused; refuses open gap quiz."""
    message = update.message
    user_tg = update.effective_user
    if message is None or user_tg is None:
        return
    user_id = user_tg.id
    if not is_registered(user_id):
        return

    if _gap_blocks_talk(user_id):
        await message.reply_text(texts.TALK_GAP_QUIZ_WAITING)
        return

    now = datetime.now(timezone.utc)
    active_m, await_m, _, _ = _settings_timeouts()
    existing = get_open_conversation_session(
        user_id,
        now=now,
        active_minutes=active_m,
        awaiting_topic_minutes=await_m,
    )
    if existing is not None and existing.payload:
        phase = str(existing.payload.get("phase") or "active")
        topic = str(existing.payload.get("topic") or "this")
        if phase == "awaiting_topic":
            await message.reply_text(
                texts.TALK_AWAITING_TOPIC, reply_markup=_end_keyboard()
            )
        else:
            await message.reply_text(
                texts.TALK_ALREADY_OPEN.format(topic=topic),
                reply_markup=_end_keyboard(),
            )
        return

    args = list(context.args or [])
    if args:
        topic = " ".join(args).strip()
        if not topic:
            await message.reply_text(texts.TALK_TOPIC_EMPTY)
            return
        await _start_active(message, user_id, topic, now=now)
        return

    topics = _topic_choices(user_id)
    lines = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics))
    await message.reply_text(
        texts.TALK_PICK_TOPIC.format(topic_lines=lines),
        reply_markup=_topic_keyboard(len(topics)),
    )


async def _start_active(
    message: Message,
    user_id: int,
    topic: str,
    *,
    now: datetime,
) -> None:
    if _gap_blocks_talk(user_id):
        await message.reply_text(texts.TALK_GAP_QUIZ_WAITING)
        return
    user = get_user(user_id)
    if user is None:
        return
    day = local_today(_user_timezone(user_id), now)
    payload = _new_payload(topic=topic, phase="active", now=now)
    insert_session(
        user_id, "conversation", day, payload=payload, completed=False
    )
    opener = texts.TALK_STARTED.format(topic=topic)
    await message.reply_text(opener, reply_markup=_end_keyboard())
    # Seed history with the opener so the model has context.
    payload["messages"] = [{"role": "assistant", "content": opener}]
    payload["last_activity"] = utc_now_iso(now)
    session = get_open_conversation_session(
        user_id,
        now=now,
        active_minutes=_settings_timeouts()[0],
        awaiting_topic_minutes=_settings_timeouts()[1],
    )
    if session is not None:
        update_session_payload(session.id, payload)


async def on_talk_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    user_id = query.from_user.id
    if not is_registered(user_id):
        await query.answer()
        return

    data = query.data or ""
    await query.answer()

    if data == "talk:end":
        await _close_out_from_callback(query, user_id)
        return

    if _gap_blocks_talk(user_id):
        if query.message is not None:
            await query.message.reply_text(texts.TALK_GAP_QUIZ_WAITING)
        return

    now = datetime.now(timezone.utc)

    if data == "talk:other":
        day = local_today(_user_timezone(user_id), now)
        # Leave any prior incomplete conversation incomplete (Neutral).
        payload = _new_payload(topic=None, phase="awaiting_topic", now=now)
        insert_session(
            user_id, "conversation", day, payload=payload, completed=False
        )
        if query.message is not None:
            await query.message.reply_text(texts.TALK_AWAITING_TOPIC)
        return

    if data.startswith("talk:topic:"):
        try:
            index = int(data.split(":", 2)[2])
        except (IndexError, ValueError):
            if query.message is not None:
                await query.message.reply_text(texts.TALK_STALE_CALLBACK)
            return
        topics = _topic_choices(user_id)
        if index < 0 or index >= len(topics):
            if query.message is not None:
                await query.message.reply_text(texts.TALK_STALE_CALLBACK)
            return
        if query.message is None:
            return
        await _start_active(query.message, user_id, topics[index], now=now)
        return

    if query.message is not None:
        await query.message.reply_text(texts.TALK_STALE_CALLBACK)


async def on_talk_orphan_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    if query.message is not None:
        await query.message.reply_text(texts.TALK_STALE_CALLBACK)


async def on_conversation_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Own private free text while an open non-stale conversation exists."""
    message = update.message
    user_tg = update.effective_user
    if message is None or user_tg is None or not message.text:
        return
    user_id = user_tg.id
    if not is_registered(user_id):
        return

    now = datetime.now(timezone.utc)
    active_m, await_m, max_turns, hist_max = _settings_timeouts()
    session = get_open_conversation_session(
        user_id,
        now=now,
        active_minutes=active_m,
        awaiting_topic_minutes=await_m,
    )
    if session is None or not session.payload:
        # Fail-open: should not happen if filter matched; let nothing crash.
        return

    payload = dict(session.payload)
    phase = str(payload.get("phase") or "active")
    text = message.text.strip()

    if phase == "awaiting_topic":
        if len(text) < 2:
            await message.reply_text(texts.TALK_TOPIC_EMPTY)
            payload["last_activity"] = utc_now_iso(now)
            update_session_payload(session.id, payload)
            return
        payload["topic"] = text
        payload["phase"] = "active"
        payload["messages"] = []
        payload["turn_count"] = 0
        payload["last_activity"] = utc_now_iso(now)
        update_session_payload(session.id, payload)
        opener = texts.TALK_STARTED.format(topic=text)
        await message.reply_text(opener, reply_markup=_end_keyboard())
        payload["messages"] = [{"role": "assistant", "content": opener}]
        update_session_payload(session.id, payload)
        return

    await _handle_active_turn(
        message,
        user_id,
        session.id,
        payload,
        text,
        now=now,
        max_turns=max_turns,
        hist_max=hist_max,
    )


async def _handle_active_turn(
    message: Message,
    user_id: int,
    session_id: int,
    payload: dict[str, Any],
    text: str,
    *,
    now: datetime,
    max_turns: int,
    hist_max: int,
) -> None:
    user = get_user(user_id)
    if user is None:
        return

    topic = str(payload.get("topic") or "this")
    history = list(payload.get("messages") or [])
    turn_count = int(payload.get("turn_count") or 0)

    await message.chat.send_action(ChatAction.TYPING)

    system = build_conversation_system_prompt(user, topic=topic)
    history_for_llm = _trim_history(
        history + [{"role": "user", "content": text}],
        max_messages=hist_max,
    )

    try:
        raw = await asyncio.to_thread(
            chat,
            history_for_llm,
            system=system,
            json_mode=False,
            max_tokens=_TURN_MAX_TOKENS,
        )
    except LLMError:
        logger.warning(
            "conversation turn LLM failed user_id=%s handler=%s",
            user_id,
            HANDLER_NAME,
        )
        payload["last_activity"] = utc_now_iso(now)
        update_session_payload(session_id, payload)
        await message.reply_text(
            texts.TALK_TURN_FAILED, reply_markup=_end_keyboard()
        )
        return

    reply = (raw if isinstance(raw, str) else str(raw or "")).strip()
    if not reply:
        payload["last_activity"] = utc_now_iso(now)
        update_session_payload(session_id, payload)
        await message.reply_text(
            texts.TALK_TURN_FAILED, reply_markup=_end_keyboard()
        )
        return

    next_turn = turn_count + 1
    body = reply
    if next_turn == max_turns - 1:
        body = reply + texts.TALK_LAST_TURN_WARN
        payload["warned_last_turn"] = True

    await message.reply_text(body, reply_markup=_end_keyboard())

    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": reply})
    payload["messages"] = _trim_history(history, max_messages=hist_max)
    payload["turn_count"] = next_turn
    payload["last_activity"] = utc_now_iso(now)
    update_session_payload(session_id, payload)

    # Zero errors mid-conversation — close-out only.
    if next_turn >= max_turns:
        await _close_out(
            message,
            user_id,
            session_id,
            payload,
            user=user,
        )


async def _close_out_from_callback(query: Any, user_id: int) -> None:
    now = datetime.now(timezone.utc)
    active_m, await_m, _, _ = _settings_timeouts()
    session = get_open_conversation_session(
        user_id,
        now=now,
        active_minutes=active_m,
        awaiting_topic_minutes=await_m,
    )
    message = query.message
    if session is None or message is None:
        if message is not None:
            await message.reply_text(texts.TALK_STALE_CALLBACK)
        return
    payload = dict(session.payload or {})
    if str(payload.get("phase") or "") == "awaiting_topic":
        # No real chat — expire the wait so text falls through to M2; do not
        # complete (would falsely mark the day Active).
        payload["last_activity"] = "1970-01-01T00:00:00+00:00"
        update_session_payload(session.id, payload)
        await message.reply_text(texts.TALK_STALE_CALLBACK)
        return
    user = get_user(user_id)
    if user is None:
        return
    await _close_out(message, user_id, session.id, payload, user=user)


async def _close_out(
    message: Message,
    user_id: int,
    session_id: int,
    payload: dict[str, Any],
    *,
    user: User,
) -> None:
    history = list(payload.get("messages") or [])
    if not history:
        complete_session(session_id, None)
        await message.reply_text(texts.TALK_CLOSING)
        return

    system = build_conversation_close_prompt(user)
    transcript_messages = _trim_history(
        history,
        max_messages=_settings_timeouts()[3],
    )

    try:
        result = await asyncio.to_thread(
            chat,
            transcript_messages,
            system=system,
            json_mode=True,
            max_tokens=_CLOSE_MAX_TOKENS,
        )
    except LLMError:
        logger.warning(
            "conversation close LLM failed user_id=%s", user_id
        )
        await message.reply_text(texts.TALK_TURN_FAILED)
        return

    if not isinstance(result, dict):
        await message.reply_text(texts.TALK_TURN_FAILED)
        return

    errors = list(result.get("errors") or [])[:MAX_CLOSE_ERRORS]
    did_well = str(result.get("did_well") or "").strip()
    correction_text = render_correction_message(errors, did_well)
    body = f"{texts.TALK_CLOSING}\n\n{correction_text}"

    try:
        await message.reply_text(body)
    except Exception:
        logger.exception(
            "conversation close send failed user_id=%s — no errors written",
            user_id,
        )
        return

    # Commit-after-send: journal only after the user saw the message.
    if errors:
        record_errors(user_id, "conversation", errors)
    complete_session(session_id, None)
    logger.info(
        "conversation closed user_id=%s session_id=%s errors=%s",
        user_id,
        session_id,
        len(errors),
    )


def build_conversation_handlers() -> tuple[
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    CallbackQueryHandler,
]:
    """Command, text filter, talk: callbacks, orphan stale talk:."""
    text_handler = MessageHandler(
        filters.ChatType.PRIVATE
        & filters.TEXT
        & ~filters.COMMAND
        & OpenConversationFilter(),
        on_conversation_text,
    )
    return (
        CommandHandler("talk", on_talk_command),
        text_handler,
        CallbackQueryHandler(on_talk_callback, pattern=r"^talk:(end|other|topic:\d+)$"),
        CallbackQueryHandler(on_talk_orphan_callback, pattern=r"^talk:"),
    )


def s26_button_labels() -> list[str]:
    return [texts.BTN_TALK_OTHER, texts.BTN_TALK_END]
