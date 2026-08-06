"""Daily quiz delivery and in-place answering (M1 / S3 + S3a)."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import string
from datetime import datetime
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app import texts
from app.db import connection
from app.handlers.onboarding import layout_buttons
from app.llm import LLMError, chat
from app.services.errors import Error, due_errors, mark_result
from app.services.sessions import (
    complete_session,
    get_open_quiz_session,
    has_session_on,
    increment_bot_messages,
    insert_session,
    local_today,
    under_message_ceiling,
    update_session_payload,
)
from app.services.streaks import (
    consume_freeze_notice,
    get_streak,
    is_in_rescue,
)
from app.services.users import get_user

logger = logging.getLogger(__name__)

HANDLER_NAME = "quiz"
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "quiz.txt"
_prompt_template: str | None = None
_error_labels: dict[str, str] = {}

_APOSTROPHES = ("'", "\u2019", "\u2018", "`", "´")
_VALID_FORMATS = frozenset({"gap", "choice", "spot", "order"})
_TRACKS = ("work", "life", "curiosity")


def init_quiz_prompt() -> None:
    global _prompt_template, _error_labels
    _prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")
    with connection() as conn:
        rows = conn.execute(
            "SELECT code, label FROM error_types"
        ).fetchall()
    _error_labels = {row["code"]: row["label"] for row in rows}
    logger.info(
        "Loaded quiz prompt template and %s error-type labels",
        len(_error_labels),
    )


def error_type_label(code: str) -> str:
    """Human label for an error_types.code. Never return the raw code."""
    if not _error_labels:
        init_quiz_prompt()
    return _error_labels.get(code, code.replace("_", " ").title())


def distribute_tracks(
    n: int,
    weights: dict[str, int] | None = None,
) -> list[str]:
    """Proportionally assign tracks, then interleave (not group).

    Largest-remainder rounding. Default weights 40/40/20.
    """
    if n <= 0:
        return []
    w = weights or {"work": 40, "life": 40, "curiosity": 20}
    total_w = sum(max(0, int(w.get(t, 0))) for t in _TRACKS) or 1
    raw = [n * max(0, int(w.get(t, 0))) / total_w for t in _TRACKS]
    counts = [int(x) for x in raw]
    rem = n - sum(counts)
    by_frac = sorted(
        range(len(_TRACKS)),
        key=lambda i: (raw[i] - counts[i], -i),
        reverse=True,
    )
    for i in by_frac[:rem]:
        counts[i] += 1

    pools = {t: counts[i] for i, t in enumerate(_TRACKS)}
    result: list[str] = []
    while len(result) < n:
        progressed = False
        for t in _TRACKS:
            if pools[t] > 0:
                result.append(t)
                pools[t] -= 1
                progressed = True
                if len(result) >= n:
                    break
        if not progressed:
            break
    return result


def normalize_answer(text: str) -> str:
    """Deterministic normalisation for gap / choice / order grading."""
    s = text.strip().lower()
    for a in _APOSTROPHES:
        s = s.replace(a, "'")
    s = s.strip(string.punctuation + string.whitespace)
    s = re.sub(r"\s+", " ", s)
    return s


def grade_answer(raw: str, accept: list[str]) -> bool:
    normalised = normalize_answer(raw)
    accepted = {normalize_answer(a) for a in accept}
    return normalised in accepted


def grade_spot(tapped: str, answer: str) -> bool:
    return normalize_answer(tapped) == normalize_answer(answer)


def recent_prompts_for_errors(
    user_id: int,
    error_ids: list[int],
    *,
    limit_per: int = 3,
) -> dict[int, list[str]]:
    """Last ``limit_per`` prompts per error_id from prior quiz session payloads."""
    wanted = set(error_ids)
    found: dict[int, list[str]] = {eid: [] for eid in error_ids}
    if not wanted:
        return found
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT payload FROM sessions
             WHERE user_id = %s
               AND task_type = 'quiz'
               AND payload IS NOT NULL
             ORDER BY id DESC
             LIMIT 40
            """,
            (user_id,),
        ).fetchall()
    for row in rows:
        payload = row["payload"]
        if not isinstance(payload, dict):
            continue
        for q in payload.get("questions") or []:
            try:
                eid = int(q.get("error_id"))
            except (TypeError, ValueError):
                continue
            if eid not in wanted:
                continue
            prompt = str(q.get("prompt") or "").strip()
            if not prompt:
                continue
            bucket = found[eid]
            if prompt in bucket:
                continue
            if len(bucket) >= limit_per:
                continue
            bucket.append(prompt)
        if all(len(found[eid]) >= limit_per for eid in wanted):
            break
    return {eid: prompts for eid, prompts in found.items() if prompts}


