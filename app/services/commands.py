"""Telegram command menu (S18b).

Single source of truth for ``setMyCommands``. ``/ping`` stays registered
as a handler but is deliberately omitted from the public menu.
"""

from __future__ import annotations

import logging

from telegram import BotCommand

from app import texts
from app.services.watch_import import watch_dir_configured

logger = logging.getLogger(__name__)

# (command, description) — order is menu order. ``import`` is appended
# only when WATCH_DIR is set (same condition as /help).
_MENU_CORE: tuple[tuple[str, str], ...] = (
    ("start", texts.CMD_DESC_START),
    ("help", texts.CMD_DESC_HELP),
    ("stats", texts.CMD_DESC_STATS),
    ("diary", texts.CMD_DESC_DIARY),
    ("shadow", texts.CMD_DESC_SHADOW),
    ("capture", texts.CMD_DESC_CAPTURE),
    ("prep", texts.CMD_DESC_PREP),
    ("book", texts.CMD_DESC_BOOK),
    ("test", texts.CMD_DESC_TEST),
    ("anki", texts.CMD_DESC_ANKI),
    ("settings", texts.CMD_DESC_SETTINGS),
    ("interests", texts.CMD_DESC_INTERESTS),
    ("pause", texts.CMD_DESC_PAUSE),
)

_HIDDEN_FROM_MENU: frozenset[str] = frozenset({"ping"})


def menu_command_entries(*, include_import: bool | None = None) -> list[tuple[str, str]]:
    """Return (command, description) pairs for the Telegram ``/`` menu."""
    if include_import is None:
        include_import = bool(watch_dir_configured())
    entries = list(_MENU_CORE)
    if include_import:
        # After anki — vocabulary group in /help.
        anki_idx = next(i for i, (c, _) in enumerate(entries) if c == "anki")
        entries.insert(anki_idx + 1, ("import", texts.CMD_DESC_IMPORT))
    return entries


def menu_command_names(*, include_import: bool | None = None) -> frozenset[str]:
    return frozenset(c for c, _ in menu_command_entries(include_import=include_import))


def build_bot_commands(*, include_import: bool | None = None) -> list[BotCommand]:
    return [
        BotCommand(command=name, description=desc)
        for name, desc in menu_command_entries(include_import=include_import)
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
