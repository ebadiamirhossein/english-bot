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
and the handler-structure test (then named
``test_no_callback_or_private_text_handler_remains``) went red (2 failed);
with ``/start`` renamed in ``build_help_handlers``, three went red, including
``test_start_and_help_give_the_same_reply``. Each restored and re-run green.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram import BotCommand, CallbackQuery, Chat, Message, MessageEntity, Update, User
from telegram.ext import ApplicationBuilder, CommandHandler

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
from core.services.access_control import request_access, approve_access
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


def test_beyond_the_commands_only_the_gate_the_couple_and_the_pointer_remain(wired_app) -> None:
    """Every Telegram teaching flow was a callback, a conversation or a private
    text filter. What is left beside the four commands: the gate (group -1),
    the couple challenge's group-answer handler, and — LAST — the two handlers
    that answer a retired path with the pointer (#86)."""
    rest = [
        (group, type(h).__name__, h.callback.__name__)
        for group, h in _handlers(wired_app)
        if not isinstance(h, CommandHandler)
    ]
    assert rest == [
        (-1, "TypeHandler", "gate_unapproved"),
        (0, "MessageHandler", "on_couple_answer"),
        (0, "MessageHandler", "on_help_command"),
        (0, "CallbackQueryHandler", "on_retired_button"),
    ]
    # Last in the table, so every live handler is tried before the pointer.
    assert [type(h).__name__ for h in wired_app.handlers[0][-2:]] == [
        "MessageHandler",
        "CallbackQueryHandler",
    ]


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


# --- #86 at W22: a retired path gets the pointer, through the real dispatch --
#
# Driven through `Application.process_update` — the bot's real entry point
# (CLAUDE.md §3 rule 1), gate included — with the reply captured at the class
# Telegram's own `reply_text` / `answer` live on, so nothing reaches the network.
#
# RED DEMONSTRATION (2026-09-25, `python -B`, caches cleared): with the
# `build_retired_path_handlers()` loop removed from `register_handlers`, five
# went red: the structure test, the three typed/command cases (no reply at all
# — the silence #86 describes) and the button toast. The stranger and `/here`
# cases stayed green, as they should. Restored.


@pytest.fixture
def approved_learner(cleanup_user: int) -> tuple[int, int]:
    """A learner the gate lets through: onboarded, and approved."""
    user_id = _onboard(cleanup_user)
    request_access(cleanup_user, username=None, display_name="Help Test")
    approve_access(cleanup_user)
    yield cleanup_user, user_id
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM access_requests WHERE telegram_user_id = %s",
                (cleanup_user,),
            )


def _private(tid: int, text: str) -> Update:
    entities = None
    if text.startswith("/"):
        entities = (MessageEntity(type=MessageEntity.BOT_COMMAND, offset=0, length=len(text.split()[0])),)
    msg = Message(
        message_id=10,
        date=datetime.now(timezone.utc),
        chat=Chat(id=tid, type="private"),
        from_user=User(id=tid, first_name="A", is_bot=False),
        text=text,
        entities=entities,
    )
    return Update(update_id=1, message=msg)


def _dispatch(app, update: Update) -> None:
    async def _run() -> None:
        update.set_bot(app.bot)
        if update.message is not None:
            update.message.set_bot(app.bot)
        if update.callback_query is not None:
            update.callback_query.set_bot(app.bot)
        me = User(id=1, first_name="Bot", is_bot=True, username="testbot")
        object.__setattr__(app.bot, "_bot_user", me)
        app._initialized = True
        try:
            await app.process_update(update)
        finally:
            app._initialized = False

    asyncio.run(_run())


def _errors_for(user_id: int) -> int:
    with connection() as conn:
        return int(
            conn.execute(
                "SELECT count(*) AS n FROM errors WHERE user_id = %s", (user_id,)
            ).fetchone()["n"]
        )


@pytest.mark.parametrize(
    "text",
    ["I goed to the shop yesterday", "/talk", "/quiz"],
    ids=["a typed sentence", "a retired command", "another retired command"],
)
def test_a_retired_path_gets_the_pointer_and_writes_nothing(
    wired_app, approved_learner, monkeypatch, text: str
) -> None:
    """v2 corrected any English typed to it and answered `/talk`; after W22 each
    gets the pointer — never silence (#86), and never a correction: the journal
    is untouched (CLAUDE.md §5)."""
    tid, user_id = approved_learner
    replies = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", replies)
    _dispatch(wired_app, _private(tid, text))
    replies.assert_awaited_once()
    assert replies.await_args.args[-1] == texts.HELP_AFTER_W22
    assert _errors_for(user_id) == 0


def test_a_retired_path_from_a_stranger_gets_nothing(wired_app, fake_telegram_id, monkeypatch) -> None:
    """The gate still stops unapproved traffic before the pointer can answer it."""
    replies = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", replies)
    _dispatch(wired_app, _private(fake_telegram_id, "hello"))
    replies.assert_not_awaited()


def test_a_retired_path_button_tap_gets_a_toast(wired_app, approved_learner, monkeypatch) -> None:
    """A tap on a quiz button from before W22: the spinner stops with a line."""
    tid, _user_id = approved_learner
    answers = AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answers)
    query = CallbackQuery(
        id="q1",
        from_user=User(id=tid, first_name="A", is_bot=False),
        chat_instance="c",
        data="quiz:choice:0:1",
    )
    _dispatch(wired_app, Update(update_id=2, callback_query=query))
    answers.assert_awaited_once()
    assert answers.await_args.args[-1] == texts.RETIRED_BUTTON


def test_the_couple_command_still_wins_over_the_pointer(wired_app, approved_learner, monkeypatch) -> None:
    """The pointer is last: `/here` in a private chat still gets the couple
    challenge's own answer, not the pointer."""
    tid, _user_id = approved_learner
    replies = AsyncMock()
    monkeypatch.setattr(Message, "reply_text", replies)
    _dispatch(wired_app, _private(tid, "/here"))
    replies.assert_awaited_once()
    assert replies.await_args.args[-1] == texts.COUPLE_HERE_PRIVATE
