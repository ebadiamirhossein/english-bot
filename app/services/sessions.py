"""Session rows and bot-initiated message ceiling (S3).

S10: nudges_sent helpers, nudgeable open sessions, sunday_report marker.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from app.db import connection

logger = logging.getLogger(__name__)

BOT_MESSAGE_CEILING = 3
NUDGEABLE_TASK_TYPES = frozenset({"quiz", "reading", "diary"})
MAX_NUDGES_PER_DAY = 2
MAX_NUDGES_PER_SESSION = 2


@dataclass(frozen=True)
class SessionRow:
    id: int
    user_id: int
    date: date
    task_type: str
    completed: bool
    score: float | None
    payload: dict[str, Any] | None


@dataclass(frozen=True)
class NudgeableSession:
    id: int
    user_id: int
    date: date
    task_type: str
    delivered_at: datetime
    nudges_sent: int
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
    """True if a quiz or free_practice session exists for this user on local_date.

    Voice (and future non-morning) sessions must not block morning delivery.
    """
    with connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM sessions
             WHERE user_id = %s AND date = %s
               AND task_type IN ('quiz', 'free_practice')
             LIMIT 1
            """,
            (user_id, local_date),
        ).fetchone()
    return row is not None


def has_reading_session_on(user_id: int, local_date: date) -> bool:
    """True if a reading session exists for this user on local_date."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM sessions
             WHERE user_id = %s AND date = %s
               AND task_type = 'reading'
             LIMIT 1
            """,
            (user_id, local_date),
        ).fetchone()
    return row is not None


def has_anki_session_on(user_id: int, local_date: date) -> bool:
    """True if an anki_export session exists for this user on local_date."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM sessions
             WHERE user_id = %s AND date = %s
               AND task_type = 'anki_export'
             LIMIT 1
            """,
            (user_id, local_date),
        ).fetchone()
    return row is not None


def has_sunday_report_session_on(user_id: int, local_date: date) -> bool:
    """True if a sunday_report session exists for this user on local_date."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM sessions
             WHERE user_id = %s AND date = %s
               AND task_type = 'sunday_report'
             LIMIT 1
            """,
            (user_id, local_date),
        ).fetchone()
    return row is not None


def has_diary_session_on(user_id: int, local_date: date) -> bool:
    """True if any diary session exists for this user on local_date."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM sessions
             WHERE user_id = %s AND date = %s
               AND task_type = 'diary'
             LIMIT 1
            """,
            (user_id, local_date),
        ).fetchone()
    return row is not None


def has_completed_diary_on(user_id: int, local_date: date) -> bool:
    """True if a completed diary session exists for this user on local_date."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM sessions
             WHERE user_id = %s AND date = %s
               AND task_type = 'diary'
               AND completed = TRUE
             LIMIT 1
            """,
            (user_id, local_date),
        ).fetchone()
    return row is not None


def get_open_diary_session(
    user_id: int, local_date: date
) -> SessionRow | None:
    """Incomplete diary session for this user on local_date, if any."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, date, task_type, completed, score, payload
              FROM sessions
             WHERE user_id = %s
               AND date = %s
               AND task_type = 'diary'
               AND completed = FALSE
             ORDER BY id DESC
             LIMIT 1
            """,
            (user_id, local_date),
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
        task_type=str(row["task_type"]),
        completed=bool(row["completed"]),
        score=float(row["score"]) if row["score"] is not None else None,
        payload=payload,
    )


# S16: shadow claims voice only within this window after clip_sent_at.
SHADOW_VOICE_CLAIM_MINUTES = 30


def get_open_shadow_session(
    user_id: int, local_date: date
) -> SessionRow | None:
    """Incomplete shadow session for this user on local_date, if any."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, date, task_type, completed, score, payload
              FROM sessions
             WHERE user_id = %s
               AND date = %s
               AND task_type = 'shadow'
               AND completed = FALSE
             ORDER BY id DESC
             LIMIT 1
            """,
            (user_id, local_date),
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
        task_type=str(row["task_type"]),
        completed=bool(row["completed"]),
        score=float(row["score"]) if row["score"] is not None else None,
        payload=payload,
    )


