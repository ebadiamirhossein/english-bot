"""Anki TSV export from un-exported chunks (S7 / M6).

Channel-neutral: building the TSV and marking rows exported lives here;
the weekly delivery and the ``/anki`` command live in
``apps/bot/anki_delivery.py`` until the worker takes them.

Rows are marked ``exported_to_anki`` only inside a transaction held across
``send_document`` — a failed send rolls back so cards are never lost.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable, Sequence

from psycopg.types.json import Jsonb

from core.db import connection
from core.services.reading import normalize_for_match

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
