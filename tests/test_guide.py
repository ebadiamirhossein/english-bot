"""S18c: /guide — tapped-only how-to wizard."""

from __future__ import annotations

import asyncio
import re
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import User
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
)

from app import texts
from app.db import close_pool, connection
from app.handlers.guide import (
    MENU,
    SECTION,
    build_guide_handler,
    format_section_body,
    menu_callback,
    on_guide_command,
    on_guide_orphan_callback,
    s18c_button_labels,
    s18c_user_facing_strings,
    section_bodies_plain,
    section_callback,
    section_keys,
)
from app.main import register_handlers
from app.services.commands import menu_command_names
from app.services.users import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_510_000_000

_GUILT = re.compile(
    r"\b(fail(ed|ure)?|broke your|disappoint|guilt|lazy|should have|"
    r"missed)\b|😞|😢|😔|☹️|🙁|😟|😤|😠",
    re.IGNORECASE,
)

_COMMAND_IN_PROSE = re.compile(
    r"(?<![<\w])/(?P<name>[a-z][a-z0-9_]*)\b"
)


@pytest.fixture
def fake_telegram_id() -> int:
    return FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)


@pytest.fixture(autouse=True)
def _close_pool_after_test() -> None:
    yield
    close_pool()


def _delete_user(telegram_user_id: int) -> None:
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM users WHERE telegram_user_id = %s",
                (telegram_user_id,),
            )


@pytest.fixture
def cleanup_user(fake_telegram_id: int):
    yield fake_telegram_id
    _delete_user(fake_telegram_id)


def _onboard(tid: int) -> None:
    save_onboarding(
        tid,
        {
            "name": "Guide Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": "08:00",
            "evening_time": "21:00",
        },
    )


def _ctx(*, chat_id: int = 20, message_id: int = 10) -> MagicMock:
    context = MagicMock()
    context.user_data = {
        "guide": {
            "wizard_chat_id": chat_id,
            "wizard_message_id": message_id,
            "wizard_state": MENU,
        }
    }
    context.bot = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    return context


def _cmd_update(user_id: int) -> MagicMock:
    user = User(id=user_id, first_name="A", is_bot=False)
    msg = MagicMock()
    msg.reply_text = AsyncMock(
        return_value=MagicMock(message_id=10, chat_id=user_id)
    )
    msg.text = "/guide"
    update = MagicMock()
    update.message = msg
    update.effective_message = msg
    update.effective_user = user
    update.callback_query = None
    return update


def _callback_update(tid: int, data: str) -> MagicMock:
    msg = MagicMock()
    msg.edit_text = AsyncMock()
    msg.message_id = 10
    msg.chat_id = tid
    cq = MagicMock()
    cq.data = data
    cq.answer = AsyncMock()
    cq.message = msg
    update = MagicMock()
    update.callback_query = cq
    update.effective_user = MagicMock(id=tid)
    update.effective_message = msg
    update.message = None
    return update


def _collect_registered_commands(app) -> set[str]:
    names: set[str] = set()

    def walk(handlers: list) -> None:
        for h in handlers:
            if isinstance(h, CommandHandler):
                names.update(h.commands)
            elif isinstance(h, ConversationHandler):
                walk(list(h.entry_points))
                for state_handlers in h.states.values():
                    walk(list(state_handlers))
                walk(list(h.fallbacks))

    for group_handlers in app.handlers.values():
        walk(list(group_handlers))
    return names


@pytest.fixture
def wired_app():
    app = ApplicationBuilder().token("1:FAKE-S18C-TEST").build()
    register_handlers(app)
    me = User(id=1, first_name="Bot", is_bot=True, username="testbot")
    object.__setattr__(app.bot, "_bot_user", me)
    app._initialized = True
    return app


# --- entry -------------------------------------------------------------------


def test_guide_opens_menu(cleanup_user: int) -> None:
    _onboard(cleanup_user)
    update = _cmd_update(cleanup_user)
    context = MagicMock()
    context.user_data = {}
    result = asyncio.run(on_guide_command(update, context))
    assert result == MENU
    update.message.reply_text.assert_awaited_once()
    body = update.message.reply_text.await_args.args[0]
    assert texts.GUIDE_TITLE in body
    markup = update.message.reply_text.await_args.kwargs["reply_markup"]
    labels = [
        btn.text for row in markup.inline_keyboard for btn in row
    ]
    for expected in (
        texts.BTN_GUIDE_HOW,
        texts.BTN_GUIDE_SAVE,
        texts.BTN_GUIDE_TRANCY,
        texts.BTN_GUIDE_LR,
        texts.BTN_GUIDE_ANKI_FIRST,
        texts.BTN_GUIDE_ANKI_WEEK,
        texts.BTN_GUIDE_ANKI_PHONE,
        texts.BTN_GUIDE_DONE,
    ):
        assert expected in labels


def test_guide_ignores_unregistered(fake_telegram_id: int) -> None:
    update = _cmd_update(fake_telegram_id)
    context = MagicMock()
    context.user_data = {}
    result = asyncio.run(on_guide_command(update, context))
    assert result == ConversationHandler.END
    update.message.reply_text.assert_not_called()


# --- sections + back ---------------------------------------------------------


@pytest.mark.parametrize("key", list(section_keys()))
def test_every_section_renders(cleanup_user: int, key: str) -> None:
    _onboard(cleanup_user)
    update = _callback_update(cleanup_user, f"guide:menu:{key}")
    context = _ctx()
    result = asyncio.run(menu_callback(update, context))
    assert result == SECTION
    context.bot.edit_message_text.assert_awaited()
    body = context.bot.edit_message_text.await_args.kwargs["text"]
    plain = section_bodies_plain()[key]
    title_line = plain.split("\n", 1)[0]
    assert title_line in body
    markup = context.bot.edit_message_text.await_args.kwargs["reply_markup"]
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert texts.BTN_BACK in labels


