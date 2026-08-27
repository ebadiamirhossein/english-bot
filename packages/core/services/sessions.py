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

from core.db import connection

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


def _parse_last_activity(payload: dict[str, Any] | None) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("last_activity")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def conversation_timeout_for_phase(
    phase: str,
    *,
    active_minutes: int,
    awaiting_topic_minutes: int,
) -> int:
    """Minutes of inactivity before the filter fails open."""
    if phase == "awaiting_topic":
        return awaiting_topic_minutes
    return active_minutes


def get_open_conversation_session(
    user_id: int,
    *,
    now: datetime,
    active_minutes: int = 30,
    awaiting_topic_minutes: int = 2,
) -> SessionRow | None:
    """Newest incomplete conversation session still inside its phase window.

    Staleness is evaluated here (filter time) — no scheduler. Fail-open: missing
    or unparseable last_activity → None.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, date, task_type, completed, score, payload
              FROM sessions
             WHERE user_id = %s
               AND task_type = 'conversation'
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
    payload = payload or {}
    phase = str(payload.get("phase") or "active")
    if phase not in ("awaiting_topic", "active"):
        return None
    last = _parse_last_activity(payload)
    if last is None:
        return None
    timeout_min = conversation_timeout_for_phase(
        phase,
        active_minutes=active_minutes,
        awaiting_topic_minutes=awaiting_topic_minutes,
    )
    age = now - last
    if age.total_seconds() > timeout_min * 60:
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


def utc_now_iso(now: datetime | None = None) -> str:
    """UTC ISO timestamp for session payload activity stamps."""
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# W10 — the daily session. PRD §4.1.
#
# Everything below this line belongs to `GET /session/today` and
# `POST /session/{id}/block/{n}/complete`. The route calls ONE function of it
# and serialises the result; all five blocks are hydrated inside that one call.
#
# **NOTHING HERE MAKES A MODEL CALL.** PRD §4.1 and ARCHITECTURE §7: items are
# generated and gated the night before, never while the learner waits. W10
# generates nothing at all, so the property is trivially true today -- and it is
# asserted anyway, through the network guard, because it stops being trivial the
# moment the generation slice lands.
# ═══════════════════════════════════════════════════════════════════════════

from core.sessions import (  # noqa: E402  (section import, see the banner above)
    BLOCK_COUNT,
    BLOCK_KINDS,
    DAILY_TASK_TYPE,
    MAX_SESSION_MINUTES,
)
from core.sessions.blocks import (  # noqa: E402
    Block,
    assemble,
    first_open_block,
    stored_state,
    visible_targets,
)


@dataclass(frozen=True, slots=True)
class DailySession:
    """One day's session, hydrated. What `GET /session/today` serialises."""

    id: int
    date: date
    #: `users.native_language`, carried ONCE on the envelope rather than on every
    #: card (#159). It is a per-user fact, and eighty copies of it is eighty
    #: chances for two of them to disagree.
    l1_language: str
    blocks: tuple[Block, ...]
    current_block: int
    completed: bool


