"""Tap-only nudge callbacks (S10). No text MessageHandler."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from app import texts
from app.handlers import quiz as quiz_handler
from app.handlers import reading as reading_handler
from app.services.motivation import EARLY_LIMIT
from app.services.sessions import (
    complete_session,
    get_session_by_id,
    update_session_payload,
)
from app.services.streaks import get_streak

logger = logging.getLogger(__name__)


async def on_nudge_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await query.answer()
    data = query.data or ""
    if not data.startswith("nudge:short:"):
        return
    try:
        session_id = int(data.split(":")[2])
    except (IndexError, ValueError):
        return

    user_id = update.effective_user.id
    session = get_session_by_id(user_id, session_id)
    if session is None or session.completed:
        return
    if session.task_type not in ("quiz", "reading"):
        return

    payload = dict(session.payload or {})
    payload["early_limit"] = EARLY_LIMIT

    if session.task_type == "quiz":
        await _apply_quiz_short(context, user_id, session.id, payload, query)
        return
    await _apply_reading_short(
        context, user_id, session.id, payload, query
    )


async def _apply_quiz_short(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    session_id: int,
    payload: dict[str, Any],
    query: Any,
) -> None:
    answered = int(payload.get("answered", 0))
    correct_count = int(payload.get("correct_count", 0))
    total = quiz_handler.quiz_effective_total(payload)

    if answered >= total:
        score = float(correct_count) / float(total) if total else 0.0
        complete_session(session_id, score)
        update_session_payload(session_id, payload)
        chat_id = int(payload.get("chat_id") or user_id)
        message_id = payload.get("message_id")
        optimistic_streak = get_streak(user_id).current_streak + 1
        summary = quiz_handler.format_completion_message(
            correct_count=correct_count,
            total=total,
            streak_days=optimistic_streak,
            improved_labels=list(payload.get("improved_labels") or []),
            struggled_labels=list(payload.get("struggled_labels") or []),
        )
        if message_id is not None:
            await quiz_handler._safe_edit(
                context,
                chat_id=chat_id,
                message_id=int(message_id),
                text=summary,
                reply_markup=None,
            )
        await query.message.reply_text(texts.NUDGE_SHORT_DONE)
        return

    update_session_payload(session_id, payload)
    # Refresh the open quiz body so dots show the shortened total.
    chat_id = payload.get("chat_id")
    message_id = payload.get("message_id")
    questions = payload.get("questions") or []
    index = int(payload.get("index", 0))
    if (
        message_id is not None
        and chat_id is not None
        and 0 <= index < len(questions)
    ):
        body = quiz_handler._question_text(payload)
        await quiz_handler._safe_edit(
            context,
            chat_id=int(chat_id),
            message_id=int(message_id),
            text=body,
            reply_markup=quiz_handler._keyboard_for_question(
                questions[index], payload
            ),
        )
    await query.message.reply_text(texts.NUDGE_SHORT_ACK)


async def _apply_reading_short(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    session_id: int,
    payload: dict[str, Any],
    query: Any,
) -> None:
    reading_id = int(payload.get("reading_id") or 0)
    answers = list(payload.get("answers") or [])
    total = EARLY_LIMIT

    if len(answers) >= total and payload.get("phase") == "questions":
        questions = reading_handler.mcqs_from_dicts(
            list(payload.get("questions") or [])
        )
        graded = questions[: len(answers)]
        correct_count = sum(
            1
            for chosen, mq in zip(answers, graded, strict=False)
            if reading_handler.grade_mcq(chosen, mq.answer_index)
        )
        payload["phase"] = "rating"
        payload["assessed"] = True
        payload["correct_count"] = correct_count
        payload["score"] = float(correct_count) / float(total)
        update_session_payload(session_id, payload)
        score_line = texts.READING_SCORE.format(
            correct=correct_count, total=total
        )
        body = reading_handler.format_rating_body(score_line=score_line)
        await reading_handler._edit_or_resend(
            context,
            user_id=user_id,
            reading_id=reading_id,
            session_id=session_id,
            payload=payload,
            text=body,
            reply_markup=reading_handler.rating_keyboard(),
        )
        await query.message.reply_text(texts.NUDGE_SHORT_ACK)
        return

    update_session_payload(session_id, payload)

    # Not yet in questions — start Q&A with early_limit already set.
    if payload.get("phase") not in ("questions", "rating"):
        await reading_handler._on_start(
            context, user_id, session_id, payload, reading_id
        )
        await query.message.reply_text(texts.NUDGE_SHORT_ACK)
        return

    if payload.get("phase") == "questions":
        questions = reading_handler.mcqs_from_dicts(
            list(payload.get("questions") or [])
        )
        q_index = int(payload.get("q_index", 0))
        if 0 <= q_index < len(questions):
            eff = reading_handler.reading_effective_total(
                payload, len(questions)
            )
            body = reading_handler.format_question_body(
                questions[q_index], q_index=q_index, total=eff
            )
            await reading_handler._edit_or_resend(
                context,
                user_id=user_id,
                reading_id=reading_id,
                session_id=session_id,
                payload=payload,
                text=body,
                reply_markup=reading_handler.option_keyboard(q_index),
            )
    await query.message.reply_text(texts.NUDGE_SHORT_ACK)


def build_nudge_handler() -> CallbackQueryHandler:
    """Callback-only — must not own free text (M2 dispatch)."""
    return CallbackQueryHandler(on_nudge_callback, pattern=r"^nudge:")
