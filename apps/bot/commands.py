"""Telegram command menu (S18b).

Single source of truth for ``setMyCommands``. ``/ping`` stays registered
as a handler but is deliberately omitted from the public menu.

**W22: the menu is two entries.** ``setMyCommands`` runs at every start-up and
REPLACES the menu, so the deploy that ships this is also what takes the deleted
commands off both learners' phones — the old menu does not linger. ``/here``
(the couple challenge's one-time group setup) is operator-only and was never on
the menu; it stays off it.
"""

from __future__ import annotations

import logging

from telegram import BotCommand

from apps.bot import texts

logger = logging.getLogger(__name__)

# (command, description) — order is menu order.
_MENU_CORE: tuple[tuple[str, str], ...] = (
    ("start", texts.CMD_DESC_START),
    ("help", texts.CMD_DESC_HELP),
)

_HIDDEN_FROM_MENU: frozenset[str] = frozenset({"ping"})


def menu_command_entries() -> list[tuple[str, str]]:
    """Return (command, description) pairs for the Telegram ``/`` menu."""
    return list(_MENU_CORE)


def menu_command_names() -> frozenset[str]:
    return frozenset(c for c, _ in menu_command_entries())


def build_bot_commands() -> list[BotCommand]:
    return [
        BotCommand(command=name, description=desc)
        for name, desc in menu_command_entries()
    ]


async def register_bot_commands(bot) -> None:
    """Call ``setMyCommands`` once at startup. Never fail the boot."""
    commands = build_bot_commands()
    try:
        await bot.set_my_commands(commands)
    except Exception:
        logger.warning(
            "setMyCommands failed; Telegram / menu may stay empty",
            exc_info=True,
        )


def hidden_from_menu() -> frozenset[str]:
    return _HIDDEN_FROM_MENU
