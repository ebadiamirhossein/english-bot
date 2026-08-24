"""Text conversation mode (/talk, S26/S26b).

Session-backed filter (not a ConversationHandler free-text state). Implicit
recasts mid-chat; explicit corrections only at close-out. Never widens
OpenQuizFilter; never edits correction.py or streaks.py.

Phase ``picking_topic`` stores offered topics when the picker is shown; it is
intentionally NOT matched by OpenConversationFilter (free text → M2).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReactionTypeEmoji,
    Update,
)
from telegram.constants import ChatAction, ChatType, ReactionEmoji
from telegram.error import BadRequest
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from apps.bot import texts
from core import PROMPTS_DIR
from core.prompt_rules import ENGLISH_ONLY_RULE, SINGLE_LANGUAGE_RULE
from core.config import load_settings
from core.db import connection
from apps.bot.handlers.correction import (
    ABSTRACT_ERROR_TYPES,
    error_type_list_text,
    render_correction_message,
)
from apps.bot.handlers.quiz import open_quiz_awaits_gap_answer
from core.llm import LLMError, chat
from core.services.books import list_units_for_user
from core.services.chunks import Chunk, sample_chunks_for_conversation
from core.services.errors import record_errors, top_error_types
from core.services.interests import list_interests
from core.services.sessions import (
    SessionRow,
    complete_session,
    get_open_conversation_session,
    insert_session,
    local_today,
    update_session_payload,
    utc_now_iso,
)
from core.services.users import User, get_user, is_registered
from apps.bot import identity as bot_identity
from core.services import identity

logger = logging.getLogger(__name__)

HANDLER_NAME = "conversation"
MAX_CLOSE_ERRORS = 3
_MAX_OFFERED_TOPICS = 3
_TURN_MAX_TOKENS = 500
_CLOSE_MAX_TOKENS = 2000
_EXC_MSG_LOG_LIMIT = 120
_TOPIC_LABEL_MAX = 80
_REACTION_EVERY_N = 3  # roughly one in three successful turns
_REACTION_EMOJIS = (
    ReactionEmoji.THUMBS_UP,
    ReactionEmoji.FIRE,
    ReactionEmoji.PARTY_POPPER,
    ReactionEmoji.CLAPPING_HANDS,
    ReactionEmoji.HIGH_VOLTAGE_SIGN,
    ReactionEmoji.RED_HEART,
    ReactionEmoji.HUNDRED_POINTS_SYMBOL,
)

# Trailing user turn required by Anthropic (no assistant-prefill / must end
# on user). Live session history always ends on the last bot reply.
_CLOSE_REVIEW_CUE = (
    "The conversation above is finished. Reply with the JSON object "
    "specified in your instructions — errors (max 3) and did_well."
)
_CLOSE_REVIEW_CUE_TWO = (
    "The conversation above is finished. Reply with the JSON object "
    "specified in your instructions — at most 2 errors and did_well. "
    "Prefer fewer."
)

_PROMPT_PATH = PROMPTS_DIR / "conversation.txt"
_CLOSE_PROMPT_PATH = (
    PROMPTS_DIR / "conversation_close.txt"
)

_prompt_template: str | None = None
_close_prompt_template: str | None = None

# S26c wrote the single-language sentences inline here; W3 moved them to
# core.prompt_rules so the other four explanation paths get the same text
# (known issue #45). The rendered string is unchanged.
_FALLBACK_RULE_TRUE = (
    "BUT when the error type is abstract grammar "
    f"({', '.join(ABSTRACT_ERROR_TYPES)}) AND the user's "
    "explanation_language_fallback is enabled, write that explanation in "
    "their native language ({native_language}) instead. Concrete error types "
    "stay English regardless. " + SINGLE_LANGUAGE_RULE
)

_FALLBACK_RULE_FALSE = (
    "Write every explanation in English, including abstract grammar types. "
    + ENGLISH_ONLY_RULE
)


def _safe_exc_msg(exc: BaseException) -> str:
    """Exception text for logs — no learner message/topic/chunk bodies."""
    msg = str(exc)
    # json_mode LLMError may embed ``raw=...`` with model output that quotes
    # the learner; drop that span before logging.
    if "raw=" in msg:
        msg = msg.split("raw=", 1)[0].rstrip(" ;,")
    msg = msg.replace("\n", " ").strip()
    if len(msg) > _EXC_MSG_LOG_LIMIT:
        return msg[:_EXC_MSG_LOG_LIMIT] + "..."
    return msg


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
    ``picking_topic`` is never matched (picker on screen ≠ awaiting Other).
    """

    def filter(self, message: Message) -> bool:
        user = message.from_user
        if user is None:
            return False
        chat = message.chat
        if chat is None or chat.type != ChatType.PRIVATE:
            return False
        try:
            # A PTB filter gets no `context`, so it cannot read the gate's
            # stash and resolves through the core resolver directly. Still one
            # translation module, which is what the rule is about.
            resolved = identity.user_id_for_telegram(user.id)
            if resolved is None:
                return False
            return open_conversation_awaits_text(resolved)
        except Exception:
            logger.exception(
                "OpenConversationFilter failed telegram_user_id=%s",
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


def chunk_topic_label(chunk: Chunk) -> str:
    """English-only topic label from chunk / full_sentence — never meaning."""
    primary = (chunk.chunk or "").strip()
    sentence = (chunk.full_sentence or "").strip()
    if primary:
        label = primary
    elif sentence:
        label = sentence
    else:
        return ""
    # Prefer a short sentence fragment when the chunk alone is cryptic.
    if sentence and len(primary) < 4 and len(sentence) <= _TOPIC_LABEL_MAX:
        label = sentence
    label = " ".join(label.split())
    if len(label) > _TOPIC_LABEL_MAX:
        label = label[: _TOPIC_LABEL_MAX - 1].rstrip() + "…"
    return label


def book_topic_label(unit: dict[str, Any]) -> str:
    book = str(unit.get("book") or "book").strip()
    num = unit.get("unit_number")
    title = str(unit.get("unit_title") or "").strip()
    if title:
        label = f"{book} unit {num}: {title}"
    else:
        label = f"{book} unit {num}"
    label = " ".join(label.split())
    if len(label) > _TOPIC_LABEL_MAX:
        label = label[: _TOPIC_LABEL_MAX - 1].rstrip() + "…"
    return label


def _dedupe_preserve(topics: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in topics:
        key = t.casefold()
        if not t or key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def build_topic_pool(user_id: int) -> list[str]:
    """Interests + English chunk labels + book units. Defaults only if all empty."""
    interests = [item.topic.strip() for item in list_interests(user_id) if item.topic.strip()]
    chunk_labels = [
        chunk_topic_label(c) for c in sample_chunks_for_conversation(user_id, limit=12)
    ]
    chunk_labels = [t for t in chunk_labels if t]
    book_labels = [
        book_topic_label(u) for u in list_units_for_user(user_id)[:8]
    ]
    book_labels = [t for t in book_labels if t]
    pool = _dedupe_preserve(interests + chunk_labels + book_labels)
    if not pool:
        return list(texts.TALK_DEFAULT_TOPICS)
    return pool


def rotate_topics(
    pool: list[str],
    last_offered: list[str] | None,
    *,
    limit: int = _MAX_OFFERED_TOPICS,
) -> list[str]:
    """Prefer topics not in the previous offer set; fall back to full pool."""
    if not pool:
        return list(texts.TALK_DEFAULT_TOPICS)[:limit]
    last_keys = {t.casefold() for t in (last_offered or [])}
    preferred = [t for t in pool if t.casefold() not in last_keys]
    chosen = preferred if preferred else list(pool)
    # If preferred is non-empty but shorter than limit, top up from pool.
    if preferred and len(preferred) < limit:
        for t in pool:
            if t.casefold() not in {c.casefold() for c in preferred}:
                preferred.append(t)
            if len(preferred) >= limit:
                break
        chosen = preferred
    return chosen[:limit]


def _topic_choices(
    user_id: int, *, last_offered: list[str] | None = None
) -> list[str]:
    return rotate_topics(build_topic_pool(user_id), last_offered)


def get_picking_conversation_session(user_id: int) -> SessionRow | None:
    """Newest incomplete conversation in ``picking_topic`` (not filter-owned)."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, date, task_type, completed, score, payload
              FROM sessions
             WHERE user_id = %s
               AND task_type = 'conversation'
               AND completed = FALSE
             ORDER BY id DESC
             LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    payload = row["payload"]
    if payload is not None and not isinstance(payload, dict):
        payload = dict(payload)
    payload = payload or {}
    if str(payload.get("phase") or "") != "picking_topic":
        return None
    return SessionRow(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        date=row["date"],
        task_type=str(row["task_type"]),
        completed=bool(row["completed"]),
        score=float(row["score"]) if row["score"] is not None else None,
        payload=payload,
    )


def get_last_offered_topics(user_id: int) -> list[str]:
    """Most recent conversation session's offered_topics (any phase/completed)."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT payload
              FROM sessions
             WHERE user_id = %s
               AND task_type = 'conversation'
             ORDER BY id DESC
             LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return []
    payload = row["payload"]
    if payload is not None and not isinstance(payload, dict):
        payload = dict(payload)
    payload = payload or {}
    raw = payload.get("offered_topics") or []
    if not isinstance(raw, list):
        return []
    return [str(t) for t in raw if str(t).strip()]


def _gap_blocks_talk(user_id: int) -> bool:
    try:
        return open_quiz_awaits_gap_answer(user_id)
    except Exception:
        logger.exception("gap check failed user_id=%s", user_id)
        return False


def _user_timezone(user_id: int) -> str:
    with connection() as conn:
        row = conn.execute(
            "SELECT timezone FROM users WHERE id = %s",
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


def build_conversation_turn_messages(
    history: list[dict[str, str]],
    user_text: str,
    *,
    max_messages: int,
) -> list[dict[str, str]]:
    """Messages for a mid-chat turn — always ends on the new user text."""
    return _trim_history(
        list(history) + [{"role": "user", "content": user_text}],
        max_messages=max_messages,
    )


def build_conversation_close_messages(
    history: list[dict[str, str]],
    *,
    max_messages: int,
    review_cue: str = _CLOSE_REVIEW_CUE,
) -> list[dict[str, str]]:
    """Transcript plus trailing user cue (Anthropic requires final = user).

    Live session history is seeded with the opener and then alternates; after
    any successful turn it ends on assistant. Passing that transcript as-is
    raises before the API responds (S26a).
    """
    trimmed = _trim_history(list(history), max_messages=max_messages)
    if max_messages >= 2 and len(trimmed) >= max_messages:
        trimmed = trimmed[-(max_messages - 1) :]
    return trimmed + [{"role": "user", "content": review_cue}]


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
    offered_topics: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "topic": topic or "",
        "phase": phase,
        "messages": [],
        "turn_count": 0,
        "last_activity": utc_now_iso(now),
        "warned_last_turn": False,
        "offered_topics": list(offered_topics or []),
        "closing": False,
        "end_keyboard_message_id": None,
    }


async def _clear_end_keyboard(
    message: Message, payload: dict[str, Any]
) -> None:
    prev = payload.get("end_keyboard_message_id")
    if prev is None:
        return
    try:
        mid = int(prev)
    except (TypeError, ValueError):
        return
    bot = message.get_bot()
    chat_id = message.chat_id
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=mid, reply_markup=None
        )
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            logger.debug(
                "clear end keyboard failed chat_id=%s message_id=%s: %s",
                chat_id,
                mid,
                exc,
            )
    except Exception:
        logger.debug(
            "clear end keyboard failed chat_id=%s message_id=%s",
            chat_id,
            mid,
            exc_info=True,
        )


async def _reply_with_end_keyboard(
    message: Message,
    text: str,
    payload: dict[str, Any],
) -> None:
    await _clear_end_keyboard(message, payload)
    sent = await message.reply_text(text, reply_markup=_end_keyboard())
    payload["end_keyboard_message_id"] = getattr(sent, "message_id", None)


async def on_talk_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """``/talk`` or ``/talk <topic>``. Works while paused; refuses open gap quiz."""
    message = update.message
    user_tg = update.effective_user
    if message is None or user_tg is None:
        return
    user_id = bot_identity.bot_user_id(update, context)
    if user_id is None:
        return
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
        payload = dict(existing.payload)
        if phase == "awaiting_topic":
            await _reply_with_end_keyboard(
                message, texts.TALK_AWAITING_TOPIC, payload
            )
        else:
            await _reply_with_end_keyboard(
                message,
                texts.TALK_ALREADY_OPEN.format(topic=topic),
                payload,
            )
        update_session_payload(existing.id, payload)
        return

    args = list(context.args or [])
    if args:
        topic = " ".join(args).strip()
        if not topic:
            await message.reply_text(texts.TALK_TOPIC_EMPTY)
            return
        await _start_active(message, user_id, topic, now=now)
        return

    await _show_topic_picker(message, user_id, now=now)


async def _show_topic_picker(
    message: Message, user_id: int, *, now: datetime
) -> None:
    """Persist offered topics at show-time (``picking_topic`` — not filter-owned)."""
    last = get_last_offered_topics(user_id)
    topics = _topic_choices(user_id, last_offered=last)
    day = local_today(_user_timezone(user_id), now)
    picking = get_picking_conversation_session(user_id)
    payload = _new_payload(
        topic=None, phase="picking_topic", now=now, offered_topics=topics
    )
    if picking is not None:
        update_session_payload(picking.id, payload)
    else:
        insert_session(
            user_id, "conversation", day, payload=payload, completed=False
        )
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
    offered_topics: list[str] | None = None,
    existing_session_id: int | None = None,
) -> None:
    if _gap_blocks_talk(user_id):
        await message.reply_text(texts.TALK_GAP_QUIZ_WAITING)
        return
    user = get_user(user_id)
    if user is None:
        return
    day = local_today(_user_timezone(user_id), now)
    payload = _new_payload(
        topic=topic,
        phase="active",
        now=now,
        offered_topics=offered_topics,
    )
    if existing_session_id is not None:
        update_session_payload(existing_session_id, payload)
        session_id = existing_session_id
    else:
        session_id = insert_session(
            user_id, "conversation", day, payload=payload, completed=False
        )
    opener = texts.TALK_STARTED.format(topic=topic)
    await _reply_with_end_keyboard(message, opener, payload)
    payload["messages"] = [{"role": "assistant", "content": opener}]
    payload["last_activity"] = utc_now_iso(now)
    update_session_payload(session_id, payload)


