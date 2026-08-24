"""Shared access gate (S18d).

Responds only to approved ``access_requests`` rows, plus ``/start``,
``/ping``, and ``access:`` callbacks (request / approve / decline).
The configured operator is always allowed (so Approve/Decline and
``/admin`` work even before their own approval row exists).

Registered at handler group ``-1`` and raises ``ApplicationHandlerStop``
so unapproved traffic never reaches group 0. This gate is load-bearing —
a bug here silences the whole bot; see the gate surface regression test.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes, TypeHandler

from core.config import load_settings
from apps.bot import identity as bot_identity
from core.services.access_control import is_approved_telegram

logger = logging.getLogger(__name__)

_ALLOWED_COMMANDS = frozenset({"/start", "/ping"})
_ALLOWED_CALLBACK_PREFIX = "access:"


def _command_name(text: str) -> str | None:
    if not text.startswith("/"):
        return None
    first = text.split()[0]
    return first.split("@", 1)[0].lower()


def is_allowed_without_approval(update: Update) -> bool:
    """True for commands/callbacks strangers may use before approval."""
    message = update.message
    if message is not None and message.text:
        cmd = _command_name(message.text.strip())
        if cmd in _ALLOWED_COMMANDS:
            return True

    query = update.callback_query
    if query is not None and query.data is not None:
        if query.data.startswith(_ALLOWED_CALLBACK_PREFIX):
            return True

    return False


def _is_operator(telegram_user_id: int) -> bool:
    """Compares a TELEGRAM id, deliberately.

    ``OPERATOR_TELEGRAM_ID`` names a Telegram account, not a learner. Feeding it
    an internal user id after W4b would silently lock the operator out of
    ``/admin`` -- the parameter is named for the type it takes so that cannot
    happen by accident.
    """
    settings = load_settings()
    return (
        settings.operator_telegram_id is not None
        and telegram_user_id == settings.operator_telegram_id
    )


async def gate_unapproved(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Stop unapproved traffic before group-0 handlers run, and resolve identity.

    Two jobs since W4b, and they belong together: this is the one function that
    already had to look at ``effective_user`` on **every** update, so it is where
    the Telegram id is translated into a ``users.id`` once and stashed for the
    handlers below (``apps/bot/identity.py``). Doing it per-handler instead is
    how a second translation path gets born.

    Approval is still asked of the **Telegram** id here, not the internal one:
    a stranger who has requested access has an ``access_requests`` row and no
    ``users`` row at all, which is exactly what that table is for.
    """
    user = update.effective_user
    if user is None:
        return
    if is_approved_telegram(user.id):
        # Resolve only for traffic we are letting through. Returns None for
        # somebody approved but not yet onboarded -- the onboarding handlers are
        # the ones that must work without a users row.
        bot_identity.stash_user_id(update, context)
        return
    if _is_operator(user.id):
        bot_identity.stash_user_id(update, context)
        return
    if is_allowed_without_approval(update):
        return
    logger.info("Stopping update from unapproved telegram_user_id=%s", user.id)
    raise ApplicationHandlerStop


def build_access_handler() -> TypeHandler:
    """Pre-handler gate for group -1."""
    return TypeHandler(Update, gate_unapproved)
