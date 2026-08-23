"""Bot entrypoint: build the Telegram application and start polling."""

from __future__ import annotations

import logging
import sys

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from apps.bot import texts
from core.logging import configure_logging
from core.config import ConfigError, load_settings
from apps.bot.handlers.access import build_access_handler
from apps.bot.handlers.access_request import build_access_request_handlers
from apps.bot.handlers.admin import build_admin_handler, build_admin_orphan_handler
from apps.bot.handlers.book import build_book_handler, init_book_prompt
from apps.bot.handlers.book_test import (
    build_book_test_handlers,
    init_book_test_prompt,
)
from apps.bot.handlers.capture import build_capture_handlers, init_capture_prompt
from apps.bot.handlers.prep import build_prep_handler, init_prep_prompt
from apps.bot.handlers.conversation import (
    build_conversation_handlers,
    init_conversation_prompt,
)
from apps.bot.handlers.correction import build_correction_handler, init_correction_prompt
from apps.bot.handlers.couple import build_couple_handlers, init_couple_prompt
from apps.bot.handlers.diary import build_diary_handlers, init_diary_prompt
from apps.bot.handlers.shadow import build_shadow_handlers
from apps.bot.handlers.help import build_help_handler
from core.services.vocab_import import init_vocab_prompt
from apps.bot.handlers.guide import build_guide_handler, build_guide_orphan_handler
from apps.bot.handlers.interests import build_interests_handler
from apps.bot.handlers.nudge import build_nudge_handler
from apps.bot.handlers.onboarding import build_onboarding_handler
from apps.bot.handlers.quiz import (
    build_present_handlers,
    build_quiz_handlers,
    init_quiz_prompt,
)
from apps.bot.handlers.reading import build_reading_handler, init_reading_prompt
from apps.bot.handlers.settings import (
    build_settings_editor_handler,
    build_settings_handlers,
    build_settings_orphan_handler,
)
from apps.bot.handlers.voice import build_voice_handler, init_voice_prompt
from core.instance_lock import InstanceLock, InstanceLockError
from apps.bot.scheduler import start_scheduler, stop_scheduler
from apps.bot.alerts import on_error
from apps.bot.anki_delivery import handle_anki_command
from apps.bot.handlers.csv_import import build_csv_import_handlers
from apps.bot.handlers.import_cmd import handle_import_command
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
    access_req, access_decide = build_access_request_handlers()
    app.add_handler(access_req)
    app.add_handler(access_decide)
    app.add_handler(build_admin_handler())  # tapped-only; operator-only
    app.add_handler(build_admin_orphan_handler())
    app.add_handler(build_onboarding_handler())
    app.add_handler(build_help_handler())
    app.add_handler(build_guide_handler())  # tapped-only; no text filter
    app.add_handler(build_guide_orphan_handler())  # stale guide: after restart
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("anki", handle_anki_command))
    app.add_handler(CommandHandler("import", handle_import_command))
    # S15b: private CSV documents; IMAGE excluded from non-CSV so /book keeps pages.
    csv_doc, non_csv_doc, share_cb, share_orphan = build_csv_import_handlers()
    app.add_handler(csv_doc)
    app.add_handler(non_csv_doc)
    app.add_handler(share_cb)
    app.add_handler(share_orphan)
    app.add_handler(build_prep_handler())
    app.add_handler(build_diary_handlers())
    shadow_cmd, shadow_cb = build_shadow_handlers()
    app.add_handler(shadow_cmd)
    app.add_handler(shadow_cb)  # shadow:again taps; no text filter
    pause_cmd, stats_cmd, pause_cb = build_settings_handlers()
    app.add_handler(pause_cmd)
    app.add_handler(stats_cmd)
    app.add_handler(pause_cb)
    app.add_handler(build_settings_editor_handler())  # tapped-only; no text filter
    app.add_handler(build_settings_orphan_handler())  # stale set: after restart
    quiz_text, quiz_choice = build_quiz_handlers()
    present_ack, present_orphan = build_present_handlers()
    app.add_handler(quiz_choice)
    app.add_handler(present_ack)
    app.add_handler(present_orphan)
    # S15: FORWARDED before gap quiz so a forward is never graded as an answer.
    # Narrow filter — ordinary typed CH answers (book Other, interests) cannot match.
    capture_fwd, capture_cmd = build_capture_handlers()
    app.add_handler(capture_fwd)
    app.add_handler(capture_cmd)
    app.add_handler(quiz_text)  # before correction — open-quiz filter
    talk_cmd, talk_text, talk_cb, talk_orphan = build_conversation_handlers()
    app.add_handler(talk_cmd)
    app.add_handler(talk_cb)
    app.add_handler(talk_orphan)
    app.add_handler(talk_text)  # after quiz gap; before correction — S26
    app.add_handler(build_reading_handler())  # callbacks only; no text filter
    app.add_handler(build_nudge_handler())  # nudge: taps only; no text filter
    test_cmd, test_cb = build_book_test_handlers()
    app.add_handler(test_cb)  # btest: callbacks; no text filter
    app.add_handler(test_cmd)
    app.add_handler(build_voice_handler())
    app.add_handler(build_interests_handler())
    app.add_handler(build_book_handler())
    couple_here, couple_answers = build_couple_handlers()
    app.add_handler(couple_here)
    app.add_handler(couple_answers)  # group text; before correction
    app.add_handler(build_correction_handler())


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

    init_correction_prompt()
    init_quiz_prompt()
    init_voice_prompt()
    init_diary_prompt()
    init_conversation_prompt()
    init_reading_prompt()
    init_book_prompt()
    init_book_test_prompt()
    init_capture_prompt()
    init_prep_prompt()
    init_couple_prompt()
    init_vocab_prompt()

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
