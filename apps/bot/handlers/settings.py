""" /settings editor (S18a), /pause and /stats (S18).

Tapped-only settings — no MessageHandler. Nested callback ConversationHandler
with per_message=True under a per_message=False parent.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime, time, timedelta, timezone
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

from apps.bot import texts
from core.config import load_settings
from apps.bot.handlers.onboarding import layout_buttons
from core.services.sessions import local_today
from core.services.stats import collect_stats, format_stats_message
from core.services.users import (
    User,
    get_paused_until,
    get_user,
    is_registered,
    set_paused_until,
    update_evening_time,
    update_explanation_language_fallback,
    update_morning_time,
    update_track_weights,
)
from core.db import connection
from apps.bot import identity as bot_identity

logger = logging.getLogger(__name__)

PAUSE_DURATIONS = (1, 3, 7)
_BTN_BY_DAYS = {
    1: texts.BTN_PAUSE_1D,
    3: texts.BTN_PAUSE_3D,
    7: texts.BTN_PAUSE_7D,
}

(MENU, WEIGHTS, MORNING, EVENING, FALLBACK) = range(5)

_WIZARD_KEY = "settings"

_WEIGHT_PRESETS: dict[str, dict[str, int]] = {
    "balanced": {"work": 40, "life": 40, "curiosity": 20},
    "work": {"work": 60, "life": 25, "curiosity": 15},
    "life": {"work": 25, "life": 60, "curiosity": 15},
    "mostly": {"work": 15, "life": 70, "curiosity": 15},
}

# Same button presets as S1b (Other free-text omitted — tapped-only).
_MORNING_TIMES: tuple[str, ...] = ("07:00", "08:00", "09:00")
_EVENING_TIMES: tuple[str, ...] = ("19:00", "20:00", "21:00")

_MORNING_LABELS = {
    "07:00": texts.BTN_MORNING_07,
    "08:00": texts.BTN_MORNING_08,
    "09:00": texts.BTN_MORNING_09,
}
_EVENING_LABELS = {
    "19:00": texts.BTN_EVENING_19,
    "20:00": texts.BTN_EVENING_20,
    "21:00": texts.BTN_EVENING_21,
}


# --- shared helpers -----------------------------------------------------------


def _esc(value: str) -> str:
    return html.escape(value, quote=False)


def _format_time(value: time | str) -> str:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return str(value)[:5]


def _format_mix(weights: dict[str, int]) -> str:
    return (
        f"{weights.get('work', 0)}/{weights.get('life', 0)}/"
        f"{weights.get('curiosity', 0)}"
    )


def _preset_key(weights: dict[str, int]) -> str | None:
    for key, preset in _WEIGHT_PRESETS.items():
        if preset == weights:
            return key
    return None


def _mix_display(weights: dict[str, int]) -> str:
    mix = _format_mix(weights)
    key = _preset_key(weights)
    if key is None:
        return mix
    label = texts.WEIGHT_SUMMARY_LABELS.get(key, "")
    if label:
        return f"{mix} ({label})"
    return mix


def _fallback_state(enabled: bool) -> str:
    return (
        texts.SETTINGS_FALLBACK_ON if enabled else texts.SETTINGS_FALLBACK_OFF
    )


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
        data.get("wizard_chat_id") is not None
        and data.get("wizard_message_id") is not None
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
    """Warm degrade when in-flight state is missing (e.g. after restart)."""
    query = update.callback_query
    if query is not None:
        await query.answer()
        if query.message is not None:
            try:
                await query.message.edit_text(
                    texts.SETTINGS_STALE, reply_markup=None
                )
            except BadRequest as exc:
                if "message is not modified" not in str(exc).lower():
                    raise
    _clear_wizard(context)
    return ConversationHandler.END


async def _show(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    state: int,
    *,
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


def _menu_body(user: User, *, notice: str | None = None) -> str:
    lines = [
        f"<b>{_esc(texts.SETTINGS_TITLE)}</b>",
        "",
        _esc(
            texts.SETTINGS_MIX_LINE.format(mix=_mix_display(user.track_weights))
        ),
        _esc(
            texts.SETTINGS_MORNING_LINE.format(
                time=_format_time(user.morning_time)
            )
        ),
        _esc(
            texts.SETTINGS_EVENING_LINE.format(
                time=_format_time(user.evening_time)
            )
        ),
        _esc(
            texts.SETTINGS_FALLBACK_LINE.format(
                state=_fallback_state(user.explanation_language_fallback)
            )
        ),
        _esc(texts.SETTINGS_LEVEL_LINE.format(level=user.cefr_level)),
        _esc(texts.SETTINGS_TOPICS_LINE),
        _esc(texts.SETTINGS_PAUSE_LINE),
    ]
    watch_line = _watch_settings_line(user.telegram_user_id)
    if watch_line:
        lines.append(_esc(watch_line))
    if notice:
        lines.extend(["", _esc(notice)])
    return "\n".join(lines)


def _watch_settings_line(user_id: int) -> str | None:
    """Read-only watch paths when WATCH_DIR is configured; else omit."""
    from core.services.watch_import import paths_for_user_display

    paths = paths_for_user_display(user_id)
    if paths is None:
        return None
    return texts.SETTINGS_WATCH_LINE.format(
        inbox=paths["inbox"],
        trancy=paths["trancy"],
        language_reactor=paths["language_reactor"],
    )


def _menu_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        layout_buttons(
            [
                (texts.BTN_SETTINGS_MIX, "set:menu:weights"),
                (texts.BTN_SETTINGS_MORNING, "set:menu:morning"),
                (texts.BTN_SETTINGS_EVENING, "set:menu:evening"),
                (texts.BTN_SETTINGS_FALLBACK, "set:menu:fallback"),
                (texts.BTN_SETTINGS_DONE, "set:menu:done"),
            ]
        )
    )


async def _show_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
    *,
    notice: str | None = None,
) -> int:
    return await _show(
        update,
        context,
        MENU,
        text=_menu_body(user, notice=notice),
        reply_markup=_menu_keyboard(),
    )


# --- /settings entry + callbacks ----------------------------------------------


async def on_settings_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END
    user_id = bot_identity.bot_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    if not is_registered(user_id):
        return ConversationHandler.END
    user = get_user(user_id)
    if user is None:
        return ConversationHandler.END

    _clear_wizard(context)
    return await _show_menu(update, context, user)


async def on_settings_orphan_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Catch ``set:`` taps when no conversation is active (post-restart)."""
    await _stale_end(update, context)


