"""Reading generation validation and atomic persist (S9a).

Persist holds an open transaction until the Telegram send succeeds; on send
failure the transaction rolls back so no poisoned chunks reach Anki.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable

from psycopg.types.json import Jsonb

from app.db import connection
from app.services.chunks import insert_chunks
from app.services.interests import mark_last_used

logger = logging.getLogger(__name__)

_MIN_WORDS = 250
_MAX_WORDS = 450
_EXPECTED_CHUNKS = 5

_APOSTROPHES = (
    "\u0027",  # '
    "\u2019",  # '
    "\u2018",  # '
    "\u0060",  # `
    "\u00b4",  # ´
)
_QUOTES = (
    "\u0022",  # "
    "\u201c",  # "
    "\u201d",  # "
    "\u00ab",  # «
    "\u00bb",  # »
)


@dataclass(frozen=True)
class ReadingPayload:
    title: str
    body: str
    questions: list[dict[str, Any]]
    chunks: list[dict[str, str]]


class ReadingValidationError(ValueError):
    """Raised when an LLM reading payload fails validation."""


def normalize_for_match(text: str) -> str:
    """Casefold, collapse whitespace, normalise apostrophes and quotes."""
    s = text.casefold()
    for a in _APOSTROPHES[1:]:
        s = s.replace(a, _APOSTROPHES[0])
    for q in _QUOTES[1:]:
        s = s.replace(q, _QUOTES[0])
    s = re.sub(r"\s+", " ", s).strip()
    return s


def word_count(body: str) -> int:
    return len(body.split())


def validate_reading_payload(raw: dict[str, Any]) -> ReadingPayload:
    """Validate LLM JSON. Raises ReadingValidationError on failure."""
    title = str(raw.get("title") or "").strip()
    body = str(raw.get("body") or "").strip()
    if not title:
        raise ReadingValidationError("missing title")
    if not body:
        raise ReadingValidationError("missing body")

    words = word_count(body)
    if words < _MIN_WORDS or words > _MAX_WORDS:
        raise ReadingValidationError(
            f"body word count {words} outside {_MIN_WORDS}-{_MAX_WORDS}"
        )

    questions = list(raw.get("questions") or [])
    if len(questions) != 5:
        raise ReadingValidationError(
            f"expected 5 questions, got {len(questions)}"
        )

    raw_chunks = list(raw.get("chunks") or [])
    if len(raw_chunks) != _EXPECTED_CHUNKS:
        raise ReadingValidationError(
            f"expected {_EXPECTED_CHUNKS} chunks, got {len(raw_chunks)}"
        )

    body_norm = normalize_for_match(body)
    cleaned: list[dict[str, str]] = []
    for i, item in enumerate(raw_chunks):
        if not isinstance(item, dict):
            raise ReadingValidationError(f"chunk {i} is not an object")
        chunk = str(item.get("chunk") or "").strip()
        if not chunk:
            raise ReadingValidationError(f"chunk {i} empty")
        chunk_norm = normalize_for_match(chunk)
        if chunk_norm not in body_norm:
            raise ReadingValidationError(
                f"chunk {i} not found in body (after normalisation)"
            )
        cleaned.append(
            {
                "chunk": chunk,  # store as model returned (trimmed)
                "full_sentence": str(item.get("full_sentence") or "").strip(),
                "meaning": str(item.get("meaning") or "").strip(),
            }
        )

    return ReadingPayload(
        title=title,
        body=body,
        questions=questions,
        chunks=cleaned,
    )


async def persist_and_send(
    *,
    user_id: int,
    local_date: date,
    topic: str,
    track: str,
    cefr_level: str,
    payload: ReadingPayload,
    send: Callable[[], Awaitable[None]],
) -> int:
    """Insert readings/chunks/session, send, then commit.

    ``send`` is awaited inside the open transaction. If it raises, the
    transaction rolls back and zero rows remain. Returns the readings id.
    Also sets interests.last_used inside the same transaction.
    """
    with connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """
                INSERT INTO readings (
                    user_id, title, body, topic, cefr_level, questions,
                    sent_at, completed
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, NOW(), FALSE
                )
                RETURNING id
                """,
                (
                    user_id,
                    payload.title,
                    payload.body,
                    topic,
                    cefr_level,
                    Jsonb(payload.questions),
                ),
            ).fetchone()
            assert row is not None
            reading_id = int(row["id"])

            insert_chunks(
                conn,
                user_id,
                source=f"reading_{reading_id}",
                track=track,
                chunks=payload.chunks,
            )

            conn.execute(
                """
                INSERT INTO sessions (
                    user_id, date, task_type, delivered_at, completed, payload
                ) VALUES (
                    %s, %s, 'reading', NOW(), FALSE, %s
                )
                """,
                (user_id, local_date, Jsonb({"reading_id": reading_id})),
            )

            mark_last_used(user_id, topic, track, local_date, conn=conn)

            await send()

    return reading_id