@pytest.mark.parametrize("key", list(section_keys()))
def test_back_returns_to_menu(cleanup_user: int, key: str) -> None:
    _onboard(cleanup_user)
    # Open section first so flight ids stay set
    open_u = _callback_update(cleanup_user, f"guide:menu:{key}")
    context = _ctx()
    asyncio.run(menu_callback(open_u, context))
    context.bot.edit_message_text.reset_mock()

    back_u = _callback_update(cleanup_user, "guide:back")
    result = asyncio.run(section_callback(back_u, context))
    assert result == MENU
    body = context.bot.edit_message_text.await_args.kwargs["text"]
    assert texts.GUIDE_TITLE in body


def test_anki_first_includes_exact_template(cleanup_user: int) -> None:
    _onboard(cleanup_user)
    update = _callback_update(cleanup_user, "guide:menu:anki1")
    context = _ctx()
    asyncio.run(menu_callback(update, context))
    body = context.bot.edit_message_text.await_args.kwargs["text"]
    assert "{{Sentence}}" in body
    assert "{{Answer}}" in body
    assert "{{Meaning}}" in body
    assert "{{Source}}" in body
    assert "&lt;hr id=answer&gt;" in body or "<hr id=answer>" in body


def test_anki_weekly_has_field_mapping() -> None:
    plain = section_bodies_plain()["anki2"]
    assert "1 → Sentence" in plain
    assert "2 → Answer" in plain
    assert "3 → Meaning" in plain
    assert "4 → Source" in plain
    assert "/anki" in plain


# --- length ------------------------------------------------------------------


def test_every_section_under_4096() -> None:
    for key, body in section_bodies_plain().items():
        assert len(body) < 4096, f"{key} is {len(body)} chars"
    for key in section_keys():
        html_body = format_section_body(key)
        assert html_body is not None
        assert len(html_body) < 4096, f"{key} html is {len(html_body)} chars"


# --- stale / double-tap ------------------------------------------------------


def test_stale_callback_after_restart_warm_line(
    cleanup_user: int,
) -> None:
    _onboard(cleanup_user)
    update = _callback_update(cleanup_user, "guide:menu:how")
    context = MagicMock()
    context.user_data = {}  # restart wiped flight
    context.bot = MagicMock()
    result = asyncio.run(menu_callback(update, context))
    assert result == ConversationHandler.END
    update.callback_query.answer.assert_awaited()
    update.callback_query.message.edit_text.assert_awaited()
    assert (
        update.callback_query.message.edit_text.await_args.args[0]
        == texts.GUIDE_STALE
    )


def test_orphan_callback_warm_line(cleanup_user: int) -> None:
    _onboard(cleanup_user)
    update = _callback_update(cleanup_user, "guide:menu:how")
    context = MagicMock()
    context.user_data = {}
    asyncio.run(on_guide_orphan_callback(update, context))
    update.callback_query.answer.assert_awaited()
    assert (
        update.callback_query.message.edit_text.await_args.args[0]
        == texts.GUIDE_STALE
    )


def test_double_tap_does_not_raise(cleanup_user: int) -> None:
    _onboard(cleanup_user)
    update = _callback_update(cleanup_user, "guide:menu:how")
    context = _ctx()
    context.bot.edit_message_text = AsyncMock(
        side_effect=BadRequest("Message is not modified")
    )
    result = asyncio.run(menu_callback(update, context))
    assert result == SECTION


# --- wiring / drift ----------------------------------------------------------


def test_no_message_handler_in_guide_conversation() -> None:
    ch = build_guide_handler()

    def walk(handlers: list) -> None:
        for h in handlers:
            assert not isinstance(h, MessageHandler), h
            if isinstance(h, ConversationHandler):
                walk(list(h.entry_points))
                for state_handlers in h.states.values():
                    walk(list(state_handlers))
                walk(list(h.fallbacks))

    walk([ch])


def test_guide_in_set_my_commands_menu() -> None:
    assert "guide" in menu_command_names(include_import=True)
    assert "guide" in menu_command_names(include_import=False)


def test_guide_has_handler(wired_app) -> None:
    registered = _collect_registered_commands(wired_app)
    assert "guide" in registered
    for name in menu_command_names(include_import=True):
        assert name in registered, f"menu command /{name} has no handler"


def test_guide_prose_commands_have_handlers(wired_app) -> None:
    """Every /command named in guide copy must have a registered handler."""
    registered = _collect_registered_commands(wired_app)
    mentioned: set[str] = set()
    for s in s18c_user_facing_strings():
        for m in _COMMAND_IN_PROSE.finditer(s):
            mentioned.add(m.group("name"))
    # Template field names like {{Sentence}} are not commands; regex skips them
    assert mentioned, "expected at least one /command in guide copy"
    for name in mentioned:
        assert name in registered, (
            f"guide mentions /{name} but no handler is registered"
        )


def test_button_labels_max_20_chars() -> None:
    for label in s18c_button_labels():
        assert len(label) <= 20, label


def test_no_guilt_in_s18c_copy() -> None:
    for s in s18c_user_facing_strings():
        assert _GUILT.search(s) is None, s


def test_no_slice_jargon_in_guide_bodies() -> None:
    joined = "\n".join(section_bodies_plain().values()).lower()
    assert "chunk" not in joined
    assert "error journal" not in joined
    assert "s18" not in joined
