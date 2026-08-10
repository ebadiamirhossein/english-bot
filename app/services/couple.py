"""Couple challenge (M8 / S8).

Chat-level daily question from the error journal, atomic first-correct
scoring into ``couple_scores``, Sunday leaderboard marker.

Does not call ``mark_result`` (no ``source_error_id`` column yet).
Does not touch streaks, ceiling, or private learning paths.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from app.config import Settings
from app.db import connection
from app.services.errors import Error
from app.services.sessions import local_today

logger = logging.getLogger(__name__)

COUPLE_TZ_NAME = "Europe/Vilnius"
COUPLE_TZ = ZoneInfo(COUPLE_TZ_NAME)
COUPLE_SLOT = time(18, 0)
LEADERBOARD_TASK = "couple_leaderboard"
SCHEDULED_MAX_CHARS = 400


@dataclass(frozen=True)
class CoupleChallenge:
    id: int
    date: date
    question: str
    answer: str
    winner_user_id: int | None
    answered_at: datetime | None


def week_start(d: date) -> date:
    """Monday of the ISO week containing ``d``."""
    return d.fromordinal(d.toordinal() - d.weekday())


def couple_local_today(now: datetime) -> date:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return local_today(COUPLE_TZ_NAME, now)


def couple_time_reached(now: datetime) -> bool:
    """True when Vilnius local time is at or past 18:00."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local = now.astimezone(COUPLE_TZ)
    return (local.hour, local.minute) >= (COUPLE_SLOT.hour, COUPLE_SLOT.minute)


def is_couple_sunday(now: datetime) -> bool:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(COUPLE_TZ).weekday() == 6


def registered_user_ids() -> list[int]:
    """All registered telegram user ids, ascending."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT telegram_user_id
              FROM users
             ORDER BY telegram_user_id ASC
            """
        ).fetchall()
    return [int(r["telegram_user_id"]) for r in rows]


def feature_ready(settings: Settings) -> bool:
    """Chat configured and at least two registered users."""
    if settings.couple_chat_id is None:
        return False
    return len(registered_user_ids()) >= 2


def stubborn_error(user_id: int) -> Error | None:
    """Unresolved error with highest times_wrong, then oldest next_review."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, you_said, correct_form, error_type, explanation,
                   streak_right, times_right, times_wrong, next_review,
                   resolved, resolved_at, unresolved_count, created_at
              FROM errors
             WHERE user_id = %s
               AND resolved = FALSE
             ORDER BY times_wrong DESC, next_review ASC, id ASC
             LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_error(row)


def pick_source_error(day: date) -> Error | None:
    """Alternate between the two users; fall back if that journal is empty."""
    ids = registered_user_ids()
    if len(ids) < 2:
        return None
    primary = ids[day.toordinal() % 2]
    secondary = ids[1 - (day.toordinal() % 2)]
    err = stubborn_error(primary)
    if err is not None:
        return err
    return stubborn_error(secondary)


def get_challenge_for_date(day: date) -> CoupleChallenge | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, date, question, answer, winner_user_id, answered_at
              FROM couple_challenges
             WHERE date = %s
             ORDER BY id ASC
             LIMIT 1
            """,
            (day,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_challenge(row)


def get_open_challenge(day: date) -> CoupleChallenge | None:
    ch = get_challenge_for_date(day)
    if ch is None or ch.winner_user_id is not None:
        return None
    return ch


def insert_challenge_if_absent(
    day: date, question: str, answer: str
) -> int | None:
    """Insert one challenge for ``day``. Returns id, or None if already present."""
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO couple_challenges (date, question, answer)
            SELECT %s, %s, %s
             WHERE NOT EXISTS (
                SELECT 1 FROM couple_challenges WHERE date = %s
             )
            RETURNING id
            """,
            (day, question, answer, day),
        ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def claim_win(challenge_id: int, user_id: int) -> bool:
    """Atomic first-correct claim. True only when this caller won."""
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE couple_challenges
               SET winner_user_id = %s,
                   answered_at = NOW()
             WHERE id = %s
               AND winner_user_id IS NULL
         RETURNING id
            """,
            (user_id, challenge_id),
        ).fetchone()
    return row is not None


def add_point(user_id: int, week: date) -> None:
    """Increment ``couple_scores`` for ``week`` (Monday week_start)."""
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO couple_scores (user_id, week_start, points)
            VALUES (%s, %s, 1)
            ON CONFLICT (user_id, week_start)
            DO UPDATE SET points = couple_scores.points + 1
            """,
            (user_id, week),
        )


def scores_for_week(week: date) -> dict[int, int]:
    """Map user_id → points for the week. Missing users are absent (not 0)."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT user_id, points
              FROM couple_scores
             WHERE week_start = %s
            """,
            (week,),
        ).fetchall()
    return {int(r["user_id"]): int(r["points"]) for r in rows}


def points_for(user_id: int, week: date) -> int:
    return scores_for_week(week).get(user_id, 0)


def claim_sunday_leaderboard(sunday: date, marker_user_id: int) -> bool:
    """Insert incomplete couple_leaderboard marker. True if this caller claimed.

    ``completed`` stays FALSE forever — must not make the day Active.
    ``date`` is the Sunday posted, not week_start.
    """
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO sessions (
                user_id, date, task_type, delivered_at, completed
            )
            SELECT %s, %s, %s, NOW(), FALSE
             WHERE NOT EXISTS (
                SELECT 1 FROM sessions
                 WHERE user_id = %s
                   AND date = %s
                   AND task_type = %s
             )
            RETURNING id, completed
            """,
            (
                marker_user_id,
                sunday,
                LEADERBOARD_TASK,
                marker_user_id,
                sunday,
                LEADERBOARD_TASK,
            ),
        ).fetchone()
    return row is not None


def leaderboard_marker_row(
    marker_user_id: int, sunday: date
) -> dict[str, Any] | None:
    """Test helper: fetch the marker row if present."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, date, task_type, completed
              FROM sessions
             WHERE user_id = %s
               AND date = %s
               AND task_type = %s
             LIMIT 1
            """,
            (marker_user_id, sunday, LEADERBOARD_TASK),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def _row_to_challenge(row: Any) -> CoupleChallenge:
    return CoupleChallenge(
        id=int(row["id"]),
        date=row["date"],
        question=str(row["question"]),
        answer=str(row["answer"]),
        winner_user_id=(
            int(row["winner_user_id"])
            if row["winner_user_id"] is not None
            else None
        ),
        answered_at=row["answered_at"],
    )


def _row_to_error(row: Any) -> Error:
    return Error(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        you_said=str(row["you_said"]),
        correct_form=str(row["correct_form"]),
        error_type=str(row["error_type"]),
        explanation=row["explanation"],
        streak_right=int(row["streak_right"]),
        times_right=int(row["times_right"]),
        times_wrong=int(row["times_wrong"]),
        next_review=row["next_review"],
        resolved=bool(row["resolved"]),
        resolved_at=row["resolved_at"],
        unresolved_count=int(row["unresolved_count"]),
        created_at=row["created_at"],
    )
