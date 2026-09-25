"""``/start`` and ``/help`` — one reply that says where practice lives now (W22).

Before W22, ``/help`` was a grouped map of about twenty commands and ``/start``
was onboarding. Every command on that map was deleted with the Telegram
teaching path, so the map would now list things that do nothing. The reply
says what the bot still does — the couple challenge — and that everything
else is in the web app. Not a new feature (PRODUCT-PRINCIPLES §1): it is what
is left of an old one, and without it a learner who taps ``/start`` gets
silence and no idea why.

User-initiated: does not increment ``bot_message_counts``. Unregistered users
are ignored (ARCHITECTURE §7), as before.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from apps.bot import texts
from core.services.users import is_registered
from apps.bot import identity as bot_identity


def format_help_message() -> str:
    """The whole reply. Pure — easy to assert in tests."""
    return texts.HELP_AFTER_W22


async def on_help_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None or update.effective_user is None:
        return
    user_id = bot_identity.bot_user_id(update, context)
    if user_id is None or not is_registered(user_id):
        return
    await update.message.reply_text(format_help_message())


def build_help_handlers() -> tuple[CommandHandler, CommandHandler]:
    return (
        CommandHandler("start", on_help_command),
        CommandHandler("help", on_help_command),
    )


def user_facing_strings() -> list[str]:
    """Every string this module and the command menu can show, for the no-guilt test."""
    return [
        texts.CMD_DESC_START,
        texts.CMD_DESC_HELP,
        texts.HELP_AFTER_W22,
    ]
