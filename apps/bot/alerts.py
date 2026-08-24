"""Telegram side of operator alerting (S18).

``on_error`` is the global PTB error handler, lifted unchanged out of
``core.services.alerts`` at W1. ``operator_send`` adapts the bot to the
channel-neutral ``send`` callable the core service now takes.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Awaitable, Callable

from telegram import Update
from telegram.ext import ContextTypes

from apps.bot import texts
from core.config import load_settings
from core.services.alerts import format_alert, notify_operator
from apps.bot import identity as bot_identity

logger = logging.getLogger(__name__)


def operator_send(bot: Any) -> Callable[[str], Awaitable[None]]:
    """Build the `send` callable `core.services.alerts` now expects."""

    async def _send(text: str) -> None:
        operator_id = load_settings().operator_telegram_id
        await bot.send_message(chat_id=operator_id, text=text)

    return _send


def _handler_name(context: ContextTypes.DEFAULT_TYPE) -> str:
    handler = getattr(context, "handler", None)
    if handler is None:
        return "unknown"
    callback = getattr(handler, "callback", None)
    if callback is not None:
        name = getattr(callback, "__name__", None)
        if name:
            return str(name)
        return type(callback).__name__
    return type(handler).__name__


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global PTB error handler: soft to user, throttled alert to operator."""
    exc = context.error
    if exc is None:
        return
    handler = _handler_name(context)
    user_id: int | None = None
    chat = None
    if isinstance(update, Update):
        if update.effective_user is not None:
            # The Telegram id on purpose. This is the error path: it must report
            # even for somebody with no users row -- which is exactly when
            # things break -- so it cannot depend on a lookup succeeding.
            # PRD §10: logs carry ids and route names, never message bodies.
            user_id = update.effective_user.id
        chat = update.effective_chat

    logger.exception(
        "Unhandled exception handler=%s user_id=%s",
        handler,
        user_id,
        exc_info=exc,
    )

    if chat is not None:
        try:
            await context.bot.send_message(
                chat_id=chat.id, text=texts.SOFT_UNHANDLED
            )
        except Exception:
            logger.exception(
                "Failed soft reply after unhandled error user_id=%s", user_id
            )

    tb = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    # Peek prior suppressed for the alert body, then notify_operator applies
    # the same throttle key. To avoid double-counting, format without
    # suppressed and let notify_operator append it.
    key = f"{type(exc).__name__}|{handler}"
    alert = format_alert(
        handler=handler,
        user_id=user_id,
        exc=exc,
        tb=tb,
        suppressed=0,
    )
    await notify_operator(operator_send(context.bot), key=key, text=alert)
