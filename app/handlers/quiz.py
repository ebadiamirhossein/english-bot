"""Daily quiz delivery and in-place answering (M1 / S3 + S3a)."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import string
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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
from app.handlers.correction import error_type_list_text
from app.handlers.onboarding import layout_buttons
from app.llm import LLMError, chat
from app.services.anki import make_sentence_with_gap
from app.services.books import select_topup_items, studied_murphy_unit_numbers
from app.services.calibration import deliver_raise_notice, maybe_calibrate
from app.services.chunks import Chunk, due_chunks, mark_chunk_result
from app.services.errors import (
    Error,
    due_errors,
    expand_murphy_units,
    get_error_for_user,
    mark_result,
    murphy_units_for_labels,
    record_errors,
    select_weekly_test_errors,
    top_error_types,
)
from app.services.sessions import (
    complete_session,
    get_open_quiz_session,
    get_session_by_id,
    has_session_on,
    increment_bot_messages,
    insert_session,
    local_today,
    mark_fossil_retest_done,
    open_fossil_sweep_for_user,
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
_ARTICLES = frozenset({"a", "an", "the"})
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


def _tokens_without_articles(text: str) -> list[str]:
    """Normalise, then drop a/an/the — used only for chunk phrase grading."""
    return [
        tok
        for tok in normalize_answer(text).split()
        if tok and tok not in _ARTICLES
    ]


def grade_chunk_answer(raw: str, accept: list[str]) -> bool:
    """Article-tolerant phrase match for chunk gaps (S7a).

    Exact content-word sequence after dropping articles. No fuzzy overlap.
    """
    raw_toks = _tokens_without_articles(raw)
    if not raw_toks:
        return False
    for candidate in accept:
        if raw_toks == _tokens_without_articles(str(candidate)):
            return True
    return False


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


def open_quiz_awaits_gap_answer(user_id: int) -> bool:
    """True when the open quiz's *current* question expects a typed gap answer.

    Non-gap formats (choice / order / spot) must not consume private text —
    that update belongs to free correction (M2).
    """
    session = get_open_quiz_session(user_id)
    if session is None or not session.payload:
        return False
    payload = session.payload
    questions = payload.get("questions") or []
    try:
        index = int(payload.get("index", 0))
    except (TypeError, ValueError):
        return False
    if index < 0 or index >= len(questions):
        return False
    question = questions[index]
    if not isinstance(question, dict):
        return False
    return question.get("format") == "gap"


class OpenQuizFilter(filters.MessageFilter):
    """Match private text only when the open quiz awaits a typed gap answer."""

    def filter(self, message: Message) -> bool:
        user = message.from_user
        if user is None:
            return False
        try:
            return open_quiz_awaits_gap_answer(user.id)
        except Exception:
            logger.exception(
                "OpenQuizFilter failed user_id=%s",
                user.id,
            )
            return False


def typed_gap_count(n: int) -> int:
    """How many gap (typed) questions for a quiz of size n.

    n=5 is the S3d hard mix (2 typed). Other sizes scale ~40%.
    n=3 (rescue) stays 1 — pinned by tests.
    """
    if n <= 0:
        return 0
    if n == 5:
        return 2
    return max(1, (n * 2) // 5)


def _gap_slot_indices(n: int, n_gap: int) -> set[int]:
    """Evenly spaced gap positions. Single gap at 0 preserves rescue layout."""
    if n_gap <= 0 or n <= 0:
        return set()
    if n_gap >= n:
        return set(range(n))
    if n_gap == 1:
        return {0}
    raw = [round(i * (n - 1) / (n_gap - 1)) for i in range(n_gap)]
    slots: set[int] = set()
    for s in raw:
        s = max(0, min(n - 1, int(s)))
        if s not in slots:
            slots.add(s)
            continue
        for d in range(1, n):
            placed = False
            for cand in (s - d, s + d):
                if 0 <= cand < n and cand not in slots:
                    slots.add(cand)
                    placed = True
                    break
            if placed:
                break
    return slots


def plan_formats(n: int) -> list[str]:
    """Hard mix: 2 gap + 3 tapped for n=5; never three of the same in a row.

    Generic path places gaps at evenly spaced indices — the old
    ``gaps_left >= slots_left - taps_left`` rule front-loaded all gaps
    (six in a row for a 15-question weekly test).
    """
    if n <= 0:
        return []
    if n == 5:
        return ["choice", "gap", "spot", "gap", "order"]
    n_gap = typed_gap_count(n)
    n_tap = n - n_gap
    taps = [["choice", "spot", "order"][i % 3] for i in range(n_tap)]
    gap_slots = _gap_slot_indices(n, n_gap)
    out: list[str] = []
    ti = 0
    for slot in range(n):
        if slot in gap_slots:
            out.append("gap")
            continue
        if ti >= len(taps):
            out.append("gap")
            continue
        cand = taps[ti]
        if len(out) >= 2 and out[-1] == cand and out[-2] == cand:
            for alt in ("choice", "spot", "order"):
                if alt != cand:
                    cand = alt
                    break
        out.append(cand)
        ti += 1
    return out


def _plan_formats_with_gap_count(n: int, n_gap: int) -> list[str]:
    """Assign formats for ``n`` slots with exactly ``n_gap`` typed gaps."""
    if n <= 0:
        return []
    n_gap = max(0, min(n, n_gap))
    if n_gap == 0:
        taps = [["choice", "spot", "order"][i % 3] for i in range(n)]
        out: list[str] = []
        for cand in taps:
            if len(out) >= 2 and out[-1] == cand and out[-2] == cand:
                for alt in ("choice", "spot", "order"):
                    if alt != cand:
                        cand = alt
                        break
            out.append(cand)
        return out
    if n_gap >= n:
        return ["gap"] * n
    n_tap = n - n_gap
    taps = [["choice", "spot", "order"][i % 3] for i in range(n_tap)]
    gap_slots = _gap_slot_indices(n, n_gap)
    out = []
    ti = 0
    for slot in range(n):
        if slot in gap_slots:
            out.append("gap")
            continue
        cand = taps[ti] if ti < len(taps) else "choice"
        ti += 1
        if len(out) >= 2 and out[-1] == cand and out[-2] == cand:
            for alt in ("choice", "spot", "order"):
                if alt != cand:
                    cand = alt
                    break
        out.append(cand)
    return out


def assign_formats(
    n_errors: int,
    n_chunks: int,
    n_books: int,
) -> list[str]:
    """Formats for errors → chunks → books. Chunks always gap; mix capped.

    When there are no chunks, delegates to ``plan_formats`` so S3d/S11 layouts
    stay byte-identical. With chunks, typed budget for LLM items is
    ``typed_gap_count(n) - n_chunks`` (chunk selection is already capped).
    """
    n = n_errors + n_chunks + n_books
    if n <= 0:
        return []
    if n_chunks == 0:
        return plan_formats(n)
    formats = ["choice"] * n
    chunk_start = n_errors
    chunk_end = n_errors + n_chunks
    for i in range(chunk_start, chunk_end):
        formats[i] = "gap"
    other_idx = [i for i in range(n) if not (chunk_start <= i < chunk_end)]
    n_gap_other = max(0, typed_gap_count(n) - n_chunks)
    other_formats = _plan_formats_with_gap_count(len(other_idx), n_gap_other)
    for i, fmt in zip(other_idx, other_formats, strict=True):
        formats[i] = fmt
    return formats


def build_chunk_question(chunk: Chunk) -> dict[str, Any]:
    """Deterministic gap question from a due chunk. No LLM."""
    assert chunk.full_sentence is not None
    gapped = make_sentence_with_gap(str(chunk.full_sentence), chunk.chunk)
    if gapped is None:
        raise ValueError(f"chunk {chunk.id} cannot form a gap")
    return {
        "source": "chunk",
        "chunk_id": chunk.id,
        "format": "gap",
        "prompt": gapped,
        "answer": chunk.chunk,
        "accept": [chunk.chunk],
        "explanation": (chunk.meaning or "").strip(),
        "error_type_label": texts.QUIZ_CHUNK_LABEL,
    }


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


def _quiz_preface(
    user_id: int, *, rescue: bool, weekly_test: bool = False
) -> str:
    """Freeze notice and/or rescue / weekly line for the opening quiz message."""
    parts: list[str] = []
    if consume_freeze_notice(user_id):
        remaining = get_streak(user_id).freeze_tokens
        parts.append(texts.format_freeze_notice(remaining))
    if rescue:
        parts.append(texts.QUIZ_RESCUE)
    elif weekly_test:
        parts.append(texts.QUIZ_WEEKLY)
    return "\n\n".join(parts)


def format_murphy_recommendation(user_id: int, *, max_recs: int = 2) -> str | None:
    """Build Murphy unit lines from top error types; None if nothing to say."""
    labels = top_error_types(user_id, n=8)
    mapped = murphy_units_for_labels(labels)
    if not mapped:
        return None
    studied = studied_murphy_unit_numbers(user_id)
    lines: list[str] = []
    for label, spec in mapped:
        units = expand_murphy_units(spec)
        if not units:
            continue
        template = (
            texts.MURPHY_REC_STUDIED
            if units & studied
            else texts.MURPHY_REC_NEW
        )
        line = template.format(units=spec, label=label)
        lines.append(line)
        if len(lines) >= max_recs:
            break
    if not lines:
        return None
    block = "\n".join(lines)
    if len(block) > 400:
        block = block[:397].rstrip() + "…"
    return block


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


def quiz_effective_total(payload: dict[str, Any]) -> int:
    """Question count the user must finish (honours S10 early_limit)."""
    questions = payload.get("questions") or []
    early = payload.get("early_limit")
    if early is not None:
        return min(int(early), len(questions)) if questions else int(early)
    return len(questions)


def _question_text(payload: dict[str, Any]) -> str:
    """Message body for READING. Hint → sentence → dots last."""
    questions = payload["questions"]
    index = int(payload["index"])
    q = questions[index]
    total = quiz_effective_total(payload)
    # Clamp display index if early_limit shortened the set.
    display_index = min(index, max(total - 1, 0))
    dots = _progress_dots(display_index, total)
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
    *,
    callback_prefix: str | None = None,
) -> InlineKeyboardMarkup | None:
    prefix = callback_prefix or str(payload.get("callback_prefix") or "quiz")
    fmt = q.get("format")
    if fmt in ("choice", "order"):
        options = list(q.get("options") or [])
        # Numbers only — full sentences live in the message body.
        items = [
            (str(i + 1), f"{prefix}:opt:{i}")
            for i in range(len(options))
        ]
        for label, _cb in items:
            if len(label) > _MAX_BUTTON_LABEL_CHARS:
                logger.warning(
                    "quiz button label too long (%s chars): %r",
                    len(label),
                    label,
                )
        rows = layout_buttons(items, max_per_row=4)
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(label, callback_data=cb) for label, cb in row]
                for row in rows
            ]
        )
    if fmt == "spot":
        tiles = list(q.get("tiles") or [])
        items = [
            (str(t)[:_MAX_BUTTON_LABEL_CHARS], f"{prefix}:stile:{i}")
            for i, t in enumerate(tiles)
        ]
        for label, _cb in items:
            if len(label) > _MAX_BUTTON_LABEL_CHARS:
                logger.warning(
                    "quiz button label too long (%s chars): %r",
                    len(label),
                    label,
                )
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


def _clean_question_fields(
    q: dict[str, Any],
    *,
    fmt: str,
    fallback_answer: str,
    fallback_correction: str,
) -> dict[str, Any]:
    accept = [str(a).lower() for a in (q.get("accept") or [])]
    answer = str(q.get("answer") or fallback_answer)
    if not accept and fmt in ("gap", "choice", "order"):
        accept = [normalize_answer(answer)]
    item: dict[str, Any] = {
        "format": fmt,
        "prompt": str(q.get("prompt") or "")[:140],
        "accept": accept,
        "answer": answer,
    }
    if fmt in ("choice", "order"):
        item["options"] = [str(o) for o in (q.get("options") or [])]
        if not item["options"] and answer:
            item["options"] = [answer]
    if fmt == "spot":
        item["tiles"] = [str(t) for t in (q.get("tiles") or [])]
        item["correction"] = str(q.get("correction") or fallback_correction)
    return item


def _build_quiz_questions(
    user_id: int,
    errors: list[Error],
    *,
    chunks: list[Chunk] | None = None,
    book_items: list[dict[str, Any]] | None = None,
    chat_fn: Any = None,
) -> tuple[list[dict], str]:
    """Generate quiz questions. Returns (questions, scenario).

    ``chat_fn`` is injectable for tests. Order: errors → chunks → books.
    Chunks are deterministic gaps (no LLM). ``book_items`` top up when
    fewer errors/chunks than the quiz size (S6a / S7a).
    """
    user = get_user(user_id)
    if user is None:
        raise RuntimeError(f"quiz: missing user {user_id}")

    chunk_list = list(chunks or [])
    books = list(book_items or [])
    total = len(errors) + len(chunk_list) + len(books)
    if total == 0:
        return [], ""

    formats = assign_formats(len(errors), len(chunk_list), len(books))
    chunk_questions = [build_chunk_question(c) for c in chunk_list]

    # Chunks alone — no LLM.
    if not errors and not books:
        return chunk_questions, ""

    if _prompt_template is None:
        init_quiz_prompt()
    assert _prompt_template is not None

    tracks = distribute_tracks(len(errors), user.track_weights)
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

    book_payload = []
    book_fmt_base = len(errors) + len(chunk_list)
    for j, b in enumerate(books):
        idx = book_fmt_base + j
        book_payload.append(
            {
                "source": "book",
                "book": b.get("book"),
                "unit_number": b.get("unit_number"),
                "unit_title": b.get("unit_title"),
                "target_item": b.get("item"),
                "format": formats[idx] if idx < len(formats) else "choice",
            }
        )

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
        book_items_json=json.dumps(book_payload, ensure_ascii=False),
        error_type_list=error_type_list_text(),
    )
    call = chat_fn or chat
    # 15Q weekly test is ~3× the 5Q payload; 2500 truncates.
    llm_total = len(errors) + len(books)
    token_budget = 7500 if llm_total >= 10 else 2500
    result = call(
        [{"role": "user", "content": "Generate today's quiz questions."}],
        system=system,
        json_mode=True,
        max_tokens=token_budget,
    )
    if not isinstance(result, dict):
        raise LLMError("quiz response was not a JSON object")
    scenario = str(result.get("scenario") or "").strip()
    questions = list(result.get("questions") or [])
    by_id = {e.id: e for e in errors}
    cleaned: list[dict] = []

    # Error-sourced questions first (same order as due_errors).
    for i, err in enumerate(errors):
        q = questions[i] if i < len(questions) else {}
        if not isinstance(q, dict):
            q = {}
        eid = int(q.get("error_id", err.id))
        if eid not in by_id:
            eid = err.id
        planned = formats[i] if i < len(formats) else "gap"
        fmt = planned  # Hard mix: trust the plan, not the model.
        item = _clean_question_fields(
            q,
            fmt=fmt,
            fallback_answer=err.correct_form,
            fallback_correction=err.correct_form,
        )
        code = by_id[eid].error_type
        item.update(
            {
                "error_id": eid,
                "error_type": code,
                "error_type_label": error_type_label(code),
                "explanation": by_id[eid].explanation,
            }
        )
        cleaned.append(item)

    # Chunk-sourced gaps in the middle (S7a).
    cleaned.extend(chunk_questions)

    # Book-sourced questions after chunks.
    # LLM returns errors then books (no chunk slots) — index into that list.
    for j, b in enumerate(books):
        idx = len(errors) + len(chunk_list) + j
        llm_idx = len(errors) + j
        q = questions[llm_idx] if llm_idx < len(questions) else {}
        if not isinstance(q, dict):
            q = {}
        planned = formats[idx] if idx < len(formats) else "choice"
        fmt = planned
        item = _clean_question_fields(
            q,
            fmt=fmt,
            fallback_answer=str(b.get("item") or ""),
            fallback_correction=str(b.get("item") or ""),
        )
        code = str(q.get("error_type") or "").strip()
        expl = str(q.get("explanation") or "").strip()
        unit_title = str(b.get("unit_title") or "")
        item.update(
            {
                "source": "book",
                "book": b.get("book"),
                "unit_number": b.get("unit_number"),
                "unit_title": unit_title,
                "target_item": b.get("item"),
                "error_type": code,
                "error_type_label": (
                    error_type_label(code) if code else unit_title
                ),
                "explanation": expl,
            }
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
    is_sunday = now.astimezone(ZoneInfo(tz)).weekday() == 6
    # S11: weekly test replaces Sunday morning quiz (same task_type).
    # Rescue keeps the 3Q re-engagement day — never a 15Q backlog.
    weekly_test = is_sunday and not rescue
    if rescue:
        quiz_limit = 3
    elif weekly_test:
        quiz_limit = 15
    else:
        quiz_limit = 5
    preface = _quiz_preface(
        user_id, rescue=rescue, weekly_test=weekly_test
    )

    retest_error: Error | None = None
    fossil_session_id: int | None = None
    # Rescue shrinks the ask (PRD §7 rule 7) — never spend a slot on M13.
    if not rescue:
        fossil = open_fossil_sweep_for_user(user_id)
        if fossil is not None and fossil.payload:
            pending = list(fossil.payload.get("pending") or [])
            if pending:
                candidate = get_error_for_user(user_id, int(pending[0]))
                if candidate is not None and candidate.resolved:
                    retest_error = candidate
                    fossil_session_id = fossil.id

    due_limit = quiz_limit - (1 if retest_error is not None else 0)
    if weekly_test:
        errors = select_weekly_test_errors(user_id, limit=max(0, due_limit))
    else:
        errors = due_errors(user_id, limit=max(0, due_limit))
    if retest_error is not None:
        errors = [retest_error] + [e for e in errors if e.id != retest_error.id]
        # Cap after fossil inject so weekly/rescue sizes stay exact.
        errors = errors[:quiz_limit]
    need = quiz_limit - len(errors)
    # S7a: chunks fill remaining slots, capped at typed_gap_count so the
    # S3d 2 typed / 3 tapped mix holds. Weekly test excludes chunks.
    chunk_rows: list[Chunk] = []
    if need and not weekly_test:
        chunk_cap = min(need, typed_gap_count(quiz_limit))
        if chunk_cap > 0:
            chunk_rows = due_chunks(user_id, chunk_cap, now=day)
    need_books = need - len(chunk_rows)
    book_items = (
        select_topup_items(user_id, need_books) if need_books else []
    )
    if not errors and not chunk_rows and not book_items:
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
            _build_quiz_questions,
            user_id,
            errors,
            chunks=chunk_rows,
            book_items=book_items,
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
    if retest_error is not None:
        for q in questions:
            if q.get("error_id") == retest_error.id:
                # Internal only — never render in user-facing copy.
                q["retest"] = True
                break

    payload: dict[str, Any] = {
        "index": 0,
        "correct_count": 0,
        "answered": 0,
        # S7a: calibration ignores chunk answers; score stays full-quiz honest.
        "calib_correct": 0,
        "calib_answered": 0,
        "questions": questions,
        "scenario": scenario,
        "chat_id": user_id,
        "message_id": None,
        "preface": preface,
    }
    if weekly_test:
        payload["weekly_test"] = True
    if fossil_session_id is not None:
        payload["fossil_sweep_session_id"] = fossil_session_id
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


def _journal_book_miss(
    user_id: int,
    question: dict[str, Any],
    *,
    user_answer: str,
) -> None:
    """Write an errors row for a wrong book-sourced answer; never invent types."""
    record_errors(
        user_id,
        "quiz",
        [
            {
                "you_said": user_answer,
                "correct_form": str(question.get("answer") or ""),
                "error_type": question.get("error_type"),
                "explanation": question.get("explanation"),
            }
        ],
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
    now: date | None = None,
) -> None:
    # Book-sourced questions have no errors row — never mark_result.
    # Chunk-sourced: shared ladder on chunks only — never mark_result / errors.
    # Typed (gap) and tapped paths both funnel here.
    # M13 retest: wrong → mark_result (un-resolves); correct → leave the row
    # alone so resolved_at is not refreshed (S10 newly-quiet lead).
    source = question.get("source")
    if source == "book":
        if not correct:
            _journal_book_miss(user_id, question, user_answer=user_answer)
    elif source == "chunk":
        review_day = now
        if review_day is None:
            tz = _user_timezone(user_id)
            review_day = local_today(tz, datetime.now(timezone.utc))
        mark_chunk_result(
            int(question["chunk_id"]),
            correct,
            now=review_day,
        )
    elif question.get("retest"):
        if not correct:
            mark_result(int(question["error_id"]), False)
        fossil_sid = payload.get("fossil_sweep_session_id")
        if fossil_sid is not None and question.get("error_id") is not None:
            mark_fossil_retest_done(int(fossil_sid), int(question["error_id"]))
    else:
        mark_result(int(question["error_id"]), correct)
    payload["answered"] = int(payload.get("answered", 0)) + 1
    # Calibration window excludes chunk phrase-recall (S7a).
    if source != "chunk":
        payload["calib_answered"] = int(payload.get("calib_answered", 0)) + 1
        if correct:
            payload["calib_correct"] = int(payload.get("calib_correct", 0)) + 1
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
    full_total = len(payload["questions"])
    total = quiz_effective_total(payload)
    index = int(payload["index"])
    answered = int(payload.get("answered", 0))
    feedback = format_feedback(
        question, correct=correct, user_answer=user_answer
    )

    # S10 early_limit: complete when answered hits the shortened target.
    # Full quizzes still complete when the last question is answered.
    early = payload.get("early_limit")
    done = (
        answered >= total
        if early is not None
        else index + 1 >= full_total
    )

    if done:
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
        # S11: Murphy routing is a reply append — not a bot-initiated message.
        if payload.get("weekly_test"):
            murphy = format_murphy_recommendation(user_id)
            if murphy:
                summary = f"{summary}\n\n{murphy}"
        body = compose_body(feedback=feedback, question_body=summary)
        update_session_payload(session_id, payload)
        await _safe_edit(
            context,
            chat_id=chat_id,
            message_id=message_id,
            text=body,
            reply_markup=None,
        )
        # M14: book_test shares this path — calibrate quiz sessions only.
        # Weekly tests are skipped inside the accuracy window (payload flag).
        session = get_session_by_id(user_id, session_id)
        if session is not None and session.task_type == "quiz":
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
    if q.get("source") == "chunk":
        correct = grade_chunk_answer(
            raw, list(q.get("accept") or [q.get("answer", "")])
        )
    else:
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
