""" /start onboarding — single-message wizard (S1b/S1c) + personality (S1d). """

from __future__ import annotations

import html
import logging
import re
from datetime import time
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
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
    NAME_OTHER,
    LANG,
    LANG_OTHER,
    EFSET,
    EFSET_SCORE,
    LEVEL,
    DOMAIN,
    DOMAIN_SPECIFIC,
    DOMAIN_OTHER,
    WHY,
    WEIGHTS,
    MORNING,
    MORNING_OTHER,
    EVENING,
    EVENING_OTHER,
    CONFIRM,
) = range(18)

_TOTAL_STEPS = 8

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

_WEIGHT_PRESETS: dict[str, dict[str, int]] = {
    "balanced": {"work": 40, "life": 40, "curiosity": 20},
    "work": {"work": 60, "life": 25, "curiosity": 15},
    "life": {"work": 25, "life": 60, "curiosity": 15},
}

_LANG_CODES = {"fa", "lt", "ru", "pl"}

_SELF_ASSESS: dict[str, str] = {
    key: cefr for key, _label, cefr in texts.SELF_ASSESS_OPTIONS
}

_DOMAIN_CATEGORY_LABELS: dict[str, str] = dict(texts.DOMAIN_CATEGORIES)

_DOMAIN_SPECIFIC_LABELS: dict[str, dict[str, str]] = {
    cat: dict(specs) for cat, specs in texts.DOMAIN_SPECIFICS.items()
}

_WHY_CLAUSES: dict[str, str] = {key: clause for key, _label, clause in texts.WHY_OPTIONS}
_WHY_ORDER: tuple[str, ...] = tuple(key for key, _label, _clause in texts.WHY_OPTIONS)

# Progress-dot index (1–8); LEVEL and DOMAIN_SPECIFIC share their parent steps.
_STEP_INDEX: dict[int, int] = {
    NAME: 1,
    NAME_OTHER: 1,
    LANG: 2,
    LANG_OTHER: 2,
    EFSET: 3,
    EFSET_SCORE: 3,
    LEVEL: 3,
    DOMAIN: 4,
    DOMAIN_SPECIFIC: 4,
    DOMAIN_OTHER: 4,
    WHY: 5,
    WEIGHTS: 6,
    MORNING: 7,
    MORNING_OTHER: 7,
    EVENING: 8,
    EVENING_OTHER: 8,
    CONFIRM: 8,
}

_BACK_TARGET: dict[int, int] = {
    NAME_OTHER: NAME,
    LANG: NAME,
    LANG_OTHER: LANG,
    EFSET: LANG,
    EFSET_SCORE: EFSET,
    LEVEL: EFSET,
    DOMAIN_SPECIFIC: DOMAIN,
    WEIGHTS: WHY,
    MORNING: WEIGHTS,
    MORNING_OTHER: MORNING,
    EVENING: MORNING,
    EVENING_OTHER: EVENING,
    CONFIRM: EVENING,
}


def build_why_sentence(selected: list[str] | set[str]) -> str:
    """Turn ordered why keys into a natural sentence for S10 to quote back."""
    keys = [k for k in _WHY_ORDER if k in selected]
    clauses = [_WHY_CLAUSES[k] for k in keys]
    if not clauses:
        return ""
    if len(clauses) == 1:
        joined = clauses[0]
    elif len(clauses) == 2:
        joined = f"{clauses[0]} and {clauses[1]}"
    else:
        joined = ", ".join(clauses[:-1]) + f", and {clauses[-1]}"
    return f"I want to {joined}."


def self_assess_to_cefr(key: str) -> str | None:
    """Map a self-assessment button key to cefr_level. efset_baseline stays NULL."""
    return _SELF_ASSESS.get(key)


