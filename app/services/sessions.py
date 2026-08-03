"""Session rows and bot-initiated message ceiling (S3)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from app.db import connection

logger = logging.getLogger(__name__)

BOT_MESSAGE_CEILING = 3


@dataclass(frozen=True)
class SessionRow:
    id: int
    user_id: int
    date: date
    task_type: str
    completed: bool
    score: float | None
    payload: dict[str, Any] | None


def local_today(timezone: str, now: datetime) -> date:
    """Return the calendar date in ``timezone`` at instant ``now``."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(ZoneInfo(timezone)).date()


def local_time_hhmm(timezone: str, now: datetime) -> tuple[int, int]:
    """Return (hour, minute) in ``timezone`` at instant ``now``."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local = now.astimezone(ZoneInfo(timezone))
    return local.hour, local.minute


def has_session_on(user_id: int, local_date: date) -> bool:
    """True if any sessions row exists for this user on local_date."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM sessions
             WHERE user_id = %s AND date = %s
             LIMIT 1
            """,
            (user_id, local_date),
        ).fetchone()
    return row is not None


def insert_session(
    user_id: int,
    task_type: str,
    local_date: date,
    *,
    payload: dict[str, Any] | None = None,
    completed: bool = False,
) -> int:
    """Insert a sessions row with delivered_at = NOW(). Returns id."""
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO sessions (
                user_id, date, task_type, delivered_at, completed, payload
            ) VALUES (
                %s, %s, %s, NOW(), %s, %s
            )
            RETURNING id
            """,
            (
                user_id,
                local_date,
                task_type,
                completed,
                Jsonb(payload) if payload is not None else None,
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def complete_session(session_id: int, score: float) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE sessions
               SET completed = TRUE,
                   completed_at = NOW(),
                   score = %s
             WHERE id = %s
            """,
            (score, session_id),
        )


def complete_open_free_practice(user_id: int, local_date: date) -> bool:
    """Mark today's open free_practice session completed. Returns True if updated."""
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE sessions
               SET completed = TRUE,
                   completed_at = NOW()
             WHERE id = (
                SELECT id FROM sessions
                 WHERE user_id = %s
                   AND date = %s
                   AND task_type = 'free_practice'
                   AND completed = FALSE
                 ORDER BY id DESC
                 LIMIT 1
             )
            RETURNING id
            """,
            (user_id, local_date),
        ).fetchone()
    return row is not None


def update_session_payload(session_id: int, payload: dict[str, Any]) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE sessions
               SET payload = %s
             WHERE id = %s
            """,
            (Jsonb(payload), session_id),
        )


def get_open_quiz_session(user_id: int, local_date: date | None = None) -> SessionRow | None:
    """Incomplete quiz session for this user.

    If ``local_date`` is given, restrict to that date. If omitted, return the
    most recent incomplete quiz (so a restart or local-midnight crossover
    cannot route a typed answer into the correction handler).
    """
    with connection() as conn:
        if local_date is not None:
            row = conn.execute(
                """
                SELECT id, user_id, date, task_type, completed, score, payload
                  FROM sessions
                 WHERE user_id = %s
                   AND date = %s
                   AND task_type = 'quiz'
                   AND completed = FALSE
                 ORDER BY id DESC
                 LIMIT 1
                """,
                (user_id, local_date),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id, user_id, date, task_type, completed, score, payload
                  FROM sessions
                 WHERE user_id = %s
                   AND task_type = 'quiz'
                   AND completed = FALSE
                 ORDER BY id DESC
                 LIMIT 1
                """,
                (user_id,),
            ).fetchone()
    if row is None:
        return None
    payload = row["payload"]
    if payload is not None and not isinstance(payload, dict):
        payload = dict(payload)
    return SessionRow(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        date=row["date"],
        task_type=row["task_type"],
        completed=bool(row["completed"]),
        score=float(row["score"]) if row["score"] is not None else None,
        payload=payload,
    )


def bot_initiated_count(user_id: int, local_date: date) -> int:
    """Messages already sent by the bot to this user on local_date."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT count FROM bot_message_counts
             WHERE user_id = %s AND local_date = %s
            """,
            (user_id, local_date),
        ).fetchone()
    if row is None:
        return 0
    return int(row["count"])


def increment_bot_messages(user_id: int, local_date: date) -> int:
    """Increment and return the new bot-initiated message count for the day."""
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO bot_message_counts (user_id, local_date, count)
            VALUES (%s, %s, 1)
            ON CONFLICT (user_id, local_date) DO UPDATE
               SET count = bot_message_counts.count + 1
            RETURNING count
            """,
            (user_id, local_date),
        ).fetchone()
    assert row is not None
    return int(row["count"])


def under_message_ceiling(user_id: int, local_date: date) -> bool:
    return bot_initiated_count(user_id, local_date) < BOT_MESSAGE_CEILING
