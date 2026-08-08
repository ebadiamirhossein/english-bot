""" /pause and /stats (S18). Tap-only pause durations; read-only stats."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from app import texts
from app.config import load_settings
from app.services.sessions import local_today
from app.services.stats import collect_stats, format_stats_message
from app.services.users import get_paused_until, get_user, set_paused_until
from app.db import connection

logger = logging.getLogger(__name__)

PAUSE_DURATIONS = (1, 3, 7)
_BTN_BY_DAYS = {
    1: texts.BTN_PAUSE_1D,
    3: texts.BTN_PAUSE_3D,
    7: texts.BTN_PAUSE_7D,
}


def _user_timezone(user_id: int) -> str:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT timezone FROM users WHERE telegram_user_id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return "Europe/Vilnius"
    return str(row["timezone"] or "Europe/Vilnius")


def pause_keyboard(*, paused: bool) -> InlineKeyboardMarkup:
    if paused:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        texts.BTN_PAUSE_RESUME,
                        callback_data="pause:resume",
                    )
                ]
            ]
        )
    rows = [
        [
            InlineKeyboardButton(
                _BTN_BY_DAYS[n], callback_data=f"pause:{n}"
            )
        ]
        for n in PAUSE_DURATIONS
    ]
    return InlineKeyboardMarkup(rows)


def s18_button_labels() -> list[str]:
    return [
        texts.BTN_PAUSE_1D,
        texts.BTN_PAUSE_3D,
        texts.BTN_PAUSE_7D,
        texts.BTN_PAUSE_RESUME,
    ]


def s18_user_facing_strings() -> list[str]:
    return [
        texts.SOFT_UNHANDLED,
        texts.PAUSE_PICK,
        texts.PAUSE_ACTIVE,
        texts.PAUSE_SET,
        texts.PAUSE_RESUMED,
        texts.STATS_HEADER,
        texts.STATS_LEVEL,
        texts.STATS_STREAK,
        texts.STATS_ACTIVE,
        texts.STATS_DUE,
        texts.STATS_RESOLVED,
        texts.STATS_RESOLVED_NONE,
        texts.STATS_CHUNKS,
        texts.STATS_BOOKS,
        texts.STATS_CALIBRATION,
        texts.STATS_CALIBRATION_NONE,
        # Operator-only string excluded from learner guilt scan surface tests
        # that check learner output; still listed for label completeness elsewhere.
    ]


async def on_pause_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None or update.effective_user is None:
        return
    user_id = update.effective_user.id
    if get_user(user_id) is None:
        return
    now = datetime.now(timezone.utc)
    tz = _user_timezone(user_id)
    day = local_today(tz, now)
    paused_until = get_paused_until(user_id)
    active = paused_until is not None and paused_until >= day
    if active:
        assert paused_until is not None
        await update.message.reply_text(
            texts.PAUSE_ACTIVE.format(until=paused_until.isoformat()),
            reply_markup=pause_keyboard(paused=True),
        )
        return
    await update.message.reply_text(
        texts.PAUSE_PICK,
        reply_markup=pause_keyboard(paused=False),
    )


async def on_pause_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await query.answer()
    data = query.data or ""
    if not data.startswith("pause:"):
        return
    user_id = update.effective_user.id
    if get_user(user_id) is None:
        return
    now = datetime.now(timezone.utc)
    tz = _user_timezone(user_id)
    day = local_today(tz, now)
    action = data.split(":", 1)[1]

    if action == "resume":
        set_paused_until(user_id, None)
        if query.message is not None:
            await query.message.edit_text(texts.PAUSE_RESUMED)
        return

    try:
        days = int(action)
    except ValueError:
        return
    if days not in PAUSE_DURATIONS:
        return

    # While already paused: offer resume only — do not stack.
    current = get_paused_until(user_id)
    if current is not None and current >= day:
        if query.message is not None:
            await query.message.edit_text(
                texts.PAUSE_ACTIVE.format(until=current.isoformat()),
                reply_markup=pause_keyboard(paused=True),
            )
        return

    until = day + timedelta(days=days - 1)
    set_paused_until(user_id, until)
    if query.message is not None:
        await query.message.edit_text(
            texts.PAUSE_SET.format(until=until.isoformat())
        )


async def on_stats_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None or update.effective_user is None:
        return
    user_id = update.effective_user.id
    if get_user(user_id) is None:
        return
    settings = load_settings()
    include_sweep = (
        settings.operator_telegram_id is not None
        and user_id == settings.operator_telegram_id
    )
    now = datetime.now(timezone.utc)
    stats = collect_stats(user_id, now=now, include_sweep=include_sweep)
    if stats is None:
        return
    body = format_stats_message(stats, include_sweep=include_sweep)
    await update.message.reply_text(body)


def build_settings_handlers() -> tuple[
    CommandHandler, CommandHandler, CallbackQueryHandler
]:
    """Return /pause, /stats, and pause: callback handlers."""
    return (
        CommandHandler("pause", on_pause_command),
        CommandHandler("stats", on_stats_command),
        CallbackQueryHandler(on_pause_callback, pattern=r"^pause:"),
    )
