"""W22: what the Telegram bot still answers — the whole surface, asserted literally.

TASKS' W22 acceptance: *"No teaching path remains in Telegram; couple challenge
still works."* The second half is ``tests/test_couple.py``. This file is the
first half, asserted against the application the entrypoint builds
(``apps.bot.main.register_handlers``) rather than against a list kept beside it:
**every handler, in every group, by type and command** — so a teaching handler
put back by any route (a command, a callback, a private-text filter) fails here.

Before W22 this file was S18b's ``/help`` map (twelve tests over twenty
commands); those tests were deleted with the commands they described.

**RED DEMONSTRATIONS (2026-09-25, ``python -B``, caches cleared):** with a
``CommandHandler("quiz", …)`` and a ``CallbackQueryHandler(pattern="^quiz:")``
added to ``register_handlers``, ``test_the_bot_answers_exactly_these_commands``
and ``test_no_callback_or_private_text_handler_remains`` went red (2 failed);
with ``/start`` renamed in ``build_help_handlers``, three went red, including
``test_start_and_help_give_the_same_reply``. Each restored and re-run green.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import BotCommand, User
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    TypeHandler,
)

from apps.bot import texts
from core.db import close_pool, connection
from apps.bot.handlers.help import (
    build_help_handlers,
    format_help_message,
    on_help_command,
    user_facing_strings,
)
from apps.bot.main import register_handlers
from apps.bot.commands import (
    build_bot_commands,
    hidden_from_menu,
    menu_command_names,
    register_bot_commands,
)
from core.copy_rules import BANNED
from core.services.identity import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_500_000_000


@pytest.fixture
def fake_telegram_id() -> int:
    return FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)


@pytest.fixture(autouse=True)
def _close_pool_after_test() -> None:
    yield
    close_pool()


@pytest.fixture
def cleanup_user(fake_telegram_id: int):
    yield fake_telegram_id
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM users WHERE telegram_user_id = %s",
                (fake_telegram_id,),
            )


def _onboard(tid: int) -> int:
    return save_onboarding(
        tid,
        {
            "name": "Help Test",
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


def _update(user_id: int, text: str) -> MagicMock:
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    msg.text = text
    update = MagicMock()
    update.message = msg
    update.effective_user = User(id=user_id, first_name="A", is_bot=False)
    return update


@pytest.fixture
def wired_app():
    """The application the entrypoint builds, with no network."""
    app = ApplicationBuilder().token("1:FAKE-W22-TEST").build()
    register_handlers(app)
    return app


def _handlers(app) -> list[tuple[int, object]]:
    return [(group, h) for group, hs in app.handlers.items() for h in hs]


# --- the whole surface -------------------------------------------------------


def test_the_bot_answers_exactly_these_commands(wired_app) -> None:
    """Literal on purpose: a command added back fails here, whatever it is."""
    commands = {
        name
        for _group, h in _handlers(wired_app)
        if isinstance(h, CommandHandler)
        for name in h.commands
    }
    assert commands == {"start", "help", "ping", "here"}


def test_no_callback_or_private_text_handler_remains(wired_app) -> None:
    """Every Telegram teaching flow was a callback, a conversation or a private
    text filter. What is left: the gate (group -1), four commands, and the
    couple challenge's group-answer handler."""
    kinds = sorted(
        (group, type(h).__name__)
        for group, h in _handlers(wired_app)
        if not isinstance(h, CommandHandler)
    )
    assert kinds == [(-1, "TypeHandler"), (0, "MessageHandler")]
    assert not any(isinstance(h, CallbackQueryHandler) for _g, h in _handlers(wired_app))
    gate = [h for g, h in _handlers(wired_app) if g == -1]
    assert len(gate) == 1 and isinstance(gate[0], TypeHandler)
    answers = [h for _g, h in _handlers(wired_app) if isinstance(h, MessageHandler)]
    assert answers[0].callback.__module__ == "apps.bot.handlers.couple"


def test_the_menu_is_start_and_help() -> None:
    """``setMyCommands`` REPLACES the menu at start-up, so this list is also what
    takes the deleted commands off the learners' phones."""
    cmds = build_bot_commands()
    assert [c.command for c in cmds] == ["start", "help"]
    assert all(isinstance(c, BotCommand) for c in cmds)
    assert all(c.description and c.description[0].islower() for c in cmds)
    assert "ping" in hidden_from_menu()
    assert "ping" not in menu_command_names()


def test_every_menu_command_has_a_handler(wired_app) -> None:
    registered = {
        name
        for _g, h in _handlers(wired_app)
        if isinstance(h, CommandHandler)
        for name in h.commands
    }
    assert menu_command_names() <= registered


def test_register_bot_commands_sends_the_menu_once() -> None:
    bot = MagicMock()
    bot.set_my_commands = AsyncMock()
    asyncio.run(register_bot_commands(bot))
    bot.set_my_commands.assert_awaited_once()
    (arg,), _kwargs = bot.set_my_commands.await_args
    assert [c.command for c in arg] == ["start", "help"]


def test_register_bot_commands_failure_logs_warning_not_raise(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bot = MagicMock()
    bot.set_my_commands = AsyncMock(side_effect=RuntimeError("network"))
    with caplog.at_level(logging.WARNING, logger="apps.bot.commands"):
        asyncio.run(register_bot_commands(bot))
    assert any("setMyCommands" in r.message for r in caplog.records)


# --- the reply ---------------------------------------------------------------


def test_start_and_help_give_the_same_reply() -> None:
    start, help_ = build_help_handlers()
    assert start.commands == frozenset({"start"})
    assert help_.commands == frozenset({"help"})
    assert start.callback is on_help_command is help_.callback


def test_the_reply_points_at_the_app_and_names_no_command() -> None:
    body = format_help_message()
    assert body == texts.HELP_AFTER_W22
    assert "app" in body.lower()
    assert "couple challenge" in body.lower()
    # Every command a learner used to type is gone; the reply names none.
    assert re.search(r"/[a-z]", body) is None


def test_help_ignores_unregistered(fake_telegram_id: int) -> None:
    update = _update(fake_telegram_id, "/help")
    asyncio.run(on_help_command(update, MagicMock()))
    update.message.reply_text.assert_not_called()


@pytest.mark.parametrize("command", ["/start", "/help"])
def test_start_and_help_reply_for_a_registered_learner(
    cleanup_user: int, command: str
) -> None:
    _onboard(cleanup_user)
    update = _update(cleanup_user, command)
    asyncio.run(on_help_command(update, MagicMock()))
    update.message.reply_text.assert_awaited_once_with(texts.HELP_AFTER_W22)


def test_no_banned_phrase_in_what_this_module_shows() -> None:
    for s in user_facing_strings():
        assert BANNED.search(s) is None, s
