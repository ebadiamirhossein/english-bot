""" /start onboarding conversation (S1). """

from __future__ import annotations

import logging
import re
from datetime import time
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app import texts
from app.handlers.access import clear_onboarding, mark_onboarding
from app.services.users import User, efset_to_cefr, get_user, save_onboarding

logger = logging.getLogger(__name__)

(
    PROFILE,
    NAME,
    NATIVE_LANG,
    NATIVE_LANG_OTHER,
    EFSET,
    DOMAIN,
    WHY,
    WEIGHTS,
    MORNING,
    MORNING_OTHER,
    EVENING,
    EVENING_OTHER,
    CONFIRM,
) = range(13)

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

_WEIGHT_PRESETS: dict[str, dict[str, int]] = {
    "balanced": {"work": 40, "life": 40, "curiosity": 20},
    "work": {"work": 60, "life": 25, "curiosity": 15},
    "life": {"work": 25, "life": 60, "curiosity": 15},
}

_LANG_CODES = {"fa": "fa", "lt": "lt"}


def _clear_answers(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("onboarding", None)


def _answers(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    store = context.user_data.setdefault("onboarding", {})
    return store


def _parse_time(raw: str) -> str | None:
    match = _TIME_RE.match(raw.strip())
    if not match:
        return None
    return f"{match.group(1)}:{match.group(2)}"


def _format_time(value: time | str) -> str:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return str(value)[:5]


def _format_weights(weights: dict[str, int]) -> str:
    return (
        f"work {weights.get('work', 0)} / "
        f"life {weights.get('life', 0)} / "
        f"curiosity {weights.get('curiosity', 0)}"
    )


def _lang_label(code: str) -> str:
    return texts.LANG_LABELS.get(code, code)


def _keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=data) for label, data in row]
            for row in rows
        ]
    )


def _native_lang_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [
                (texts.BTN_LANG_FARSI, "lang:fa"),
                (texts.BTN_LANG_LITHUANIAN, "lang:lt"),
            ],
            [(texts.BTN_LANG_OTHER, "lang:other")],
        ]
    )


def _efset_keyboard() -> InlineKeyboardMarkup:
    return _keyboard([[(texts.BTN_EFSET_NOT_YET, "efset:skip")]])


def _weights_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [(texts.BTN_WEIGHTS_BALANCED, "weights:balanced")],
            [(texts.BTN_WEIGHTS_WORK, "weights:work")],
            [(texts.BTN_WEIGHTS_LIFE, "weights:life")],
        ]
    )


def _morning_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [
                ("07:00", "morning:07:00"),
                ("08:00", "morning:08:00"),
                ("09:00", "morning:09:00"),
            ],
            [(texts.BTN_TIME_OTHER, "morning:other")],
        ]
    )


def _evening_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [
                ("19:00", "evening:19:00"),
                ("20:00", "evening:20:00"),
                ("21:00", "evening:21:00"),
            ],
            [(texts.BTN_TIME_OTHER, "evening:other")],
        ]
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [
                (texts.BTN_SAVE, "confirm:save"),
                (texts.BTN_START_OVER, "confirm:restart"),
            ]
        ]
    )


def _profile_keyboard() -> InlineKeyboardMarkup:
    return _keyboard(
        [
            [
                (texts.BTN_REDO, "profile:redo"),
                (texts.BTN_KEEP, "profile:keep"),
            ]
        ]
    )


def _summary_from_answers(data: dict[str, Any]) -> str:
    efset = data.get("efset_baseline")
    efset_line = "not yet" if efset is None else str(efset)
    return (
        f"{texts.ONBOARD_CONFIRM_INTRO}\n\n"
        f"Name: {data['name']}\n"
        f"Native language: {_lang_label(data['native_language'])}\n"
        f"EF SET: {efset_line} → {data['cefr_level']}\n"
        f"Work: {data['work_domain']}\n"
        f"Why: {data['why_statement']}\n"
        f"Focus: {_format_weights(data['track_weights'])}\n"
        f"Morning: {_format_time(data['morning_time'])}\n"
        f"Evening: {_format_time(data['evening_time'])}"
    )


def _summary_from_user(user: User) -> str:
    efset = user.efset_baseline
    efset_line = "not yet" if efset is None else str(efset)
    return (
        f"{texts.ONBOARD_PROFILE_INTRO}\n\n"
        f"Name: {user.name}\n"
        f"Native language: {_lang_label(user.native_language)}\n"
        f"EF SET: {efset_line} → {user.cefr_level}\n"
        f"Work: {user.work_domain or '—'}\n"
        f"Why: {user.why_statement or '—'}\n"
        f"Focus: {_format_weights(user.track_weights)}\n"
        f"Morning: {_format_time(user.morning_time)}\n"
        f"Evening: {_format_time(user.evening_time)}"
    )


