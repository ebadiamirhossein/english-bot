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
    """Distinct local dates in [start, end] with a completed session OR practice.

    **#259 (W19):** this counted `completed = TRUE` only, a flag no `daily` row
    has ever carried, so a learner on the web session every day counted zero —
    in the v2 `/stats` line and the operator panel. A day the learner practised
    (`core.services.activity`, the one signal the streak and the nudge ladder
    read too) now counts; v2's completed rows still do.
    """
    from core.services.activity import practised_dates

    with connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT date AS d
              FROM sessions
             WHERE user_id = %s
               AND completed = TRUE
               AND date BETWEEN %s AND %s
            """,
            (user_id, start, end),
        ).fetchall()
        days = {r["d"] for r in rows}
        days |= practised_dates(conn, user_id, start=start, end=end)
    return len(days)


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
    breakdown_of,
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


def _input_block(
    conn: Any, user_id: int, *, local_date: date
) -> tuple[str, dict[str, Any]]:
    """Block 2. **W13-i fills it. It has been `empty` since W10 (#302).**

    PRD §4.1 gives this block a video at the learner's coverage with an
    interactive transcript. **The pipeline is W12b's and the player is this
    slice**, so the block stops being structurally empty and starts being
    empty only on the four days in seven that have no video.

    **THE OLD REASON IS QUOTED RATHER THAN DELETED (#82's shape), because it was
    right when it was written and a reader needs to see what changed:** *"THE
    BLOCK IS STILL `empty`, AND FOR A REASON THAT SURVIVED THE CORRECTION. The
    tables exist and the pool is being filled, but W13 -- the player -- is not
    built, so there is nothing this block can render."* W13-i is built. What was
    missing was the player, and the player is what arrived.

    **THREE STATES, AND THEY ARE THREE FACTS THE LEARNER CAN ONLY SEE ONE OF:**

    * **no row for today** -> `empty`. PRD §7.1 assigns video on Mon/Wed/Fri, so
      this is the ordinary state on most days and nothing failed.
    * **a row whose `transcript` is NULL** -> `ready`, with
      `transcript_available: false`. **#335.** The 30-day purge nulls the
      transcript and returns the row to `pending`; nothing coordinates it with
      the weekly assignment and there is no cron (#69), so a learner really can
      open a day whose video is still assigned and still watchable while the
      interactive half is gone. **`youtube_id` survives the purge by design**
      (migration 019's header), so the video plays and only the transcript
      surface is absent -- which is a smaller loss than `unavailable` would
      claim, and nothing failed, so `unavailable` would be a lie.
    * **a row with a transcript** -> `ready`, with the transcript, the unknown
      lemmas and the band.

    **NOTHING IS GENERATED HERE, AND NOTHING IS BILLED.** Coverage is recomputed
    locally over text already stored -- pure CPU, no external call, which is the
    argument migration 019's header rests `video_coverage`'s
    audit-record-not-cache ruling on. **`video_coverage` IS NOT READ**: `assign`
    recomputes on every run and so does this, so the stored row keeps having no
    invalidation rule because nothing consults it. Tap-to-define and register
    detection are W13-ii's and are gated on the operator's §1a ruling; **this
    block reaches no model at all.**

    **THE BADGE IS A BAND TOKEN AND NEVER A NUMBER.** `core.video.badge` returns
    `below`/`in`/`above` or `None`, and the percentage never crosses the wire --
    so no client can render a figure it was never given. #288 (the floor ranks
    proper nouns as vocabulary, by an amount nobody has counted), #334
    (`coverage_fit` returns 1.0 across the whole band) and #330 (a percentage
    over 234 characters) are the three reasons, and they are written out at
    `core/video/badge.py`.

    **ONE COVERAGE CALL SERVES BOTH THE BADGE AND THE HIGHLIGHTING**, from the
    same string, deliberately: a band computed over one text and a highlight
    computed over another are two instruments on one screen that agree until
    they do not -- the same class as a stored 94% and a real 94% being
    indistinguishable, which is why `video_coverage` stores its whole basis.
    """
    from core.services import video as video_service
    from core.video.badge import band_for

    assigned = video_service.today_for(conn, user_id, on=local_date)
    if assigned is None:
        # `empty`, and empty is a FACT: the query ran and returned nothing.
        return "empty", {}

    payload: dict[str, Any] = {
        "video_id": assigned.video_id,
        "youtube_id": assigned.youtube_id,
        "title": assigned.title,
        "duration_s": assigned.duration_s,
        "accent": assigned.accent,
        "track": assigned.track,
        "resume_position_s": assigned.resume_position_s,
        "completed": assigned.completed_at is not None,
        "transcript_available": assigned.transcript is not None,
        "transcript": None,
        # **None is the THIRD STATE and not a gap**: transcript present, cues
        # absent. It renders, its words stay tappable, the coverage badge still
        # shows, and there is no follow-along highlight -- and the learner is
        # told nothing about it, because a line explaining a missing feature is
        # a message about our pipeline dressed as a message about the video.
        # The ordinary case for every pool row the backfill did not reach, and
        # nothing drains it on a schedule (#69).
        "transcript_cues": None,
        "transcript_lang": assigned.transcript_lang,
        "unknown_lemmas": [],
        "coverage_band": None,
    }
    if assigned.transcript is None:
        return "ready", payload

    from core.services import lexicon as lexicon_service

    report = lexicon_service.coverage_for(conn, user_id, assigned.transcript)
    payload["transcript"] = assigned.transcript
    payload["transcript_cues"] = assigned.transcript_cues
    payload["unknown_lemmas"] = sorted(report.unknown_lemmas)
    payload["coverage_band"] = band_for(
        report.coverage,
        counted_tokens=report.counted_tokens,
        proper_nouns_detected=report.proper_nouns_detected,
    )
    return "ready", payload


def _session_payload(conn, session_id: int) -> dict:
    """The session row's payload, for the facts a sitting stores about itself.

    `focus_item_ids` (#275) and `review_card_ids` (#258) both live here, for the
    reason #269's `item_ids` does: a set the learner is working through is a fact
    about the session, not a query result that can be re-run.
    """
    row = conn.execute(
        "SELECT payload FROM sessions WHERE id = %s", (session_id,)
    ).fetchone()
    return dict((row["payload"] if row else None) or {})


def _focus_block(
    unit: Any,
    user_id: int,
    *,
    section_index: int | None = None,
    conn: Any = None,
    session_id: int | None = None,
    stored_payload: dict | None = None,
    now: datetime | None = None,
) -> tuple[str, dict[str, Any]]:
    """Block 3. The unit's can-do, its grammar targets, and **its eight items.**

    **W17: UP TO TWO OF THE EIGHT ARE WEAK-SPOT DRILLS** — items written for a
    pattern this learner's error journal evidences (`core.services.drills`), served
    after the unit's items and each carrying the pattern's plain `learner_label`
    as `pattern`. **Inside the session, never as a separate queue, and never with
    a count** (#160, CLAUDE.md §4): no tally of how often the learner got it wrong
    crosses the wire. The block does not grow — the unit's share shrinks to make
    room. With no evidenced pattern, or no drills generated for one, block 3 is
    exactly what it was before W17. `now` is what the evidence window is read
    against; without it no drill is served.

    PRD §4.1 asks for "this week's grammar target: 90-second explanation + 8
    generated items". **W10c filled the second half and W10b fills the first**,
    so §4.1 block 3 is whole for the first time. `lesson` is still None for a
    unit nobody has generated for -- generation is human-run (#196) -- and a
    reader can still tell "no lesson yet" from "this shape has no lessons".

    THE BLOCK-3 CONTRACT, updated once here so it is readable from the record
    rather than from a diff. `items` is now populated where W10 shipped it empty:
    ``{unit_number, can_do, grammar_targets: [{target}], lesson, items: [...]}``

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
    from core.services import lessons as lessons_service

    # **THE SESSION'S EIGHT ARE A STORED FACT, NOT A FRESH SELECTION (#275).**
    #
    # `bank_for_session` orders by LEAST-RECENTLY-ATTEMPTED first, so answering an
    # item moves it to the back and the next eight are a DIFFERENT eight. One
    # cause, two symptoms: practice restarted at 1 of 8 on a refresh, and
    # **`focus` could never reach `done`** -- `_derive_done` compares the served
    # set against the answered set, and the served set was rebuilt every mount.
    #
    # Unit 1 shows why it bit now rather than at W10: its block-3 bank was four
    # items until session 86 sat the checkpoint, and a SAT checkpoint's twelve
    # stop being reserved and become ordinary practice stock -- sixteen items
    # behind an eight-item window, the first time the window could churn at all.
    #
    # **The same repair as #269's sitting and #258's review card ids**, on the
    # same `sessions.payload` and for the same reason: a set the learner is
    # working through is a fact about the session, not a query result.
    stored_ids = list((stored_payload or {}).get("focus_item_ids") or ())
    if stored_ids:
        presentations = items_service.items_by_id(user_id, stored_ids)
    else:
        drills = _weak_spot_drills(user_id, now)
        presentations = items_service.focus_items(
            user_id,
            unit_number=unit.unit_number,
            limit=items_service.FOCUS_ITEM_COUNT - len(drills),
        ) + drills
        if presentations and conn is not None and session_id is not None:
            conn.execute(
                # COALESCE: a daily row is inserted with NO payload and
                # `NULL || x` is NULL -- that write vanished silently once (#258).
                "UPDATE sessions SET payload = COALESCE(payload, '{}'::jsonb) || %s"
                " WHERE id = %s",
                (Jsonb({"focus_item_ids": [one.id for one in presentations]}),
                 session_id),
            )
    # **W10b fills the field W10 named and left NULL.** `for_unit` returns None
    # for a unit nobody has generated for -- which is most of them, because
    # generation is human-run (#196) -- and also for a stored lesson below the
    # current `LESSON_VERSION`, which it refuses rather than serving teaching
    # checked by rules that no longer exist. Both cases render the same line a
    # learner already sees, so `None` keeps meaning exactly what it meant.
    stored = lessons_service.for_unit(unit.unit_number)

    # **W11: THE LESSON IS PACED.** Operator ruling 2026-08-29 (#245): a section
    # advances per COMPLETED SESSION, not per calendar day, so a learner who
    # skips a day loses nothing and sees the next section when they next open a
    # session. When the sections run out before Saturday, block 3 shows PRACTICE
    # ONLY -- no new teaching and no repeated section.
    #
    # **TWO KEYS, NOT ONE, because running out of teaching and having no
    # teaching are different facts and the learner can only see one of them on
    # the screen.** That is `BLOCK_STATES`' own `empty`-versus-`unavailable`
    # reasoning applied one level in: a unit with no lesson must keep saying
    # "the explanation is on its way", and a learner who has read all four
    # sections must not be told the same thing about teaching they have finished.
    #
    #   lesson None                  -> section None, complete False  (most units)
    #   index < len(sections)        -> section index, complete False
    #   index >= len(sections)       -> section None,  complete TRUE
    sections = (stored.sections if stored else ()) or ()
    lesson_section: int | None = None
    teaching_complete = False
    if stored and sections:
        if section_index is None or section_index < len(sections):
            lesson_section = min(section_index or 0, len(sections) - 1)
        else:
            teaching_complete = True

    # **The resume position, on the wire.** It was React state, so a refresh
    # restarted practice at 1 of 8 while `item_attempts` held the answers (#275).
    answered_count = 0
    seen_before: set[int] = set()
    if conn is not None and session_id is not None and presentations:
        done_ids = _answered_ids(conn, "item_attempts", "item_id", session_id)
        answered_count = sum(1 for one in presentations if one.id in done_ids)
        # **#276 (c), operator ruling: when block 3 serves an item the learner
        # has met before, the surface says so.** BEFORE THIS SESSION, not
        # earlier in it -- telling someone they have answered a question they
        # answered ninety seconds ago is noise, and the fact worth stating is
        # that the bank has come round again.
        row = conn.execute(
            "SELECT array_agg(DISTINCT item_id) FROM item_attempts"
            " WHERE user_id = %s AND item_id = ANY(%s)"
            "   AND (session_id IS NULL OR session_id <> %s)",
            (user_id, [one.id for one in presentations], session_id),
        ).fetchone()
        seen_before = set((row["array_agg"] or []) if row else [])

    patterns = _drill_labels(user_id, [one.id for one in presentations])

    return "ready", {
        "answered": answered_count,
        "unit_number": unit.unit_number,
        "can_do": unit.can_do,
        "grammar_targets": [dict(one) for one in visible_targets(unit.grammar_targets)],
        "lesson": stored.model_dump(mode="json") if stored else None,
        "lesson_section": lesson_section,
        "teaching_complete": teaching_complete,
        "items": [
            focus_item_out(one, seen=one.id in seen_before, pattern=patterns.get(one.id))
            for one in presentations
        ],
    }


def focus_item_out(presentation: Any, *, seen: bool, pattern: str | None) -> dict[str, Any]:
    """One of block 3's items as it goes on the wire. **Pure, and the ONE shape.**

    `scripts/export_drill_fixture.py` builds the committed Vitest/Playwright
    fixture through this function, so the fixture and the route cannot describe
    two different shapes (#190). W17's `pattern` — the pattern's plain label —
    is present on a drill only, and is never a count.
    """
    out: dict[str, Any] = {
        "id": presentation.id,
        "response_mode": presentation.response_mode,
        "projection": presentation.projection,
        "seen": seen,
    }
    if pattern:
        out["pattern"] = pattern
    return out


def _weak_spot_drills(user_id: int, now: datetime | None) -> list[Any]:
    """Block 3's drills for today: evidenced patterns only (W17).

    **A failure here costs the drills, never the block.** The unit's items are
    the block's main business; a journal read that raises serves the day without
    drills rather than turning block 3 `unavailable`. Logged with the user id
    only (PRD §10).
    """
    if now is None:
        return []
    from core.services import drills as drills_service
    from core.services import items as items_service

    try:
        codes = [one.code for one in drills_service.evidenced_patterns(user_id, now=now)]
        return items_service.drill_items(user_id, codes=codes)
    except Exception:  # noqa: BLE001 -- see docstring
        logger.exception("weak-spot drills failed user_id=%s", user_id)
        return []


def _drill_labels(user_id: int, item_ids: list[int]) -> dict[int, str]:
    from core.services import drills as drills_service

    try:
        return drills_service.drill_labels(user_id, item_ids)
    except Exception:  # noqa: BLE001 -- a missing label costs the eyebrow only
        logger.exception("drill labels failed user_id=%s", user_id)
        return {}


def _output_block(
    unit: Any,
    conn: Any = None,
    user_id: int | None = None,
    *,
    local_date: date | None = None,
) -> tuple[str, dict[str, Any]]:
    """Block 4. PRD §4.1's *Speak or write* — and until W14 it only wrote.

    ────────────────────────────────────────────────────────────────────────────
    **W16a: THE PAYLOAD IS `{"day_kind"}` AND NOTHING ELSE.** It carried
    `{"unit_number", "mode", "task"}` until now. **All three are gone because
    nothing renders them**: design `1c`'s card draws no task text, and
    `unit_number` and `mode` were never read by any component (#390/#398/#403's
    rule — a field nothing renders is a defect). The day's task lives on
    `/write`, which asks `GET /write/today` for it.

    **`day_kind` is `journal` on every date in W16a** (`core.writing.rules`).
    PRD §4.2's Thursday paragraph is W16b's and is reported unmet in W16a's
    slice row. **The paragraphs below describing `output_task_written` served
    every day are HISTORY as of W16a** and are left as written (#82's shape):
    the unit's written task returns with W16b's paragraph, on Thursdays only.

    **The block still needs a seeded unit to be `ready`** — an unseeded unit
    keeps both blocks 3 and 4 `empty`, exactly as before. The journal does not
    read the unit; changing that is not this slice's and is not done silently.
    ────────────────────────────────────────────────────────────────────────────

    ────────────────────────────────────────────────────────────────────────────
    **W14 GIVES THIS BLOCK ITS SPEAK HALF, AND THE OLD CLAUSE IS QUOTED RATHER
    THAN DELETED (#82's shape) BECAUSE IT PROMISED MORE THAN W14 DELIVERS:**

        *"The written half only. Speaking is W14 (`speech_attempts`, Azure
        scoring) and W15, so `output_task_spoken` is deliberately not served
        here -- offering a task nothing can score is worse than not offering
        it."*

    **THAT EXPECTATION IS MET IN PART, AND THE PART MATTERS.**
    `output_task_spoken` is *"Tell me about your yesterday, from waking up to
    going to bed. Two minutes, no notes."* — **PRD §8 RUNG 3 (Answer)**, an open
    response scored by a model for content coverage. **W14 BUILDS RUNG 1
    (Shadow), WHICH IS NOT THAT.** So this block gains a *speak* surface
    **without serving `output_task_spoken`**; the 24 such strings in
    `data/syllabus_units.json` stay unserved and **W15 owns them.** The original
    clause's reasoning is still right and still binding on W15: offering a task
    nothing can score is worse than not offering it.

    **WHY SHADOW IS HERE AND NOT ON A SCREEN OF ITS OWN (§1e).** PRD §4.1's
    block 4 is literally *"Speak or write. Corrected. Errors → journal."*, and
    #160 forbids the alternative: *a tab whose counter accumulates while the
    learner is away is a backlog presented*, and **a queue of sentences you have
    not yet said out loud is a backlog in the most literal form this product can
    produce.** #160 also settles it positively — *due cards surface inside the
    daily session as real exercises: typed production, **spoken production**,
    cued gaps* — and the shadow target **is** a deck card's sentence. W13-i ruled
    the same way for the player, and `ARCHITECTURE §3`'s standalone
    `watch/[videoId]/` was never built.

    **THE LINE IS SERVED HERE AND NOWHERE ELSE.** There is no `GET /shadow/today`:
    one place decides today's line, the way block 2's video arrives in this same
    payload. `POST /shadow/{card_id}/score` is the only new route.

    **THIS BLOCK STILL CANNOT SELF-REPORT `done`, AND A SHADOW LOG DOES NOT
    CHANGE THAT (#361).** `_derive_done`'s `output` clause is about the WRITTEN
    task — `POST /correct` records no `session_id` — so marking the block done
    off a shadow attempt while the written task sits unanswered would claim a
    learner completed work they did not do. **#259 does not close and is not
    narrowed.**
    ────────────────────────────────────────────────────────────────────────────

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
    # Imported here, not at module level: `core.writing.rules` imports
    # `core.services.correction`, which imports this module.
    from core.writing import rules as writing_rules

    payload: dict[str, Any] = {
        "day_kind": writing_rules.day_kind(local_date) if local_date else "journal",
    }
    # ────────────────────────────────────────────────────────────────────
    # **THE SHADOW CONTROL IS RETIRED FROM BLOCK 4. OPERATOR RULING,
    # 2026-09-05. THE CODE STAYS; ONLY THE PAYLOAD KEY IS GONE.**
    #
    # **THE REASON IS #376's MEASUREMENT, NOT A PREFERENCE.** Pronunciation
    # assessment detects a word said as a DIFFERENT WORD and does not detect
    # an INFLECTIONAL ENDING. The operator deliberately mispronounced
    # `model→models`, `window→windows`, `can→can't` and `validation`, and
    # **only `trust` was caught.** So a learner who wants to speak better is
    # told they said it right when they did not, and **a surface whose
    # silence is uninformative is worse than no surface.**
    #
    # **DISABLE, DO NOT DELETE — #348's PRECEDENT FROM THREE DAYS AGO.** The
    # Sunday job was unregistered and its code left standing because W22
    # deletes the bot wholesale and a partial deletion makes that harder to
    # reason about. **AND THERE IS A SECOND REASON HERE: `speech_attempts`,
    # the Azure door and the scoring feed W17's weak-spot surface**, which
    # is the thing pronunciation assessment genuinely does well. W17 is the
    # consumer that keeps this code alive.
    #
    # `shadow_line`, `score_attempt`, `line_audio`, both routes,
    # `speech_api.py`, migration 024 and every shadow test are UNTOUCHED.
    # **W14 IS NOT UN-MARKED AND NOT REOPENED**: its three acceptance
    # criteria were met and evidenced. *The surface it built is retired from
    # the session pending W17* is a different statement from *it failed*.
    #
    # `test_block_four_offers_no_shadow_control` holds this, so a later
    # slice cannot restore the key without meeting the ruling.
    # ────────────────────────────────────────────────────────────────────
    # **W13b. THE CONVERSATION IS BLOCK 4's OTHER SPEAK-OR-WRITE HALF, AND
    # IT ARRIVES HERE RATHER THAN FROM A ROUTE OF ITS OWN** -- §1e's
    # precedent, applied unchanged: one place decides what block 4 serves,
    # because a second producer of one contract is #190's defect.
    #
    # **ADDITIVE, LIKE THE SHADOW LINE. It replaces nothing** -- the written
    # task stands, and PRD §8.6.6's warning about a sixth block does not
    # fire because no block is added.
    #
    # **W13b/3 §A: BLOCK 4 RENDERS NO CHAT AND CARRIES NO FLAG.**
    #
    # The conversation moved to `/talk`, a full-height page of its own, and
    # block 4 keeps only a **low-emphasis link** into it -- W11b's Sunday
    # shape. **A link needs no gate**, so the `voice` flag this payload used
    # to carry is gone rather than left as a key nobody reads: `/talk` gets
    # it from `POST /conversation/topics`, its own first call.
    #
    # **#160 IS STILL HONOURED IN FULL AND IT IS THE PART THAT WAS ALWAYS
    # RIGHT:** no count, no badge, no dot, no *days since your last
    # conversation*, and never the primary call-to-action. What §3.2 got
    # wrong was reading #160 as forbidding a PAGE; it forbids a COUNTER.
    return "ready", payload


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



def _answered_ids(conn, table: str, column: str, session_id: int) -> set[int]:
    row = conn.execute(
        f"SELECT array_agg(DISTINCT {column}) FROM {table} WHERE session_id = %s",
        (session_id,),
    ).fetchone()
    return set(row["array_agg"] or []) if row else set()


def _derive_done(conn, session_id: int, built: dict, stored_payload: dict) -> dict:
    """**#258: a block records itself done. The manual button is gone.**

    OPERATOR RULING, 2026-08-29. Nobody tapped it in three days of real use, it
    sat below five blocks on a phone, and **a signal that requires five taps
    below the fold is not a signal -- it is a form nobody fills in.**

    `block_breakdown->>'focus' = 'done'` keeps its meaning; **what changes is who
    writes it.** Two alternatives were refused and are recorded here so they are
    not re-proposed: `completed_at IS NOT NULL`, for the reason `day_in_unit`'s
    own docstring gives -- a learner can finish a session having skipped block 3
    -- and *any daily session advances*, because that makes opening the app mean
    practising and feeds #259 the same wrong signal.

    **WHAT "ANSWERED ITS ITEMS" MEANS, PER KIND, BECAUSE THE FIVE ARE NOT
    UNIFORM:**

    * ``review`` -- every card it served has a `card_reviews` row for this
      session. The queue is capped, so "every card served" is the right bar and
      not "every card due".
    * ``input`` -- **W13-i: `done` when `video_assignments.completed_at` is set
      for the video this block served.** The old clause is quoted rather than
      deleted (#82's shape): *"``input`` -- serves nothing until W12/W13.
      **`empty`, never `done`.**"* **That was true of a block that SERVED
      NOTHING, which is exactly what the per-kind rule turns on** -- `review`
      has `card_reviews`, `focus` has `item_attempts`, and block 2 had no log
      because it had no content. W13-i gives it both: the progress ping is
      block 2's `card_reviews`, `core.services.video.save_progress` is its one
      writer, and this branch reads what that wrote. **No control was added and
      none returns** -- the ruling above is honoured by supplying the evidence
      it asks for.
    * ``focus`` -- every item it served has an `item_attempts` row for this
      session.
    * ``output`` -- **W16a: `done` when `writing_submissions` holds a row for
      this session with `is_english`.** The old clause is quoted rather than
      deleted (#82's shape): *"``output`` -- **cannot self-report.** `POST
      /correct` records no `session_id`, so nothing links a correction to the
      sitting it happened in. It stays `ready`, and that is why
      `sessions.completed` is still unreachable and why #259 is NARROWED by this
      ruling rather than repaired."* **The first half is now false and the
      second half is STILL TRUE**: `sessions.completed` stays unreachable,
      because `complete_block` was removed at W11 and `minutes`/`completed_at`
      have no writer (#349, #361). **#259 is unchanged.** The row is the log
      (migration 027), not a flag a route sets -- #258's own shape. A clean
      entry writes a submission row and no `errors` row, which is why `errors`
      could never have carried this.
    * ``close`` -- a summary, not a task. Nothing to answer.

    **A BLOCK THAT SERVED NOTHING IS `empty`, NOT `done`**, and the two must not
    collapse: that distinction is `_build_block`'s reason for existing and
    `BLOCK_STATES` says so in as many words. Recording an empty block `done`
    would claim a learner completed work that does not exist.
    """
    out = dict(built)

    # **REVIEW'S SERVED SET HAS TO BE REMEMBERED, AND FOCUS'S DOES NOT.**
    # `cards.due_queue` excludes a card the moment it is graded, so by the time
    # the block is re-read the cards it served are gone and `empty` is
    # indistinguishable from `done` -- the exact collapse `BLOCK_STATES` forbids,
    # arriving from the other side. `focus_items` has no such filter: an answered
    # item is still served, only ordered last, which is why focus needs no memory.
    #
    # So the ids block 1 served are recorded on first hydration, on
    # `sessions.payload` -- **the same repair #269 made for the checkpoint's
    # twelve, for the same reason.**
    review_state, review_payload = built.get("review", ("empty", {}))
    live = [c.get("id") for c in (review_payload.get("cards") or [])]
    served = list(stored_payload.get("review_card_ids") or ()) or live
    if served:
        if not stored_payload.get("review_card_ids") and live:
            conn.execute(
                # COALESCE: a daily row is inserted with NO payload, and `NULL || x` is NULL —
                # the write vanished silently until this was found by a test that
                # asserted the RESULT rather than that the statement ran.
                "UPDATE sessions SET payload = COALESCE(payload, '{}'::jsonb) || %s"
                " WHERE id = %s",
                (Jsonb({"review_card_ids": live}), session_id),
            )
        graded = _answered_ids(conn, "card_reviews", "card_id", session_id)
        if all(one in graded for one in served):
            out["review"] = ("done", review_payload)

    # **BLOCK 2, AND IT READS A LOG RATHER THAN A TAP.** `completed_at` is
    # written only by `save_progress`, only from a position ping, and only when
    # `core.video.watch.is_complete` says the video was watched -- so `done`
    # here means the same kind of thing `review`'s and `focus`'s do.
    #
    # **A video with no stored `duration_s` NEVER REACHES THIS, and that is the
    # documented gap (#330).** `is_complete` returns False without a
    # denominator, so the block stays `ready` and this learner is returned to
    # the same video tomorrow -- #188's shape on a new surface. It is a stated
    # cost, not an oversight: the fix is a free metadata re-read on the refresh
    # path, and inferring a completion from nothing is what #258 forbids.
    input_state, input_payload = built.get("input", ("empty", {}))
    if input_state == "ready" and input_payload.get("completed"):
        out["input"] = ("done", input_payload)

    focus_state, focus_payload = built.get("focus", ("empty", {}))
    items = [one.get("id") for one in (focus_payload.get("items") or [])]
    if focus_state == "ready" and items:
        answered = _answered_ids(conn, "item_attempts", "item_id", session_id)
        if all(one in answered for one in items):
            out["focus"] = ("done", focus_payload)

    # W16a. A non-English submission spent a call and counts toward the ceiling,
    # but it is not the learner's English, so it does not finish the block.
    output_state, output_payload = built.get("output", ("empty", {}))
    if output_state == "ready":
        wrote = conn.execute(
            """
            SELECT 1 FROM writing_submissions
             WHERE session_id = %s AND is_english
             LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        if wrote is not None:
            out["output"] = ("done", output_payload)

    return out


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

        # **W11: the learner's first row for this unit, created here.**
        #
        # A read path that writes -- and the shape matters. This is an
        # `INSERT ... ON CONFLICT DO NOTHING` decided by 014's
        # `UNIQUE (user_id, unit_number)`, exactly like `_get_or_create_daily`
        # above it: idempotent create-once, race-free, and a refetch changes
        # nothing. What must NOT go on a read path is a MUTATING write -- an
        # incrementing counter would double-count on the refetch this route's own
        # rate-limit comment records, which is why the within-unit position is
        # computed rather than stored.
        #
        # It runs BEFORE the blocks are built because block 3 needs the row:
        # `unit_section_index` counts sessions since `entered_at`, so without it
        # the very first render of a unit is the one that cannot be paced.
        # Hanging this off `POST /session/{id}/block/{n}/complete` -- the only
        # POST on this router -- would fire after blocks 3 and 4 were already
        # served, which is too late by exactly one session.
        from core.services import syllabus as syllabus_service

        section_index: int | None = None
        if unit is not None:
            try:
                syllabus_service.record_unit_entry(
                    conn, user_id, unit.unit_number, now=now
                )
                section_index = syllabus_service.unit_section_index(
                    conn, user_id, unit.unit_number, local_today=local_date
                )
            except Exception:  # noqa: BLE001 -- the session must still open
                # An unpaced block 3 is the pre-W11 behaviour and is survivable;
                # a session that will not open is not. Logged with ids and route
                # names only (PRD §10).
                logger.exception(
                    "unit entry/pacing failed user_id=%s unit=%s",
                    user_id, unit.unit_number,
                )

        built: dict[str, tuple[str, dict[str, Any]]] = {
            "input": _build_block(
                "input",
                lambda: _input_block(conn, user_id, local_date=local_date),
            ),
            # A unit read that FAILED is `unavailable` for both blocks that
            # depend on it, and a unit that is simply not seeded is `empty` for
            # both. Two facts, kept apart even though they come from one query.
            "focus": ("unavailable", {})
            if unit_failed
            else _build_block(
                "focus",
                lambda: _focus_block(
                    unit,
                    user_id,
                    section_index=section_index,
                    conn=conn,
                    session_id=session_id,
                    stored_payload=_session_payload(conn, session_id),
                    now=now,
                ),
            ),
            "output": ("unavailable", {})
            if unit_failed
            else _build_block(
                "output",
                lambda: _output_block(
                    unit, conn=conn, user_id=user_id, local_date=local_date
                ),
            ),
        }

    # Second checkout, taken by `cards.due_queue` itself. The first is released.
    built["review"] = _build_block("review", lambda: _review_block(user_id, now=now))

    # **DERIVED, THEN the stored value, and the order matters (#258).** A block
    # earns `done` from the log; a stored `done` still wins afterwards so a
    # finished block stays finished when its live builder would now say `empty`
    # -- a learner who graded every due card must not see block 1 reopen.
    with connection() as conn:
        payload_row = conn.execute(
            "SELECT payload FROM sessions WHERE id = %s", (session_id,)
        ).fetchone()
        session_payload = dict((payload_row["payload"] if payload_row else None) or {})
        built = _derive_done(conn, session_id, built, session_payload)
        conn.commit()

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

    # **PERSISTED FROM A GET, and the reasoning is the one this file already
    # accepted twice.** `day_in_unit` reads `block_breakdown ->> 'focus'`, so a
    # derived value that is never written advances nothing. The write is
    # IDEMPOTENT AND CONVERGENT -- the same facts produce the same breakdown, so
    # re-reading the session writes the same row -- which is a different thing
    # from a mutating write on a read path, exactly as `_get_or_create_daily`'s
    # create-once is.
    with connection() as conn:
        conn.execute(
            "UPDATE sessions SET block_breakdown = %s WHERE id = %s",
            (Jsonb(breakdown_of(blocks)), session_id),
        )
        conn.commit()

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