async def menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        return MENU
    if not _has_flight(context):
        return await _stale_end(update, context)
    await query.answer()

    data = query.data
    resolved = bot_identity.bot_user_id(update, context)
    user = None if resolved is None else get_user(resolved)
    if user is None:
        return await _stale_end(update, context)

    if data == "set:menu:done":
        await _safe_edit_message_text(
            context,
            chat_id=int(_wizard(context)["wizard_chat_id"]),
            message_id=int(_wizard(context)["wizard_message_id"]),
            text=_esc(texts.SETTINGS_DONE),
            reply_markup=None,
        )
        _clear_wizard(context)
        return ConversationHandler.END

    if data == "set:menu:weights":
        mix = _mix_display(user.track_weights)
        body = f"<b>{_esc(texts.SETTINGS_ASK_WEIGHTS.format(mix=mix))}</b>"
        rows = layout_buttons(
            [
                (
                    texts.BTN_SETTINGS_WEIGHTS_BALANCED,
                    "set:weights:balanced",
                ),
                (texts.BTN_SETTINGS_WEIGHTS_WORK, "set:weights:work"),
                (texts.BTN_SETTINGS_WEIGHTS_LIFE, "set:weights:life"),
                (texts.BTN_SETTINGS_WEIGHTS_MOSTLY, "set:weights:mostly"),
            ]
        )
        rows.append([(texts.BTN_BACK, "set:back")])
        return await _show(
            update, context, WEIGHTS, text=body, reply_markup=_keyboard(rows)
        )

    if data == "set:menu:morning":
        now = _format_time(user.morning_time)
        body = f"<b>{_esc(texts.SETTINGS_ASK_MORNING.format(time=now))}</b>"
        time_rows = layout_buttons(
            [
                (_MORNING_LABELS[t], f"set:morning:{t}")
                for t in _MORNING_TIMES
            ],
            max_per_row=3,
        )
        time_rows.append([(texts.BTN_BACK, "set:back")])
        return await _show(
            update,
            context,
            MORNING,
            text=body,
            reply_markup=_keyboard(time_rows),
        )

    if data == "set:menu:evening":
        now = _format_time(user.evening_time)
        body = f"<b>{_esc(texts.SETTINGS_ASK_EVENING.format(time=now))}</b>"
        time_rows = layout_buttons(
            [
                (_EVENING_LABELS[t], f"set:evening:{t}")
                for t in _EVENING_TIMES
            ],
            max_per_row=3,
        )
        time_rows.append([(texts.BTN_BACK, "set:back")])
        return await _show(
            update,
            context,
            EVENING,
            text=body,
            reply_markup=_keyboard(time_rows),
        )

    if data == "set:menu:fallback":
        state = _fallback_state(user.explanation_language_fallback)
        body = (
            f"<b>{_esc(texts.SETTINGS_ASK_FALLBACK.format(state=state))}</b>"
        )
        if user.explanation_language_fallback:
            choice = (texts.BTN_SETTINGS_FALLBACK_OFF, "set:fallback:off")
        else:
            choice = (texts.BTN_SETTINGS_FALLBACK_ON, "set:fallback:on")
        rows = layout_buttons([choice])
        rows.append([(texts.BTN_BACK, "set:back")])
        return await _show(
            update, context, FALLBACK, text=body, reply_markup=_keyboard(rows)
        )

    return MENU