async def _ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_answers(context)
    if update.effective_user is not None:
        mark_onboarding(context, update.effective_user.id)
    target = update.effective_message
    assert target is not None
    await target.reply_text(texts.ONBOARD_ASK_NAME)
    return NAME


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END

    existing = get_user(update.effective_user.id)
    if existing is not None and existing.onboarded:
        await update.message.reply_text(
            _summary_from_user(existing),
            reply_markup=_profile_keyboard(),
        )
        return PROFILE

    mark_onboarding(context, update.effective_user.id)
    await update.message.reply_text(texts.ONBOARD_WELCOME)
    return await _ask_name(update, context)


async def profile_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return PROFILE
    await query.answer()

    if query.data == "profile:keep":
        await query.edit_message_reply_markup(reply_markup=None)
        assert query.message is not None
        await query.message.reply_text(texts.ONBOARD_KEEP)
        if update.effective_user is not None:
            clear_onboarding(context, update.effective_user.id)
        return ConversationHandler.END

    if query.data == "profile:redo":
        await query.edit_message_reply_markup(reply_markup=None)
        assert query.message is not None
        await query.message.reply_text(texts.ONBOARD_REDO)
        return await _ask_name(update, context)

    return PROFILE


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.message.text is None:
        return NAME
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text(texts.ONBOARD_INVALID_NAME)
        return NAME
    _answers(context)["name"] = name
    await update.message.reply_text(
        texts.ONBOARD_ASK_NATIVE_LANG,
        reply_markup=_native_lang_keyboard(),
    )
    return NATIVE_LANG


