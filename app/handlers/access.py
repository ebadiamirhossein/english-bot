"""Shared access control for Phases 1–4.

The bot responds only to telegram_user_id values present in `users`,
plus `/start` and `/ping`. Everyone else is ignored silently.

Users mid-onboarding are not in `users` yet (rows are written only on
Save). Track those ids in bot_data so their answers are not treated as
unauthorized traffic.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes, TypeHandler

from app.services.users import is_registered

logger = logging.getLogger(__name__)

_ALLOWED_COMMANDS = frozenset({"/start", "/ping"})
_ONBOARDING_IDS_KEY = "onboarding_in_progress"


def _command_name(text: str) -> str | None:
    if not text.startswith("/"):
        return None
    first = text.split()[0]
    return first.split("@", 1)[0].lower()


def mark_onboarding(context: ContextTypes.DEFAULT_TYPE, telegram_user_id: int) -> None:
    ids = context.application.bot_data.setdefault(_ONBOARDING_IDS_KEY, set())
    ids.add(telegram_user_id)


def clear_onboarding(context: ContextTypes.DEFAULT_TYPE, telegram_user_id: int) -> None:
    ids = context.application.bot_data.get(_ONBOARDING_IDS_KEY)
    if ids is not None:
        ids.discard(telegram_user_id)


def is_onboarding(context: ContextTypes.DEFAULT_TYPE, telegram_user_id: int) -> bool:
    ids = context.application.bot_data.get(_ONBOARDING_IDS_KEY, set())
    return telegram_user_id in ids


def is_allowed_without_registration(update: Update) -> bool:
    """True for the two commands that strangers may use."""
    message = update.message
    if message is None or not message.text:
        return False
    cmd = _command_name(message.text.strip())
    return cmd in _ALLOWED_COMMANDS


async def ignore_unregistered(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Log and swallow updates from strangers. No reply."""
    user = update.effective_user
    if user is None:
        return
    if is_registered(user.id):
        return
    if is_onboarding(context, user.id):
        return
    if is_allowed_without_registration(update):
        return
    logger.info("Ignoring update from unregistered user_id=%s", user.id)


def build_access_handler() -> TypeHandler:
    """Handler for a non-zero group: silently drops unregistered traffic."""
    return TypeHandler(Update, ignore_unregistered)