async def on_talk_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    user_id = bot_identity.bot_user_id(update, context)
    if user_id is None:
        await query.answer()
        return
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
        picking = get_picking_conversation_session(user_id)
        day = local_today(_user_timezone(user_id), now)
        offered = list((picking.payload or {}).get("offered_topics") or []) if picking else []
        payload = _new_payload(
            topic=None,
            phase="awaiting_topic",
            now=now,
            offered_topics=[str(t) for t in offered],
        )
        if picking is not None:
            update_session_payload(picking.id, payload)
        else:
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
        picking = get_picking_conversation_session(user_id)
        topics: list[str] = []
        session_id: int | None = None
        if picking is not None and picking.payload:
            raw = picking.payload.get("offered_topics") or []
            topics = [str(t) for t in raw if str(t).strip()]
            session_id = picking.id
        if not topics:
            topics = _topic_choices(user_id)
        if index < 0 or index >= len(topics):
            if query.message is not None:
                await query.message.reply_text(texts.TALK_STALE_CALLBACK)
            return
        if query.message is None:
            return
        await _start_active(
            query.message,
            user_id,
            topics[index],
            now=now,
            offered_topics=topics,
            existing_session_id=session_id,
        )
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
    user_id = bot_identity.bot_user_id(update, context)
    if user_id is None:
        return
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
        offered = list(payload.get("offered_topics") or [])
        payload["topic"] = text
        payload["phase"] = "active"
        payload["messages"] = []
        payload["turn_count"] = 0
        payload["last_activity"] = utc_now_iso(now)
        payload["offered_topics"] = offered
        update_session_payload(session.id, payload)
        opener = texts.TALK_STARTED.format(topic=text)
        await _reply_with_end_keyboard(message, opener, payload)
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


