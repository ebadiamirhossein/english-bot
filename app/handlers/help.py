"""``/help`` — grouped command map (S18b).

User-initiated: does not increment ``bot_message_counts``. Unregistered
users are ignored (ARCHITECTURE §7).
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app import texts
from app.services.users import is_registered
from app.services.watch_import import watch_dir_configured


def format_help_message(*, include_import: bool | None = None) -> str:
    """Build the scannable /help body. Pure — easy to assert in tests."""
    if include_import is None:
        include_import = bool(watch_dir_configured())

    sections: list[str] = [
        texts.HELP_HEADER,
        "",
        texts.HELP_SECTION_EVERY_DAY,
        texts.HELP_LINE_STATS,
        texts.HELP_LINE_QUIZ_ARRIVES,
        "",
        texts.HELP_SECTION_SPEAKING,
        texts.HELP_LINE_DIARY,
        texts.HELP_LINE_SHADOW,
        "",
        texts.HELP_SECTION_REAL_ENGLISH,
        texts.HELP_LINE_FORWARD,
        texts.HELP_LINE_CAPTURE,
        texts.HELP_LINE_PREP,
        texts.HELP_LINE_TYPE,
        "",
        texts.HELP_SECTION_BOOKS,
        texts.HELP_LINE_BOOK,
        texts.HELP_LINE_TEST,
        "",
        texts.HELP_SECTION_VOCAB,
        texts.HELP_LINE_ANKI,
        texts.HELP_LINE_CSV_UPLOAD,
    ]
    if include_import:
        sections.append(texts.HELP_LINE_IMPORT)
    sections.extend(
        [
            "",
            texts.HELP_SECTION_SETTINGS,
            texts.HELP_LINE_SETTINGS,
            texts.HELP_LINE_INTERESTS,
            texts.HELP_LINE_PAUSE,
        ]
    )
    return "\n".join(sections)


async def on_help_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None or update.effective_user is None:
        return
    if not is_registered(update.effective_user.id):
        return
    await update.message.reply_text(format_help_message())


def build_help_handler() -> CommandHandler:
    return CommandHandler("help", on_help_command)


def s18b_user_facing_strings() -> list[str]:
    """Strings introduced by S18b for the no-guilt assertion."""
    return [
        texts.CMD_DESC_START,
        texts.CMD_DESC_HELP,
        texts.CMD_DESC_STATS,
        texts.CMD_DESC_DIARY,
        texts.CMD_DESC_SHADOW,
        texts.CMD_DESC_CAPTURE,
        texts.CMD_DESC_PREP,
        texts.CMD_DESC_BOOK,
        texts.CMD_DESC_TEST,
        texts.CMD_DESC_ANKI,
        texts.CMD_DESC_IMPORT,
        texts.CMD_DESC_SETTINGS,
        texts.CMD_DESC_INTERESTS,
        texts.CMD_DESC_PAUSE,
        texts.HELP_HEADER,
        texts.HELP_SECTION_EVERY_DAY,
        texts.HELP_LINE_STATS,
        texts.HELP_LINE_QUIZ_ARRIVES,
        texts.HELP_SECTION_SPEAKING,
        texts.HELP_LINE_DIARY,
        texts.HELP_LINE_SHADOW,
        texts.HELP_SECTION_REAL_ENGLISH,
        texts.HELP_LINE_FORWARD,
        texts.HELP_LINE_CAPTURE,
        texts.HELP_LINE_PREP,
        texts.HELP_LINE_TYPE,
        texts.HELP_SECTION_BOOKS,
        texts.HELP_LINE_BOOK,
        texts.HELP_LINE_TEST,
        texts.HELP_SECTION_VOCAB,
        texts.HELP_LINE_ANKI,
        texts.HELP_LINE_CSV_UPLOAD,
        texts.HELP_LINE_IMPORT,
        texts.HELP_SECTION_SETTINGS,
        texts.HELP_LINE_SETTINGS,
        texts.HELP_LINE_INTERESTS,
        texts.HELP_LINE_PAUSE,
        texts.ONBOARD_SAVED,
        texts.ONBOARD_SAVED_EFSET_NUDGE,
    ]
