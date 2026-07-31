"""Bot entrypoint: build the Telegram application and start polling."""

from __future__ import annotations

import logging
import sys

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from app.config import ConfigError, load_settings
from app import texts


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(texts.PONG)


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

    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .build()
    )
    app.add_handler(CommandHandler("ping", ping))

    logging.getLogger(__name__).info("Starting bot (polling)")
    app.run_polling(drop_pending_updates=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
