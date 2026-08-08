"""Evening reading delivery (S9a) + comprehension Q&A / rating (S9c).

S9a sends title+body with a Questions button. S9c delivers MCQs via
edit_message_text, grades by index, then collects a 1–5 topic rating.
All answers are taps — no text handler (free text stays on correction).
"""

from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, ContextTypes

from app import texts
from app.handlers.onboarding import layout_buttons
from app.llm import LLMError, chat
from app.services.calibration import deliver_raise_notice, maybe_calibrate
from app.services.interests import adjust_weight_for_rating, select_topic
from app.services.reading import (
    ReadingMcq,
    ReadingValidationError,
    complete_reading,
    get_reading_for_user,
    parse_stored_questions,
    persist_and_send,
    validate_reading_payload,
)
from app.services.sessions import (
    complete_session,
    get_reading_session_by_message,
    has_reading_session_on,
    increment_bot_messages,
    local_today,
    under_message_ceiling,
    update_session_payload,
)
from app.services.users import get_user

logger = logging.getLogger(__name__)

HANDLER_NAME = "reading"
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "reading.txt"
_prompt_template: str | None = None

_MAX_BUTTON_LABEL_CHARS = 20
_TOTAL_QUESTIONS = 5


def init_reading_prompt() -> None:
    """Load the reading system prompt from disk (call once at boot)."""
    global _prompt_template
    _prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")


def _system_prompt(
    *,
    cefr_level: str,
    native_language: str,
    topic: str,
    track: str,
) -> str:
    if _prompt_template is None:
        init_reading_prompt()
    assert _prompt_template is not None
    return _prompt_template.format(
        cefr_level=cefr_level,
        native_language=native_language,
        topic=topic,
        track=track,
    )