def _parse_clip_sent_at(payload: dict[str, Any] | None) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("clip_sent_at")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def get_claimable_shadow_session(
    user_id: int,
    local_date: date,
    *,
    now: datetime,
    claim_minutes: int = SHADOW_VOICE_CLAIM_MINUTES,
) -> SessionRow | None:
    """Open shadow that still owns the microphone (clip sent recently).

    Session may stay open until 03:00 (rule 2); only the voice *claim*
    is time-bounded so an abandoned /shadow does not strand M3.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    session = get_open_shadow_session(user_id, local_date)
    if session is None:
        return None
    sent = _parse_clip_sent_at(session.payload)
    if sent is None:
        return None
    age = now - sent
    if age.total_seconds() > claim_minutes * 60:
        return None
    return session


def daily_nudges_sent(user_id: int, local_date: date) -> int:
    """Sum of nudges_sent across all sessions for this user on local_date."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(nudges_sent), 0) AS total
              FROM sessions
             WHERE user_id = %s AND date = %s
            """,
            (user_id, local_date),
        ).fetchone()
    assert row is not None
    return int(row["total"])


def get_session_by_id(user_id: int, session_id: int) -> SessionRow | None:
    """Load a session scoped by user_id (never cross-user)."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, date, task_type, completed, score, payload
              FROM sessions
             WHERE id = %s AND user_id = %s
            """,
            (session_id, user_id),
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
        task_type=str(row["task_type"]),
        completed=bool(row["completed"]),
        score=float(row["score"]) if row["score"] is not None else None,
        payload=payload,
    )


def list_open_nudgeable_sessions(user_id: int) -> list[NudgeableSession]:
    """Incomplete quiz/reading/diary sessions, oldest delivery first."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, date, task_type, delivered_at, nudges_sent,
                   payload
              FROM sessions
             WHERE user_id = %s
               AND completed = FALSE
               AND task_type = ANY(%s)
               AND delivered_at IS NOT NULL
             ORDER BY delivered_at ASC, id ASC
            """,
            (user_id, list(NUDGEABLE_TASK_TYPES)),
        ).fetchall()
    out: list[NudgeableSession] = []
    for row in rows:
        delivered = row["delivered_at"]
        if delivered.tzinfo is None:
            delivered = delivered.replace(tzinfo=timezone.utc)
        payload = row["payload"]
        if payload is not None and not isinstance(payload, dict):
            payload = dict(payload)
        out.append(
            NudgeableSession(
                id=int(row["id"]),
                user_id=int(row["user_id"]),
                date=row["date"],
                task_type=str(row["task_type"]),
                delivered_at=delivered,
                nudges_sent=int(row["nudges_sent"] or 0),
                payload=payload,
            )
        )
    return out


def increment_nudges_sent(user_id: int, session_id: int) -> int:
    """Increment nudges_sent for a session owned by user_id. Returns new value."""
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE sessions
               SET nudges_sent = nudges_sent + 1
             WHERE id = %s AND user_id = %s
            RETURNING nudges_sent
            """,
            (session_id, user_id),
        ).fetchone()
    if row is None:
        raise ValueError(
            f"increment_nudges_sent: no session id={session_id} user_id={user_id}"
        )
    return int(row["nudges_sent"])


def set_session_delivered_at(
    user_id: int,
    session_id: int,
    delivered_at: datetime,
) -> None:
    """Test/helper: backdate delivered_at (scoped by user_id)."""
    if delivered_at.tzinfo is None:
        raise ValueError("delivered_at must be timezone-aware")
    with connection() as conn:
        conn.execute(
            """
            UPDATE sessions
               SET delivered_at = %s
             WHERE id = %s AND user_id = %s
            """,
            (delivered_at, session_id, user_id),
        )


def count_active_days(
    user_id: int,
    *,
    start: date,
    end: date,
) -> int:
    """Distinct local dates with any completed session in [start, end]."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT date) AS n
              FROM sessions
             WHERE user_id = %s
               AND completed = TRUE
               AND date BETWEEN %s AND %s
            """,
            (user_id, start, end),
        ).fetchone()
    assert row is not None
    return int(row["n"])


