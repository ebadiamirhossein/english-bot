"""Telegram document CSV import (S15b) + slang Share (S24) + vocabulary (S24a).

User-initiated — does not increment ``bot_message_counts``. Independent of
``WATCH_DIR``. Downloads to memory only; never writes the upload to disk.

Slang Share uses CallbackQueryHandler only — no MessageHandler /
ConversationHandler (free text must still reach M2).

Vocabulary (Trancy Word/Phonetic/Translation/Date) is sender-only: no Share
keyboard, no shared_content. LLM sentence generation runs via
``asyncio.to_thread`` through ``vocab_import`` (this handler never imports
the LLM wrapper module directly).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from apps.bot import texts
from core.db import connection
from apps.bot.alerts import operator_send
from core.services.alerts import notify_operator
from core.services.chunks import count_due_chunks, insert_chunks
from core.services.reading import normalize_for_match
from core.services.shared_content import record_and_fanout_chunks
from core.services.users import get_user, is_registered
from core.services.vocab_import import (
    VocabGenerationError,
    format_vocab_import_reply,
    persist_vocabulary_and_send,
    prepare_vocabulary_import,
)
from core.services.watch_import import (
    CSV_IMPORT_MAX_BYTES,
    classify_csv_format,
    import_csv_bytes,
    parse_csv_bytes,
    parse_slang_chunk_items,
)

logger = logging.getLogger(__name__)

HANDLER_NAME = "csv_import"
_SHARE_PENDING_KEY = "share_slang_pending"

# Book COLLECT_PAGES accepts Document.IMAGE only — CSV never matches it.
# Non-CSV replies exclude IMAGE so mid-/book page scans still reach book.
_CSV_FILTER = (
    filters.Document.FileExtension("csv") & filters.ChatType.PRIVATE
)
_NON_CSV_FILTER = (
    filters.Document.ALL
    & ~filters.Document.IMAGE
    & ~filters.Document.FileExtension("csv")
    & filters.ChatType.PRIVATE
)


def _share_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    texts.BTN_SHARE_SLANG_ALL, callback_data="share:slang:yes"
                ),
                InlineKeyboardButton(
                    texts.BTN_SHARE_SLANG_ME, callback_data="share:slang:no"
                ),
            ]
        ]
    )


def s24_share_button_labels() -> list[str]:
    return [texts.BTN_SHARE_SLANG_ALL, texts.BTN_SHARE_SLANG_ME]


def _failed_headers_log_line(
    *, user_id: int, filename: str, headers: list[str]
) -> str:
    """Stable operator log line — do not change wording without cause."""
    return (
        f"telegram csv failed_headers user_id={user_id} "
        f"file={filename} headers={headers}"
    )


async def _alert_failed_headers(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
    filename: str,
    headers: list[str],
    now: datetime,
) -> None:
    log_line = _failed_headers_log_line(
        user_id=user_id, filename=filename, headers=headers
    )
    logger.warning("%s", log_line)
    await notify_operator(
        operator_send(context.bot),
        key=f"csv_headers:{user_id}:{filename}",
        text=texts.OPERATOR_CSV_FAILED_HEADERS.format(
            user_id=user_id,
            filename=filename,
            headers=headers,
        ),
        now=now,
    )


async def on_csv_document(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    user = update.effective_user
    if message is None or user is None or message.document is None:
        return
    user_id = int(user.id)
    if not is_registered(user_id):
        return

    doc = message.document
    filename = doc.file_name or "export.csv"
    size = doc.file_size
    if size is not None and size > CSV_IMPORT_MAX_BYTES:
        logger.info(
            "csv import refuse_size user_id=%s file=%s size=%s max=%s",
            user_id,
            filename,
            size,
            CSV_IMPORT_MAX_BYTES,
        )
        await message.reply_text(texts.IMPORT_DOC_TOO_LARGE)
        return

    now = datetime.now(timezone.utc)
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        data = bytes(await tg_file.download_as_bytearray())
    except Exception:
        logger.exception(
            "csv import download failed user_id=%s file=%s handler=%s",
            user_id,
            filename,
            HANDLER_NAME,
        )
        await message.reply_text(texts.IMPORT_DOC_READ_FAILED)
        return

    if len(data) > CSV_IMPORT_MAX_BYTES:
        logger.info(
            "csv import refuse_size_after_dl user_id=%s file=%s size=%s",
            user_id,
            filename,
            len(data),
        )
        await message.reply_text(texts.IMPORT_DOC_TOO_LARGE)
        return

    try:
        headers, rows = parse_csv_bytes(data)
    except UnicodeDecodeError:
        logger.warning(
            "csv import decode_failed user_id=%s file=%s",
            user_id,
            filename,
        )
        await message.reply_text(texts.IMPORT_DOC_READ_FAILED)
        return
    except Exception:
        logger.exception(
            "csv import error user_id=%s file=%s handler=%s",
            user_id,
            filename,
            HANDLER_NAME,
        )
        await message.reply_text(texts.IMPORT_DOC_READ_FAILED)
        return

    fmt = classify_csv_format(headers)
    if fmt is None:
        await _alert_failed_headers(
            context,
            user_id=user_id,
            filename=filename,
            headers=list(headers),
            now=now,
        )
        await message.reply_text(
            texts.IMPORT_DOC_FAILED_HEADERS.format(filename=filename)
        )
        return

    if fmt == "slang":
        try:
            items, invalid = parse_slang_chunk_items(headers, rows)
        except ValueError:
            await message.reply_text(
                texts.IMPORT_DOC_FAILED_HEADERS.format(filename=filename)
            )
            return
        context.user_data[_SHARE_PENDING_KEY] = {
            "items": items,
            "rejected": invalid,
            "filename": filename,
        }
        await message.reply_text(
            texts.IMPORT_SLANG_CONFIRM.format(n=len(items)),
            reply_markup=_share_keyboard(),
        )
        return

    if fmt == "vocabulary":
        profile = get_user(user_id)
        if profile is None:
            return
        await context.bot.send_chat_action(
            chat_id=message.chat_id, action=ChatAction.TYPING
        )
        try:
            chunks, counts = await asyncio.to_thread(
                prepare_vocabulary_import,
                headers,
                rows,
                user_id=user_id,
                cefr_level=profile.cefr_level,
                work_domain=profile.work_domain or "",
                now=now.date(),
            )
        except VocabGenerationError:
            logger.exception(
                "csv import vocab_llm_failed user_id=%s file=%s handler=%s",
                user_id,
                filename,
                HANDLER_NAME,
            )
            await notify_operator(
                operator_send(context.bot),
                key=f"csv_vocab_llm:{user_id}:{filename}",
                text=texts.OPERATOR_CSV_VOCAB_LLM_FAILED.format(
                    user_id=user_id,
                    filename=filename,
                ),
                now=now,
            )
            await message.reply_text(texts.IMPORT_DOC_VOCAB_LLM_FAILED)
            return
        except Exception:
            logger.exception(
                "csv import vocab_error user_id=%s file=%s handler=%s",
                user_id,
                filename,
                HANDLER_NAME,
            )
            await message.reply_text(texts.IMPORT_DOC_READ_FAILED)
            return

        body = format_vocab_import_reply(counts)

        async def _send() -> None:
            await message.reply_text(body)

        try:
            await persist_vocabulary_and_send(
                user_id=user_id,
                chunks=chunks,
                send=_send,
            )
        except Exception:
            logger.exception(
                "csv import vocab_persist user_id=%s file=%s handler=%s",
                user_id,
                filename,
                HANDLER_NAME,
            )
            await message.reply_text(texts.IMPORT_DOC_READ_FAILED)
        return

    # Trancy-legacy / Language Reactor — sender-only (never share).
    try:
        result = import_csv_bytes(
            data, user_id=user_id, filename=filename, now=now, tool=fmt
        )
    except Exception:
        logger.exception(
            "csv import error user_id=%s file=%s handler=%s",
            user_id,
            filename,
            HANDLER_NAME,
        )
        await message.reply_text(texts.IMPORT_DOC_READ_FAILED)
        return

    if result.status == "failed_headers":
        await _alert_failed_headers(
            context,
            user_id=user_id,
            filename=filename,
            headers=list(result.headers_seen),
            now=now,
        )
        await message.reply_text(
            texts.IMPORT_DOC_FAILED_HEADERS.format(filename=filename)
        )
        return

    due = result.due_after if result.due_after is not None else 0
    await message.reply_text(
        texts.IMPORT_DOC_RESULT.format(
            imported=result.imported,
            duplicates=result.duplicates,
            invalid=result.invalid,
            due=due,
        )
    )


async def on_share_slang_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or query.data is None or user is None:
        return
    await query.answer()
    user_id = int(user.id)
    if not is_registered(user_id):
        return

    pending = context.user_data.get(_SHARE_PENDING_KEY)
    if not isinstance(pending, dict) or "items" not in pending:
        try:
            await query.edit_message_text(texts.IMPORT_SHARE_STALE)
        except Exception:
            if query.message is not None:
                await query.message.reply_text(texts.IMPORT_SHARE_STALE)
        return

    items = list(pending.get("items") or [])
    rejected = int(pending.get("rejected") or 0)
    context.user_data.pop(_SHARE_PENDING_KEY, None)

    now = datetime.now(timezone.utc)
    share = query.data == "share:slang:yes"

    if share:
        # Fan-out only — does not also run sender-only insert.
        stats = record_and_fanout_chunks(
            items, created_by=user_id, source="slang", rejected=rejected
        )
        due = count_due_chunks(user_id, now=now.date())
        body = texts.IMPORT_SHARE_RESULT.format(
            imported=stats.imported,
            duplicates=stats.duplicates,
            rejected=stats.rejected,
            users_reached=stats.users_reached,
            due=due,
        )
    else:
        imported, duplicates = _insert_slang_sender_only(user_id, items)
        due = count_due_chunks(user_id, now=now.date())
        body = texts.IMPORT_DOC_RESULT.format(
            imported=imported,
            duplicates=duplicates,
            invalid=rejected,
            due=due,
        )

    try:
        await query.edit_message_text(body)
    except Exception:
        if query.message is not None:
            await query.message.reply_text(body)


async def on_share_orphan_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Warm-degrade orphan ``share:`` taps after restart (no pending payload)."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    try:
        await query.edit_message_text(texts.IMPORT_SHARE_STALE)
    except Exception:
        if query.message is not None:
            await query.message.reply_text(texts.IMPORT_SHARE_STALE)


def _insert_slang_sender_only(
    user_id: int, items: list[dict[str, str]]
) -> tuple[int, int]:
    """Just-me path: insert slang chunks for sender only (no ledger)."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT chunk FROM chunks WHERE user_id = %s",
            (user_id,),
        ).fetchall()
        existing = {
            normalize_for_match(str(r["chunk"])) for r in rows if r["chunk"]
        }
        to_insert: list[dict[str, str]] = []
        duplicates = 0
        for item in items:
            key = normalize_for_match(item["chunk"])
            if not key or key in existing:
                duplicates += 1
                continue
            existing.add(key)
            to_insert.append(item)
        if to_insert:
            with conn.transaction():
                insert_chunks(
                    conn,
                    user_id,
                    source="slang",
                    track=None,
                    chunks=to_insert,
                )
        return len(to_insert), duplicates


async def on_non_csv_document(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return
    if not is_registered(int(user.id)):
        return
    await message.reply_text(texts.IMPORT_DOC_NOT_CSV)


def build_csv_import_handlers() -> tuple[
    MessageHandler, MessageHandler, CallbackQueryHandler, CallbackQueryHandler
]:
    """Return (csv, non_csv, share_cb, share_orphan) handlers."""
    return (
        MessageHandler(_CSV_FILTER, on_csv_document),
        MessageHandler(_NON_CSV_FILTER, on_non_csv_document),
        CallbackQueryHandler(
            on_share_slang_callback, pattern=r"^share:slang:(yes|no)$"
        ),
        CallbackQueryHandler(on_share_orphan_callback, pattern=r"^share:"),
    )


__all__ = [
    "build_csv_import_handlers",
    "on_csv_document",
    "on_non_csv_document",
    "on_share_slang_callback",
    "on_share_orphan_callback",
    "s24_share_button_labels",
]
