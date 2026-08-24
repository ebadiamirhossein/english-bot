""" /interests — single-message multi-select wizard (S9).

Seeds the interests table. Reading/video engines (S9a/S9b) consume the rows.
Callback data carries option indexes only — never topic text (64-byte limit
and colon-splitting; S1b).
"""

from __future__ import annotations

import html
import logging
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

from apps.bot import texts
from apps.bot.handlers.onboarding import layout_buttons
from core.services.interests import list_interests, replace_interests
from core.services.users import is_registered
from apps.bot import identity as bot_identity

logger = logging.getLogger(__name__)

(
    SUMMARY,
    WORK,
    WORK_OTHER,
    LIFE,
    LIFE_OTHER,
    CURIOSITY,
    CURIOSITY_OTHER,
) = range(7)

_TRACKS = ("work", "life", "curiosity")
_TRACK_CODE = {"work": "w", "life": "l", "curiosity": "c"}
_CODE_TRACK = {v: k for k, v in _TRACK_CODE.items()}
_TOGGLE_PREFIX = {"work": "tw", "life": "tl", "curiosity": "tc"}
_PREFIX_TRACK = {v: k for k, v in _TOGGLE_PREFIX.items()}

_TRACK_STATE = {"work": WORK, "life": LIFE, "curiosity": CURIOSITY}
_OTHER_STATE = {
    "work": WORK_OTHER,
    "life": LIFE_OTHER,
    "curiosity": CURIOSITY_OTHER,
}
_STATE_TRACK = {
    WORK: "work",
    WORK_OTHER: "work",
    LIFE: "life",
    LIFE_OTHER: "life",
    CURIOSITY: "curiosity",
    CURIOSITY_OTHER: "curiosity",
}
_NEXT_TRACK = {"work": "life", "life": "curiosity"}
_PREV_TRACK = {"life": "work", "curiosity": "life"}

_MIN_PER_TRACK = 2
_WIZARD_KEY = "interests"


def _esc(value: str) -> str:
    return html.escape(value, quote=False)


def topic_button_label(topic: str) -> str:
    """Display label for a topic; customs use the topic text as-is."""
    return texts.INTEREST_TOPIC_LABELS.get(topic, topic)


def can_proceed(selected: set[str] | list[str]) -> bool:
    return len(selected) >= _MIN_PER_TRACK


def done_button_label(selected_count: int) -> str:
    """Done-row label: tells the user how many more picks are needed."""
    if selected_count <= 0:
        return texts.BTN_INTERESTS_DONE_NEED_2
    if selected_count == 1:
        return texts.BTN_INTERESTS_DONE_NEED_1
    return texts.BTN_INTERESTS_DONE_READY


def track_ask_body(track: str) -> str:
    """Per-track screen body: header only (instruction lives on the Done button)."""
    ask = {
        "work": texts.INTERESTS_ASK_WORK,
        "life": texts.INTERESTS_ASK_LIFE,
        "curiosity": texts.INTERESTS_ASK_CURIOSITY,
    }[track]
    return f"<b>{_esc(ask)}</b>"


def build_option_list(track: str, extras: set[str] | list[str] | None = None) -> list[str]:
    """Presets first, then any non-preset topics (customs / DB leftovers)."""
    presets = list(texts.INTEREST_PRESETS[track])
    seen = set(presets)
    options = list(presets)
    for topic in extras or []:
        t = topic.strip().lower()
        if t and t not in seen:
            options.append(t)
            seen.add(t)
    return options


def track_topic_button_rows(
    track: str,
    options: list[str],
    selected: set[str],
) -> list[list[tuple[str, str]]]:
    """Topic toggle rows for a track, laid out via the shared S1d helper."""
    prefix = _TOGGLE_PREFIX[track]
    items: list[tuple[str, str]] = []
    for i, topic in enumerate(options):
        label = topic_button_label(topic)
        shown = f"✅ {label}" if topic in selected else label
        items.append((shown, f"int:{prefix}:{i}"))
    return layout_buttons(items)


