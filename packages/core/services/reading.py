"""Reading generation validation and atomic persist (S9a); MCQ parse (S9c).

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

from core.db import connection
from core.services.chunks import insert_chunks
from core.services.interests import mark_last_used

logger = logging.getLogger(__name__)

_MIN_WORDS = 250
_MAX_WORDS = 450
_EXPECTED_CHUNKS = 5
_EXPECTED_QUESTIONS = 5
_EXPECTED_OPTIONS = 4
_MAX_WHY_WORDS = 25

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
class ReadingMcq:
    q: str
    options: list[str]
    answer_index: int
    why: str


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


def _validate_one_mcq(item: Any, index: int) -> dict[str, Any]:
    """Validate one MCQ for generation; raises ReadingValidationError."""
    if not isinstance(item, dict):
        raise ReadingValidationError(f"question {index} is not an object")
    q = str(item.get("q") or "").strip()
    if not q:
        raise ReadingValidationError(f"question {index} missing q")
    options_raw = item.get("options")
    if not isinstance(options_raw, list) or len(options_raw) != _EXPECTED_OPTIONS:
        raise ReadingValidationError(
            f"question {index} expected {_EXPECTED_OPTIONS} options"
        )
    options = [str(o).strip() for o in options_raw]
    if any(not o for o in options):
        raise ReadingValidationError(f"question {index} has empty option")
    try:
        answer_index = int(item.get("answer_index"))
    except (TypeError, ValueError) as exc:
        raise ReadingValidationError(
            f"question {index} answer_index invalid"
        ) from exc
    if answer_index < 0 or answer_index >= _EXPECTED_OPTIONS:
        raise ReadingValidationError(
            f"question {index} answer_index out of range"
        )
    why = str(item.get("why") or "").strip()
    if not why:
        raise ReadingValidationError(f"question {index} missing why")
    if word_count(why) > _MAX_WHY_WORDS:
        raise ReadingValidationError(
            f"question {index} why exceeds {_MAX_WHY_WORDS} words"
        )
    return {
        "q": q,
        "options": options,
        "answer_index": answer_index,
        "why": why,
    }


def parse_stored_questions(raw: Any) -> list[ReadingMcq] | None:
    """Parse stored readings.questions as MCQ. Returns None if legacy/malformed.

    Soft for the user — never raises. Used only at Q&A delivery (S9c).
    """
    if not isinstance(raw, list) or len(raw) != _EXPECTED_QUESTIONS:
        return None
    out: list[ReadingMcq] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        q = str(item.get("q") or "").strip()
        options_raw = item.get("options")
        if not q or not isinstance(options_raw, list):
            return None
        if len(options_raw) != _EXPECTED_OPTIONS:
            return None
        options = [str(o).strip() for o in options_raw]
        if any(not o for o in options):
            return None
        try:
            answer_index = int(item.get("answer_index"))
        except (TypeError, ValueError):
            return None
        if answer_index < 0 or answer_index >= _EXPECTED_OPTIONS:
            return None
        why = str(item.get("why") or "").strip()
        if not why or word_count(why) > _MAX_WHY_WORDS:
            return None
        out.append(
            ReadingMcq(
                q=q,
                options=options,
                answer_index=answer_index,
                why=why,
            )
        )
    return out


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

    questions_raw = list(raw.get("questions") or [])
    if len(questions_raw) != _EXPECTED_QUESTIONS:
        raise ReadingValidationError(
            f"expected {_EXPECTED_QUESTIONS} questions, got {len(questions_raw)}"
        )
    questions = [_validate_one_mcq(item, i) for i, item in enumerate(questions_raw)]

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
    send: Callable[[], Awaitable[tuple[int, int]]],
) -> int:
    """Insert readings/chunks/session, send, then commit.

    ``send`` must return ``(chat_id, message_id)`` and is awaited inside the
    open transaction. If it raises, the transaction rolls back and zero rows
    remain. Returns the readings id. Also sets interests.last_used and stores
    chat_id/message_id on the session payload for S9c callback resolve.
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

            session_row = conn.execute(
                """
                INSERT INTO sessions (
                    user_id, date, task_type, delivered_at, completed, payload
                ) VALUES (
                    %s, %s, 'reading', NOW(), FALSE, %s
                )
                RETURNING id
                """,
                (user_id, local_date, Jsonb({"reading_id": reading_id})),
            ).fetchone()
            assert session_row is not None
            session_id = int(session_row["id"])

            mark_last_used(user_id, topic, track, local_date, conn=conn)

            chat_id, message_id = await send()

            conn.execute(
                """
                UPDATE sessions
                   SET payload = %s
                 WHERE id = %s AND user_id = %s
                """,
                (
                    Jsonb(
                        {
                            "reading_id": reading_id,
                            "chat_id": chat_id,
                            "message_id": message_id,
                        }
                    ),
                    session_id,
                    user_id,
                ),
            )

    return reading_id


def get_reading_for_user(user_id: int, reading_id: int) -> dict[str, Any] | None:
    """Return reading row scoped by user_id, or None."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, title, body, topic, cefr_level, questions,
                   completed, score, rating
              FROM readings
             WHERE id = %s AND user_id = %s
            """,
            (reading_id, user_id),
        ).fetchone()
    if row is None:
        return None
    questions = row["questions"]
    if questions is not None and not isinstance(questions, list):
        questions = list(questions)
    return {
        "id": int(row["id"]),
        "user_id": int(row["user_id"]),
        "title": row["title"],
        "body": row["body"],
        "topic": str(row["topic"] or ""),
        "cefr_level": row["cefr_level"],
        "questions": questions,
        "completed": bool(row["completed"]),
        "score": float(row["score"]) if row["score"] is not None else None,
        "rating": int(row["rating"]) if row["rating"] is not None else None,
    }


def complete_reading(
    user_id: int,
    reading_id: int,
    *,
    rating: int,
    score: float | None,
) -> None:
    """Mark reading completed with rating; score NULL when not assessed."""
    with connection() as conn:
        conn.execute(
            """
            UPDATE readings
               SET completed = TRUE,
                   rating = %s,
                   score = %s
             WHERE id = %s AND user_id = %s
            """,
            (rating, score, reading_id, user_id),
        )