def claim_sunday_report_session(
    user_id: int,
    local_date: date,
    *,
    payload: dict[str, Any] | None = None,
) -> int:
    """Insert completed sunday_report marker. Returns session id."""
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO sessions (
                user_id, date, task_type, delivered_at, completed,
                completed_at, payload
            ) VALUES (
                %s, %s, 'sunday_report', NOW(), TRUE, NOW(), %s
            )
            RETURNING id
            """,
            (
                user_id,
                local_date,
                Jsonb(payload) if payload is not None else None,
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


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


def complete_session(session_id: int, score: float | None) -> None:
    """Mark a session completed. ``score`` may be NULL when not assessed (S9c)."""
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


def get_reading_session_by_message(
    user_id: int,
    chat_id: int,
    message_id: int,
) -> SessionRow | None:
    """Incomplete reading session whose payload matches this Telegram message.

    Lookup key is message_id (+ chat_id), not "any open reading" — orphans
    without a message_id (e.g. pre-S9c reading 17) cannot steal callbacks.
    Not scoped to a local date so next-day taps still resolve.
    """
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, date, task_type, completed, score, payload
              FROM sessions
             WHERE user_id = %s
               AND task_type = 'reading'
               AND completed = FALSE
               AND (payload ->> 'message_id') = %s
               AND (payload ->> 'chat_id') = %s
             ORDER BY id DESC
             LIMIT 1
            """,
            (user_id, str(message_id), str(chat_id)),
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
        task_type=str(row["task_type"]),
        completed=bool(row["completed"]),
        score=float(row["score"]) if row["score"] is not None else None,
        payload=payload,
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


def get_book_test_session_by_message(
    user_id: int,
    chat_id: int,
    message_id: int,
) -> SessionRow | None:
    """Incomplete book_test whose payload matches this Telegram message."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, date, task_type, completed, score, payload
              FROM sessions
             WHERE user_id = %s
               AND task_type = 'book_test'
               AND completed = FALSE
               AND (payload ->> 'message_id') = %s
               AND (payload ->> 'chat_id') = %s
             ORDER BY id DESC
             LIMIT 1
            """,
            (user_id, str(message_id), str(chat_id)),
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
        task_type=str(row["task_type"]),
        completed=bool(row["completed"]),
        score=float(row["score"]) if row["score"] is not None else None,
        payload=payload,
    )


def abandon_open_book_tests(user_id: int) -> int:
    """Mark incomplete book_test sessions completed-as-abandoned (score NULL).

    Returns the number of rows updated. Used when starting a fresh /test so
    abandoned mid-sets do not accumulate forever.
    """
    with connection() as conn:
        rows = conn.execute(
            """
            UPDATE sessions
               SET completed = TRUE,
                   completed_at = NOW(),
                   score = NULL
             WHERE user_id = %s
               AND task_type = 'book_test'
               AND completed = FALSE
            RETURNING id
            """,
            (user_id,),
        ).fetchall()
    return len(rows)


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


def get_fossil_sweep_session(user_id: int, month_start: date) -> SessionRow | None:
    """fossil_sweep marker for this user on the local month-start date."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, date, task_type, completed, score, payload
              FROM sessions
             WHERE user_id = %s
               AND date = %s
               AND task_type = 'fossil_sweep'
             ORDER BY id DESC
             LIMIT 1
            """,
            (user_id, month_start),
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
        task_type=str(row["task_type"]),
        completed=bool(row["completed"]),
        score=float(row["score"]) if row["score"] is not None else None,
        payload=payload,
    )