def _clear_answers(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("onboarding", None)
    context.user_data.pop("wizard_message_id", None)
    context.user_data.pop("wizard_chat_id", None)
    context.user_data.pop("suggested_name", None)
    context.user_data.pop("reaction", None)


def _answers(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    return context.user_data.setdefault("onboarding", {})


def _why_selected(context: ContextTypes.DEFAULT_TYPE) -> set[str]:
    answers = _answers(context)
    selected = answers.setdefault("why_keys", set())
    if not isinstance(selected, set):
        selected = set(selected)
        answers["why_keys"] = selected
    return selected


def _parse_time(raw: str) -> str | None:
    match = _TIME_RE.match(raw.strip())
    if not match:
        return None
    return f"{match.group(1)}:{match.group(2)}"


def _format_time(value: time | str) -> str:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return str(value)[:5]


def _lang_label(code: str) -> str:
    return texts.LANG_LABELS.get(code, code)


def _progress_dots(step: int) -> str:
    filled = max(0, min(step, _TOTAL_STEPS))
    return ("●" * filled) + ("○" * (_TOTAL_STEPS - filled))


def _esc(value: str) -> str:
    return html.escape(value, quote=False)


def _keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=data) for label, data in row]
            for row in rows
        ]
    )


def _with_back(rows: list[list[tuple[str, str]]]) -> list[list[tuple[str, str]]]:
    return rows + [[(texts.BTN_BACK, "wiz:back")]]


_MAX_SHARED_LABEL_LEN = 12


def layout_buttons(
    items: list[tuple[str, str]],
    *,
    max_per_row: int = 2,
) -> list[list[tuple[str, str]]]:
    """Lay out buttons so shared rows never include a label longer than 12 chars.

    Two (or ``max_per_row``) buttons share a row only when *every* label on that
    row is ≤ 12 characters including emoji. Longer labels always get their own
    row. Times use ``max_per_row=3``.
    """
    if max_per_row < 1:
        raise ValueError("max_per_row must be >= 1")
    rows: list[list[tuple[str, str]]] = []
    i = 0
    while i < len(items):
        label, _cb = items[i]
        if len(label) > _MAX_SHARED_LABEL_LEN:
            rows.append([items[i]])
            i += 1
            continue
        row = [items[i]]
        i += 1
        while (
            i < len(items)
            and len(row) < max_per_row
            and len(items[i][0]) <= _MAX_SHARED_LABEL_LEN
        ):
            row.append(items[i])
            i += 1
        rows.append(row)
    return rows


def _set_reaction(context: ContextTypes.DEFAULT_TYPE, key: str) -> None:
    reaction = texts.REACTIONS.get(key)
    if reaction:
        context.user_data["reaction"] = reaction
    else:
        context.user_data.pop("reaction", None)


def _prefix_lines(
    context: ContextTypes.DEFAULT_TYPE, error: str | None
) -> str:
    """Error replaces reaction; both never show at once."""
    if error:
        return f"{_esc(error)}\n\n"
    reaction = context.user_data.get("reaction")
    if reaction:
        return f"{_esc(str(reaction))}\n\n"
    return ""


def _weight_key_for(weights: dict[str, int]) -> str | None:
    for key, preset in _WEIGHT_PRESETS.items():
        if preset == weights:
            return key
    return None


def _back_target(context: ContextTypes.DEFAULT_TYPE, current: int) -> int:
    """Resolve Back, including dynamic domain / why targets."""
    if current == DOMAIN:
        if _answers(context).get("efset_baseline") is not None:
            return EFSET_SCORE
        return LEVEL
    if current == DOMAIN_OTHER:
        if _answers(context).get("domain_category"):
            return DOMAIN_SPECIFIC
        return DOMAIN
    if current == WHY:
        if _answers(context).get("domain_category"):
            return DOMAIN_SPECIFIC
        return DOMAIN
    return _BACK_TARGET.get(current, NAME)


def _profile_body_html(data: dict[str, Any]) -> str:
    name = _esc(str(data["name"]))
    lang = _esc(_lang_label(str(data["native_language"])))
    cefr = _esc(str(data["cefr_level"]))
    domain = _esc(str(data.get("work_domain") or "—"))
    why = _esc(str(data.get("why_statement") or "—"))
    weights = data["track_weights"]
    weight_key = _weight_key_for(weights) if isinstance(weights, dict) else None
    weight_label = texts.WEIGHT_SUMMARY_LABELS.get(weight_key or "", "Custom")
    morning = _esc(_format_time(data["morning_time"]))
    evening = _esc(_format_time(data["evening_time"]))
    return (
        f"{name} · {lang} · {cefr}\n"
        f"{domain}\n"
        f"{_esc(weight_label)} — work {weights.get('work', 0)} · "
        f"life {weights.get('life', 0)} · "
        f"curiosity {weights.get('curiosity', 0)}\n"
        f"Morning {morning} · Evening {evening}\n\n"
        f'"{why}"'
    )