def _wizard(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    data = context.user_data.setdefault(_WIZARD_KEY, {})
    if not isinstance(data, dict):
        data = {}
        context.user_data[_WIZARD_KEY] = data
    return data


def _clear_wizard(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(_WIZARD_KEY, None)


def _selected(context: ContextTypes.DEFAULT_TYPE, track: str) -> set[str]:
    wiz = _wizard(context)
    selected_map = wiz.setdefault("selected", {})
    if not isinstance(selected_map, dict):
        selected_map = {}
        wiz["selected"] = selected_map
    bucket = selected_map.setdefault(track, set())
    if not isinstance(bucket, set):
        bucket = set(bucket)
        selected_map[track] = bucket
    return bucket


def _options(context: ContextTypes.DEFAULT_TYPE, track: str) -> list[str]:
    wiz = _wizard(context)
    options_map = wiz.setdefault("options", {})
    if not isinstance(options_map, dict):
        options_map = {}
        wiz["options"] = options_map
    opts = options_map.get(track)
    if not isinstance(opts, list):
        opts = build_option_list(track, _selected(context, track))
        options_map[track] = opts
    return opts


def _set_options(
    context: ContextTypes.DEFAULT_TYPE, track: str, options: list[str]
) -> None:
    wiz = _wizard(context)
    options_map = wiz.setdefault("options", {})
    if not isinstance(options_map, dict):
        options_map = {}
        wiz["options"] = options_map
    options_map[track] = options


def _keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=data) for label, data in row]
            for row in rows
        ]
    )


def _init_empty_wizard(context: ContextTypes.DEFAULT_TYPE) -> None:
    wiz = _wizard(context)
    wiz["selected"] = {t: set() for t in _TRACKS}
    wiz["options"] = {t: build_option_list(t) for t in _TRACKS}


