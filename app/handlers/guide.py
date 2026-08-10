"""``/guide`` — how to use the bot, in the bot (S18c).

Tapped-only single-message wizard. Nested callback ConversationHandler
with ``per_message=True`` under a ``per_message=False`` parent. No
``MessageHandler`` — same Agent-mode contract as ``/settings`` (S18a).
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
)

from app import texts
from app.handlers.onboarding import layout_buttons
from app.services.users import is_registered

logger = logging.getLogger(__name__)

(MENU, SECTION) = range(2)

_WIZARD_KEY = "guide"

# Section key → (button label, body text). Order is menu order.
_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("how", texts.BTN_GUIDE_HOW, texts.GUIDE_SECTION_HOW),
    ("save", texts.BTN_GUIDE_SAVE, texts.GUIDE_SECTION_SAVE),
    ("trancy", texts.BTN_GUIDE_TRANCY, texts.GUIDE_SECTION_TRANCY),
    ("lr", texts.BTN_GUIDE_LR, texts.GUIDE_SECTION_LR),
    ("anki1", texts.BTN_GUIDE_ANKI_FIRST, texts.GUIDE_SECTION_ANKI_FIRST),
    ("anki2", texts.BTN_GUIDE_ANKI_WEEK, texts.GUIDE_SECTION_ANKI_WEEK),
    ("phone", texts.BTN_GUIDE_ANKI_PHONE, texts.GUIDE_SECTION_ANKI_PHONE),
)

_SECTION_BY_KEY: dict[str, str] = {key: body for key, _label, body in _SECTIONS}


# --- shared helpers -----------------------------------------------------------


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
                    texts.GUIDE_STALE, reply_markup=None
                )
            except BadRequest as exc:
                if "message is not modified" not in str(exc).lower():
                    raise
    _clear_wizard(context)
    return ConversationHandler.END


def format_section_body(key: str) -> str | None:
    """Return HTML body for a section key, or None if unknown."""
    raw = _SECTION_BY_KEY.get(key)
    if raw is None:
        return None
    if "{template}" in raw:
        before, _, after = raw.partition("{template}")
        tmpl = html.escape(texts.GUIDE_ANKI_BACK_TEMPLATE, quote=False)
        return f"{_esc(before)}<pre>{tmpl}</pre>{_esc(after)}"
    return _esc(raw)


def section_keys() -> tuple[str, ...]:
    return tuple(key for key, _label, _body in _SECTIONS)


def section_bodies_plain() -> dict[str, str]:
    """Plain (pre-HTML) bodies for length / guilt tests — template expanded."""
    out: dict[str, str] = {}
    for key, _label, body in _SECTIONS:
        if "{template}" in body:
            out[key] = body.replace("{template}", texts.GUIDE_ANKI_BACK_TEMPLATE)
        else:
            out[key] = body
    return out


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


def _menu_body() -> str:
    return (
        f"<b>{_esc(texts.GUIDE_TITLE)}</b>\n\n"
        f"{_esc(texts.GUIDE_INTRO)}"
    )


def _menu_keyboard() -> InlineKeyboardMarkup:
    items = [
        (label, f"guide:menu:{key}") for key, label, _body in _SECTIONS
    ]
    items.append((texts.BTN_GUIDE_DONE, "guide:menu:done"))
    return _keyboard(layout_buttons(items))


def _section_keyboard() -> InlineKeyboardMarkup:
    return _keyboard([[(texts.BTN_BACK, "guide:back")]])


async def _show_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await _show(
        update,
        context,
        MENU,
        text=_menu_body(),
        reply_markup=_menu_keyboard(),
    )


# --- /guide entry + callbacks -------------------------------------------------


async def on_guide_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.effective_user is None or update.message is None:
        return ConversationHandler.END
    if not is_registered(update.effective_user.id):
        return ConversationHandler.END

    _clear_wizard(context)
    return await _show_menu(update, context)


async def on_guide_orphan_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Catch ``guide:`` taps when no conversation is active (post-restart)."""
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
    if data == "guide:menu:done":
        await _safe_edit_message_text(
            context,
            chat_id=int(_wizard(context)["wizard_chat_id"]),
            message_id=int(_wizard(context)["wizard_message_id"]),
            text=_esc(texts.GUIDE_DONE),
            reply_markup=None,
        )
        _clear_wizard(context)
        return ConversationHandler.END

    if data.startswith("guide:menu:"):
        key = data.removeprefix("guide:menu:")
        body = format_section_body(key)
        if body is None:
            return MENU
        return await _show(
            update,
            context,
            SECTION,
            text=body,
            reply_markup=_section_keyboard(),
        )

    return MENU


async def section_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        return SECTION
    if not _has_flight(context):
        return await _stale_end(update, context)
    await query.answer()

    if query.data == "guide:back":
        return await _show_menu(update, context)
    return SECTION


async def cancel_guide(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    _clear_wizard(context)
    if update.message is not None:
        await update.message.reply_text(texts.GUIDE_CANCELLED)
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


def build_guide_handler() -> ConversationHandler:
    """Tapped-only /guide — no MessageHandler, no conversation_timeout."""
    return ConversationHandler(
        entry_points=[CommandHandler("guide", on_guide_command)],
        states={
            MENU: [
                _button_conversation(
                    "guide_menu",
                    menu_callback,
                    r"^guide:menu:",
                    {
                        MENU: MENU,
                        SECTION: SECTION,
                        ConversationHandler.END: ConversationHandler.END,
                    },
                ),
            ],
            SECTION: [
                _button_conversation(
                    "guide_section",
                    section_callback,
                    r"^guide:back$",
                    {
                        MENU: MENU,
                        SECTION: SECTION,
                        ConversationHandler.END: ConversationHandler.END,
                    },
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_guide)],
        name="guide",
        persistent=False,
        allow_reentry=True,
        per_message=False,
    )


def build_guide_orphan_handler() -> CallbackQueryHandler:
    """Warm-degrade orphan ``guide:`` taps after restart (no active conversation)."""
    return CallbackQueryHandler(
        on_guide_orphan_callback, pattern=r"^guide:"
    )


def s18c_button_labels() -> list[str]:
    """Every S18c button label — for the ≤20-char audit."""
    return [
        texts.BTN_GUIDE_HOW,
        texts.BTN_GUIDE_SAVE,
        texts.BTN_GUIDE_TRANCY,
        texts.BTN_GUIDE_LR,
        texts.BTN_GUIDE_ANKI_FIRST,
        texts.BTN_GUIDE_ANKI_WEEK,
        texts.BTN_GUIDE_ANKI_PHONE,
        texts.BTN_GUIDE_DONE,
        texts.BTN_BACK,
    ]


def s18c_user_facing_strings() -> list[str]:
    """Strings introduced by S18c for the no-guilt assertion."""
    bodies = list(section_bodies_plain().values())
    return [
        texts.CMD_DESC_GUIDE,
        texts.HELP_LINE_GUIDE,
        texts.GUIDE_TITLE,
        texts.GUIDE_INTRO,
        texts.GUIDE_DONE,
        texts.GUIDE_CANCELLED,
        texts.GUIDE_STALE,
        texts.GUIDE_ANKI_BACK_TEMPLATE,
        texts.ONBOARD_SAVED,
        texts.ONBOARD_SAVED_EFSET_NUDGE,
        *s18c_button_labels(),
        *bodies,
    ]
