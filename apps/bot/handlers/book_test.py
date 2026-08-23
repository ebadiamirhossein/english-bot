"""User-initiated /test on a stored book unit (S6a).

Tap-only answers. Session task_type is book_test — never quiz — so morning
eligibility and OpenQuizFilter stay untouched. No text MessageHandler.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
from datetime import datetime, timezone
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from apps.bot import texts
from core import PROMPTS_DIR
from core.db import connection
from apps.bot.handlers.correction import error_type_list_text
from apps.bot.handlers.onboarding import layout_buttons
from apps.bot.handlers.quiz import (
    _MAX_BUTTON_LABEL_CHARS,
    _advance_after_answer,
    _clean_question_fields,
    _keyboard_for_question,
    _question_text,
    error_type_label,
    grade_answer,
    grade_spot,
)
from core.llm import LLMError, chat
from core.services.books import (
    find_units_by_number,
    list_units_for_user,
    teachable_items_for_unit,
)
from core.services.sessions import (
    abandon_open_book_tests,
    get_book_test_session_by_message,
    insert_session,
    local_today,
    update_session_payload,
)
from core.services.users import get_user

logger = logging.getLogger(__name__)

HANDLER_NAME = "book_test"
_PROMPT_PATH = PROMPTS_DIR / "book_quiz.txt"
_prompt_template: str | None = None

_BOOK_LABELS = {
    "murphy": "Murphy",
    "vocabulary_in_use": "Vocab in Use",
    "marketing": "Marketing",
}

_TAP_FORMATS = ("choice", "spot", "order")


def init_book_test_prompt() -> None:
    global _prompt_template
    _prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")
    logger.info("Loaded book_test prompt template")


def book_label(book: str) -> str:
    return _BOOK_LABELS.get(book, book.replace("_", " ").title())


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


def parse_test_unit_arg(args: list[str] | None) -> str | None:
    """Return unit_number string from `/test unit N`, or None for bare /test."""
    if not args:
        return None
    if args[0].lower() != "unit":
        # Allow `/test 12` as a convenience — still a string, never int().
        return " ".join(args).strip() or None
    rest = " ".join(args[1:]).strip()
    return rest or None


def _unit_button_label(unit_number: str, *, book: str | None = None) -> str:
    if book:
        label = f"U{unit_number} {book_label(book)}"
    else:
        label = texts.BTN_TEST_UNIT_PREFIX.format(unit=unit_number)
    if len(label) > _MAX_BUTTON_LABEL_CHARS:
        label = label[:_MAX_BUTTON_LABEL_CHARS]
    return label


def _available_units_text(units: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    seen: set[tuple[str, str]] = set()
    for u in units:
        key = (str(u["book"]), str(u["unit_number"]))
        if key in seen:
            continue
        seen.add(key)
        parts.append(f"{key[1]} ({book_label(key[0])})")
    return ", ".join(parts) if parts else "(none)"


def _units_keyboard(units: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    """One button per (book, unit). Short labels; details stay in the body."""
    items: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    multi_book = len({str(u["book"]) for u in units}) > 1
    for u in units:
        book = str(u["book"])
        num = str(u["unit_number"])
        key = (book, num)
        if key in seen:
            continue
        seen.add(key)
        label = _unit_button_label(num, book=book if multi_book else None)
        cb = f"btest:go:{book}:{num}"
        items.append((label, cb))
    rows = layout_buttons(items, max_per_row=2)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=cb) for label, cb in row]
            for row in rows
        ]
    )


def _books_keyboard(unit_number: str, books: list[str]) -> InlineKeyboardMarkup:
    items = [
        (_clip_label(book_label(b)), f"btest:go:{b}:{unit_number}") for b in books
    ]
    rows = layout_buttons(items, max_per_row=2)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=cb) for label, cb in row]
            for row in rows
        ]
    )


def _clip_label(label: str) -> str:
    return label if len(label) <= _MAX_BUTTON_LABEL_CHARS else label[:_MAX_BUTTON_LABEL_CHARS]


def plan_tap_formats(n: int) -> list[str]:
    """Tap-only mix for /test — never gap."""
    if n <= 0:
        return []
    out: list[str] = []
    for i in range(n):
        cand = _TAP_FORMATS[i % 3]
        if len(out) >= 2 and out[-1] == cand and out[-2] == cand:
            for alt in _TAP_FORMATS:
                if alt != cand:
                    cand = alt
                    break
        out.append(cand)
    return out


def _build_book_test_questions(
    user_id: int,
    *,
    book: str,
    unit_number: str,
    unit_title: str,
    items: list[str],
    chat_fn: Any = None,
) -> tuple[list[dict], str]:
    user = get_user(user_id)
    if user is None:
        raise RuntimeError(f"book_test: missing user {user_id}")
    if _prompt_template is None:
        init_book_test_prompt()
    assert _prompt_template is not None

    n = len(items)
    formats = plan_tap_formats(n)
    payload = [
        {
            "source": "book",
            "target_item": item,
            "format": formats[i] if i < len(formats) else "choice",
        }
        for i, item in enumerate(items)
    ]
    system = _prompt_template.format(
        cefr_level=user.cefr_level,
        native_language=user.native_language,
        work_domain=user.work_domain or "everyday life",
        book_label=book_label(book),
        unit_number=unit_number,
        unit_title=unit_title or unit_number,
        error_type_list=error_type_list_text(),
        target_items_json=json.dumps(payload, ensure_ascii=False),
    )
    call = chat_fn or chat
    result = call(
        [{"role": "user", "content": "Generate the unit practice questions."}],
        system=system,
        json_mode=True,
        max_tokens=2500,
    )
    if not isinstance(result, dict):
        raise LLMError("book_test response was not a JSON object")
    scenario = str(result.get("scenario") or "").strip()
    questions = list(result.get("questions") or [])
    cleaned: list[dict] = []
    for i, target in enumerate(items):
        q = questions[i] if i < len(questions) else {}
        if not isinstance(q, dict):
            q = {}
        fmt = formats[i] if i < len(formats) else "choice"
        if fmt not in _TAP_FORMATS:
            fmt = "choice"
        # Hard: never allow gap on /test.
        if str(q.get("format") or "") == "gap":
            fmt = "choice"
        item = _clean_question_fields(
            q,
            fmt=fmt,
            fallback_answer=target,
            fallback_correction=target,
        )
        code = str(q.get("error_type") or "").strip()
        expl = str(q.get("explanation") or "").strip()
        item.update(
            {
                "source": "book",
                "book": book,
                "unit_number": unit_number,
                "unit_title": unit_title,
                "target_item": target,
                "error_type": code,
                "error_type_label": (
                    error_type_label(code) if code else unit_title
                ),
                "explanation": expl,
            }
        )
        cleaned.append(item)
    return cleaned, scenario


async def _start_unit_test(
    *,
    bot: Any,
    user_id: int,
    chat_id: int,
    book: str,
    unit_number: str,
    unit_title: str,
    reply_to: Any | None = None,
    now: datetime | None = None,
    chat_fn: Any = None,
) -> None:
    abandon_open_book_tests(user_id)
    items = teachable_items_for_unit(user_id, book, unit_number)[:5]
    if not items:
        body = texts.TEST_NO_ITEMS.format(unit=html.escape(unit_number))
        if reply_to is not None:
            await reply_to.reply_text(body)
        else:
            await bot.send_message(chat_id=chat_id, text=body)
        return

    try:
        questions, scenario = await asyncio.to_thread(
            _build_book_test_questions,
            user_id,
            book=book,
            unit_number=unit_number,
            unit_title=unit_title,
            items=items,
            chat_fn=chat_fn,
        )
    except (LLMError, Exception):
        logger.exception(
            "book_test generation failed user_id=%s handler=%s",
            user_id,
            HANDLER_NAME,
        )
        body = texts.TEST_FAILED
        if reply_to is not None:
            await reply_to.reply_text(body)
        else:
            await bot.send_message(chat_id=chat_id, text=body)
        return

    if not questions:
        body = texts.TEST_FAILED
        if reply_to is not None:
            await reply_to.reply_text(body)
        else:
            await bot.send_message(chat_id=chat_id, text=body)
        return

    when = now or datetime.now(timezone.utc)
    day = local_today(_user_timezone(user_id), when)
    payload: dict[str, Any] = {
        "index": 0,
        "correct_count": 0,
        "answered": 0,
        "questions": questions,
        "scenario": scenario,
        "chat_id": chat_id,
        "message_id": None,
        "book": book,
        "unit_number": unit_number,
        "callback_prefix": "btest",
    }
    session_id = insert_session(
        user_id, "book_test", day, payload=payload, completed=False
    )
    payload["session_id"] = session_id
    q0 = questions[0]
    markup = _keyboard_for_question(q0, payload, callback_prefix="btest")
    text = _question_text(payload)
    msg = await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=markup,
        parse_mode=ParseMode.HTML,
    )
    # User-initiated — do not increment bot_message_counts.
    payload["message_id"] = msg.message_id
    update_session_payload(session_id, payload)


async def handle_test_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None or update.effective_user is None:
        return
    user_id = update.effective_user.id
    if get_user(user_id) is None:
        return

    unit_arg = parse_test_unit_arg(list(context.args or []))
    units = list_units_for_user(user_id)

    if unit_arg is None:
        if not units:
            await update.message.reply_text(texts.TEST_EMPTY)
            return
        body_lines = [texts.TEST_LIST, ""]
        seen: set[tuple[str, str]] = set()
        for u in units:
            key = (str(u["book"]), str(u["unit_number"]))
            if key in seen:
                continue
            seen.add(key)
            title = str(u.get("unit_title") or "").strip()
            line = f"• {key[1]} — {book_label(key[0])}"
            if title:
                line += f" ({title})"
            body_lines.append(line)
        await update.message.reply_text(
            "\n".join(body_lines),
            reply_markup=_units_keyboard(units),
        )
        return

    matches = find_units_by_number(user_id, unit_arg)
    if not matches:
        if units:
            await update.message.reply_text(
                texts.TEST_UNKNOWN.format(
                    unit=unit_arg,
                    available=_available_units_text(units),
                )
            )
        else:
            await update.message.reply_text(
                texts.TEST_UNKNOWN_NONE.format(unit=unit_arg)
            )
        return

    books = list(dict.fromkeys(str(m["book"]) for m in matches))
    if len(books) > 1:
        await update.message.reply_text(
            texts.TEST_WHICH_BOOK.format(unit=unit_arg),
            reply_markup=_books_keyboard(unit_arg, books),
        )
        return

    row = matches[0]
    await _start_unit_test(
        bot=context.bot,
        user_id=user_id,
        chat_id=update.effective_chat.id if update.effective_chat else user_id,
        book=str(row["book"]),
        unit_number=str(row["unit_number"]),
        unit_title=str(row.get("unit_title") or ""),
        reply_to=update.message,
    )


async def on_book_test_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None or query.message is None:
        return
    await query.answer()
    data = query.data or ""
    if not data.startswith("btest:"):
        return
    user_id = update.effective_user.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    if data.startswith("btest:go:"):
        # btest:go:{book}:{unit_number} — unit_number may contain '-'
        rest = data[len("btest:go:") :]
        book, sep, unit_number = rest.partition(":")
        if not sep or not book or not unit_number:
            return
        matches = find_units_by_number(user_id, unit_number)
        row = next(
            (m for m in matches if str(m["book"]) == book),
            None,
        )
        if row is None:
            await query.message.reply_text(
                texts.TEST_UNKNOWN.format(
                    unit=unit_number,
                    available=_available_units_text(list_units_for_user(user_id)),
                )
            )
            return
        await _start_unit_test(
            bot=context.bot,
            user_id=user_id,
            chat_id=chat_id,
            book=book,
            unit_number=unit_number,
            unit_title=str(row.get("unit_title") or ""),
        )
        return

    session = get_book_test_session_by_message(user_id, chat_id, message_id)
    if session is None or not session.payload:
        return
    payload = dict(session.payload)
    questions = payload.get("questions") or []
    index = int(payload.get("index", 0))
    if index >= len(questions):
        return
    q = questions[index]
    parts = data.split(":")

    if data.startswith("btest:opt:") and q.get("format") in ("choice", "order"):
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

    if data.startswith("btest:stile:") and q.get("format") == "spot":
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


def all_s6a_button_labels(
    *,
    unit_numbers: list[str] | None = None,
    books: list[str] | None = None,
) -> list[str]:
    """Labels used by S6a keyboards — for the ≤20-char audit."""
    labels = [str(i + 1) for i in range(4)]
    for n in unit_numbers or ["12", "12A", "101-102"]:
        labels.append(_unit_button_label(n))
        labels.append(_unit_button_label(n, book="murphy"))
    for b in books or list(_BOOK_LABELS):
        labels.append(_clip_label(book_label(b)))
    return labels


def build_book_test_handlers() -> tuple:
    """Return (command_handler, callback_handler). Callbacks only — no text."""
    return (
        CommandHandler("test", handle_test_command),
        CallbackQueryHandler(on_book_test_callback, pattern=r"^btest:"),
    )
