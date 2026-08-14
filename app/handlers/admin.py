"""``/admin`` — operator-only activity panel (S18d).

Tapped-only nested ConversationHandler (S18a/S18c pattern). No
MessageHandler. Activity and state only — never learner content.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
)

from app import texts
from app.config import load_settings
from app.handlers.onboarding import layout_buttons
from app.handlers.settings import PAUSE_DURATIONS, _BTN_BY_DAYS
from app.services.access_control import (
    approve_access,
    decline_access,
    list_pending_requests,
    revoke_access,
)
from app.services.alerts import notify_operator
from app.services.admin_panel import (
    admin_user_label,
    format_admin_home,
    format_pending_list,
    list_admin_users,
)
from app.services.motivation import WEEKLY_SUCCESS_DAYS
from app.services.sessions import local_today
from app.services.shared_content import try_backfill_soft
from app.services.users import set_paused_until

logger = logging.getLogger(__name__)

(HOME, PENDING, USER) = range(3)

_WIZARD_KEY = "admin"


async def _soft_backfill_after_approve(
    context: ContextTypes.DEFAULT_TYPE, target_id: int
) -> None:
    if not try_backfill_soft(target_id):
        await notify_operator(
            context.application,
            key=f"shared_backfill:{target_id}",
            text=f"shared backfill failed after approve user_id={target_id}",
        )


def _esc(value: str) -> str:
    return html.escape(value, quote=False)


def _keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=data) for label, data in row]
            for row in rows
        ]
    )


def _wizard(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    data = context.user_data.setdefault(_WIZARD_KEY, {})
    if not isinstance(data, dict):
        data = {}
        context.user_data[_WIZARD_KEY] = data
    return data


def _clear_wizard(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(_WIZARD_KEY, None)


def _has_flight(context: ContextTypes.DEFAULT_TYPE) -> bool:
    data = context.user_data.get(_WIZARD_KEY)
    if not isinstance(data, dict):
        return False
    return (
        data.get("wizard_message_id") is not None
        and data.get("wizard_chat_id") is not None
    )


def _is_operator(user_id: int) -> bool:
    settings = load_settings()
    return (
        settings.operator_telegram_id is not None
        and user_id == settings.operator_telegram_id
    )


async def _safe_edit_message_text(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> None:
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    except BadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        raise


async def _stale_end(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    _clear_wizard(context)
    query = update.callback_query
    if query is not None:
        await query.answer()
        try:
            await query.edit_message_text(texts.ADMIN_STALE)
        except BadRequest:
            pass
    return ConversationHandler.END


async def _show(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    state: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> int:
    wiz = _wizard(context)
    wiz["wizard_state"] = state
    wizard_id = wiz.get("wizard_message_id")
    chat_id = wiz.get("wizard_chat_id")

    if wizard_id is not None and chat_id is not None:
        await _safe_edit_message_text(
            context,
            chat_id=int(chat_id),
            message_id=int(wizard_id),
            text=text,
            reply_markup=reply_markup,
        )
        return state

    target = update.effective_message
    assert target is not None
    msg = await target.reply_text(
        text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
    )
    wiz["wizard_message_id"] = msg.message_id
    wiz["wizard_chat_id"] = msg.chat_id
    return state


def _home_keyboard(users: list[Any]) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = [
        [
            (texts.BTN_ADMIN_PENDING, "admin:pending"),
            (texts.BTN_ADMIN_REFRESH, "admin:refresh"),
        ]
    ]
    user_btns: list[tuple[str, str]] = []
    for u in users:
        label = u.name[:18] if len(u.name) <= 18 else u.name[:17] + "…"
        if u.revoked:
            label = ("✗ " + label)[:20]
        user_btns.append((label, f"admin:user:{u.telegram_user_id}"))
    rows.extend(layout_buttons(user_btns, max_per_row=2))
    rows.append([(texts.BTN_ADMIN_DONE, "admin:done")])
    return _keyboard(rows)


def _pending_keyboard(pending: list[Any]) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    for req in pending:
        tid = req.telegram_user_id
        rows.append(
            [
                (texts.BTN_ACCESS_APPROVE, f"admin:approve:{tid}"),
                (texts.BTN_ACCESS_DECLINE, f"admin:decline:{tid}"),
            ]
        )
    rows.append([(texts.BTN_ADMIN_BACK, "admin:home")])
    return _keyboard(rows)


def _user_keyboard(user_id: int, *, revoked: bool, paused: bool) -> InlineKeyboardMarkup:
    rows: list[list[tuple[str, str]]] = []
    if paused:
        rows.append([(texts.BTN_ADMIN_RESUME, f"admin:resume:{user_id}")])
    else:
        pause_btns = [
            (_BTN_BY_DAYS[n], f"admin:pause:{user_id}:{n}")
            for n in PAUSE_DURATIONS
        ]
        rows.extend(layout_buttons(pause_btns, max_per_row=3))
    if revoked:
        rows.append([(texts.BTN_ADMIN_REAPPROVE, f"admin:reapprove:{user_id}")])
    else:
        rows.append([(texts.BTN_ADMIN_REVOKE, f"admin:revoke:{user_id}")])
    rows.append([(texts.BTN_ADMIN_BACK, "admin:home")])
    return _keyboard(rows)


async def _show_home(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    notice: str | None = None,
) -> int:
    users = list_admin_users()
    body = format_admin_home(users)
    if notice:
        body = f"{body}\n\n{notice}"
    return await _show(
        update, context, HOME, _esc(body), _home_keyboard(users)
    )


async def on_admin_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END
    if not _is_operator(update.effective_user.id):
        return ConversationHandler.END

    _clear_wizard(context)
    return await _show_home(update, context)


async def home_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        return HOME
    if not _is_operator(update.effective_user.id):
        return ConversationHandler.END
    if not _has_flight(context):
        return await _stale_end(update, context)
    await query.answer()

    data = query.data
    if data == "admin:done":
        _clear_wizard(context)
        await query.edit_message_text(texts.ADMIN_DONE)
        return ConversationHandler.END
    if data == "admin:refresh" or data == "admin:home":
        return await _show_home(update, context)
    if data == "admin:pending":
        pending = list_pending_requests()
        body = _esc(format_pending_list(pending))
        return await _show(
            update, context, PENDING, body, _pending_keyboard(pending)
        )
    if data.startswith("admin:user:"):
        try:
            tid = int(data.split(":", 2)[2])
        except (IndexError, ValueError):
            return HOME
        users = {u.telegram_user_id: u for u in list_admin_users()}
        user = users.get(tid)
        if user is None:
            return await _show_home(update, context, notice=texts.ADMIN_NOTHING)
        line = texts.ADMIN_USER_LINE.format(
            name=(
                f"{user.name} ({texts.ADMIN_REVOKED_TAG})"
                if user.revoked
                else user.name
            ),
            level=user.cefr_level,
            streak=user.current_streak,
            active=user.active_days,
            week=WEEKLY_SUCCESS_DAYS,
            last=(
                user.last_active.isoformat()
                if user.last_active is not None
                else texts.ADMIN_LAST_NEVER
            ),
            paused=(
                texts.ADMIN_PAUSED_YES if user.paused else texts.ADMIN_PAUSED_NO
            ),
        )
        _wizard(context)["focus_user_id"] = tid
        return await _show(
            update,
            context,
            USER,
            _esc(line),
            _user_keyboard(tid, revoked=user.revoked, paused=user.paused),
        )
    return HOME


async def pending_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        return PENDING
    if not _is_operator(update.effective_user.id):
        return ConversationHandler.END
    if not _has_flight(context):
        return await _stale_end(update, context)
    await query.answer()

    data = query.data
    if data == "admin:home":
        return await _show_home(update, context)

    parts = data.split(":")
    if len(parts) != 3:
        return PENDING
    _, action, raw_id = parts
    try:
        tid = int(raw_id)
    except ValueError:
        return PENDING

    if action == "approve":
        approve_access(tid)
        await _soft_backfill_after_approve(context, tid)
        try:
            await context.bot.send_message(chat_id=tid, text=texts.ACCESS_APPROVED)
        except Exception:
            logger.exception("admin approve notify failed user_id=%s", tid)
        notice = texts.ACCESS_OPERATOR_APPROVED.format(telegram_id=tid)
    elif action == "decline":
        decline_access(tid)
        try:
            await context.bot.send_message(chat_id=tid, text=texts.ACCESS_DECLINED)
        except Exception:
            logger.exception("admin decline notify failed user_id=%s", tid)
        notice = texts.ACCESS_OPERATOR_DECLINED.format(telegram_id=tid)
    else:
        return PENDING

    pending = list_pending_requests()
    body = format_pending_list(pending) + f"\n\n{notice}"
    return await _show(
        update, context, PENDING, _esc(body), _pending_keyboard(pending)
    )


async def user_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        return USER
    if not _is_operator(update.effective_user.id):
        return ConversationHandler.END
    if not _has_flight(context):
        return await _stale_end(update, context)
    await query.answer()

    data = query.data
    if data == "admin:home":
        return await _show_home(update, context)

    parts = data.split(":")
    if len(parts) < 3:
        return USER
    action = parts[1]
    try:
        tid = int(parts[2])
    except ValueError:
        return USER

    name = admin_user_label(tid)

    if action == "revoke":
        revoke_access(tid)
        return await _show_home(
            update, context, notice=texts.ADMIN_REVOKED.format(name=name)
        )
    if action == "reapprove":
        approve_access(tid)
        await _soft_backfill_after_approve(context, tid)
        return await _show_home(
            update, context, notice=texts.ADMIN_REAPPROVED.format(name=name)
        )
    if action == "resume":
        set_paused_until(tid, None)
        return await _show_home(
            update, context, notice=texts.ADMIN_RESUMED.format(name=name)
        )
    if action == "pause" and len(parts) == 4:
        try:
            days = int(parts[3])
        except ValueError:
            return USER
        if days not in PAUSE_DURATIONS:
            return USER
        # Same duration math as /pause: 1 day = today only.
        day = local_today("Europe/Vilnius", datetime.now(timezone.utc))
        until = day + timedelta(days=days - 1)
        set_paused_until(tid, until)
        return await _show_home(
            update,
            context,
            notice=texts.ADMIN_PAUSED.format(name=name, until=until.isoformat()),
        )
    return USER


async def cancel_admin(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    _clear_wizard(context)
    if update.message is not None and update.effective_user is not None:
        if _is_operator(update.effective_user.id):
            await update.message.reply_text(texts.ADMIN_CANCELLED)
    return ConversationHandler.END


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


def build_admin_handler() -> ConversationHandler:
    """Tapped-only /admin — no MessageHandler, operator-only entry."""
    return ConversationHandler(
        entry_points=[CommandHandler("admin", on_admin_command)],
        states={
            HOME: [
                _button_conversation(
                    "admin_home",
                    home_callback,
                    r"^admin:(pending|refresh|done|home|user:\d+)$",
                    {
                        HOME: HOME,
                        PENDING: PENDING,
                        USER: USER,
                        ConversationHandler.END: ConversationHandler.END,
                    },
                ),
            ],
            PENDING: [
                _button_conversation(
                    "admin_pending",
                    pending_callback,
                    r"^admin:(home|approve:\d+|decline:\d+)$",
                    {
                        HOME: HOME,
                        PENDING: PENDING,
                        ConversationHandler.END: ConversationHandler.END,
                    },
                ),
            ],
            USER: [
                _button_conversation(
                    "admin_user",
                    user_callback,
                    r"^admin:(home|revoke:\d+|reapprove:\d+|resume:\d+|pause:\d+:\d+)$",
                    {
                        HOME: HOME,
                        USER: USER,
                        ConversationHandler.END: ConversationHandler.END,
                    },
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_admin)],
        name="admin",
        persistent=False,
        allow_reentry=True,
        per_message=False,
    )


async def on_admin_orphan_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    try:
        await query.edit_message_text(texts.ADMIN_STALE)
    except BadRequest:
        pass


def build_admin_orphan_handler() -> CallbackQueryHandler:
    return CallbackQueryHandler(on_admin_orphan_callback, pattern=r"^admin:")


def s18d_admin_button_labels() -> list[str]:
    return [
        texts.BTN_ADMIN_PENDING,
        texts.BTN_ADMIN_USERS,
        texts.BTN_ADMIN_REFRESH,
        texts.BTN_ADMIN_DONE,
        texts.BTN_ADMIN_PAUSE,
        texts.BTN_ADMIN_RESUME,
        texts.BTN_ADMIN_REVOKE,
        texts.BTN_ADMIN_REAPPROVE,
        texts.BTN_ADMIN_BACK,
        texts.BTN_ACCESS_APPROVE,
        texts.BTN_ACCESS_DECLINE,
        texts.BTN_PAUSE_1D,
        texts.BTN_PAUSE_3D,
        texts.BTN_PAUSE_7D,
    ]


def s18d_button_labels() -> list[str]:
    from app.handlers.access_request import s18d_access_button_labels

    return list(dict.fromkeys(s18d_access_button_labels() + s18d_admin_button_labels()))
