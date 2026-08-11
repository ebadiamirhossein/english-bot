"""Access request callbacks (S18d) — no MessageHandler.

Strangers tap ``access:request`` after ``/start``. The operator gets
Approve/Decline buttons (``access:approve:`` / ``access:decline:``).
"""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from app import texts
from app.config import load_settings
from app.services.access_control import (
    approve_access,
    decline_access,
    get_access_request,
    request_access,
)

logger = logging.getLogger(__name__)


def _keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=data) for label, data in row]
            for row in rows
        ]
    )


def _display_name(user: object) -> str | None:
    parts: list[str] = []
    first = getattr(user, "first_name", None) or ""
    last = getattr(user, "last_name", None) or ""
    if first:
        parts.append(str(first).strip())
    if last:
        parts.append(str(last).strip())
    if not parts:
        return None
    return " ".join(parts)


async def on_access_request(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await query.answer()

    user = update.effective_user
    result = request_access(
        user.id,
        username=user.username,
        display_name=_display_name(user),
    )

    settings = load_settings()
    operator_id = settings.operator_telegram_id

    if result.already_pending:
        await query.edit_message_text(texts.ACCESS_REQUEST_ALREADY)
        return

    if operator_id is None:
        logger.error(
            "access request stored but OPERATOR_TELEGRAM_ID unset user_id=%s",
            user.id,
        )
        await query.edit_message_text(texts.ACCESS_REQUEST_CLOSED)
        return

    if result.capped or not result.notify_operator:
        await query.edit_message_text(texts.ACCESS_REQUEST_CAPPED)
        return

    username = f"@{user.username}" if user.username else "—"
    display = _display_name(user) or "—"
    body = texts.ACCESS_OPERATOR_REQUEST.format(
        telegram_id=user.id,
        username=username,
        display_name=display,
    )
    kb = _keyboard(
        [
            [
                (texts.BTN_ACCESS_APPROVE, f"access:approve:{user.id}"),
                (texts.BTN_ACCESS_DECLINE, f"access:decline:{user.id}"),
            ]
        ]
    )
    try:
        await context.bot.send_message(
            chat_id=operator_id, text=body, reply_markup=kb
        )
    except Exception:
        logger.exception(
            "failed to notify operator of access request user_id=%s", user.id
        )
        await query.edit_message_text(texts.ACCESS_REQUEST_CLOSED)
        return

    await query.edit_message_text(texts.ACCESS_REQUEST_SENT)


async def on_access_decide(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        return

    settings = load_settings()
    if (
        settings.operator_telegram_id is None
        or update.effective_user.id != settings.operator_telegram_id
    ):
        await query.answer()
        return

    parts = query.data.split(":", 2)
    if len(parts) != 3 or parts[0] != "access":
        await query.answer()
        return
    action, raw_id = parts[1], parts[2]
    try:
        target_id = int(raw_id)
    except ValueError:
        await query.answer()
        return

    await query.answer()

    existing = get_access_request(target_id)
    if existing is None or existing.status != "pending":
        await query.edit_message_text(texts.ACCESS_OPERATOR_DONE)
        return

    if action == "approve":
        approve_access(target_id)
        await query.edit_message_text(
            texts.ACCESS_OPERATOR_APPROVED.format(telegram_id=target_id)
        )
        try:
            await context.bot.send_message(
                chat_id=target_id, text=texts.ACCESS_APPROVED
            )
        except Exception:
            logger.exception(
                "failed to notify requester of approval user_id=%s", target_id
            )
        return

    if action == "decline":
        decline_access(target_id)
        await query.edit_message_text(
            texts.ACCESS_OPERATOR_DECLINED.format(telegram_id=target_id)
        )
        try:
            await context.bot.send_message(
                chat_id=target_id, text=texts.ACCESS_DECLINED
            )
        except Exception:
            logger.exception(
                "failed to notify requester of decline user_id=%s", target_id
            )


def build_access_request_handlers() -> tuple[
    CallbackQueryHandler, CallbackQueryHandler
]:
    return (
        CallbackQueryHandler(on_access_request, pattern=r"^access:request$"),
        CallbackQueryHandler(
            on_access_decide, pattern=r"^access:(approve|decline):\d+$"
        ),
    )


def s18d_access_button_labels() -> list[str]:
    return [
        texts.BTN_REQUEST_ACCESS,
        texts.BTN_ACCESS_APPROVE,
        texts.BTN_ACCESS_DECLINE,
    ]