async def field_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        return MENU
    if not _has_flight(context):
        return await _stale_end(update, context)
    await query.answer()

    data = query.data
    user_id = bot_identity.bot_user_id(update, context)
    if user_id is None:
        return MENU

    if data == "set:back":
        user = get_user(user_id)
        if user is None:
            return await _stale_end(update, context)
        return await _show_menu(update, context, user)

    if data.startswith("set:weights:"):
        key = data.removeprefix("set:weights:")
        preset = _WEIGHT_PRESETS.get(key)
        if preset is None:
            return WEIGHTS
        update_track_weights(user_id, dict(preset))
        user = get_user(user_id)
        if user is None:
            return await _stale_end(update, context)
        detail = texts.SETTINGS_SAVED_MIX.format(
            mix=_mix_display(user.track_weights)
        )
        notice = texts.SETTINGS_SAVED.format(
            detail=detail, applies=texts.SETTINGS_APPLIES_NEXT
        )
        return await _show_menu(update, context, user, notice=notice)

    if data.startswith("set:morning:"):
        # split(":", 2) so set:morning:07:00 keeps "07:00"
        parts = data.split(":", 2)
        value = parts[2] if len(parts) == 3 else ""
        if value not in _MORNING_TIMES:
            return MORNING
        update_morning_time(user_id, value)
        user = get_user(user_id)
        if user is None:
            return await _stale_end(update, context)
        detail = texts.SETTINGS_SAVED_MORNING.format(
            time=_format_time(user.morning_time)
        )
        notice = texts.SETTINGS_SAVED.format(
            detail=detail, applies=texts.SETTINGS_APPLIES_NEXT
        )
        return await _show_menu(update, context, user, notice=notice)

    if data.startswith("set:evening:"):
        parts = data.split(":", 2)
        value = parts[2] if len(parts) == 3 else ""
        if value not in _EVENING_TIMES:
            return EVENING
        update_evening_time(user_id, value)
        user = get_user(user_id)
        if user is None:
            return await _stale_end(update, context)
        detail = texts.SETTINGS_SAVED_EVENING.format(
            time=_format_time(user.evening_time)
        )
        notice = texts.SETTINGS_SAVED.format(
            detail=detail, applies=texts.SETTINGS_APPLIES_NEXT
        )
        return await _show_menu(update, context, user, notice=notice)

    if data.startswith("set:fallback:"):
        action = data.removeprefix("set:fallback:")
        if action not in ("on", "off"):
            return FALLBACK
        update_explanation_language_fallback(user_id, action == "on")
        user = get_user(user_id)
        if user is None:
            return await _stale_end(update, context)
        detail = texts.SETTINGS_SAVED_FALLBACK.format(
            state=_fallback_state(user.explanation_language_fallback)
        )
        notice = texts.SETTINGS_SAVED.format(
            detail=detail, applies=texts.SETTINGS_APPLIES_NEXT
        )
        return await _show_menu(update, context, user, notice=notice)

    return MENU


