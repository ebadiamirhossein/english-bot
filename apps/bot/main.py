"""Bot entrypoint: build the Telegram application and start polling.

**W22: the bot is the couple challenge and nothing else a learner can use.**
Every teaching handler — quiz, reading, diary, talk, shadow, voice, capture,
prep, books, CSV import, settings, onboarding, the guide, the admin panel —
was deleted with its dispatch tests; the web app is where practice lives
(PRODUCT-PRINCIPLES §1). What is left: the access gate, `/start` and `/help`
(one reply pointing at the app), `/ping`, the couple challenge, and the error
handler that tells the operator when one of those raises.
"""

from __future__ import annotations

import logging
import sys

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from apps.bot import texts
from core.logging import configure_logging
from core.config import ConfigError, load_settings
from apps.bot.handlers.access import build_access_handler
from apps.bot.handlers.couple import build_couple_handlers, init_couple_prompt
from apps.bot.handlers.help import build_help_handlers
from core.instance_lock import InstanceLock, InstanceLockError
from apps.bot.scheduler import start_scheduler, stop_scheduler
from apps.bot.alerts import on_error
from apps.bot.commands import register_bot_commands

logger = logging.getLogger(__name__)

_instance_lock: InstanceLock | None = None


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(texts.PONG)


def register_handlers(app: Application) -> None:
    """Wire every handler. Extracted so tests can assert menu ↔ handlers."""
    app.add_error_handler(on_error)
    # S18d: real pre-handler gate — unapproved traffic never reaches group 0.
    app.add_handler(build_access_handler(), group=-1)
    for handler in build_help_handlers():
        app.add_handler(handler)
    app.add_handler(CommandHandler("ping", ping))
    couple_here, couple_answers = build_couple_handlers()
    app.add_handler(couple_here)
    app.add_handler(couple_answers)  # group text


async def _post_init(application) -> None:
    await register_bot_commands(application.bot)
    start_scheduler(application)


async def _post_shutdown(application) -> None:
    stop_scheduler(application)
    global _instance_lock
    if _instance_lock is not None:
        _instance_lock.release()
        _instance_lock = None


def main() -> int:
    global _instance_lock
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    # core.config no longer requires TELEGRAM_BOT_TOKEN — apps/api and
    # apps/worker must boot without one. This process cannot.
    if not settings.telegram_bot_token:
        print(
            "Config error: missing required environment variable(s): "
            "TELEGRAM_BOT_TOKEN",
            file=sys.stderr,
        )
        return 1

    try:
        _instance_lock = InstanceLock(settings.instance_lock_file)
        _instance_lock.acquire()
    except InstanceLockError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    configure_logging(settings)

    init_couple_prompt()

    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    register_handlers(app)

    logger.info("Starting bot (polling)")
    app.run_polling(drop_pending_updates=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