def create_fossil_sweep_session(
    user_id: int,
    month_start: date,
    *,
    pending: list[int],
) -> int:
    """Insert monthly M13 queue. Returns session id."""
    payload = {"pending": [int(i) for i in pending], "done": []}
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO sessions (
                user_id, date, task_type, delivered_at, completed, payload
            ) VALUES (
                %s, %s, 'fossil_sweep', NOW(), FALSE, %s
            )
            RETURNING id
            """,
            (user_id, month_start, Jsonb(payload)),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def open_fossil_sweep_for_user(user_id: int) -> SessionRow | None:
    """Most recent incomplete fossil_sweep with pending ids (any month)."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, date, task_type, completed, score, payload
              FROM sessions
             WHERE user_id = %s
               AND task_type = 'fossil_sweep'
               AND completed = FALSE
             ORDER BY date DESC, id DESC
             LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    payload = row["payload"]
    if payload is not None and not isinstance(payload, dict):
        payload = dict(payload)
    pending = list((payload or {}).get("pending") or [])
    if not pending:
        return None
    return SessionRow(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        date=row["date"],
        task_type=str(row["task_type"]),
        completed=bool(row["completed"]),
        score=float(row["score"]) if row["score"] is not None else None,
        payload=payload,
    )


def mark_fossil_retest_done(session_id: int, error_id: int) -> None:
    """Move error_id from pending to done; complete session when pending empty."""
    with connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """
                SELECT payload FROM sessions
                 WHERE id = %s AND task_type = 'fossil_sweep'
                 FOR UPDATE
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return
            payload = row["payload"]
            if payload is not None and not isinstance(payload, dict):
                payload = dict(payload)
            data = dict(payload or {})
            pending = [int(x) for x in (data.get("pending") or [])]
            done = [int(x) for x in (data.get("done") or [])]
            eid = int(error_id)
            if eid in pending:
                pending = [x for x in pending if x != eid]
            if eid not in done:
                done.append(eid)
            data["pending"] = pending
            data["done"] = done
            completed = len(pending) == 0
            conn.execute(
                """
                UPDATE sessions
                   SET payload = %s,
                       completed = %s,
                       completed_at = CASE
                           WHEN %s THEN NOW()
                           ELSE completed_at
                       END
                 WHERE id = %s
                """,
                (Jsonb(data), completed, completed, session_id),
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


def get_continuable_voice_session(
    user_id: int,
    *,
    now: datetime,
    context_minutes: int,
    max_turns: int,
) -> SessionRow | None:
    """Most recent voice session still inside the conversation window.

    Live conversation is found by recency and turn count, not by completed
    (voice exchanges are marked completed as soon as they succeed).
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, date, task_type, completed, score, payload,
                   completed_at
              FROM sessions
             WHERE user_id = %s
               AND task_type = 'voice'
             ORDER BY id DESC
             LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    completed_at = row["completed_at"]
    if completed_at is None:
        return None
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    age = now - completed_at
    if age.total_seconds() > context_minutes * 60:
        return None
    payload = row["payload"]
    if payload is not None and not isinstance(payload, dict):
        payload = dict(payload)
    payload = payload or {}
    turn_count = int(payload.get("turn_count") or 0)
    if turn_count >= max_turns:
        return None
    return SessionRow(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        date=row["date"],
        task_type=row["task_type"],
        completed=bool(row["completed"]),
        score=float(row["score"]) if row["score"] is not None else None,
        payload=payload,
    )


def save_voice_exchange(
    session_id: int | None,
    user_id: int,
    local_date: date,
    payload: dict[str, Any],
) -> int:
    """Insert or update a voice session after a successful exchange.

    Always sets completed=TRUE and completed_at=NOW() so abandoned mid-turn
    failures that never reach this function leave no incomplete voice row.
    """
    with connection() as conn:
        if session_id is None:
            row = conn.execute(
                """
                INSERT INTO sessions (
                    user_id, date, task_type, delivered_at,
                    completed, completed_at, payload
                ) VALUES (
                    %s, %s, 'voice', NOW(), TRUE, NOW(), %s
                )
                RETURNING id
                """,
                (user_id, local_date, Jsonb(payload)),
            ).fetchone()
            assert row is not None
            return int(row["id"])
        conn.execute(
            """
            UPDATE sessions
               SET payload = %s,
                   completed = TRUE,
                   completed_at = NOW()
             WHERE id = %s
               AND user_id = %s
            """,
            (Jsonb(payload), session_id, user_id),
        )
        return session_id