async def cancel_settings(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    _clear_wizard(context)
    if update.message is not None:
        await update.message.reply_text(texts.SETTINGS_CANCELLED)
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


_FIELD_MAP: dict[object, object] = {
    MENU: MENU,
    WEIGHTS: WEIGHTS,
    MORNING: MORNING,
    EVENING: EVENING,
    FALLBACK: FALLBACK,
    ConversationHandler.END: ConversationHandler.END,
}


def build_settings_editor_handler() -> ConversationHandler:
    """Tapped-only /settings — no MessageHandler, no conversation_timeout."""
    return ConversationHandler(
        entry_points=[CommandHandler("settings", on_settings_command)],
        states={
            MENU: [
                _button_conversation(
                    "settings_menu",
                    menu_callback,
                    r"^set:menu:",
                    {
                        MENU: MENU,
                        WEIGHTS: WEIGHTS,
                        MORNING: MORNING,
                        EVENING: EVENING,
                        FALLBACK: FALLBACK,
                        ConversationHandler.END: ConversationHandler.END,
                    },
                ),
            ],
            WEIGHTS: [
                _button_conversation(
                    "settings_weights",
                    field_callback,
                    r"^set:(weights:|back$)",
                    _FIELD_MAP,
                ),
            ],
            MORNING: [
                _button_conversation(
                    "settings_morning",
                    field_callback,
                    r"^set:(morning:|back$)",
                    _FIELD_MAP,
                ),
            ],
            EVENING: [
                _button_conversation(
                    "settings_evening",
                    field_callback,
                    r"^set:(evening:|back$)",
                    _FIELD_MAP,
                ),
            ],
            FALLBACK: [
                _button_conversation(
                    "settings_fallback",
                    field_callback,
                    r"^set:(fallback:|back$)",
                    _FIELD_MAP,
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_settings)],
        name="settings",
        persistent=False,
        allow_reentry=True,
        per_message=False,
    )


def build_settings_orphan_handler() -> CallbackQueryHandler:
    """Warm-degrade orphan ``set:`` taps after restart (no active conversation)."""
    return CallbackQueryHandler(
        on_settings_orphan_callback, pattern=r"^set:"
    )


def s18a_button_labels() -> list[str]:
    """Every S18a button label — for the ≤20-char audit."""
    return [
        texts.BTN_SETTINGS_MIX,
        texts.BTN_SETTINGS_MORNING,
        texts.BTN_SETTINGS_EVENING,
        texts.BTN_SETTINGS_FALLBACK,
        texts.BTN_SETTINGS_DONE,
        texts.BTN_SETTINGS_WEIGHTS_BALANCED,
        texts.BTN_SETTINGS_WEIGHTS_WORK,
        texts.BTN_SETTINGS_WEIGHTS_LIFE,
        texts.BTN_SETTINGS_WEIGHTS_MOSTLY,
        texts.BTN_SETTINGS_FALLBACK_ON,
        texts.BTN_SETTINGS_FALLBACK_OFF,
        texts.BTN_BACK,
        texts.BTN_MORNING_07,
        texts.BTN_MORNING_08,
        texts.BTN_MORNING_09,
        texts.BTN_EVENING_19,
        texts.BTN_EVENING_20,
        texts.BTN_EVENING_21,
    ]


def parse_settings_time_callback(data: str) -> str | None:
    """Extract HH:MM from set:morning:HH:MM / set:evening:HH:MM via split(:, 2)."""
    if not (
        data.startswith("set:morning:") or data.startswith("set:evening:")
    ):
        return None
    parts = data.split(":", 2)
    if len(parts) != 3:
        return None
    return parts[2]


# --- /pause + /stats (S18) ----------------------------------------------------


def _user_timezone(user_id: int) -> str:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT timezone FROM users WHERE id = %s
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
    user_id = bot_identity.bot_user_id(update, context)
    if user_id is None:
        return
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
    user_id = bot_identity.bot_user_id(update, context)
    if user_id is None:
        return
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
    user_id = bot_identity.bot_user_id(update, context)
    if user_id is None:
        return
    if get_user(user_id) is None:
        return
    settings = load_settings()
    # Against the TELEGRAM id, not `user_id`. This comparison is inlined rather
    # than going through `_is_operator`, which is why it nearly survived W4b
    # unnoticed: with an internal id on the left it can never match, and the
    # operator's fossil-sweep line would have vanished from /stats with no error
    # anywhere. `OPERATOR_TELEGRAM_ID` names a Telegram account.
    telegram_user_id = bot_identity.telegram_id_of(update)
    include_sweep = (
        settings.operator_telegram_id is not None
        and telegram_user_id == settings.operator_telegram_id
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