def _generate(
    *,
    cefr_level: str,
    native_language: str,
    topic: str,
    track: str,
    chat_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    system = _system_prompt(
        cefr_level=cefr_level,
        native_language=native_language,
        topic=topic,
        track=track,
    )
    call = chat_fn or chat
    result = call(
        [{"role": "user", "content": "Generate today's reading passage."}],
        system=system,
        json_mode=True,
        max_tokens=4000,
    )
    if not isinstance(result, dict):
        raise LLMError("reading response was not a JSON object")
    return result


def _user_timezone(user_id: int) -> str:
    from app.db import connection

    with connection() as conn:
        row = conn.execute(
            """
            SELECT timezone FROM users WHERE telegram_user_id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None or not row["timezone"]:
        return "Europe/Vilnius"
    return str(row["timezone"])


def questions_keyboard() -> InlineKeyboardMarkup:
    label = texts.BTN_READING_QUESTIONS
    assert len(label) <= _MAX_BUTTON_LABEL_CHARS
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data="read:start")]]
    )


def option_keyboard(q_index: int) -> InlineKeyboardMarkup:
    items = [
        (str(i + 1), f"read:a:{q_index}:{i}") for i in range(4)
    ]
    rows = layout_buttons(items, max_per_row=4)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=cb) for label, cb in row]
            for row in rows
        ]
    )


def rating_keyboard() -> InlineKeyboardMarkup:
    items = [(str(i), f"read:r:{i}") for i in range(1, 6)]
    rows = layout_buttons(items, max_per_row=5)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=cb) for label, cb in row]
            for row in rows
        ]
    )


def all_s9c_button_labels() -> list[str]:
    """Labels used by S9c keyboards — for the ≤20-char audit."""
    labels = [texts.BTN_READING_QUESTIONS]
    labels.extend(str(i + 1) for i in range(4))
    labels.extend(str(i) for i in range(1, 6))
    return labels


def grade_mcq(chosen_index: int, answer_index: int) -> bool:
    return chosen_index == answer_index


def score_from_answers(answers: list[int], questions: list[ReadingMcq]) -> float:
    if not questions:
        return 0.0
    correct = sum(
        1
        for chosen, q in zip(answers, questions, strict=False)
        if grade_mcq(chosen, q.answer_index)
    )
    return float(correct) / float(len(questions))


def reading_effective_total(payload: dict[str, Any], question_count: int) -> int:
    """MCQ count the user must finish (honours S10 early_limit)."""
    early = payload.get("early_limit")
    if early is not None:
        return min(int(early), question_count) if question_count else int(early)
    return question_count


def format_question_body(q: ReadingMcq, *, q_index: int, total: int) -> str:
    header = texts.READING_Q_PROGRESS.format(n=q_index + 1, total=total)
    prompt = html.escape(q.q, quote=False)
    opts = "\n".join(
        f"{i}. {html.escape(opt, quote=False)}"
        for i, opt in enumerate(q.options, start=1)
    )
    return f"{header}\n\n{prompt}\n\n{opts}"


def format_feedback(q: ReadingMcq, *, correct: bool) -> str:
    if correct:
        return texts.READING_CORRECT
    why = html.escape(q.why, quote=False)
    return texts.READING_WRONG.format(why=why)


def compose_body(*, feedback: str | None, body: str) -> str:
    if feedback:
        return f"{feedback}\n\n{body}"
    return body


def format_rating_body(*, score_line: str | None) -> str:
    if score_line:
        return f"{score_line}\n\n{texts.READING_RATE_PROMPT}"
    return texts.READING_RATE_PROMPT


def mcqs_from_dicts(items: list[dict[str, Any]]) -> list[ReadingMcq]:
    return [
        ReadingMcq(
            q=str(i["q"]),
            options=[str(o) for o in i["options"]],
            answer_index=int(i["answer_index"]),
            why=str(i["why"]),
        )
        for i in items
    ]


async def _edit_or_resend(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
    reading_id: int,
    session_id: int,
    payload: dict[str, Any],
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> dict[str, Any]:
    """Edit the session message; on real BadRequest, send a new one and update payload."""
    chat_id = int(payload["chat_id"])
    message_id = int(payload["message_id"])
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
        return payload
    except BadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return payload
        logger.warning(
            "reading edit failed user_id=%s reading_id=%s — resending: %s",
            user_id,
            reading_id,
            exc,
        )
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
        payload = dict(payload)
        payload["chat_id"] = msg.chat_id
        payload["message_id"] = msg.message_id
        update_session_payload(session_id, payload)
        return payload


async def deliver_evening(
    app: Any,
    user_id: int,
    *,
    now: datetime,
    chat_fn: Callable[..., Any] | None = None,
) -> str:
    """Deliver one reading for ``user_id``. Returns action taken."""
    bot = app.bot
    tz = _user_timezone(user_id)
    day = local_today(tz, now)

    if has_reading_session_on(user_id, day):
        return "skipped_existing"

    if not under_message_ceiling(user_id, day):
        logger.warning(
            "reading skip user_id=%s reason=ceiling_reached day=%s",
            user_id,
            day,
        )
        return "skipped_ceiling"

    user = get_user(user_id)
    if user is None:
        logger.warning(
            "reading skip user_id=%s reason=user_not_found",
            user_id,
        )
        return "skipped_no_user"

    topic_row = select_topic(user_id, user.track_weights, day)
    if topic_row is None:
        logger.warning(
            "reading skip user_id=%s reason=no_interests",
            user_id,
        )
        return "skipped_no_interests"

    raw: dict[str, Any] | None = None
    payload = None
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            # Off the event loop — sync chat() must not block JobQueue ticks.
            raw = await asyncio.to_thread(
                _generate,
                cefr_level=user.cefr_level,
                native_language=user.native_language,
                topic=topic_row.topic,
                track=topic_row.track,
                chat_fn=chat_fn,
            )
            payload = validate_reading_payload(raw)
            break
        except LLMError as exc:
            last_err = exc
            logger.warning(
                "reading LLM failure user_id=%s attempt=%s: %s",
                user_id,
                attempt + 1,
                exc,
            )
        except ReadingValidationError as exc:
            last_err = exc
            logger.warning(
                "reading validation failure user_id=%s attempt=%s: %s",
                user_id,
                attempt + 1,
                exc,
            )
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            logger.warning(
                "reading generation failure user_id=%s attempt=%s: %s",
                user_id,
                attempt + 1,
                exc,
            )

    if payload is None:
        reason = "llm_failure" if isinstance(last_err, LLMError) else "validation_failure"
        if last_err is not None and not isinstance(
            last_err, (LLMError, ReadingValidationError)
        ):
            reason = "generation_failure"
        logger.warning(
            "reading skip user_id=%s reason=%s after_retry detail=%s",
            user_id,
            reason,
            last_err,
        )
        return f"skipped_{reason}"

    message_text = texts.READING_DELIVERY.format(
        title=payload.title,
        body=payload.body,
    )

    async def _send() -> tuple[int, int]:
        msg = await bot.send_message(
            chat_id=user_id,
            text=message_text,
            reply_markup=questions_keyboard(),
        )
        return int(msg.chat_id), int(msg.message_id)

    try:
        await persist_and_send(
            user_id=user_id,
            local_date=day,
            topic=topic_row.topic,
            track=topic_row.track,
            cefr_level=user.cefr_level,
            payload=payload,
            send=_send,
        )
    except Exception:
        logger.exception(
            "reading send/persist failed user_id=%s — rolled back",
            user_id,
        )
        return "skipped_send_failed"

    increment_bot_messages(user_id, day)
    return "reading"


def _resolve_from_callback(
    update: Update,
) -> tuple[int, int, int, Any] | None:
    """Return (user_id, chat_id, message_id, session) or None."""
    query = update.callback_query
    if query is None or update.effective_user is None:
        return None
    msg = query.message
    if msg is None:
        return None
    user_id = update.effective_user.id
    chat_id = msg.chat_id
    message_id = msg.message_id
    session = get_reading_session_by_message(user_id, chat_id, message_id)
    if session is None or not session.payload:
        return None
    return user_id, chat_id, message_id, session


async def on_reading_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    resolved = _resolve_from_callback(update)
    if resolved is None:
        return
    user_id, _chat_id, _message_id, session = resolved
    payload = dict(session.payload or {})
    reading_id = int(payload.get("reading_id") or 0)
    if reading_id <= 0:
        return

    data = query.data
    if data == "read:start":
        await _on_start(context, user_id, session.id, payload, reading_id)
        return

    if data.startswith("read:a:"):
        parts = data.split(":")
        if len(parts) != 4:
            return
        try:
            q_index = int(parts[2])
            opt = int(parts[3])
        except ValueError:
            return
        await _on_answer(
            context,
            user_id,
            session.id,
            payload,
            reading_id,
            q_index=q_index,
            opt=opt,
        )
        return

    if data.startswith("read:r:"):
        parts = data.split(":")
        if len(parts) != 3:
            return
        try:
            rating = int(parts[2])
        except ValueError:
            return
        if rating < 1 or rating > 5:
            return
        await _on_rating(
            context,
            user_id,
            session.id,
            payload,
            reading_id,
            rating=rating,
        )


async def _on_start(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    session_id: int,
    payload: dict[str, Any],
    reading_id: int,
) -> None:
    # Already mid-flow — ignore re-taps of Questions.
    if payload.get("phase") in ("questions", "rating"):
        return

    reading = get_reading_for_user(user_id, reading_id)
    if reading is None or reading["completed"]:
        return

    mcqs = parse_stored_questions(reading.get("questions"))
    if mcqs is None:
        logger.warning(
            "reading questions not MCQ user_id=%s reading_id=%s — skip to rating",
            user_id,
            reading_id,
        )
        payload["phase"] = "rating"
        payload["assessed"] = False
        payload.pop("q_index", None)
        payload.pop("answers", None)
        payload.pop("questions", None)
        update_session_payload(session_id, payload)
        body = format_rating_body(score_line=None)
        await _edit_or_resend(
            context,
            user_id=user_id,
            reading_id=reading_id,
            session_id=session_id,
            payload=payload,
            text=body,
            reply_markup=rating_keyboard(),
        )
        return

    payload["phase"] = "questions"
    payload["assessed"] = True
    payload["q_index"] = 0
    payload["answers"] = []
    payload["questions"] = [
        {
            "q": q.q,
            "options": q.options,
            "answer_index": q.answer_index,
            "why": q.why,
        }
        for q in mcqs
    ]
    update_session_payload(session_id, payload)
    total = reading_effective_total(payload, len(mcqs))
    body = format_question_body(mcqs[0], q_index=0, total=total)
    await _edit_or_resend(
        context,
        user_id=user_id,
        reading_id=reading_id,
        session_id=session_id,
        payload=payload,
        text=body,
        reply_markup=option_keyboard(0),
    )


async def _on_answer(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    session_id: int,
    payload: dict[str, Any],
    reading_id: int,
    *,
    q_index: int,
    opt: int,
) -> None:
    if payload.get("phase") != "questions":
        return
    if int(payload.get("q_index", -1)) != q_index:
        return  # stale / double-tap
    if opt < 0 or opt > 3:
        return

    questions = mcqs_from_dicts(list(payload.get("questions") or []))
    if q_index < 0 or q_index >= len(questions):
        return
    q = questions[q_index]
    correct = grade_mcq(opt, q.answer_index)
    answers = list(payload.get("answers") or [])
    answers.append(opt)
    payload["answers"] = answers
    feedback = format_feedback(q, correct=correct)

    total = reading_effective_total(payload, len(questions))
    answered = len(answers)
    early = payload.get("early_limit")
    done = (
        answered >= total
        if early is not None
        else q_index + 1 >= len(questions)
    )

    if done:
        # Score over the attempted set only (early_limit=2 → / 2.0).
        graded = questions[:answered]
        correct_count = sum(
            1
            for chosen, mq in zip(answers, graded, strict=True)
            if grade_mcq(chosen, mq.answer_index)
        )
        score_line = texts.READING_SCORE.format(
            correct=correct_count,
            total=total,
        )
        payload["phase"] = "rating"
        payload["assessed"] = True
        payload["correct_count"] = correct_count
        payload["score"] = float(correct_count) / float(total) if total else 0.0
        update_session_payload(session_id, payload)
        body = compose_body(
            feedback=feedback,
            body=format_rating_body(score_line=score_line),
        )
        await _edit_or_resend(
            context,
            user_id=user_id,
            reading_id=reading_id,
            session_id=session_id,
            payload=payload,
            text=body,
            reply_markup=rating_keyboard(),
        )
        return

    next_index = q_index + 1
    payload["q_index"] = next_index
    update_session_payload(session_id, payload)
    next_body = format_question_body(
        questions[next_index],
        q_index=next_index,
        total=total,
    )
    body = compose_body(feedback=feedback, body=next_body)
    await _edit_or_resend(
        context,
        user_id=user_id,
        reading_id=reading_id,
        session_id=session_id,
        payload=payload,
        text=body,
        reply_markup=option_keyboard(next_index),
    )


async def _on_rating(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    session_id: int,
    payload: dict[str, Any],
    reading_id: int,
    *,
    rating: int,
) -> None:
    if payload.get("phase") != "rating":
        return

    reading = get_reading_for_user(user_id, reading_id)
    if reading is None or reading["completed"]:
        return

    assessed = bool(payload.get("assessed"))
    score: float | None
    if assessed and "score" in payload:
        score = float(payload["score"])
    elif assessed and payload.get("answers") and payload.get("questions"):
        questions = mcqs_from_dicts(list(payload["questions"]))
        score = score_from_answers(list(payload["answers"]), questions)
    else:
        score = None  # skip path — not assessed

    complete_reading(user_id, reading_id, rating=rating, score=score)
    complete_session(session_id, score)
    topic = reading.get("topic") or ""
    if topic:
        adjust_weight_for_rating(user_id, topic, rating)

    payload["phase"] = "done"
    update_session_payload(session_id, payload)

    close = texts.READING_CLOSE
    await _edit_or_resend(
        context,
        user_id=user_id,
        reading_id=reading_id,
        session_id=session_id,
        payload=payload,
        text=close,
        reply_markup=None,
    )

    # M14: only assessed readings vote on level (NULL score = skip/legacy).
    if score is not None:
        instant = datetime.now(timezone.utc)
        outcome = maybe_calibrate(user_id, now=instant)
        if outcome.raise_notice:
            day = local_today(_user_timezone(user_id), instant)
            await deliver_raise_notice(
                context.bot,
                user_id,
                day=day,
                notice=outcome.raise_notice,
            )


def build_reading_handler() -> CallbackQueryHandler:
    """Callback-only handler — register near quiz callbacks; no text filter."""
    return CallbackQueryHandler(on_reading_callback, pattern=r"^read:")
