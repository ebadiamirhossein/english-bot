"""S18b: /help + setMyCommands — menu drift, conditional import, access."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import BotCommand, User
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
)

from app.db import close_pool, connection
from app.handlers.help import (
    format_help_message,
    on_help_command,
    s18b_user_facing_strings,
)
from app.main import register_handlers
from app.services.commands import (
    build_bot_commands,
    hidden_from_menu,
    menu_command_names,
    register_bot_commands,
)
from app.services.users import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_500_000_000

_GUILT = re.compile(
    r"\b(fail(ed|ure)?|broke your|disappoint|guilt|lazy|should have|"
    r"missed)\b|😞|😢|😔|☹️|🙁|😟|😤|😠",
    re.IGNORECASE,
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


def _update(user_id: int, text: str = "/help") -> MagicMock:
    user = User(id=user_id, first_name="A", is_bot=False)
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    msg.text = text
    update = MagicMock()
    update.message = msg
    update.effective_user = user
    return update


def _collect_registered_commands(app) -> set[str]:
    """Walk Application handlers (incl. ConversationHandler) for command names."""
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
    """Application with the same handlers as production (no network)."""
    app = ApplicationBuilder().token("1:FAKE-S18B-TEST").build()
    register_handlers(app)
    me = User(id=1, first_name="Bot", is_bot=True, username="testbot")
    object.__setattr__(app.bot, "_bot_user", me)
    app._initialized = True
    return app


# --- setMyCommands -----------------------------------------------------------


def test_build_bot_commands_omits_ping_and_matches_core() -> None:
    cmds = build_bot_commands(include_import=False)
    names = [c.command for c in cmds]
    assert "ping" not in names
    assert "help" in names
    assert "import" not in names
    assert all(isinstance(c, BotCommand) for c in cmds)
    assert all(c.description and c.description[0].islower() for c in cmds)


def test_build_bot_commands_includes_import_when_asked() -> None:
    names = [c.command for c in build_bot_commands(include_import=True)]
    assert "import" in names
    assert names.index("import") == names.index("anki") + 1


def test_register_bot_commands_calls_set_my_commands_once() -> None:
    bot = MagicMock()
    bot.set_my_commands = AsyncMock()
    with patch(
        "app.services.commands.watch_dir_configured", return_value=""
    ):
        asyncio.run(register_bot_commands(bot))
    bot.set_my_commands.assert_awaited_once()
    (arg,), _kwargs = bot.set_my_commands.await_args
    assert [c.command for c in arg] == [
        c.command for c in build_bot_commands(include_import=False)
    ]


def test_register_bot_commands_failure_logs_warning_not_raise(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bot = MagicMock()
    bot.set_my_commands = AsyncMock(side_effect=RuntimeError("network"))
    with caplog.at_level(logging.WARNING, logger="app.services.commands"):
        asyncio.run(register_bot_commands(bot))
    assert any("setMyCommands" in r.message for r in caplog.records)
    assert any(r.levelno == logging.WARNING for r in caplog.records)


# --- /help content -----------------------------------------------------------


def test_help_lists_menu_commands_except_hidden() -> None:
    # /start and /help live in the Telegram menu but not the intent body
    # (already completed onboarding; /help is the message itself).
    skip_in_body = frozenset({"start", "help"})
    body = format_help_message(include_import=True)
    for name in menu_command_names(include_import=True):
        if name in skip_in_body:
            continue
        assert f"/{name}" in body, name
    for name in hidden_from_menu():
        assert f"/{name}" not in body


def test_help_omits_import_when_watch_unset() -> None:
    body = format_help_message(include_import=False)
    assert "/import" not in body
    assert "/anki" in body


def test_help_includes_import_when_watch_set() -> None:
    body = format_help_message(include_import=True)
    assert "/import" in body


def test_help_mentions_no_command_behaviours() -> None:
    body = format_help_message(include_import=False)
    lower = body.lower()
    assert "type any english" in lower
    assert "forward any english" in lower
    assert "journal" in lower or "correct" in lower
    assert "chunk" in lower or "explain" in lower


def test_help_ignores_unregistered(fake_telegram_id: int) -> None:
    update = _update(fake_telegram_id)
    context = MagicMock()
    asyncio.run(on_help_command(update, context))
    update.message.reply_text.assert_not_called()


def test_help_replies_for_registered(cleanup_user: int) -> None:
    _onboard(cleanup_user)
    update = _update(cleanup_user)
    context = MagicMock()
    asyncio.run(on_help_command(update, context))
    update.message.reply_text.assert_awaited_once()
    body = update.message.reply_text.await_args.args[0]
    assert "/stats" in body
    assert "/ping" not in body


# --- drift: menu ⊆ registered handlers --------------------------------------


def test_menu_commands_have_handlers(wired_app) -> None:
    registered = _collect_registered_commands(wired_app)
    for name in menu_command_names(include_import=True):
        assert name in registered, f"menu command /{name} has no handler"
    # Deliberately hidden still works
    assert "ping" in registered
    assert "ping" not in menu_command_names(include_import=True)
    assert "help" in registered


def test_no_guilt_in_s18b_copy() -> None:
    for s in s18b_user_facing_strings():
        assert _GUILT.search(s) is None, s
