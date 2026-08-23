"""Anki TSV export from un-exported chunks (S7 / M6).

Weekly Sunday delivery claims a ``sessions`` row with
``task_type='anki_export'``. Manual ``/anki`` does not claim a session and
does not increment the bot-initiated message ceiling.

Rows are marked ``exported_to_anki`` only inside a transaction held across
``send_document`` — a failed send rolls back so cards are never lost.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from io import BytesIO
from typing import Any, Awaitable, Callable, Sequence

from psycopg.types.json import Jsonb
from telegram import InputFile
from telegram.ext import ContextTypes

from core import copy
from core.db import connection
from core.services.reading import normalize_for_match
from core.services.sessions import (
    has_anki_session_on,
    increment_bot_messages,
    local_today,
    under_message_ceiling,
)
from core.services.users import is_registered

logger = logging.getLogger(__name__)

GAP = "_____"
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class ChunkExportRow:
    id: int
    chunk: str
    full_sentence: str | None
    meaning: str | None
    source: str | None


def sanitize_tsv_field(value: str) -> str:
    """Neutralise tabs/newlines so one field cannot break the TSV row."""
    s = value.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s


def make_sentence_with_gap(full_sentence: str, chunk: str) -> str | None:
    """Replace the first normalised match of ``chunk`` with ``_____``.

    Uses :func:`normalize_for_match` (S9a) so case, apostrophes/quotes and
    whitespace differences still locate the span in the original sentence.
    Returns None when the chunk cannot be found.
    """
    target = normalize_for_match(chunk)
    if not target:
        return None
    n = len(full_sentence)
    for start in range(n):
        for end in range(start + 1, n + 1):
            candidate = normalize_for_match(full_sentence[start:end])
            if candidate == target:
                # Normalisation strips edges — trim the original span so we
                # don't swallow the spaces around the chunk.
                lo, hi = start, end
                while lo < hi and full_sentence[lo].isspace():
                    lo += 1
                while hi > lo and full_sentence[hi - 1].isspace():
                    hi -= 1
                return full_sentence[:lo] + GAP + full_sentence[hi:]
            if not candidate:
                continue
            if len(candidate) > len(target) or not target.startswith(candidate):
                break
    return None


def prompt_field(
    *,
    user_id: int,
    chunk_id: int,
    chunk: str,
    full_sentence: str | None,
) -> str:
    """Build the Anki prompt field (sentence_with_gap or chunk fallback)."""
    if full_sentence is None or not str(full_sentence).strip():
        logger.warning(
            "anki gap fallback user_id=%s chunk_id=%s reason=empty_full_sentence",
            user_id,
            chunk_id,
        )
        return chunk
    gapped = make_sentence_with_gap(str(full_sentence), chunk)
    if gapped is None:
        logger.warning(
            "anki gap fallback user_id=%s chunk_id=%s reason=chunk_not_in_sentence",
            user_id,
            chunk_id,
        )
        return chunk
    return gapped


def row_fields(
    row: ChunkExportRow,
    *,
    user_id: int,
) -> tuple[str, str, str, str]:
    """Return the four TSV fields, already sanitised."""
    prompt = prompt_field(
        user_id=user_id,
        chunk_id=row.id,
        chunk=row.chunk,
        full_sentence=row.full_sentence,
    )
    meaning = row.meaning if row.meaning is not None else ""
    source = row.source if row.source is not None else ""
    return (
        sanitize_tsv_field(prompt),
        sanitize_tsv_field(row.chunk),
        sanitize_tsv_field(meaning),
        sanitize_tsv_field(source),
    )


def build_tsv(rows: Sequence[ChunkExportRow], *, user_id: int) -> str:
    """Build a headerless UTF-8 TSV body."""
    lines = ["\t".join(row_fields(row, user_id=user_id)) for row in rows]
    return "\n".join(lines) + ("\n" if lines else "")


def filename_for(local_date: date) -> str:
    return f"english-bot-{local_date.isoformat()}.tsv"


def fetch_unexported_chunks(conn: Any, user_id: int) -> list[ChunkExportRow]:
    """Un-exported chunks for ``user_id``, oldest first."""
    rows = conn.execute(
        """
        SELECT id, chunk, full_sentence, meaning, source
          FROM chunks
         WHERE user_id = %s
           AND exported_to_anki = FALSE
         ORDER BY created_at ASC, id ASC
        """,
        (user_id,),
    ).fetchall()
    return [
        ChunkExportRow(
            id=int(r["id"]),
            chunk=str(r["chunk"]),
            full_sentence=r["full_sentence"],
            meaning=r["meaning"],
            source=r["source"],
        )
        for r in rows
    ]


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


async def export_and_send(
    *,
    user_id: int,
    local_date: date,
    send_document: Callable[[bytes, str, str], Awaitable[None]],
    claim_session: bool,
    caption: str,
) -> int:
    """Export un-exported chunks, send the TSV, commit marks (and session).

    ``send_document(tsv_bytes, filename, caption)`` is awaited inside the open
    transaction. Returns the number of cards exported.
    """
    with connection() as conn:
        with conn.transaction():
            rows = fetch_unexported_chunks(conn, user_id)
            if not rows:
                return 0

            tsv = build_tsv(rows, user_id=user_id)
            filename = filename_for(local_date)
            ids = [r.id for r in rows]

            # S15a: folder write is additive and failure-tolerant — never
            # blocks Telegram delivery or exported_to_anki marks.
            try:
                from core.services.watch_import import write_anki_outbox

                write_anki_outbox(
                    user_id,
                    tsv.encode("utf-8"),
                    filename,
                )
            except Exception:
                logger.warning(
                    "anki outbox unexpected failure user_id=%s — continuing",
                    user_id,
                    exc_info=True,
                )

            if claim_session:
                conn.execute(
                    """
                    INSERT INTO sessions (
                        user_id, date, task_type, delivered_at, completed,
                        payload
                    ) VALUES (
                        %s, %s, 'anki_export', NOW(), TRUE, %s
                    )
                    """,
                    (
                        user_id,
                        local_date,
                        Jsonb({"card_count": len(ids)}),
                    ),
                )

            conn.execute(
                """
                UPDATE chunks
                   SET exported_to_anki = TRUE
                 WHERE user_id = %s
                   AND id = ANY(%s)
                """,
                (user_id, ids),
            )

            await send_document(
                tsv.encode("utf-8"),
                filename,
                caption,
            )

    return len(ids)


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
    caption = copy.ANKI_WEEKLY.format(count=count)

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
        await message.reply_text(copy.ANKI_EMPTY)
        return

    count = len(pending)
    caption = copy.ANKI_MANUAL.format(count=count)
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
        await message.reply_text(copy.ANKI_SEND_FAILED)
        return

    if exported == 0:
        await message.reply_text(copy.ANKI_EMPTY)
