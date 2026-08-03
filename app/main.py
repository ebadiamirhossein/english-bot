"""Bot entrypoint: build the Telegram application and start polling."""

from __future__ import annotations

import logging
import sys

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from app import texts
from app.config import ConfigError, load_settings
from app.handlers.access import build_access_handler
from app.handlers.correction import build_correction_handler, init_correction_prompt
from app.handlers.onboarding import build_onboarding_handler
from app.handlers.quiz import build_quiz_handlers, init_quiz_prompt
from app.scheduler import start_scheduler, stop_scheduler


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(texts.PONG)


async def _post_init(application) -> None:
    start_scheduler(application)


async def _post_shutdown(application) -> None:
    stop_scheduler(application)


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    init_correction_prompt()
    init_quiz_prompt()

    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.add_handler(build_onboarding_handler())
    app.add_handler(CommandHandler("ping", ping))
    quiz_text, quiz_choice = build_quiz_handlers()
    app.add_handler(quiz_choice)
    app.add_handler(quiz_text)  # before correction — open-quiz filter
    app.add_handler(build_correction_handler())
    app.add_handler(build_access_handler(), group=1)

    logging.getLogger(__name__).info("Starting bot (polling)")
    app.run_polling(drop_pending_updates=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
