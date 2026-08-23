"""Manual ``/import`` for the watched-folder bridge (S15a).

User-initiated — does not increment ``bot_message_counts``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram.ext import ContextTypes

from app import texts
from app.services.users import is_registered
from app.services.watch_import import (
    WatchConfigError,
    paths_for_user_display,
    resolve_watch_root,
    scan_user_inbox,
    watch_dir_configured,
)

logger = logging.getLogger(__name__)


def _format_paths(user_id: int) -> str:
    paths = paths_for_user_display(user_id)
    if paths is None:
        return ""
    return texts.IMPORT_PATHS.format(
        inbox=paths["inbox"],
        trancy=paths["trancy"],
        language_reactor=paths["language_reactor"],
    )


async def handle_import_command(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scan the caller's inbox only. Silent no-op when WATCH_DIR unset."""
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return
    user_id = int(user.id)
    if not is_registered(user_id):
        return

    if not watch_dir_configured():
        return

    try:
        root = resolve_watch_root()
    except WatchConfigError as exc:
        logger.error("WATCH_DIR unusable on /import: %s", exc)
        return
    except ValueError:
        return

    now = datetime.now(timezone.utc)
    result = scan_user_inbox(root, user_id, now=now)
    paths = _format_paths(user_id)

    failed = [f for f in result.files if f.status == "failed_headers"]
    imported_files = [f for f in result.files if f.status == "imported"]

    if failed:
        for f in failed:
            await message.reply_text(
                texts.IMPORT_FAILED_HEADERS.format(
                    filename=f.filename,
                    headers=", ".join(f.headers_seen) or "(none)",
                )
            )

    if imported_files:
        due = imported_files[-1].due_after
        if due is None:
            due = 0
        await message.reply_text(
            texts.IMPORT_RESULT.format(
                imported=result.total_imported,
                duplicates=result.total_duplicates,
                invalid=result.total_invalid,
                due=due,
                paths=paths,
            )
        )
        return

    if result.settling > 0 and not failed:
        await message.reply_text(
            texts.IMPORT_SETTLING.format(n=result.settling, paths=paths)
        )
        return

    if failed:
        # Already sent failure lines; still show paths.
        await message.reply_text(paths)
        return

    await message.reply_text(texts.IMPORT_EMPTY.format(paths=paths))
