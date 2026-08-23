""" /book — photograph textbook pages → vision OCR → book_units (S6).

Album-aware debounce (cancel-then-reschedule). Conversation ends via Done
callback — JobQueue cannot return ConversationHandler.END. After a batch,
``collecting`` gates late photos; ``conversation_timeout`` clears abandoned
sessions without poking PTB internals.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from app import texts
from app.config import load_settings
from app.llm import LLMError
from app.services.books import (
    MAX_PAGES_PER_BATCH,
    MergedUnit,
    PageFailure,
    build_summary_text,
    merge_page_results,
    ocr_one_page,
    parse_ocr_payload,
    persist_units,
    preset_book_slug,
    slugify_book_name,
)
from app.services.reading import normalize_for_match
from app.services.shared_content import record_and_fanout_book_units
from app.services.users import is_registered

logger = logging.getLogger(__name__)

ASK_BOOK, ASK_BOOK_OTHER, COLLECT_PAGES = range(3)

_SESSION_KEY = "book"
_DEBOUNCE_SECONDS = 2.5
_CHAT_ACTION_INTERVAL_SECONDS = 4.0


def _shared_book_slug_set() -> set[str]:
    return {
        normalize_for_match(s)
        for s in load_settings().shared_book_slugs
        if s.strip()
    }


def _maybe_fanout_shared_book(
    user_id: int, book: str, units: list[MergedUnit]
) -> None:
    """Fan out operator uploads of configured shared books; else log and stay personal."""
    if not units:
        return
    settings = load_settings()
    operator_id = settings.operator_telegram_id
    shared = _shared_book_slug_set()
    book_norm = normalize_for_match(book)

    if operator_id is None or user_id != operator_id:
        return
    if book_norm not in shared:
        logger.info(
            "book stay_personal user_id=%s book=%s reason=slug_not_in_SHARED_BOOK_SLUGS "
            "configured=%s",
            user_id,
            book,
            sorted(shared),
        )
        return
    stats = record_and_fanout_book_units(
        book, units, created_by=user_id
    )
    logger.info(
        "book shared_fanout user_id=%s book=%s units=%s users_reached=%s",
        user_id,
        book,
        len(units),
        stats.users_reached,
    )
CONVERSATION_TIMEOUT_SECONDS = 3600.0
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "book_ocr.txt"
_prompt_template: str | None = None

HANDLER_NAME = "book"


def init_book_prompt() -> None:
    """Load the book OCR system prompt from disk (call once at boot)."""
    global _prompt_template
    _prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")


def _system_prompt() -> str:
    if _prompt_template is None:
        init_book_prompt()
    assert _prompt_template is not None
    return _prompt_template


def debounce_job_name(user_id: int) -> str:
    return f"book_debounce:{user_id}"


def book_choice_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                texts.BTN_BOOK_MURPHY, callback_data="book:pick:murphy"
            ),
            InlineKeyboardButton(
                texts.BTN_BOOK_VOCAB, callback_data="book:pick:vocabulary_in_use"
            ),
        ],
        [
            InlineKeyboardButton(
                texts.BTN_BOOK_MARKETING, callback_data="book:pick:marketing"
            ),
            InlineKeyboardButton(
                texts.BTN_BOOK_OTHER, callback_data="book:pick:other"
            ),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def summary_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    texts.BTN_BOOK_DONE, callback_data="book:after:done"
                ),
                InlineKeyboardButton(
                    texts.BTN_BOOK_ADD_MORE, callback_data="book:after:more"
                ),
            ]
        ]
    )


def all_book_button_labels() -> list[str]:
    """Every S6 button label — for ≤20-char tests."""
    return [
        texts.BTN_BOOK_MURPHY,
        texts.BTN_BOOK_VOCAB,
        texts.BTN_BOOK_MARKETING,
        texts.BTN_BOOK_OTHER,
        texts.BTN_BOOK_DONE,
        texts.BTN_BOOK_ADD_MORE,
    ]


def _session(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    data = context.user_data.setdefault(_SESSION_KEY, {})
    if not isinstance(data, dict):
        data = {}
        context.user_data[_SESSION_KEY] = data
    return data


def _clear_session(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(_SESSION_KEY, None)


def _cancel_debounce(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    jq = context.job_queue
    if jq is None:
        return
    name = debounce_job_name(user_id)
    for job in jq.get_jobs_by_name(name):
        job.schedule_removal()


def _schedule_debounce(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
    chat_id: int,
) -> None:
    jq = context.job_queue
    if jq is None:
        logger.error(
            "book debounce: no job_queue user_id=%s handler=%s",
            user_id,
            HANDLER_NAME,
        )
        return
    name = debounce_job_name(user_id)
    for job in jq.get_jobs_by_name(name):
        job.schedule_removal()
    jq.run_once(
        process_pages,
        when=_DEBOUNCE_SECONDS,
        name=name,
        data={"user_id": user_id, "chat_id": chat_id},
        chat_id=chat_id,
        user_id=user_id,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END
    user_id = update.effective_user.id
    if not is_registered(user_id):
        return ConversationHandler.END

    _cancel_debounce(context, user_id)
    _clear_session(context)
    sess = _session(context)
    sess["collecting"] = False
    sess["processing"] = False
    sess["pages"] = []
    sess["over_cap"] = False

    await update.message.reply_text(
        texts.BOOK_ASK_WHICH,
        reply_markup=book_choice_keyboard(),
    )
    return ASK_BOOK


async def pick_book(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return ASK_BOOK
    await query.answer()

    key = query.data.removeprefix("book:pick:")
    if key == "other":
        await query.edit_message_text(texts.BOOK_ASK_OTHER)
        return ASK_BOOK_OTHER

    slug = preset_book_slug(key)
    if slug is None:
        await query.edit_message_text(texts.BOOK_ASK_WHICH, reply_markup=book_choice_keyboard())
        return ASK_BOOK

    sess = _session(context)
    sess["book"] = slug
    sess["collecting"] = True
    sess["pages"] = []
    sess["over_cap"] = False
    await query.edit_message_text(texts.BOOK_ASK_PAGES)
    return COLLECT_PAGES


async def receive_other_book(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return ASK_BOOK_OTHER
    slug = slugify_book_name(update.message.text)
    if not slug:
        await update.message.reply_text(texts.BOOK_INVALID_OTHER)
        return ASK_BOOK_OTHER

    sess = _session(context)
    sess["book"] = slug
    sess["collecting"] = True
    sess["pages"] = []
    sess["over_cap"] = False
    await update.message.reply_text(texts.BOOK_ASK_PAGES)
    return COLLECT_PAGES


def _extract_page_from_message(message: Any) -> tuple[str, str | None] | None:
    """Return (file_id, mime_type) for a photo or image document."""
    if message.photo:
        # Largest size last.
        photo = message.photo[-1]
        return photo.file_id, "image/jpeg"
    doc = message.document
    if doc is None:
        return None
    mime = (doc.mime_type or "").lower()
    if not mime.startswith("image/"):
        return None
    return doc.file_id, mime or None


async def collect_page(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return COLLECT_PAGES

    sess = _session(context)
    if not sess.get("collecting"):
        await message.reply_text(texts.BOOK_NUDGE_AWAITING)
        return COLLECT_PAGES

    extracted = _extract_page_from_message(message)
    if extracted is None:
        return COLLECT_PAGES

    file_id, mime_type = extracted
    pages: list[dict[str, Any]] = sess.setdefault("pages", [])
    if len(pages) >= MAX_PAGES_PER_BATCH:
        sess["over_cap"] = True
        # Still refresh debounce so a trailing album finishes processing.
        _schedule_debounce(context, user_id=user.id, chat_id=message.chat_id)
        return COLLECT_PAGES

    batch_index = len(pages) + 1
    pages.append(
        {
            "batch_index": batch_index,
            "file_id": file_id,
            "mime_type": mime_type,
            "media_group_id": message.media_group_id,
        }
    )
    sess["pages"] = pages
    _schedule_debounce(context, user_id=user.id, chat_id=message.chat_id)
    return COLLECT_PAGES


async def after_batch_choice(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        return COLLECT_PAGES
    await query.answer()

    user_id = update.effective_user.id
    action = query.data.removeprefix("book:after:")

    if action == "done":
        _cancel_debounce(context, user_id)
        _clear_session(context)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except BadRequest:
            pass
        return ConversationHandler.END

    if action == "more":
        sess = _session(context)
        sess["pages"] = []
        sess["over_cap"] = False
        sess["collecting"] = True
        sess["processing"] = False
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except BadRequest:
            pass
        if query.message is not None:
            await query.message.reply_text(texts.BOOK_ASK_PAGES)
        return COLLECT_PAGES

    return COLLECT_PAGES


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user is not None:
        _cancel_debounce(context, user.id)
    _clear_session(context)
    if update.message is not None:
        await update.message.reply_text(texts.BOOK_CANCELLED)
    return ConversationHandler.END


async def on_conversation_timeout(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Clear abandoned /book session state when conversation_timeout fires."""
    user = update.effective_user
    if user is not None:
        _cancel_debounce(context, user.id)
    _clear_session(context)
    return ConversationHandler.END