def _confirm_body(data: dict[str, Any]) -> str:
    return (
        f"{_progress_dots(8)}\n\n"
        f"<b>{_esc(texts.ONBOARD_CONFIRM_INTRO)}</b>\n\n"
        f"{_profile_body_html(data)}"
    )


def _profile_summary_body(user: User) -> str:
    data = {
        "name": user.name,
        "native_language": user.native_language,
        "efset_baseline": user.efset_baseline,
        "cefr_level": user.cefr_level,
        "work_domain": user.work_domain or "—",
        "why_statement": user.why_statement or "—",
        "track_weights": user.track_weights,
        "morning_time": user.morning_time,
        "evening_time": user.evening_time,
    }
    return (
        f"<b>{_esc(texts.ONBOARD_PROFILE_INTRO)}</b>\n\n"
        f"{_profile_body_html(data)}"
    )


def _load_user_into_answers(context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    answers = _answers(context)
    answers["name"] = user.name
    answers["native_language"] = user.native_language
    answers["efset_baseline"] = user.efset_baseline
    answers["cefr_level"] = user.cefr_level
    answers["work_domain"] = user.work_domain or ""
    answers["why_statement"] = user.why_statement or ""
    answers["track_weights"] = dict(user.track_weights)
    answers["morning_time"] = _format_time(user.morning_time)
    answers["evening_time"] = _format_time(user.evening_time)
    if "why_keys" not in answers:
        answers["why_keys"] = set()


def _build_step(
    context: ContextTypes.DEFAULT_TYPE, state: int, error: str | None = None
) -> tuple[str, InlineKeyboardMarkup | None]:
    step = _STEP_INDEX.get(state, 1)
    dots = _progress_dots(step)
    prefix = _prefix_lines(context, error)

    if state == NAME:
        suggested = context.user_data.get("suggested_name")
        if suggested:
            body = texts.ONBOARD_GREETING.format(name=_esc(str(suggested)))
            kb = _keyboard(
                layout_buttons(
                    [
                        (texts.BTN_NAME_YES, "wiz:name:yes"),
                        (texts.BTN_NAME_OTHER, "wiz:name:other"),
                    ]
                )
            )
            return f"{dots}\n\n{prefix}{body}", kb
        body = f"<b>{_esc(texts.ONBOARD_ASK_NAME)}</b>"
        return f"{dots}\n\n{prefix}{body}", None

    if state == NAME_OTHER:
        body = f"<b>{_esc(texts.ONBOARD_ASK_NAME)}</b>"
        kb = _keyboard(_with_back([]))
        return f"{dots}\n\n{prefix}{body}", kb

    if state == LANG:
        body = f"<b>{_esc(texts.ONBOARD_ASK_NATIVE_LANG)}</b>"
        kb = _keyboard(
            _with_back(
                layout_buttons(
                    [
                        (texts.BTN_LANG_FARSI, "wiz:lang:fa"),
                        (texts.BTN_LANG_LITHUANIAN, "wiz:lang:lt"),
                        (texts.BTN_LANG_RUSSIAN, "wiz:lang:ru"),
                        (texts.BTN_LANG_POLISH, "wiz:lang:pl"),
                        (texts.BTN_LANG_OTHER, "wiz:lang:other"),
                    ]
                )
            )
        )
        return f"{dots}\n\n{prefix}{body}", kb

    if state == LANG_OTHER:
        body = f"<b>{_esc(texts.ONBOARD_ASK_NATIVE_LANG_OTHER)}</b>"
        kb = _keyboard(_with_back([]))
        return f"{dots}\n\n{prefix}{body}", kb

    if state == EFSET:
        body = (
            f"<b>{_esc(texts.ONBOARD_ASK_EFSET)}</b>\n"
            f"{_esc(texts.ONBOARD_ASK_EFSET_HELPER)}"
        )
        kb = _keyboard(
            _with_back(
                layout_buttons(
                    [
                        (texts.BTN_EFSET_KNOW, "wiz:efset:know"),
                        (texts.BTN_EFSET_NOT_YET, "wiz:efset:skip"),
                    ]
                )
            )
        )
        return f"{dots}\n\n{prefix}{body}", kb

    if state == EFSET_SCORE:
        body = f"<b>{_esc(texts.ONBOARD_ASK_EFSET_SCORE)}</b>"
        kb = _keyboard(_with_back([]))
        return f"{dots}\n\n{prefix}{body}", kb

    if state == LEVEL:
        body = f"<b>{_esc(texts.ONBOARD_ASK_LEVEL)}</b>"
        level_buttons = [
            (label, f"wiz:level:{key}")
            for key, label, _cefr in texts.SELF_ASSESS_OPTIONS
        ]
        kb = _keyboard(_with_back(layout_buttons(level_buttons)))
        return f"{dots}\n\n{prefix}{body}", kb

    if state == DOMAIN:
        body = f"<b>{_esc(texts.ONBOARD_ASK_DOMAIN)}</b>"
        cat_buttons = [
            (label, f"wiz:domain:cat:{key}")
            for key, label in texts.DOMAIN_CATEGORIES
        ]
        kb = _keyboard(_with_back(layout_buttons(cat_buttons)))
        return f"{dots}\n\n{prefix}{body}", kb

    if state == DOMAIN_SPECIFIC:
        cat = str(_answers(context).get("domain_category") or "")
        specifics = texts.DOMAIN_SPECIFICS.get(cat, [])
        body = f"<b>{_esc(texts.ONBOARD_ASK_DOMAIN_SPECIFIC)}</b>"
        spec_buttons = [
            (label, f"wiz:domain:pick:{key}") for key, label in specifics
        ]
        rows = layout_buttons(spec_buttons)
        rows.append([(texts.BTN_DOMAIN_OTHER, "wiz:domain:other")])
        kb = _keyboard(_with_back(rows))
        return f"{dots}\n\n{prefix}{body}", kb

    if state == DOMAIN_OTHER:
        body = f"<b>{_esc(texts.ONBOARD_ASK_DOMAIN_OTHER)}</b>"
        kb = _keyboard(_with_back([]))
        return f"{dots}\n\n{prefix}{body}", kb

    if state == WHY:
        selected = _why_selected(context)
        helper = "" if error else f"\n{_esc(texts.ONBOARD_ASK_WHY_HELPER)}"
        body = (
            f"{dots}\n\n{prefix}"
            f"<b>{_esc(texts.ONBOARD_ASK_WHY)}</b>{helper}"
        )
        why_buttons: list[tuple[str, str]] = []
        for key, label, _clause in texts.WHY_OPTIONS:
            shown = f"✅ {label}" if key in selected else label
            why_buttons.append((shown, f"wiz:why:toggle:{key}"))
        rows = layout_buttons(why_buttons)
        rows.append([(texts.BTN_WHY_DONE, "wiz:why:done")])
        kb = _keyboard(_with_back(rows))
        return body, kb

    if state == WEIGHTS:
        body = f"<b>{_esc(texts.ONBOARD_ASK_WEIGHTS)}</b>"
        kb = _keyboard(
            _with_back(
                layout_buttons(
                    [
                        (texts.BTN_WEIGHTS_BALANCED, "wiz:weights:balanced"),
                        (texts.BTN_WEIGHTS_WORK, "wiz:weights:work"),
                        (texts.BTN_WEIGHTS_LIFE, "wiz:weights:life"),
                    ]
                )
            )
        )
        return f"{dots}\n\n{prefix}{body}", kb

    if state == MORNING:
        body = f"<b>{_esc(texts.ONBOARD_ASK_MORNING)}</b>"
        time_rows = layout_buttons(
            [
                (texts.BTN_MORNING_07, "wiz:morning:07:00"),
                (texts.BTN_MORNING_08, "wiz:morning:08:00"),
                (texts.BTN_MORNING_09, "wiz:morning:09:00"),
            ],
            max_per_row=3,
        )
        time_rows.append([(texts.BTN_TIME_OTHER, "wiz:morning:other")])
        kb = _keyboard(_with_back(time_rows))
        return f"{dots}\n\n{prefix}{body}", kb

    if state == MORNING_OTHER:
        body = f"<b>{_esc(texts.ONBOARD_ASK_MORNING_OTHER)}</b>"
        kb = _keyboard(_with_back([]))
        return f"{dots}\n\n{prefix}{body}", kb

    if state == EVENING:
        body = f"<b>{_esc(texts.ONBOARD_ASK_EVENING)}</b>"
        time_rows = layout_buttons(
            [
                (texts.BTN_EVENING_19, "wiz:evening:19:00"),
                (texts.BTN_EVENING_20, "wiz:evening:20:00"),
                (texts.BTN_EVENING_21, "wiz:evening:21:00"),
            ],
            max_per_row=3,
        )
        time_rows.append([(texts.BTN_TIME_OTHER, "wiz:evening:other")])
        kb = _keyboard(_with_back(time_rows))
        return f"{dots}\n\n{prefix}{body}", kb

    if state == EVENING_OTHER:
        body = f"<b>{_esc(texts.ONBOARD_ASK_EVENING_OTHER)}</b>"
        kb = _keyboard(_with_back([]))
        return f"{dots}\n\n{prefix}{body}", kb

    if state == CONFIRM:
        body = _confirm_body(_answers(context))
        if prefix:
            body = f"{prefix}{body}"
        kb = _keyboard(
            layout_buttons(
                [
                    (texts.BTN_SAVE, "wiz:confirm:save"),
                    (texts.BTN_CHANGE, "wiz:confirm:change"),
                ]
            )
        )
        return body, kb

    return f"{dots}\n\n{_esc('Something went wrong. Say /start.')}", None


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


async def _show(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    state: int,
    error: str | None = None,
) -> int:
    context.user_data["wizard_state"] = state
    text, keyboard = _build_step(context, state, error)
    wizard_id = context.user_data.get("wizard_message_id")
    chat_id = context.user_data.get("wizard_chat_id")

    if wizard_id is not None and chat_id is not None:
        await _safe_edit_message_text(
            context,
            chat_id=chat_id,
            message_id=wizard_id,
            text=text,
            reply_markup=keyboard,
        )
        return state

    target = update.effective_message
    assert target is not None
    msg = await target.reply_text(
        text, reply_markup=keyboard, parse_mode=ParseMode.HTML
    )
    context.user_data["wizard_message_id"] = msg.message_id
    context.user_data["wizard_chat_id"] = msg.chat_id
    return state


def _button_conversation(
    name: str,
    callback: Any,
    pattern: str,
    map_to_parent: dict[object, object],
) -> ConversationHandler:
    """Callback-only nested conversation (per_message=True)."""
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


_WIZARD_MAP: dict[object, object] = {
    PROFILE: PROFILE,
    NAME: NAME,
    NAME_OTHER: NAME_OTHER,
    LANG: LANG,
    LANG_OTHER: LANG_OTHER,
    EFSET: EFSET,
    EFSET_SCORE: EFSET_SCORE,
    LEVEL: LEVEL,
    DOMAIN: DOMAIN,
    DOMAIN_SPECIFIC: DOMAIN_SPECIFIC,
    DOMAIN_OTHER: DOMAIN_OTHER,
    WHY: WHY,
    WEIGHTS: WEIGHTS,
    MORNING: MORNING,
    MORNING_OTHER: MORNING_OTHER,
    EVENING: EVENING,
    EVENING_OTHER: EVENING_OTHER,
    CONFIRM: CONFIRM,
    ConversationHandler.END: ConversationHandler.END,
}


async def _begin_wizard(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, preserve: bool
) -> int:
    if not preserve:
        _clear_answers(context)

    if update.effective_user is not None:
        mark_onboarding(context, update.effective_user.id)
        if not preserve or not context.user_data.get("suggested_name"):
            first = (update.effective_user.first_name or "").strip()
            if first:
                context.user_data["suggested_name"] = first
            else:
                context.user_data.pop("suggested_name", None)

    return await _show(update, context, NAME)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END

    existing = get_user(update.effective_user.id)
    if existing is not None and existing.onboarded:
        context.user_data.pop("wizard_message_id", None)
        context.user_data.pop("wizard_chat_id", None)
        body = _profile_summary_body(existing)
        kb = _keyboard(
            [
                [
                    (texts.BTN_CHANGE, "profile:change"),
                    (texts.BTN_KEEP, "profile:keep"),
                ]
            ]
        )
        msg = await update.message.reply_text(
            body, reply_markup=kb, parse_mode=ParseMode.HTML
        )
        context.user_data["wizard_message_id"] = msg.message_id
        context.user_data["wizard_chat_id"] = msg.chat_id
        return PROFILE

    return await _begin_wizard(update, context, preserve=False)


async def profile_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return PROFILE
    await query.answer()

    if query.data == "profile:keep":
        chat_id = context.user_data.get("wizard_chat_id")
        msg_id = context.user_data.get("wizard_message_id")
        if chat_id is not None and msg_id is not None:
            await _safe_edit_message_text(
                context,
                chat_id=chat_id,
                message_id=msg_id,
                text=_esc(texts.ONBOARD_KEEP),
                reply_markup=None,
            )
        if update.effective_user is not None:
            clear_onboarding(context, update.effective_user.id)
        _clear_answers(context)
        return ConversationHandler.END

    if query.data == "profile:change":
        if update.effective_user is not None:
            user = get_user(update.effective_user.id)
            if user is not None:
                context.user_data.pop("onboarding", None)
                _load_user_into_answers(context, user)
                context.user_data["suggested_name"] = user.name
                mark_onboarding(context, update.effective_user.id)
                return await _show(update, context, NAME)
        return await _begin_wizard(update, context, preserve=False)

    return PROFILE


async def wizard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return NAME
    await query.answer()
    data = query.data

    current = context.user_data.get("wizard_state")
    if current is None:
        current = NAME

    if data == "wiz:back":
        context.user_data.pop("reaction", None)
        target = _back_target(context, int(current))
        return await _show(update, context, target)

    if data == "wiz:name:yes":
        suggested = context.user_data.get("suggested_name") or ""
        if not str(suggested).strip():
            _set_reaction(context, "name:other")
            return await _show(update, context, NAME_OTHER)
        _answers(context)["name"] = str(suggested).strip()
        _set_reaction(context, "name:yes")
        return await _show(update, context, LANG)

    if data == "wiz:name:other":
        _set_reaction(context, "name:other")
        return await _show(update, context, NAME_OTHER)

    if data.startswith("wiz:lang:"):
        choice = data.removeprefix("wiz:lang:")
        if choice == "other":
            _set_reaction(context, "lang:other")
            return await _show(update, context, LANG_OTHER)
        if choice not in _LANG_CODES:
            return LANG
        _answers(context)["native_language"] = choice
        _set_reaction(context, f"lang:{choice}")
        return await _show(update, context, EFSET)

    if data == "wiz:efset:know":
        _set_reaction(context, "efset:know")
        return await _show(update, context, EFSET_SCORE)

    if data == "wiz:efset:skip":
        answers = _answers(context)
        answers["efset_baseline"] = None
        answers.pop("cefr_level", None)
        _set_reaction(context, "efset:skip")
        return await _show(update, context, LEVEL)

    if data.startswith("wiz:level:"):
        key = data.removeprefix("wiz:level:")
        cefr = self_assess_to_cefr(key)
        if cefr is None:
            return LEVEL
        answers = _answers(context)
        answers["efset_baseline"] = None
        answers["cefr_level"] = cefr
        _set_reaction(context, f"level:{key}")
        return await _show(update, context, DOMAIN)

    # Domain drill-down: wiz:domain:cat:<key> | wiz:domain:pick:<key> | wiz:domain:other
    if data.startswith("wiz:domain:"):
        parts = data.split(":", 3)
        action = parts[2] if len(parts) >= 3 else ""
        if action == "other":
            _set_reaction(context, "domain:other")
            return await _show(update, context, DOMAIN_OTHER)
        if action == "cat" and len(parts) == 4:
            cat = parts[3]
            if cat not in _DOMAIN_CATEGORY_LABELS:
                return DOMAIN
            _answers(context)["domain_category"] = cat
            _set_reaction(context, f"domain:cat:{cat}")
            return await _show(update, context, DOMAIN_SPECIFIC)
        if action == "pick" and len(parts) == 4:
            spec_key = parts[3]
            cat = str(_answers(context).get("domain_category") or "")
            label = _DOMAIN_SPECIFIC_LABELS.get(cat, {}).get(spec_key)
            if label is None:
                return DOMAIN_SPECIFIC
            _answers(context)["work_domain"] = label.lower()
            pick_key = f"domain:pick:{spec_key}"
            if pick_key not in texts.REACTIONS:
                pick_key = f"domain:cat:{cat}"
            _set_reaction(context, pick_key)
            return await _show(update, context, WHY)
        return DOMAIN

    if data.startswith("wiz:why:toggle:"):
        key = data.removeprefix("wiz:why:toggle:")
        if key not in _WHY_CLAUSES:
            return WHY
        selected = _why_selected(context)
        if key in selected:
            selected.discard(key)
        else:
            selected.add(key)
            _set_reaction(context, f"why:{key}")
        return await _show(update, context, WHY)

    if data == "wiz:why:done":
        selected = _why_selected(context)
        if not selected:
            return await _show(update, context, WHY, error=texts.ONBOARD_WHY_NUDGE)
        _answers(context)["why_statement"] = build_why_sentence(selected)
        _set_reaction(context, "why:done")
        return await _show(update, context, WEIGHTS)

    if data.startswith("wiz:weights:"):
        key = data.removeprefix("wiz:weights:")
        preset = _WEIGHT_PRESETS.get(key)
        if preset is None:
            return WEIGHTS
        answers = _answers(context)
        answers["track_weights"] = dict(preset)
        answers["weight_key"] = key
        _set_reaction(context, f"weights:{key}")
        return await _show(update, context, MORNING)

    if data.startswith("wiz:morning:"):
        parts = data.split(":", 2)
        value = parts[2] if len(parts) == 3 else ""
        if value == "other":
            _set_reaction(context, "morning:other")
            return await _show(update, context, MORNING_OTHER)
        if _parse_time(value) is None:
            return MORNING
        _answers(context)["morning_time"] = value
        _set_reaction(context, f"morning:{value}")
        return await _show(update, context, EVENING)

    if data.startswith("wiz:evening:"):
        parts = data.split(":", 2)
        value = parts[2] if len(parts) == 3 else ""
        if value == "other":
            _set_reaction(context, "evening:other")
            return await _show(update, context, EVENING_OTHER)
        if _parse_time(value) is None:
            return EVENING
        _answers(context)["evening_time"] = value
        _set_reaction(context, f"evening:{value}")
        return await _show(update, context, CONFIRM)

    if data == "wiz:confirm:change":
        context.user_data.pop("reaction", None)
        suggested = _answers(context).get("name")
        if suggested:
            context.user_data["suggested_name"] = suggested
        return await _show(update, context, NAME)

    if data == "wiz:confirm:save":
        if update.effective_user is None:
            return CONFIRM
        data_answers = _answers(context)
        try:
            save_onboarding(update.effective_user.id, data_answers)
        except Exception:
            logger.exception(
                "save_onboarding failed user_id=%s", update.effective_user.id
            )
            chat_id = context.user_data.get("wizard_chat_id")
            msg_id = context.user_data.get("wizard_message_id")
            if chat_id is not None and msg_id is not None:
                await _safe_edit_message_text(
                    context,
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=_esc(texts.ONBOARD_SAVE_FAILED),
                    reply_markup=None,
                )
            clear_onboarding(context, update.effective_user.id)
            _clear_answers(context)
            return ConversationHandler.END

        name = str(data_answers["name"])
        morning = _format_time(data_answers["morning_time"])
        efset = data_answers.get("efset_baseline")
        template = (
            texts.ONBOARD_SAVED
            if efset is not None
            else texts.ONBOARD_SAVED_EFSET_NUDGE
        )
        clear_onboarding(context, update.effective_user.id)
        _clear_answers(context)

        # Sticker celebration skipped — no stable public file_id without bundling.
        assert query.message is not None
        await query.message.reply_text(
            template.format(name=name, morning_time=morning)
        )
        return ConversationHandler.END

    return int(current)


async def receive_name_other(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return NAME_OTHER
    name = update.message.text.strip()
    if not name:
        return await _show(update, context, NAME_OTHER, error=texts.ONBOARD_INVALID_NAME)
    _answers(context)["name"] = name
    _set_reaction(context, "name:typed")
    return await _show(update, context, LANG)


async def receive_name_direct(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Free-text name when Telegram first_name is empty (no confirm buttons)."""
    if update.message is None or update.message.text is None:
        return NAME
    name = update.message.text.strip()
    if not name:
        return await _show(update, context, NAME, error=texts.ONBOARD_INVALID_NAME)
    _answers(context)["name"] = name
    _set_reaction(context, "name:typed")
    return await _show(update, context, LANG)


async def receive_lang_other(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return LANG_OTHER
    language = update.message.text.strip().lower()
    if not language:
        return await _show(
            update, context, LANG_OTHER, error=texts.ONBOARD_INVALID_LANG
        )
    _answers(context)["native_language"] = language
    _set_reaction(context, "lang:typed")
    return await _show(update, context, EFSET)


async def receive_efset_score(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return EFSET_SCORE
    raw = update.message.text.strip()
    try:
        score = int(raw)
    except ValueError:
        return await _show(
            update, context, EFSET_SCORE, error=texts.ONBOARD_INVALID_EFSET
        )
    if score < 1 or score > 100:
        return await _show(
            update, context, EFSET_SCORE, error=texts.ONBOARD_INVALID_EFSET
        )
    answers = _answers(context)
    answers["efset_baseline"] = score
    answers["cefr_level"] = efset_to_cefr(score)
    _set_reaction(context, f"efset_score:{answers['cefr_level']}")
    return await _show(update, context, DOMAIN)


async def receive_domain_other(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return DOMAIN_OTHER
    domain = update.message.text.strip()
    if not domain:
        return await _show(
            update, context, DOMAIN_OTHER, error=texts.ONBOARD_ASK_DOMAIN_OTHER
        )
    _answers(context)["work_domain"] = domain
    _set_reaction(context, "domain:typed")
    return await _show(update, context, WHY)


async def receive_morning_other(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return MORNING_OTHER
    parsed = _parse_time(update.message.text)
    if parsed is None:
        return await _show(
            update, context, MORNING_OTHER, error=texts.ONBOARD_INVALID_TIME
        )
    _answers(context)["morning_time"] = parsed
    _set_reaction(context, "morning:typed")
    return await _show(update, context, EVENING)


async def receive_evening_other(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.message is None or update.message.text is None:
        return EVENING_OTHER
    parsed = _parse_time(update.message.text)
    if parsed is None:
        return await _show(
            update, context, EVENING_OTHER, error=texts.ONBOARD_INVALID_TIME
        )
    _answers(context)["evening_time"] = parsed
    _set_reaction(context, "evening:typed")
    return await _show(update, context, CONFIRM)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_answers(context)
    if update.effective_user is not None:
        clear_onboarding(context, update.effective_user.id)
    if update.message is not None:
        await update.message.reply_text(texts.ONBOARD_CANCELLED)
    return ConversationHandler.END


def _wizard_buttons(name: str) -> ConversationHandler:
    """Fresh nested CH per parent state — do not reuse one instance."""
    return _button_conversation(name, wizard_callback, r"^wiz:", _WIZARD_MAP)


def build_onboarding_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PROFILE: [
                _button_conversation(
                    "onboarding_profile",
                    profile_choice,
                    r"^profile:(change|keep)$",
                    {
                        PROFILE: PROFILE,
                        NAME: NAME,
                        ConversationHandler.END: ConversationHandler.END,
                    },
                ),
            ],
            NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name_direct),
                _wizard_buttons("onboarding_wiz_name"),
            ],
            NAME_OTHER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name_other),
                _wizard_buttons("onboarding_wiz_name_other"),
            ],
            LANG: [_wizard_buttons("onboarding_wiz_lang")],
            LANG_OTHER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_lang_other),
                _wizard_buttons("onboarding_wiz_lang_other"),
            ],
            EFSET: [_wizard_buttons("onboarding_wiz_efset")],
            EFSET_SCORE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_efset_score),
                _wizard_buttons("onboarding_wiz_efset_score"),
            ],
            LEVEL: [_wizard_buttons("onboarding_wiz_level")],
            DOMAIN: [_wizard_buttons("onboarding_wiz_domain")],
            DOMAIN_SPECIFIC: [_wizard_buttons("onboarding_wiz_domain_specific")],
            DOMAIN_OTHER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_domain_other),
                _wizard_buttons("onboarding_wiz_domain_other"),
            ],
            WHY: [_wizard_buttons("onboarding_wiz_why")],
            WEIGHTS: [_wizard_buttons("onboarding_wiz_weights")],
            MORNING: [_wizard_buttons("onboarding_wiz_morning")],
            MORNING_OTHER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_morning_other),
                _wizard_buttons("onboarding_wiz_morning_other"),
            ],
            EVENING: [_wizard_buttons("onboarding_wiz_evening")],
            EVENING_OTHER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_evening_other),
                _wizard_buttons("onboarding_wiz_evening_other"),
            ],
            CONFIRM: [_wizard_buttons("onboarding_wiz_confirm")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        name="onboarding",
        persistent=False,
        per_message=False,
    )
