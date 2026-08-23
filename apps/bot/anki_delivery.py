"""Telegram delivery for the Anki export (S7 / M6).

Lifted unchanged out of ``core.services.anki`` at W1 so the core service
is channel-neutral. The TSV build, the transaction and the
``exported_to_anki`` marks stay in core; only the send lives here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from telegram import InputFile
from telegram.ext import ContextTypes

from apps.bot import texts
from core.db import connection
from core.services.anki import export_and_send, fetch_unexported_chunks
from core.services.sessions import (
    has_anki_session_on,
    increment_bot_messages,
    local_today,
    under_message_ceiling,
)
from core.services.users import is_registered

logger = logging.getLogger(__name__)


def _user_timezone(user_id: int) -> str:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT timezone FROM users WHERE telegram_user_id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None or not row["timezone"]:
        return "Europe/Vilnius"
    return str(row["timezone"])


async def deliver_weekly(
    app: Any,
    user_id: int,
    *,
    now: datetime,
) -> str:
    """Sunday Anki export for one user. Returns action taken."""
    bot = app.bot
    tz = _user_timezone(user_id)
    day = local_today(tz, now)

    if has_anki_session_on(user_id, day):
        return "skipped_existing"

    if not under_message_ceiling(user_id, day):
        logger.warning(
            "anki skip user_id=%s reason=ceiling_reached day=%s",
            user_id,
            day,
        )
        return "skipped_ceiling"

    with connection() as conn:
        pending = fetch_unexported_chunks(conn, user_id)
    if not pending:
        logger.info(
            "anki weekly empty user_id=%s day=%s — nothing to export",
            user_id,
            day,
        )
        return "skipped_empty"

    count = len(pending)
    caption = texts.ANKI_WEEKLY.format(count=count)

    async def _send(tsv_bytes: bytes, filename: str, cap: str) -> None:
        await bot.send_document(
            chat_id=user_id,
            document=InputFile(BytesIO(tsv_bytes), filename=filename),
            caption=cap,
        )

    try:
        exported = await export_and_send(
            user_id=user_id,
            local_date=day,
            send_document=_send,
            claim_session=True,
            caption=caption,
        )
    except Exception:
        logger.exception(
            "anki weekly send/persist failed user_id=%s — rolled back",
            user_id,
        )
        return "skipped_send_failed"

    if exported == 0:
        logger.info(
            "anki weekly empty user_id=%s day=%s — nothing to export",
            user_id,
            day,
        )
        return "skipped_empty"

    increment_bot_messages(user_id, day)
    return "anki_export"


async def handle_anki_command(
    update: Any,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Manual ``/anki`` — user-initiated; no ceiling increment, no session."""
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return
    user_id = int(user.id)
    if not is_registered(user_id):
        return

    tz = _user_timezone(user_id)
    day = local_today(tz, datetime.now(timezone.utc))

    with connection() as conn:
        pending = fetch_unexported_chunks(conn, user_id)
    if not pending:
        await message.reply_text(texts.ANKI_EMPTY)
        return

    count = len(pending)
    caption = texts.ANKI_MANUAL.format(count=count)
    bot = context.bot

    async def _send(tsv_bytes: bytes, filename: str, cap: str) -> None:
        await bot.send_document(
            chat_id=user_id,
            document=InputFile(BytesIO(tsv_bytes), filename=filename),
            caption=cap,
        )

    try:
        exported = await export_and_send(
            user_id=user_id,
            local_date=day,
            send_document=_send,
            claim_session=False,
            caption=caption,
        )
    except Exception:
        logger.exception("anki /anki send failed user_id=%s", user_id)
        await message.reply_text(texts.ANKI_SEND_FAILED)
        return

    if exported == 0:
        await message.reply_text(texts.ANKI_EMPTY)