async def _repeat_typing(bot: Any, chat_id: int) -> None:
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(_CHAT_ACTION_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        raise


async def _edit_status(
    bot: Any, chat_id: int, message_id: int, text: str
) -> None:
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text
        )
    except BadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        raise


async def _delete_status(bot: Any, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except BadRequest:
        logger.debug(
            "status delete failed chat_id=%s message_id=%s",
            chat_id,
            message_id,
        )


async def process_pages(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback: OCR popped pages, upsert, send summary + Done/Add more."""
    job = context.job
    if job is None or job.data is None:
        return
    data = job.data
    user_id = int(data["user_id"])
    chat_id = int(data["chat_id"])

    # user_data on JobQueue callbacks is the triggering user's user_data when
    # user_id was passed to run_once.
    sess = context.user_data.get(_SESSION_KEY)
    if not isinstance(sess, dict):
        return

    if sess.get("processing"):
        return

    pages_raw = sess.get("pages") or []
    # Pop in one step so a racing second job sees an empty list.
    sess["pages"] = []
    if not pages_raw:
        return

    sess["processing"] = True
    sess["collecting"] = False
    over_cap = bool(sess.get("over_cap"))
    book = str(sess.get("book") or "")
    if not book:
        sess["processing"] = False
        logger.warning(
            "book process missing book slug user_id=%s handler=%s",
            user_id,
            HANDLER_NAME,
        )
        return

    bot = context.bot
    status_id: int | None = None
    typing_task: asyncio.Task[None] | None = None

    try:
        status_msg = await bot.send_message(
            chat_id=chat_id, text=texts.BOOK_STATUS_READING
        )
        status_id = int(status_msg.message_id)
        typing_task = asyncio.create_task(_repeat_typing(bot, chat_id))

        system = _system_prompt()
        page_payloads: list[tuple[int, dict[str, Any] | PageFailure | Exception]] = []

        for entry in pages_raw:
            batch_index = int(entry["batch_index"])
            file_id = str(entry["file_id"])
            try:
                tg_file = await bot.get_file(file_id)
                image_buf = await tg_file.download_as_bytearray()
                image_bytes = bytes(image_buf)
                raw = await asyncio.to_thread(
                    ocr_one_page,
                    image_bytes,
                    system=system,
                )
                parsed = parse_ocr_payload(
                    raw, batch_index=batch_index, user_id=user_id
                )
                page_payloads.append((batch_index, parsed))
            except LLMError as exc:
                page_payloads.append((batch_index, exc))
            except Exception as exc:  # noqa: BLE001 — page-level soft failure
                logger.warning(
                    "book page download/OCR failed user_id=%s page=%s error=%s",
                    user_id,
                    batch_index,
                    exc,
                )
                page_payloads.append((batch_index, exc))

        units, failures = merge_page_results(page_payloads, user_id=user_id)

        if status_id is not None:
            await _edit_status(bot, chat_id, status_id, texts.BOOK_STATUS_SAVING)

        written = await asyncio.to_thread(persist_units, user_id, book, units)

        await asyncio.to_thread(
            _maybe_fanout_shared_book, user_id, book, units
        )

        logger.info(
            "book batch user_id=%s pages=%s units_written=%s pages_failed=%s",
            user_id,
            len(pages_raw),
            written,
            len(failures),
        )

        summary = build_summary_text(
            book=book,
            units=units,
            failures=failures,
            over_cap=over_cap,
            texts_module=texts,
        )

        if status_id is not None:
            await _delete_status(bot, chat_id, status_id)
            status_id = None

        await bot.send_message(
            chat_id=chat_id,
            text=summary,
            reply_markup=summary_keyboard(),
        )
        sess["over_cap"] = False
    except Exception:
        logger.exception(
            "book process failed user_id=%s handler=%s",
            user_id,
            HANDLER_NAME,
        )
        try:
            await bot.send_message(chat_id=chat_id, text=texts.BOOK_PROCESS_FAILED)
        except Exception:  # noqa: BLE001
            pass
    finally:
        if typing_task is not None:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass
        if status_id is not None:
            await _delete_status(bot, chat_id, status_id)
        sess["processing"] = False


def _button_conversation(
    name: str,
    callback: Any,
    pattern: str,
    map_to_parent: dict[object, object],
) -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(callback, pattern=pattern)],
        states={},
        fallbacks=[],
        per_message=True,
        map_to_parent=map_to_parent,
        name=name,
        persistent=False,
        allow_reentry=True,
    )


def build_book_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("book", start)],
        states={
            ASK_BOOK: [
                _button_conversation(
                    "book_pick",
                    pick_book,
                    r"^book:pick:",
                    {
                        ASK_BOOK: ASK_BOOK,
                        ASK_BOOK_OTHER: ASK_BOOK_OTHER,
                        COLLECT_PAGES: COLLECT_PAGES,
                        ConversationHandler.END: ConversationHandler.END,
                    },
                ),
            ],
            ASK_BOOK_OTHER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_other_book),
            ],
            COLLECT_PAGES: [
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE,
                    collect_page,
                ),
                _button_conversation(
                    "book_after",
                    after_batch_choice,
                    r"^book:after:",
                    {
                        COLLECT_PAGES: COLLECT_PAGES,
                        ConversationHandler.END: ConversationHandler.END,
                    },
                ),
            ],
            # TypeHandler matches message or callback last-update without a
            # CallbackQueryHandler on the per_message=False parent (S1a).
            ConversationHandler.TIMEOUT: [
                TypeHandler(Update, on_conversation_timeout),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="book",
        persistent=False,
        allow_reentry=True,
        per_message=False,
        conversation_timeout=CONVERSATION_TIMEOUT_SECONDS,
    )


__all__ = [
    "ASK_BOOK",
    "ASK_BOOK_OTHER",
    "COLLECT_PAGES",
    "CONVERSATION_TIMEOUT_SECONDS",
    "all_book_button_labels",
    "book_choice_keyboard",
    "build_book_handler",
    "collect_page",
    "debounce_job_name",
    "init_book_prompt",
    "on_conversation_timeout",
    "process_pages",
    "start",
    "summary_keyboard",
]