async def receive_native_lang(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return NATIVE_LANG
    await query.answer()

    if query.data == "lang:other":
        await query.edit_message_reply_markup(reply_markup=None)
        assert query.message is not None
        await query.message.reply_text(texts.ONBOARD_ASK_NATIVE_LANG_OTHER)
        return NATIVE_LANG_OTHER

    code = query.data.removeprefix("lang:")
    if code not in _LANG_CODES:
        return NATIVE_LANG
    _answers(context)["native_language"] = _LANG_CODES[code]
    await query.edit_message_reply_markup(reply_markup=None)
    assert query.message is not None
    await query.message.reply_text(
        texts.ONBOARD_ASK_EFSET,
        reply_markup=_efset_keyboard(),
    )
    return EFSET


async def receive_native_lang_other(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return NATIVE_LANG_OTHER
    language = update.message.text.strip().lower()
    if not language:
        await update.message.reply_text(texts.ONBOARD_INVALID_LANG)
        return NATIVE_LANG_OTHER
    _answers(context)["native_language"] = language
    await update.message.reply_text(
        texts.ONBOARD_ASK_EFSET,
        reply_markup=_efset_keyboard(),
    )
    return EFSET


async def receive_efset_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return EFSET
    raw = update.message.text.strip()
    try:
        score = int(raw)
    except ValueError:
        await update.message.reply_text(
            texts.ONBOARD_INVALID_EFSET,
            reply_markup=_efset_keyboard(),
        )
        return EFSET
    if score < 1 or score > 100:
        await update.message.reply_text(
            texts.ONBOARD_INVALID_EFSET,
            reply_markup=_efset_keyboard(),
        )
        return EFSET
    answers = _answers(context)
    answers["efset_baseline"] = score
    answers["cefr_level"] = efset_to_cefr(score)
    await update.message.reply_text(texts.ONBOARD_ASK_DOMAIN)
    return DOMAIN


async def receive_efset_skip(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query is None:
        return EFSET
    await query.answer()
    answers = _answers(context)
    answers["efset_baseline"] = None
    answers["cefr_level"] = "B1"
    await query.edit_message_reply_markup(reply_markup=None)
    assert query.message is not None
    await query.message.reply_text(texts.ONBOARD_ASK_DOMAIN)
    return DOMAIN


async def receive_domain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.message.text is None:
        return DOMAIN
    domain = update.message.text.strip()
    if not domain:
        await update.message.reply_text(texts.ONBOARD_ASK_DOMAIN)
        return DOMAIN
    _answers(context)["work_domain"] = domain
    await update.message.reply_text(texts.ONBOARD_ASK_WHY)
    return WHY


async def receive_why(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.message.text is None:
        return WHY
    why = update.message.text.strip()
    if not why:
        await update.message.reply_text(texts.ONBOARD_ASK_WHY)
        return WHY
    _answers(context)["why_statement"] = why
    await update.message.reply_text(
        texts.ONBOARD_ASK_WEIGHTS,
        reply_markup=_weights_keyboard(),
    )
    return WEIGHTS


async def receive_weights(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return WEIGHTS
    await query.answer()
    key = query.data.removeprefix("weights:")
    preset = _WEIGHT_PRESETS.get(key)
    if preset is None:
        return WEIGHTS
    _answers(context)["track_weights"] = dict(preset)
    await query.edit_message_reply_markup(reply_markup=None)
    assert query.message is not None
    await query.message.reply_text(
        texts.ONBOARD_ASK_MORNING,
        reply_markup=_morning_keyboard(),
    )
    return MORNING


async def receive_morning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return MORNING
    await query.answer()

    if query.data == "morning:other":
        await query.edit_message_reply_markup(reply_markup=None)
        assert query.message is not None
        await query.message.reply_text(texts.ONBOARD_ASK_MORNING_OTHER)
        return MORNING_OTHER

    value = query.data.removeprefix("morning:")
    if _parse_time(value) is None:
        return MORNING
    _answers(context)["morning_time"] = value
    await query.edit_message_reply_markup(reply_markup=None)
    assert query.message is not None
    await query.message.reply_text(
        texts.ONBOARD_ASK_EVENING,
        reply_markup=_evening_keyboard(),
    )
    return EVENING


async def receive_morning_other(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return MORNING_OTHER
    parsed = _parse_time(update.message.text)
    if parsed is None:
        await update.message.reply_text(texts.ONBOARD_INVALID_TIME)
        return MORNING_OTHER
    _answers(context)["morning_time"] = parsed
    await update.message.reply_text(
        texts.ONBOARD_ASK_EVENING,
        reply_markup=_evening_keyboard(),
    )
    return EVENING


async def receive_evening(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return EVENING
    await query.answer()

    if query.data == "evening:other":
        await query.edit_message_reply_markup(reply_markup=None)
        assert query.message is not None
        await query.message.reply_text(texts.ONBOARD_ASK_EVENING_OTHER)
        return EVENING_OTHER

    value = query.data.removeprefix("evening:")
    if _parse_time(value) is None:
        return EVENING
    _answers(context)["evening_time"] = value
    await query.edit_message_reply_markup(reply_markup=None)
    assert query.message is not None
    await query.message.reply_text(
        _summary_from_answers(_answers(context)),
        reply_markup=_confirm_keyboard(),
    )
    return CONFIRM


async def receive_evening_other(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return EVENING_OTHER
    parsed = _parse_time(update.message.text)
    if parsed is None:
        await update.message.reply_text(texts.ONBOARD_INVALID_TIME)
        return EVENING_OTHER
    _answers(context)["evening_time"] = parsed
    await update.message.reply_text(
        _summary_from_answers(_answers(context)),
        reply_markup=_confirm_keyboard(),
    )
    return CONFIRM


async def receive_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        return CONFIRM
    await query.answer()

    if query.data == "confirm:restart":
        await query.edit_message_reply_markup(reply_markup=None)
        assert query.message is not None
        await query.message.reply_text(texts.ONBOARD_REDO)
        return await _ask_name(update, context)

    if query.data != "confirm:save":
        return CONFIRM

    data = _answers(context)
    try:
        save_onboarding(update.effective_user.id, data)
    except Exception:
        logger.exception(
            "save_onboarding failed user_id=%s", update.effective_user.id
        )
        await query.edit_message_reply_markup(reply_markup=None)
        assert query.message is not None
        await query.message.reply_text(texts.ONBOARD_SAVE_FAILED)
        _clear_answers(context)
        clear_onboarding(context, update.effective_user.id)
        return ConversationHandler.END

    _clear_answers(context)
    clear_onboarding(context, update.effective_user.id)
    await query.edit_message_reply_markup(reply_markup=None)
    assert query.message is not None
    await query.message.reply_text(texts.ONBOARD_SAVED)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_answers(context)
    if update.effective_user is not None:
        clear_onboarding(context, update.effective_user.id)
    if update.message is not None:
        await update.message.reply_text(texts.ONBOARD_CANCELLED)
    return ConversationHandler.END


def build_onboarding_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PROFILE: [
                CallbackQueryHandler(profile_choice, pattern=r"^profile:(redo|keep)$"),
            ],
            NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
            ],
            NATIVE_LANG: [
                CallbackQueryHandler(receive_native_lang, pattern=r"^lang:"),
            ],
            NATIVE_LANG_OTHER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, receive_native_lang_other
                ),
            ],
            EFSET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_efset_text),
                CallbackQueryHandler(receive_efset_skip, pattern=r"^efset:skip$"),
            ],
            DOMAIN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_domain),
            ],
            WHY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_why),
            ],
            WEIGHTS: [
                CallbackQueryHandler(receive_weights, pattern=r"^weights:"),
            ],
            MORNING: [
                CallbackQueryHandler(receive_morning, pattern=r"^morning:"),
            ],
            MORNING_OTHER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, receive_morning_other
                ),
            ],
            EVENING: [
                CallbackQueryHandler(receive_evening, pattern=r"^evening:"),
            ],
            EVENING_OTHER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, receive_evening_other
                ),
            ],
            CONFIRM: [
                CallbackQueryHandler(
                    receive_confirm, pattern=r"^confirm:(save|restart)$"
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        name="onboarding",
        persistent=False,
    )