def recent_scenarios(user_id: int, *, limit: int = 5) -> list[str]:
    """Recent quiz scenario labels from prior sessions (avoid repeats)."""
    out: list[str] = []
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT payload FROM sessions
             WHERE user_id = %s
               AND task_type = 'quiz'
               AND payload IS NOT NULL
             ORDER BY id DESC
             LIMIT 30
            """,
            (user_id,),
        ).fetchall()
    for row in rows:
        payload = row["payload"]
        if not isinstance(payload, dict):
            continue
        scenario = str(payload.get("scenario") or "").strip()
        if not scenario or scenario in out:
            continue
        out.append(scenario)
        if len(out) >= limit:
            break
    return out


def _user_timezone(user_id: int) -> str:
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


def user_has_open_quiz(
    user_id: int,
    *,
    now: datetime | None = None,
) -> bool:
    """True when an incomplete quiz session exists (any date)."""
    del now
    return get_open_quiz_session(user_id) is not None


class OpenQuizFilter(filters.MessageFilter):
    """Match private text only when the sender has an open quiz."""

    def filter(self, message: Message) -> bool:
        user = message.from_user
        if user is None:
            return False
        try:
            return user_has_open_quiz(user.id)
        except Exception:
            logger.exception(
                "OpenQuizFilter failed user_id=%s",
                user.id,
            )
            return False


def typed_gap_count(n: int) -> int:
    """How many gap (typed) questions for a quiz of size n."""
    if n <= 0:
        return 0
    if n >= 5:
        return 2
    return max(1, (n * 2) // 5)  # ~40% rounded down, min 1


def plan_formats(n: int) -> list[str]:
    """Hard mix: 2 gap + 3 tapped for n=5; never three of the same in a row."""
    if n <= 0:
        return []
    if n == 5:
        return ["choice", "gap", "spot", "gap", "order"]
    n_gap = typed_gap_count(n)
    n_tap = n - n_gap
    taps = [["choice", "spot", "order"][i % 3] for i in range(n_tap)]
    out: list[str] = []
    gi = ti = 0
    for slot in range(n):
        slots_left = n - slot
        gaps_left = n_gap - gi
        taps_left = n_tap - ti
        if gaps_left > 0 and gaps_left >= slots_left - taps_left:
            out.append("gap")
            gi += 1
        elif taps_left > 0:
            cand = taps[ti]
            if len(out) >= 2 and out[-1] == cand and out[-2] == cand:
                for alt in ("choice", "spot", "order"):
                    if alt != cand:
                        cand = alt
                        break
            out.append(cand)
            ti += 1
        else:
            out.append("gap")
            gi += 1
    return out


def fill_gap_html(prompt: str, answer: str) -> str:
    """Replace ___ with a bolded answer inside an HTML sentence."""
    esc_ans = html.escape(answer, quote=False)
    if re.search(r"_{2,}", prompt):
        parts = re.split(r"_{2,}", prompt, maxsplit=1)
        return (
            f"{html.escape(parts[0], quote=False)}"
            f"<b>{esc_ans}</b>"
            f"{html.escape(parts[1], quote=False)}"
        )
    return f"{html.escape(prompt, quote=False)} <b>{esc_ans}</b>"


def gap_prompt_with_bold_blank(prompt: str) -> str:
    """Show the gap as a bold blank slot."""
    if re.search(r"_{2,}", prompt):
        parts = re.split(r"_{2,}", prompt, maxsplit=1)
        return (
            f"{html.escape(parts[0], quote=False)}"
            f"<b>___</b>"
            f"{html.escape(parts[1], quote=False)}"
        )
    return html.escape(prompt, quote=False)


def corrected_spot_sentence(q: dict[str, Any]) -> str:
    """Sentence with the wrong word replaced by the correction."""
    tiles = [str(t) for t in (q.get("tiles") or [])]
    wrong = str(q.get("answer") or "")
    right = str(q.get("correction") or wrong)
    out: list[str] = []
    replaced = False
    for t in tiles:
        if not replaced and normalize_answer(t) == normalize_answer(wrong):
            out.append(right)
            replaced = True
        else:
            out.append(t)
    return " ".join(out)


def spot_sentence_struck(q: dict[str, Any]) -> str:
    """Sentence with the wrong word struck through (HTML)."""
    tiles = [str(t) for t in (q.get("tiles") or [])]
    wrong = str(q.get("answer") or "")
    parts: list[str] = []
    struck = False
    for t in tiles:
        if not struck and normalize_answer(t) == normalize_answer(wrong):
            parts.append(f"<s>{html.escape(t, quote=False)}</s>")
            struck = True
        else:
            parts.append(html.escape(t, quote=False))
    return " ".join(parts)


def format_feedback(
    question: dict[str, Any],
    *,
    correct: bool,
    user_answer: str,
) -> str:
    """Show the question context: what they said + full correct sentence."""
    fmt = question.get("format")
    expl = (question.get("explanation") or "").strip()
    lines: list[str] = []

    if fmt == "gap":
        prompt = str(question.get("prompt") or "")
        filled = fill_gap_html(prompt, str(question.get("answer") or ""))
        if correct:
            lines.append(texts.QUIZ_CORRECT_SENTENCE.format(sentence=filled))
        else:
            lines.append(
                texts.QUIZ_YOU_SAID.format(said=html.escape(user_answer, quote=False))
            )
            lines.append(texts.QUIZ_CORRECT_SENTENCE.format(sentence=filled))
            if expl:
                lines.append(
                    texts.QUIZ_WRONG_EXPLAIN.format(
                        explanation=html.escape(expl, quote=False)
                    )
                )
        return "\n".join(lines)

    if fmt in ("choice", "order"):
        correct_sent = html.escape(str(question.get("answer") or ""), quote=False)
        if correct:
            lines.append(
                texts.QUIZ_CORRECT_SENTENCE.format(
                    sentence=f"<b>{correct_sent}</b>"
                )
            )
        else:
            lines.append(
                texts.QUIZ_YOU_SAID.format(
                    said=html.escape(user_answer, quote=False)
                )
            )
            lines.append(
                texts.QUIZ_CORRECT_SENTENCE.format(
                    sentence=f"<b>{correct_sent}</b>"
                )
            )
            if expl:
                lines.append(
                    texts.QUIZ_WRONG_EXPLAIN.format(
                        explanation=html.escape(expl, quote=False)
                    )
                )
        return "\n".join(lines)

    if fmt == "spot":
        corrected = corrected_spot_sentence(question)
        bold_corr = html.escape(corrected, quote=False)
        # Bold the correction word inside the sentence if present
        corr_word = str(question.get("correction") or "")
        if corr_word and corr_word in corrected:
            bold_corr = html.escape(corrected, quote=False).replace(
                html.escape(corr_word, quote=False),
                f"<b>{html.escape(corr_word, quote=False)}</b>",
                1,
            )
        if correct:
            lines.append(texts.QUIZ_CORRECT_SENTENCE.format(sentence=bold_corr))
        else:
            lines.append(
                texts.QUIZ_YOU_SAID.format(said=spot_sentence_struck(question))
            )
            lines.append(texts.QUIZ_CORRECT_SENTENCE.format(sentence=bold_corr))
            if expl:
                lines.append(
                    texts.QUIZ_WRONG_EXPLAIN.format(
                        explanation=html.escape(expl, quote=False)
                    )
                )
        return "\n".join(lines)

    # Fallback
    if correct:
        return texts.QUIZ_CORRECT_SENTENCE.format(
            sentence=html.escape(str(question.get("answer") or ""), quote=False)
        )
    return texts.QUIZ_YOU_SAID.format(
        said=html.escape(user_answer, quote=False)
    )


def _format_hint(fmt: str) -> str:
    if fmt == "gap":
        return texts.QUIZ_HINT_GAP
    if fmt == "spot":
        return texts.QUIZ_HINT_SPOT
    if fmt == "order":
        return texts.QUIZ_HINT_ORDER
    return texts.QUIZ_HINT_CHOICE


def _progress_dots(index: int, total: int) -> str:
    return "".join("●" if i == index else "○" for i in range(total))


def _spot_sentence(q: dict[str, Any]) -> str:
    """Full sentence for reading — never leave spot body as tiles-only."""
    explicit = str(q.get("sentence") or "").strip()
    if explicit:
        return explicit
    return " ".join(str(t) for t in (q.get("tiles") or []))


def _quiz_preface(user_id: int, *, rescue: bool) -> str:
    """Freeze notice and/or rescue line for the opening quiz message."""
    parts: list[str] = []
    if consume_freeze_notice(user_id):
        remaining = get_streak(user_id).freeze_tokens
        parts.append(texts.format_freeze_notice(remaining))
    if rescue:
        parts.append(texts.QUIZ_RESCUE)
    return "\n\n".join(parts)


# Telegram truncates inline button labels to button width. Never put readable
# content in a label — numbers / single words only (see .cursorrules).
_MAX_BUTTON_LABEL_CHARS = 20


def _numbered_options_block(options: list[str]) -> str:
    """Full options for the message body — one numbered line each."""
    lines = [
        f"{i}. {html.escape(str(opt), quote=False)}"
        for i, opt in enumerate(options, start=1)
    ]
    return "\n".join(lines)


def _question_text(payload: dict[str, Any]) -> str:
    """Message body for READING. Hint → sentence → dots last."""
    questions = payload["questions"]
    index = int(payload["index"])
    q = questions[index]
    dots = _progress_dots(index, len(questions))
    fmt = q.get("format") or "gap"
    hint = _format_hint(fmt)

    if fmt == "spot":
        sentence = html.escape(_spot_sentence(q), quote=False)
        body = f'{hint}\n\n"{sentence}"\n\n{dots}'
    elif fmt == "gap":
        sentence = gap_prompt_with_bold_blank(str(q.get("prompt") or ""))
        body = f"{hint}\n\n{sentence}\n\n{dots}"
    else:
        # choice / order — options in the body; buttons are numbers only
        prompt = html.escape(
            str(q.get("prompt") or "Which one sounds right?"), quote=False
        )
        options = [str(o) for o in (q.get("options") or [])]
        opts_block = _numbered_options_block(options)
        body = f"{hint}\n\n{prompt}\n\n{opts_block}\n\n{dots}"

    # Preface (freeze / rescue) only on the first question.
    preface = str(payload.get("preface") or "").strip()
    if preface and index == 0:
        return f"{preface}\n\n{body}"
    return body


def compose_body(*, feedback: str | None, question_body: str) -> str:
    """Feedback then next question, separated by a blank line."""
    if feedback:
        return f"{feedback}\n\n{question_body}"
    return question_body


def _keyboard_for_question(
    q: dict[str, Any],
    payload: dict[str, Any],
) -> InlineKeyboardMarkup | None:
    del payload  # reserved for formats that keep mid-question state
    fmt = q.get("format")
    if fmt in ("choice", "order"):
        options = list(q.get("options") or [])
        # Numbers only — full sentences live in the message body.
        items = [(str(i + 1), f"quiz:opt:{i}") for i in range(len(options))]
        rows = layout_buttons(items, max_per_row=4)
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(label, callback_data=cb) for label, cb in row]
                for row in rows
            ]
        )
    if fmt == "spot":
        tiles = list(q.get("tiles") or [])
        items = [(t, f"quiz:stile:{i}") for i, t in enumerate(tiles)]
        rows = layout_buttons(items, max_per_row=3)
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(label, callback_data=cb) for label, cb in row]
                for row in rows
            ]
        )
    return None


async def _safe_edit(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    except BadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        raise


def _build_quiz_questions(
    user_id: int,
    errors: list[Error],
    *,
    chat_fn: Any = None,
) -> tuple[list[dict], str]:
    """Generate quiz questions. Returns (questions, scenario).

    ``chat_fn`` is injectable for tests.
    """
    user = get_user(user_id)
    if user is None:
        raise RuntimeError(f"quiz: missing user {user_id}")
    if _prompt_template is None:
        init_quiz_prompt()
    assert _prompt_template is not None

    tracks = distribute_tracks(len(errors), user.track_weights)
    formats = plan_formats(len(errors))
    recent = recent_prompts_for_errors(user_id, [e.id for e in errors])
    avoid_sc = recent_scenarios(user_id)
    due_payload = []
    for i, e in enumerate(errors):
        item: dict[str, Any] = {
            "error_id": e.id,
            "you_said": e.you_said,
            "correct_form": e.correct_form,
            "error_type": e.error_type,
            "explanation": e.explanation,
            "track": tracks[i] if i < len(tracks) else "life",
            "format": formats[i] if i < len(formats) else "gap",
        }
        avoid = recent.get(e.id)
        if avoid:
            item["avoid_prompts"] = avoid
        due_payload.append(item)

    avoid_scenarios_text = (
        json.dumps(avoid_sc, ensure_ascii=False) if avoid_sc else "(none yet)"
    )
    system = _prompt_template.format(
        cefr_level=user.cefr_level,
        native_language=user.native_language,
        work_domain=user.work_domain or "everyday life",
        track_weights_json=json.dumps(user.track_weights, ensure_ascii=False),
        avoid_scenarios=avoid_scenarios_text,
        due_errors_json=json.dumps(due_payload, ensure_ascii=False),
    )
    call = chat_fn or chat
    result = call(
        [{"role": "user", "content": "Generate today's quiz questions."}],
        system=system,
        json_mode=True,
        max_tokens=2500,
    )
    if not isinstance(result, dict):
        raise LLMError("quiz response was not a JSON object")
    scenario = str(result.get("scenario") or "").strip()
    questions = list(result.get("questions") or [])
    by_id = {e.id: e for e in errors}
    cleaned: list[dict] = []
    for i, (q, err) in enumerate(zip(questions, errors, strict=False)):
        eid = int(q.get("error_id", err.id))
        if eid not in by_id:
            eid = err.id
        planned = formats[i] if i < len(formats) else "gap"
        fmt = q.get("format") or planned
        if fmt not in _VALID_FORMATS:
            fmt = planned
        # Hard mix: trust the plan, not the model.
        fmt = planned
        accept = [str(a).lower() for a in (q.get("accept") or [])]
        answer = str(q.get("answer") or err.correct_form)
        if not accept and fmt in ("gap", "choice", "order"):
            accept = [normalize_answer(answer)]
        code = by_id[eid].error_type
        item = {
            "error_id": eid,
            "format": fmt,
            "prompt": str(q.get("prompt") or "")[:140],
            "accept": accept,
            "answer": answer,
            "error_type": code,
            "error_type_label": error_type_label(code),
            "explanation": by_id[eid].explanation,
        }
        if fmt in ("choice", "order"):
            item["options"] = [str(o) for o in (q.get("options") or [])]
            if not item["options"] and answer:
                # Minimal fallback so a button still exists if the model skipped options.
                item["options"] = [answer]
        if fmt == "spot":
            item["tiles"] = [str(t) for t in (q.get("tiles") or [])]
            item["correction"] = str(
                q.get("correction") or by_id[eid].correct_form
            )
        cleaned.append(item)
    return cleaned, scenario


async def deliver_morning(
    app: Any,
    user_id: int,
    *,
    now: datetime,
) -> str:
    """Deliver quiz or free-practice for one user. Returns action taken."""
    bot = app.bot
    tz = _user_timezone(user_id)
    day = local_today(tz, now)
    if has_session_on(user_id, day):
        return "skipped_existing"
    if not under_message_ceiling(user_id, day):
        return "skipped_ceiling"

    rescue = is_in_rescue(user_id, day)
    quiz_limit = 3 if rescue else 5
    preface = _quiz_preface(user_id, rescue=rescue)

    errors = due_errors(user_id, limit=quiz_limit)
    if not errors:
        insert_session(user_id, "free_practice", day, completed=False)
        body = texts.QUIZ_FREE_PRACTICE
        if preface:
            body = f"{preface}\n\n{body}"
        await bot.send_message(chat_id=user_id, text=body)
        increment_bot_messages(user_id, day)
        return "free_practice"

    try:
        # Off the event loop — a blocking LLM call would make APScheduler
        # skip the evening poll (misfire grace) for that tick.
        questions, scenario = await asyncio.to_thread(
            _build_quiz_questions, user_id, errors
        )
    except (LLMError, Exception):
        logger.exception(
            "quiz generation failed user_id=%s handler=%s",
            user_id,
            HANDLER_NAME,
        )
        try:
            await bot.send_message(
                chat_id=user_id,
                text=texts.LLM_FAILED,
            )
            increment_bot_messages(user_id, day)
        except Exception:
            logger.exception("failed to notify user_id=%s of quiz LLM error", user_id)
        return "skipped_llm"

    if not questions:
        insert_session(user_id, "free_practice", day, completed=False)
        body = texts.QUIZ_FREE_PRACTICE
        if preface:
            body = f"{preface}\n\n{body}"
        await bot.send_message(chat_id=user_id, text=body)
        increment_bot_messages(user_id, day)
        return "free_practice"

    questions = questions[:quiz_limit]

    payload: dict[str, Any] = {
        "index": 0,
        "correct_count": 0,
        "answered": 0,
        "questions": questions,
        "scenario": scenario,
        "chat_id": user_id,
        "message_id": None,
        "preface": preface,
    }
    session_id = insert_session(
        user_id, "quiz", day, payload=payload, completed=False
    )
    payload["session_id"] = session_id

    q0 = questions[0]
    msg = await bot.send_message(
        chat_id=user_id,
        text=_question_text(payload),
        reply_markup=_keyboard_for_question(q0, payload),
        parse_mode=ParseMode.HTML,
    )
    increment_bot_messages(user_id, day)
    payload["message_id"] = msg.message_id
    update_session_payload(session_id, payload)
    return "quiz"


def format_completion_message(
    *,
    correct_count: int,
    total: int,
    streak_days: int | None = None,
    improved_labels: list[str] | None = None,
    struggled_labels: list[str] | None = None,
) -> str:
    """Score line with stars, optimistic streak, progress / came-back lines."""
    improved = list(improved_labels or [])
    struggled = list(struggled_labels or [])
    stars = ("⭐️" * correct_count) + ("☆" * max(0, total - correct_count))
    lines = [
        texts.QUIZ_DONE.format(
            correct=correct_count, total=total, stars=stars
        )
    ]
    if streak_days is not None and streak_days > 0:
        lines.append(texts.QUIZ_STREAK.format(n=streak_days))
    detail: list[str] = []
    if improved:
        detail.append(texts.QUIZ_IMPROVED.format(label=improved[0]))
    if struggled:
        detail.append(texts.QUIZ_CAME_BACK.format(label=struggled[0]))
    if detail:
        lines.append("")
        lines.extend(detail)
    return "\n".join(lines)


def _label_for_question(question: dict[str, Any]) -> str:
    return str(
        question.get("error_type_label")
        or error_type_label(str(question.get("error_type") or ""))
    )


async def _advance_after_answer(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    session_id: int,
    payload: dict[str, Any],
    *,
    correct: bool,
    question: dict[str, Any],
    user_answer: str,
) -> None:
    mark_result(int(question["error_id"]), correct)
    payload["answered"] = int(payload.get("answered", 0)) + 1
    label = _label_for_question(question)
    if correct:
        payload["correct_count"] = int(payload.get("correct_count", 0)) + 1
        improved = list(payload.get("improved_labels") or [])
        if label and label not in improved:
            improved.append(label)
        payload["improved_labels"] = improved
    else:
        struggled = list(payload.get("struggled_labels") or [])
        if label and label not in struggled:
            struggled.append(label)
        payload["struggled_labels"] = struggled

    chat_id = int(payload["chat_id"])
    message_id = int(payload["message_id"])
    total = len(payload["questions"])
    index = int(payload["index"])
    feedback = format_feedback(
        question, correct=correct, user_answer=user_answer
    )

    if index + 1 >= total:
        score = (
            float(payload["correct_count"]) / float(total) if total else 0.0
        )
        complete_session(session_id, score)
        # Optimistic display only — rollover at 03:00 is the real evaluation.
        optimistic_streak = get_streak(user_id).current_streak + 1
        summary = format_completion_message(
            correct_count=int(payload["correct_count"]),
            total=total,
            streak_days=optimistic_streak,
            improved_labels=list(payload.get("improved_labels") or []),
            struggled_labels=list(payload.get("struggled_labels") or []),
        )
        body = compose_body(feedback=feedback, question_body=summary)
        update_session_payload(session_id, payload)
        await _safe_edit(
            context,
            chat_id=chat_id,
            message_id=message_id,
            text=body,
            reply_markup=None,
        )
        return

    payload["index"] = index + 1
    next_q = payload["questions"][payload["index"]]
    body = compose_body(
        feedback=feedback,
        question_body=_question_text(payload),
    )
    update_session_payload(session_id, payload)
    await _safe_edit(
        context,
        chat_id=chat_id,
        message_id=message_id,
        text=body,
        reply_markup=_keyboard_for_question(next_q, payload),
    )


async def on_quiz_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    user_id = update.effective_user.id
    session = get_open_quiz_session(user_id)
    if session is None or not session.payload:
        return
    payload = dict(session.payload)
    questions = payload.get("questions") or []
    index = int(payload.get("index", 0))
    if index >= len(questions):
        return
    q = questions[index]
    if q.get("format") != "gap":
        return
    raw = update.message.text or ""
    correct = grade_answer(raw, list(q.get("accept") or []))
    try:
        await update.message.delete()
    except BadRequest:
        pass
    await _advance_after_answer(
        context,
        user_id,
        session.id,
        payload,
        correct=correct,
        question=q,
        user_answer=raw,
    )


async def on_quiz_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await query.answer()
    data = query.data or ""
    if not data.startswith("quiz:"):
        return
    user_id = update.effective_user.id
    session = get_open_quiz_session(user_id)
    if session is None or not session.payload:
        return
    payload = dict(session.payload)
    questions = payload.get("questions") or []
    index = int(payload.get("index", 0))
    if index >= len(questions):
        return
    q = questions[index]
    parts = data.split(":")

    if data.startswith("quiz:opt:") and q.get("format") in ("choice", "order"):
        try:
            opt_index = int(parts[-1])
        except ValueError:
            return
        options = list(q.get("options") or [])
        if opt_index < 0 or opt_index >= len(options):
            return
        chosen = options[opt_index]
        correct = grade_answer(
            chosen, list(q.get("accept") or [q.get("answer", "")])
        )
        await _advance_after_answer(
            context,
            user_id,
            session.id,
            payload,
            correct=correct,
            question=q,
            user_answer=chosen,
        )
        return

    if data.startswith("quiz:stile:") and q.get("format") == "spot":
        try:
            tile_i = int(parts[-1])
        except ValueError:
            return
        tiles = list(q.get("tiles") or [])
        if tile_i < 0 or tile_i >= len(tiles):
            return
        tapped = tiles[tile_i]
        correct = grade_spot(tapped, str(q.get("answer") or ""))
        await _advance_after_answer(
            context,
            user_id,
            session.id,
            payload,
            correct=correct,
            question=q,
            user_answer=tapped,
        )


def build_quiz_handlers() -> tuple:
    """Return (text_handler, callback_handler) to register before correction."""
    text_handler = MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND & OpenQuizFilter(),
        on_quiz_text,
    )
    callback_handler = CallbackQueryHandler(on_quiz_callback, pattern=r"^quiz:")
    return text_handler, callback_handler