async def _maybe_react_to_user_message(
    message: Message, *, turn_count: int
) -> None:
    """Occasional emoji reaction on the learner's message. Never fatal."""
    # After this turn succeeds, turn_count becomes turn_count+1; react on
    # turns 1, 4, 7… (~1 in 3) using the count before increment.
    next_turn = turn_count + 1
    if next_turn % _REACTION_EVERY_N != 1:
        return
    emoji = _REACTION_EMOJIS[(next_turn // _REACTION_EVERY_N) % len(_REACTION_EMOJIS)]
    try:
        bot = message.get_bot()
        await bot.set_message_reaction(
            chat_id=message.chat_id,
            message_id=message.message_id,
            reaction=[ReactionTypeEmoji(emoji)],
        )
    except Exception:
        logger.debug(
            "set_message_reaction failed chat_id=%s message_id=%s",
            getattr(message, "chat_id", None),
            getattr(message, "message_id", None),
            exc_info=True,
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
    history_for_llm = build_conversation_turn_messages(
        history, text, max_messages=hist_max
    )

    try:
        raw = await asyncio.to_thread(
            chat,
            history_for_llm,
            system=system,
            json_mode=False,
            max_tokens=_TURN_MAX_TOKENS,
            reject_truncation=True,
        )
    except LLMError as exc:
        logger.warning(
            "conversation turn LLM failed user_id=%s handler=%s "
            "exc_type=%s exc_msg=%s",
            user_id,
            HANDLER_NAME,
            type(exc).__name__,
            _safe_exc_msg(exc),
        )
        payload["last_activity"] = utc_now_iso(now)
        update_session_payload(session_id, payload)
        await _reply_with_end_keyboard(message, texts.TALK_TURN_FAILED, payload)
        update_session_payload(session_id, payload)
        return

    reply = (raw if isinstance(raw, str) else str(raw or "")).strip()
    if not reply:
        payload["last_activity"] = utc_now_iso(now)
        update_session_payload(session_id, payload)
        await _reply_with_end_keyboard(message, texts.TALK_TURN_FAILED, payload)
        update_session_payload(session_id, payload)
        return

    # Reaction only on a successful turn — never replaces the reply / close-out.
    await _maybe_react_to_user_message(message, turn_count=turn_count)

    next_turn = turn_count + 1
    body = reply
    if next_turn == max_turns - 1:
        body = reply + texts.TALK_LAST_TURN_WARN
        payload["warned_last_turn"] = True

    await _reply_with_end_keyboard(message, body, payload)

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
    if payload.get("closing"):
        # Second tap during close-out — answer already sent; no-op.
        return
    user = get_user(user_id)
    if user is None:
        return

    # Immediate feedback before any LLM work.
    try:
        await message.edit_text(
            texts.TALK_WRAPPING_UP, reply_markup=None
        )
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            try:
                await message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
    except Exception:
        try:
            await message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    payload["closing"] = True
    payload["end_keyboard_message_id"] = None
    update_session_payload(session.id, payload)

    await _close_out(message, user_id, session.id, payload, user=user)


def _generate_close_result(
    user: User,
    history: list[dict[str, str]],
    *,
    hist_max: int,
) -> dict[str, Any]:
    """Close-out LLM with one truncation retry at max two corrections."""
    system = build_conversation_close_prompt(user)

    def _call(cue: str) -> dict[str, Any]:
        transcript_messages = build_conversation_close_messages(
            history, max_messages=hist_max, review_cue=cue
        )
        result = chat(
            transcript_messages,
            system=system,
            json_mode=True,
            max_tokens=_CLOSE_MAX_TOKENS,
            reject_truncation=True,
        )
        if not isinstance(result, dict):
            raise LLMError("close response was not a JSON object")
        return result

    try:
        return _call(_CLOSE_REVIEW_CUE)
    except LLMError as first_exc:
        logger.warning(
            "conversation close first attempt failed exc_type=%s exc_msg=%s "
            "— retrying at most two corrections",
            type(first_exc).__name__,
            _safe_exc_msg(first_exc),
        )
        return _call(_CLOSE_REVIEW_CUE_TWO)


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

    hist_max = _settings_timeouts()[3]
    try:
        await message.chat.send_action(ChatAction.TYPING)
    except Exception:
        pass

    try:
        result = await asyncio.to_thread(
            _generate_close_result, user, history, hist_max=hist_max
        )
        errors = list(result.get("errors") or [])[:MAX_CLOSE_ERRORS]
        did_well = str(result.get("did_well") or "").strip()
        correction_text = render_correction_message(errors, did_well)
        body = f"{texts.TALK_CLOSING}\n\n{correction_text}"
    except Exception as exc:
        # Generation failure: release the user. Losing ≤3 corrections is
        # better than trapping them until the 30-minute timeout (S26a).
        logger.warning(
            "conversation close LLM failed user_id=%s exc_type=%s exc_msg=%s",
            user_id,
            type(exc).__name__,
            _safe_exc_msg(exc),
        )
        await message.reply_text(texts.TALK_CLOSE_FAILED)
        complete_session(session_id, None)
        return

    try:
        await message.reply_text(body)
    except Exception as exc:
        # Send failure: content exists — keep session open for retry.
        logger.warning(
            "conversation close send failed user_id=%s exc_type=%s "
            "exc_msg=%s — no errors written",
            user_id,
            type(exc).__name__,
            _safe_exc_msg(exc),
        )
        # Allow another End tap after a send failure.
        payload["closing"] = False
        update_session_payload(session_id, payload)
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