def _user_context(conn: Any, user_id: int) -> tuple[str, str] | None:
    """``(timezone, native_language)`` for this learner, or None if unknown.

    Both columns have existed since `001_init_postgres.sql` -- `timezone` at :27
    with `DEFAULT 'Europe/Vilnius'`, `native_language` at :19 `NOT NULL`. #159
    was filed as "nothing in the schema records a learner's first language" and
    corrected in its own row: there is no missing column and no migration, only
    a value that never reached the card.

    `COALESCE` on the timezone mirrors `core.scheduling.list_candidate_users`,
    which defaults the same way for the same reason.
    """
    row = conn.execute(
        """
        SELECT COALESCE(timezone, 'Europe/Vilnius') AS tz, native_language
          FROM users
         WHERE id = %s
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return str(row["tz"]), str(row["native_language"])


def _get_or_create_daily(
    conn: Any, user_id: int, local_date: date, *, now: datetime
) -> tuple[int, Any, bool]:
    """``(session_id, stored_breakdown, completed)`` for this learner's day.

    Idempotent, and idempotent by the DATABASE rather than by a read-then-write:
    `sessions_one_daily_per_user_per_date` (migration 016) is a partial UNIQUE on
    `(user_id, date) WHERE task_type = 'daily'`, so `ON CONFLICT DO NOTHING`
    plus a re-read is race-free. Two tabs, or `assign_daily` racing this lazy
    create, cannot produce two rows.

    **The date is the LEARNER's local date** -- see `today()` and migration 016's
    header. The index enforces one row per date and cannot tell you the date was
    computed wrongly, which is why the convention is named in three places
    rather than left to whoever writes the next caller.

    **`delivered_at` is PASSED IN, never `NOW()`**, and it is the same rule
    migration 013 states for `card_reviews.reviewed_at`: a column default makes
    the instant that opened the session and the instant everything downstream
    reasons about two different clock reads. `minutes` is the difference between
    this stamp and the completing one, so a `NOW()` here would make that
    difference depend on which of two clocks was ahead -- and it would be
    invisible until someone tried to explain a NULL.
    """
    conn.execute(
        """
        INSERT INTO sessions (user_id, date, task_type, delivered_at, completed)
        VALUES (%s, %s, %s, %s, FALSE)
        ON CONFLICT (user_id, date) WHERE task_type = 'daily' DO NOTHING
        """,
        (user_id, local_date, DAILY_TASK_TYPE, now),
    )
    row = conn.execute(
        """
        SELECT id, block_breakdown, completed
          FROM sessions
         WHERE user_id = %s AND date = %s AND task_type = %s
        """,
        (user_id, local_date, DAILY_TASK_TYPE),
    ).fetchone()
    assert row is not None
    return int(row["id"]), row["block_breakdown"], bool(row["completed"])


def _review_block(user_id: int, *, now: datetime) -> tuple[str, dict[str, Any]]:
    """Block 1. #160: the due deck lives INSIDE the session, not behind a tab.

    `/review` is not deleted and keeps its route -- someone who wants extra work
    can still open it -- but it stops being a daily obligation with a count on
    it. CLAUDE.md §4 is the binding rule and it is a rule this project already
    had: *"Never present a backlog. Missed days shrink the task; they never pile
    up."* A tab whose counter accumulates while the learner is away is a backlog
    presented, and it had been one since W7.

    The queue is the CAPPED queue (`cards.due_queue` enforces PRD §5's two
    budgets), so what block 1 offers is what a learner will actually be shown.
    A learner with two hundred overdue cards is offered eighty and is told
    nothing at all about the other hundred and twenty.
    """
    from core.services import cards as cards_service

    queue = cards_service.due_queue(user_id, now=now, limit=REVIEW_BLOCK_LIMIT)
    if not queue:
        # `empty`, and empty is a FACT: the query ran and returned nothing.
        # The copy the learner reads for it is block 1's alone -- see
        # `apps/web/components/session/copy.ts` -- and it offers watching rather
        # than inventing practice.
        return "empty", {}
    # `cards_service.card_face` and NOT `card.face()` (#190). The bare `face()`
    # omits `intervals`, which the client's `CardFace` type declares as
    # non-optional and `GradeButtons` reads unguarded — so this line shipped a
    # session that crashed on the first card a learner graded. One contract, one
    # producer.
    return "ready", {"cards": [cards_service.card_face(c, now=now) for c in queue]}


def _input_block() -> tuple[str, dict[str, Any]]:
    """Block 2. **Empty, honestly, and empty for a structural reason.**

    PRD §4.1 gives this block a video at the learner's coverage with an
    interactive transcript. The video engine is W12 and the player is W13;
    `videos` and `video_assignments` do not exist as tables yet (migration 017 in
    the authoritative table). There is nothing to read and nothing failed, so the
    state is `empty` and never `unavailable`.

    **Rendering it rather than hiding it is the point.** A four-block session
    would say the product has four blocks. This one says: this part is not built
    yet, which is true.
    """
    return "empty", {}


def _focus_block(unit: Any, user_id: int) -> tuple[str, dict[str, Any]]:
    """Block 3. The unit's can-do, its grammar targets, and **its eight items.**

    PRD §4.1 asks for "this week's grammar target: 90-second explanation + 8
    generated items". **W10c fills the second half.** The explanation is still
    W10b, which is approved and not started, so `lesson` stays named and NULL --
    a reader can tell "no lesson yet" from "this shape has no lessons".

    THE BLOCK-3 CONTRACT, updated once here so it is readable from the record
    rather than from a diff. `items` is now populated where W10 shipped it empty:
    ``{unit_number, can_do, grammar_targets: [{target}], lesson: None, items: [...]}``

    **NOTHING IS GENERATED HERE.** `focus_items` is `bank_for_session` plus the
    projection -- one read, of items that were validated, target-checked and
    written by a human-run command days earlier. That is W10's own criterion and
    `tests/test_session_route.py::test_nothing_is_generated_while_the_learner_waits`
    holds it structurally, through session-wide `netguard`, rather than by
    intention.

    **An empty list is the ordinary state for a unit nobody has generated for**,
    and block 3 renders it as the honest empty state it has had since W10. Only
    units 1-3 have items today, and only for the learner they were generated for
    -- #159 is why they were not copied to the second learner.

    `visible_targets` and not the raw column: #171, and the citation is dropped
    at this seam. See `core.sessions.blocks.visible_target`. The generator drops
    it at the same seam, for the sharper reason that an assumption embedded in a
    generated sentence is invisible in a way a rendered number is not.
    """
    if unit is None:
        return "empty", {}
    from core.services import items as items_service

    presentations = items_service.focus_items(
        user_id, unit_number=unit.unit_number
    )
    return "ready", {
        "unit_number": unit.unit_number,
        "can_do": unit.can_do,
        "grammar_targets": [dict(one) for one in visible_targets(unit.grammar_targets)],
        "lesson": None,
        "items": [
            {
                "id": one.id,
                "response_mode": one.response_mode,
                "projection": one.projection,
            }
            for one in presentations
        ],
    }


def _output_block(unit: Any) -> tuple[str, dict[str, Any]]:
    """Block 4. The unit's written task, corrected through the existing `/correct`.

    The written half only. Speaking is W14 (`speech_attempts`, Azure scoring) and
    W15, so `output_task_spoken` is deliberately not served here -- offering a
    task nothing can score is worse than not offering it.

    **THIS BLOCK REPEATS. Every day, until W11.** `current_unit` cannot advance
    -- `user_unit_state` is empty and W11 owns every write to it -- so this is
    unit 1's single `output_task_written`, verbatim, on day two and on day
    thirty. Unit 1 has one written task and there is no rotation to draw on.

    It ships repeating rather than empty, and the reasoning is recorded because
    the alternative was live: an empty block says *nothing here yet* and is
    honest, while a block showing an identical prompt every morning can read as
    the app not paying attention. But the task is real, doing it twice is not
    harmful, and shipping it empty would leave the session with no production
    surface at all. **The failure would be presenting it as working content
    without saying it repeats**, which is what this docstring, the decisions log
    and the day-two phone check exist to prevent.

    No journal writer is added here. `POST /correct` (W3, ✅ verified) is the
    only path that writes `errors`, it already has its integration test through
    the ASGI transport, and this block hands the learner to it.
    """
    if unit is None:
        return "empty", {}
    return "ready", {
        "unit_number": unit.unit_number,
        "mode": "write",
        "task": unit.output_task_written,
    }


def _close_block(conn: Any, session_id: int, blocks_done: int) -> tuple[str, dict[str, Any]]:
    """Block 5. What you actually did. **No XP number.**

    PRD §4.1 asks for three lines on what you learned, tomorrow's preview and
    XP. Two of the three are not this slice's:

    * the three lines need a model call, and nothing may be generated while a
      learner waits;
    * **XP is W19's**, which owns the effort weighting (a spoken sentence must
      outscore a tapped MCQ). Migration 016 ships `sessions.xp` and W10 writes
      NULL into it. Inventing a weighting now would make the first weeks of
      history incomparable with every week after them -- the same reasoning that
      left `item_attempts.grade` NULL at W6 rather than synthesising a 1-4 from a
      boolean.

    What is left is real and is counted from the log rather than from a counter
    column: how many cards were graded inside this session.
    """
    row = conn.execute(
        "SELECT count(*)::int AS n FROM card_reviews WHERE session_id = %s",
        (session_id,),
    ).fetchone()
    assert row is not None
    return "ready", {
        "cards_reviewed": int(row["n"]),
        "blocks_completed": blocks_done,
        "block_count": BLOCK_COUNT,
    }


#: One screenful of block 1. The daily caps bound the day (`cards.due_queue`);
#: this bounds one hydration, so a phone on a slow connection is not made to
#: wait for eighty card faces it will not reach before the app is closed. Same
#: reasoning and same shape as `apps/api/routers/cards.py`'s `MAX_LIMIT`.
REVIEW_BLOCK_LIMIT = 20


def _build_block(
    kind: str,
    builder: Any,
) -> tuple[str, dict[str, Any]]:
    """Run one block's builder, converting a failure into `unavailable`.

    **THIS IS THE SEAM THAT KEEPS "I AM EMPTY" AND "I FAILED TO LOAD" APART, and
    it is the only place `unavailable` is ever produced.** A builder that
    returns `empty` has run to completion and found nothing; a builder that
    raises produces `unavailable`, and the two say different things on a screen.
    A learner told *nothing's due, go watch something* because a query timed out
    has been lied to, and on the screen the lie is indistinguishable from the
    truth.

    One block failing must not take the session down -- the other four are still
    worth having -- but a WHOLE-ROUTE failure is an HTTP error and produces
    neither state. That distinction is the client's `problem` branch, which
    renders a retry and never the empty copy.

    The exception is logged with the block name and no payload: PRD §10, logs
    carry ids and route names, never content.
    """
    try:
        return builder()
    except Exception:  # noqa: BLE001 -- deliberate: any failure is `unavailable`
        logger.exception("session block failed kind=%s", kind)
        return "unavailable", {}


def today(user_id: int, *, now: datetime) -> DailySession | None:
    """This learner's session for today, hydrated. ``None`` if the user is unknown.

    **The one function `GET /session/today` calls.** All five blocks are built
    here; the route parses, authorises, calls this, and serialises.

    WHOSE DATE: THE LEARNER'S. `local_today(users.timezone, now)`, which is
    already how every other `sessions.date` in that table is computed across
    eleven task types. UTC was the live alternative and is rejected because
    `date` would then mean the learner's day for `quiz`, `reading` and `diary`
    and the server's day for `daily`, in one column -- a session opened at 00:30
    Vilnius would land on a row dated yesterday, beside a `reading` row dated
    today. `now` is INJECTED, as it is throughout `apps/api/routers/cards.py`, so
    a boundary test can walk local midnight without freezing the clock
    (CLAUDE.md §3 rule 6).

    **A stored `done` wins over a live rebuild, and nothing else does.** The
    breakdown is the resume state: a block the learner finished stays finished
    when they come back, even though its live builder would now say `empty`
    (they graded every due card) or `ready` (a card came back). Every other
    stored value is ignored and the block is rebuilt from live data, so a stale
    breakdown cannot pin a block open or shut.

    **Yesterday leaves nothing behind.** There is no carry-over, no unfinished
    count, and no reference anywhere to a session that was not completed. The
    row stays in `sessions` as history; the learner is never shown it.

    **The pool checkouts here are SEQUENTIAL and never nested**, which is a
    constraint rather than a style: `DB_POOL_MAX` defaults to 5, and a function
    that held one connection while `cards.due_queue` took a second would need two
    per in-flight request and could starve the pool under concurrency. Every
    other read in this file follows the same shape.
    """
    with connection() as conn:
        context = _user_context(conn, user_id)
        if context is None:
            return None
        tz, l1_language = context
        local_date = local_today(tz, now)

        session_id, stored, completed = _get_or_create_daily(
            conn, user_id, local_date, now=now
        )

        # Blocks 3 and 4 share one unit read. `current_unit` never writes --
        # W11 owns `user_unit_state` -- so this returns 1 for everyone today and
        # keeps returning 1; see its docstring for what that costs block 4.
        unit_state, unit_holder = _build_block(
            "unit", lambda: ("ready", {"unit": _current_unit_row(conn, user_id)})
        )
        unit = unit_holder.get("unit") if unit_state == "ready" else None
        unit_failed = unit_state == "unavailable"

        built: dict[str, tuple[str, dict[str, Any]]] = {
            "input": _input_block(),
            # A unit read that FAILED is `unavailable` for both blocks that
            # depend on it, and a unit that is simply not seeded is `empty` for
            # both. Two facts, kept apart even though they come from one query.
            "focus": ("unavailable", {})
            if unit_failed
            else _build_block("focus", lambda: _focus_block(unit, user_id)),
            "output": ("unavailable", {})
            if unit_failed
            else _build_block("output", lambda: _output_block(unit)),
        }

    # Second checkout, taken by `cards.due_queue` itself. The first is released.
    built["review"] = _build_block("review", lambda: _review_block(user_id, now=now))

    for kind in ("review", "input", "focus", "output"):
        if stored_state(stored, kind) == "done":
            built[kind] = ("done", built[kind][1])

    done_so_far = sum(1 for state, _ in built.values() if state == "done")

    with connection() as conn:
        built["close"] = _build_block(
            "close", lambda: _close_block(conn, session_id, done_so_far)
        )
    if stored_state(stored, "close") == "done":
        built["close"] = ("done", built["close"][1])

    blocks = assemble(built)

    return DailySession(
        id=session_id,
        date=local_date,
        l1_language=l1_language,
        blocks=blocks,
        current_block=first_open_block(blocks),
        completed=completed,
    )


def _current_unit_row(conn: Any, user_id: int) -> Any:
    """The learner's current unit row, or None when the syllabus is not seeded.

    Two service calls behind one name so `today()` reads as one step. Imported
    inside the function because `core.services.syllabus` imports
    `core.syllabus.content`, which reads `data/`, and this module is imported by
    the bot's scheduler on a path that has no business touching the syllabus
    file.
    """
    from core.services import syllabus as syllabus_service

    return syllabus_service.unit_for_session(
        conn, syllabus_service.current_unit(conn, user_id)
    )


def complete_block(
    user_id: int, session_id: int, block_n: int, *, now: datetime
) -> DailySession | None:
    """Mark one block done. ``None`` when the session is not this learner's.

    Scoped by `user_id` in the UPDATE itself, never checked and then written:
    "not yours" and "no such session" collapse into one answer here for the same
    reason they do in `items.presentation_for` and `cards.get_card` -- telling a
    caller that an id exists but belongs to someone else is a fact about another
    learner.

    **`minutes` is computed HERE, server-side, from stored timestamps**, and is
    never reported by the browser. #108 is the standing lesson: `latency_ms` is
    the one value W6 wrote from a number the client chose, and a phone
    backgrounded mid-session produces a real-but-meaningless figure. Anything
    outside 0..`MAX_SESSION_MINUTES` is stored NULL rather than as a lie.

    `xp` is deliberately not written. W19 owns the effort weighting; see
    `_close_block`.
    """
    if block_n not in range(1, BLOCK_COUNT + 1):
        raise ValueError(f"block must be 1..{BLOCK_COUNT}, got {block_n}")
    kind = BLOCK_KINDS[block_n - 1]

    with connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """
                SELECT id, block_breakdown, delivered_at
                  FROM sessions
                 WHERE id = %s AND user_id = %s AND task_type = %s
                 FOR UPDATE
                """,
                (session_id, user_id, DAILY_TASK_TYPE),
            ).fetchone()
            if row is None:
                return None

            stored = row["block_breakdown"]
            breakdown = dict(stored) if isinstance(stored, dict) else {}
            breakdown[kind] = "done"

            all_done = all(
                breakdown.get(one) == "done" for one in BLOCK_KINDS
            )
            minutes = _session_minutes(row["delivered_at"], now) if all_done else None

            conn.execute(
                """
                UPDATE sessions
                   SET block_breakdown = %s,
                       completed = CASE WHEN %s THEN TRUE ELSE completed END,
                       completed_at = CASE WHEN %s THEN %s ELSE completed_at END,
                       minutes = COALESCE(%s, minutes)
                 WHERE id = %s
                """,
                (
                    Jsonb(breakdown),
                    all_done,
                    all_done,
                    now,
                    minutes,
                    session_id,
                ),
            )

    return today(user_id, now=now)


def _session_minutes(delivered_at: datetime | None, now: datetime) -> int | None:
    """Whole minutes from delivery to completion, or None if implausible.

    Mirrors `items._clean_latency` and `cards._clean_duration`: a measurement
    outside the plausible range is stored as NULL rather than as a lie.
    """
    if delivered_at is None:
        return None
    if delivered_at.tzinfo is None:
        delivered_at = delivered_at.replace(tzinfo=timezone.utc)
    elapsed = (now - delivered_at).total_seconds() / 60
    if elapsed < 0 or elapsed > MAX_SESSION_MINUTES:
        return None
    return int(elapsed)


def ensure_daily_session(user_id: int, local_date: date, *, now: datetime) -> int:
    """Create this learner's daily session row for `local_date`. Returns its id.

    **`apps/worker/jobs.py::assign_daily`'s entry point, and it hydrates
    nothing.** ARCHITECTURE §7 gives `assign_daily` three jobs -- build the
    session, pick and pre-validate items, choose the video. Two of the three have
    no subject in this slice: nothing generates items and the video engine is
    W12. So the job creates the row and stops, and the emptiness is recorded
    rather than dressed up.

    Idempotent through the same partial UNIQUE the lazy path uses, so the job
    running and a learner opening the app early cannot make two rows.
    """
    with connection() as conn:
        session_id, _, _ = _get_or_create_daily(
            conn, user_id, local_date, now=now
        )
    return session_id