def _preload_from_db(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Load selections and option lists so custom topics stay toggleable."""
    rows = list_interests(user_id)
    selected: dict[str, set[str]] = {t: set() for t in _TRACKS}
    for row in rows:
        track = row.track if row.track in _TRACKS else ""
        if not track:
            continue
        selected[track].add(row.topic)
    options = {
        t: build_option_list(t, selected[t]) for t in _TRACKS
    }
    wiz = _wizard(context)
    wiz["selected"] = selected
    wiz["options"] = options


def _summary_from_selections(
    selections: list[tuple[str, str]],
) -> str:
    """Plain-text summary of saved topics by track (for the finish message)."""
    by_track: dict[str, list[str]] = {t: [] for t in _TRACKS}
    for topic, track in selections:
        if track in by_track:
            by_track[track].append(topic)
    lines: list[str] = []
    for track in _TRACKS:
        topics = by_track[track]
        label = texts.INTERESTS_TRACK_LABELS[track]
        if topics:
            shown = ", ".join(topics)
        else:
            shown = "—"
        lines.append(f"{label}: {shown}")
    return "\n".join(lines)


def _summary_body(user_id: int) -> str:
    rows = list_interests(user_id)
    by_track: dict[str, list[str]] = {t: [] for t in _TRACKS}
    for row in rows:
        if row.track in by_track:
            by_track[row.track].append(row.topic)
    lines = [
        f"<b>{_esc(texts.INTERESTS_PROFILE_INTRO)}</b>",
        "",
    ]
    for track in _TRACKS:
        topics = by_track[track]
        label = texts.INTERESTS_TRACK_LABELS[track]
        if topics:
            shown = ", ".join(_esc(t) for t in topics)
        else:
            shown = "—"
        lines.append(f"<b>{_esc(label)}</b>: {shown}")
    return "\n".join(lines)


def _track_keyboard(
    context: ContextTypes.DEFAULT_TYPE, track: str
) -> InlineKeyboardMarkup:
    options = _options(context, track)
    selected = _selected(context, track)
    rows = track_topic_button_rows(track, options, selected)
    code = _TRACK_CODE[track]
    rows.append([(texts.BTN_INTERESTS_OTHER, f"int:other:{code}")])
    rows.append([(done_button_label(len(selected)), f"int:done:{code}")])
    if track in _PREV_TRACK:
        rows.append([(texts.BTN_BACK, "int:back")])
    return _keyboard(rows)


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


async def _show_track(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    track: str,
) -> int:
    return await _show(
        update,
        context,
        _TRACK_STATE[track],
        text=track_ask_body(track),
        reply_markup=_track_keyboard(context, track),
    )


async def _show_other(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    track: str,
    error: str | None = None,
) -> int:
    prefix = f"{_esc(error)}\n\n" if error else ""
    body = f"{prefix}{_esc(texts.INTERESTS_ASK_OTHER)}"
    rows: list[list[tuple[str, str]]] = [[(texts.BTN_BACK, "int:back")]]
    return await _show(
        update,
        context,
        _OTHER_STATE[track],
        text=body,
        reply_markup=_keyboard(rows),
    )


def _selections_for_save(
    context: ContextTypes.DEFAULT_TYPE,
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for track in _TRACKS:
        for topic in sorted(_selected(context, track)):
            out.append((topic, track))
    return out


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END
    user_id = bot_identity.bot_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    if not is_registered(user_id):
        return ConversationHandler.END

    _clear_wizard(context)
    existing = list_interests(user_id)
    if existing:
        body = _summary_body(user_id)
        kb = _keyboard(
            layout_buttons(
                [
                    (texts.BTN_CHANGE, "int:profile:change"),
                    (texts.BTN_KEEP, "int:profile:keep"),
                ]
            )
        )
        return await _show(update, context, SUMMARY, text=body, reply_markup=kb)

    _init_empty_wizard(context)
    intro = f"{_esc(texts.INTERESTS_INTRO)}\n\n{track_ask_body('work')}"
    return await _show(
        update,
        context,
        WORK,
        text=intro,
        reply_markup=_track_keyboard(context, "work"),
    )


async def profile_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return SUMMARY
    await query.answer()

    parts = query.data.split(":", 2)
    if len(parts) < 3:
        return SUMMARY
    action = parts[2]

    if action == "keep":
        wiz = _wizard(context)
        chat_id = wiz.get("wizard_chat_id")
        msg_id = wiz.get("wizard_message_id")
        if chat_id is not None and msg_id is not None:
            await _safe_edit_message_text(
                context,
                chat_id=int(chat_id),
                message_id=int(msg_id),
                text=_esc(texts.INTERESTS_KEEP),
                reply_markup=None,
            )
        _clear_wizard(context)
        return ConversationHandler.END

    if action == "change":
        user_id = bot_identity.bot_user_id(update, context)
        if user_id is None:
            return ConversationHandler.END
        _preload_from_db(context, user_id)
        return await _show_track(update, context, "work")

    return SUMMARY


async def wizard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return WORK
    data = query.data

    parts = data.split(":", 2)
    if len(parts) < 2 or parts[0] != "int":
        await query.answer()
        return int(_wizard(context).get("wizard_state", WORK))

    action = parts[1]
    rest = parts[2] if len(parts) > 2 else ""

    current = int(_wizard(context).get("wizard_state", WORK))
    current_track = _STATE_TRACK.get(current)

    if action == "back":
        await query.answer()
        if current in (WORK_OTHER, LIFE_OTHER, CURIOSITY_OTHER):
            assert current_track is not None
            return await _show_track(update, context, current_track)
        if current_track and current_track in _PREV_TRACK:
            return await _show_track(update, context, _PREV_TRACK[current_track])
        return await _show_track(update, context, "work")

    if action in _PREFIX_TRACK:
        await query.answer()
        track = _PREFIX_TRACK[action]
        try:
            index = int(rest)
        except ValueError:
            return _TRACK_STATE[track]
        options = _options(context, track)
        if index < 0 or index >= len(options):
            return _TRACK_STATE[track]
        topic = options[index]
        selected = _selected(context, track)
        if topic in selected:
            selected.discard(topic)
        else:
            selected.add(topic)
        return await _show_track(update, context, track)

    if action == "other":
        await query.answer()
        track = _CODE_TRACK.get(rest)
        if track is None:
            return current
        return await _show_other(update, context, track)

    if action == "done":
        track = _CODE_TRACK.get(rest)
        if track is None:
            await query.answer()
            return current
        selected = _selected(context, track)
        if not can_proceed(selected):
            # Toast is instant; do not duplicate prose into the message body.
            await query.answer(text=texts.INTERESTS_DONE_TOAST)
            return await _show_track(update, context, track)
        await query.answer()
        if track in _NEXT_TRACK:
            return await _show_track(update, context, _NEXT_TRACK[track])
        # Curiosity done → save
        user_id = bot_identity.bot_user_id(update, context)
        if user_id is None:
            return ConversationHandler.END
        try:
            replace_interests(user_id, _selections_for_save(context))
        except Exception:
            logger.exception(
                "Failed to save interests for user_id=%s",
                user_id,
            )
            await _show(
                update,
                context,
                CURIOSITY,
                text=_esc(texts.INTERESTS_SAVE_FAILED),
                reply_markup=None,
            )
            _clear_wizard(context)
            return ConversationHandler.END
        selections = _selections_for_save(context)
        summary = _summary_from_selections(selections)
        await _show(
            update,
            context,
            CURIOSITY,
            text=_esc(
                texts.INTERESTS_SAVED_NAMED.format(summary=summary)
            ),
            reply_markup=None,
        )
        _clear_wizard(context)
        return ConversationHandler.END

    await query.answer()
    return current


async def receive_other(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Accept a custom topic from free text (Other screen or track screen).

    S26c: track screens previously had no MessageHandler, so ConversationHandler
    claimed the update (block=True) and dropped it — silence. Treat typed text
    on a track screen the same as Other: add the topic and confirm.
    """
    if update.message is None or update.message.text is None:
        current = int(_wizard(context).get("wizard_state", WORK_OTHER))
        track = _STATE_TRACK.get(current, "work")
        return await _show_other(update, context, track)

    current = int(_wizard(context).get("wizard_state", WORK_OTHER))
    track = _STATE_TRACK.get(current, "work")
    topic = update.message.text.strip().lower()
    if not topic:
        return await _show_other(
            update, context, track, error=texts.INTERESTS_INVALID_OTHER
        )

    options = _options(context, track)
    if topic not in options:
        options = list(options) + [topic]
        _set_options(context, track, options)
    _selected(context, track).add(topic)

    # Confirm on the typed message so the user always sees a reply (never silence).
    await update.message.reply_text(
        texts.INTERESTS_CUSTOM_ADDED.format(topic=topic)
    )

    # Keep editing the wizard message (not the typed one).
    return await _show_track(update, context, track)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_wizard(context)
    if update.message is not None:
        await update.message.reply_text(texts.INTERESTS_CANCELLED)
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


_WIZARD_MAP: dict[object, object] = {
    SUMMARY: SUMMARY,
    WORK: WORK,
    WORK_OTHER: WORK_OTHER,
    LIFE: LIFE,
    LIFE_OTHER: LIFE_OTHER,
    CURIOSITY: CURIOSITY,
    CURIOSITY_OTHER: CURIOSITY_OTHER,
    ConversationHandler.END: ConversationHandler.END,
}


def build_interests_handler() -> ConversationHandler:
    """Interests wizard. Free text on track + Other screens always gets a reply."""
    track_text = MessageHandler(filters.TEXT & ~filters.COMMAND, receive_other)
    return ConversationHandler(
        entry_points=[CommandHandler("interests", start)],
        states={
            SUMMARY: [
                _button_conversation(
                    "interests_profile",
                    profile_choice,
                    r"^int:profile:(change|keep)$",
                    {
                        SUMMARY: SUMMARY,
                        WORK: WORK,
                        ConversationHandler.END: ConversationHandler.END,
                    },
                ),
            ],
            WORK: [
                track_text,
                _button_conversation(
                    "interests_wiz_work",
                    wizard_callback,
                    r"^int:",
                    _WIZARD_MAP,
                ),
            ],
            WORK_OTHER: [
                track_text,
                _button_conversation(
                    "interests_wiz_work_other",
                    wizard_callback,
                    r"^int:",
                    _WIZARD_MAP,
                ),
            ],
            LIFE: [
                track_text,
                _button_conversation(
                    "interests_wiz_life",
                    wizard_callback,
                    r"^int:",
                    _WIZARD_MAP,
                ),
            ],
            LIFE_OTHER: [
                track_text,
                _button_conversation(
                    "interests_wiz_life_other",
                    wizard_callback,
                    r"^int:",
                    _WIZARD_MAP,
                ),
            ],
            CURIOSITY: [
                track_text,
                _button_conversation(
                    "interests_wiz_curiosity",
                    wizard_callback,
                    r"^int:",
                    _WIZARD_MAP,
                ),
            ],
            CURIOSITY_OTHER: [
                track_text,
                _button_conversation(
                    "interests_wiz_curiosity_other",
                    wizard_callback,
                    r"^int:",
                    _WIZARD_MAP,
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="interests",
        persistent=False,
        allow_reentry=True,
        per_message=False,
    )
