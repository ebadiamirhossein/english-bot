"""Telegram document CSV import (S15b).

User-initiated — does not increment ``bot_message_counts``. Independent of
``WATCH_DIR``. Downloads to memory only; never writes the upload to disk.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app import texts
from app.services.alerts import notify_operator
from app.services.users import is_registered
from app.services.watch_import import (
    CSV_IMPORT_MAX_BYTES,
    import_csv_bytes,
)

logger = logging.getLogger(__name__)

HANDLER_NAME = "csv_import"

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
        # Size missing on the Document, or lied — still refuse in memory.
        logger.info(
            "csv import refuse_size_after_dl user_id=%s file=%s size=%s",
            user_id,
            filename,
            len(data),
        )
        await message.reply_text(texts.IMPORT_DOC_TOO_LARGE)
        return

    try:
        result = import_csv_bytes(
            data, user_id=user_id, filename=filename, now=now
        )
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

    if result.status == "failed_headers":
        await notify_operator(
            context.application,
            key=f"csv_headers:{user_id}:{filename}",
            text=(
                f"telegram csv failed_headers user_id={user_id} "
                f"file={filename} headers={list(result.headers_seen)}"
            ),
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


def build_csv_import_handlers() -> tuple[MessageHandler, MessageHandler]:
    """Return (csv_handler, non_csv_handler) for private-chat documents."""
    return (
        MessageHandler(_CSV_FILTER, on_csv_document),
        MessageHandler(_NON_CSV_FILTER, on_non_csv_document),
    )


__all__ = [
    "build_csv_import_handlers",
    "on_csv_document",
    "on_non_csv_document",
]
