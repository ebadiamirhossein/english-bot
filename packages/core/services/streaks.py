"""Streak, freeze tokens, and rescue mode (S4 / PRD §7 rules 5–7).

ARCHITECTURE §8: a silent bug here destroys the product without being visible.
Tests are mandatory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from core.db import connection
from core.services.sessions import local_time_hhmm, local_today

logger = logging.getLogger(__name__)

BACKFILL_MAX_DAYS = 30
USERS_PER_POLL_TICK = 50
RESCUE_MISS_THRESHOLD = 3
RESCUE_DURATION_DAYS = 7
ROLLOVER_HOUR = 3
DEFAULT_FREEZE_TOKENS = 2

Outcome = Literal["active", "missed", "neutral", "skipped"]


@dataclass(frozen=True)
class Streak:
    user_id: int
    current_streak: int
    longest_streak: int
    freeze_tokens: int
    last_active_date: date | None
    last_evaluated_date: date | None
    rescue_mode_until: date | None
    total_active_days: int
    freeze_reset_on: date | None
    pending_freeze_notice: bool


@dataclass(frozen=True)
class StreakResult:
    user_id: int
    day: date
    outcome: Outcome
    current_streak: int
    longest_streak: int
    freeze_tokens: int
    freeze_consumed: bool
    rescue_started: bool
    rescue_mode_until: date | None
    last_active_date: date | None
    total_active_days: int


def get_streak(user_id: int) -> Streak:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT user_id, current_streak, longest_streak, freeze_tokens,
                   last_active_date, last_evaluated_date, rescue_mode_until,
                   total_active_days, freeze_reset_on, pending_freeze_notice
              FROM streaks
             WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        raise LookupError(f"No streaks row for user_id={user_id}")
    return _row_to_streak(row)


def is_in_rescue(user_id: int, day: date) -> bool:
    streak = get_streak(user_id)
    until = streak.rescue_mode_until
    return until is not None and day <= until


def consume_freeze_notice(user_id: int) -> bool:
    """Clear pending_freeze_notice if set. Returns True when a notice was pending."""
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE streaks
               SET pending_freeze_notice = FALSE
             WHERE user_id = %s
               AND pending_freeze_notice = TRUE
            RETURNING freeze_tokens
            """,
            (user_id,),
        ).fetchone()
    return row is not None


def closed_through_date(timezone: str, now: datetime) -> date:
    """Latest local calendar day whose 03:00 window has closed."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    today = local_today(timezone, now)
    hour, _minute = local_time_hhmm(timezone, now)
    if hour >= ROLLOVER_HOUR:
        return today - timedelta(days=1)
    return today - timedelta(days=2)


def roll_over_day(user_id: int, day: date) -> StreakResult:
    """Evaluate one past day for one user. Idempotent via last_evaluated_date."""
    with connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """
                SELECT user_id, current_streak, longest_streak, freeze_tokens,
                       last_active_date, last_evaluated_date, rescue_mode_until,
                       total_active_days, freeze_reset_on, pending_freeze_notice
                  FROM streaks
                 WHERE user_id = %s
                 FOR UPDATE
                """,
                (user_id,),
            ).fetchone()
            if row is None:
                raise LookupError(f"No streaks row for user_id={user_id}")

            last_eval = row["last_evaluated_date"]
            if last_eval is not None and day <= last_eval:
                return StreakResult(
                    user_id=user_id,
                    day=day,
                    outcome="skipped",
                    current_streak=int(row["current_streak"]),
                    longest_streak=int(row["longest_streak"]),
                    freeze_tokens=int(row["freeze_tokens"]),
                    freeze_consumed=False,
                    rescue_started=False,
                    rescue_mode_until=row["rescue_mode_until"],
                    last_active_date=row["last_active_date"],
                    total_active_days=int(row["total_active_days"]),
                )

            # Day-state precedence (S5): Active > Missed > Neutral.
            # Any completed session (any task_type) makes the day Active, even
            # if an incomplete quiz also exists. Missed only when there is an
            # incomplete quiz and no completed session. Do not use ORDER BY id
            # LIMIT 1 — insert order must not decide engagement.
            day_rows = conn.execute(
                """
                SELECT task_type, completed
                  FROM sessions
                 WHERE user_id = %s AND date = %s
                """,
                (user_id, day),
            ).fetchall()
            any_completed = any(bool(r["completed"]) for r in day_rows)
            incomplete_quiz = any(
                (not bool(r["completed"])) and str(r["task_type"]) == "quiz"
                for r in day_rows
            )

            current = int(row["current_streak"])
            longest = int(row["longest_streak"])
            tokens = int(row["freeze_tokens"])
            last_active = row["last_active_date"]
            rescue_until = row["rescue_mode_until"]
            total_active = int(row["total_active_days"])
            pending_notice = bool(row["pending_freeze_notice"])
            freeze_consumed = False
            rescue_started = False
            outcome: Outcome = "neutral"

            if any_completed:
                outcome = "active"
                current += 1
                total_active += 1
                last_active = day
                if current > longest:
                    longest = current
            elif incomplete_quiz:
                outcome = "missed"
                if tokens > 0:
                    tokens -= 1
                    freeze_consumed = True
                    pending_notice = True
                else:
                    current = 0
                consecutive = _consecutive_missed_ending_at(conn, user_id, day)
                if consecutive >= RESCUE_MISS_THRESHOLD:
                    # Fixed 7-day window from entry; do not extend while still in rescue.
                    if rescue_until is None or day > rescue_until:
                        rescue_until = day + timedelta(days=RESCUE_DURATION_DAYS)
                        rescue_started = True
            # else: Neutral (no session, or incomplete free_practice / voice)

            conn.execute(
                """
                UPDATE streaks
                   SET current_streak = %s,
                       longest_streak = %s,
                       freeze_tokens = %s,
                       last_active_date = %s,
                       last_evaluated_date = %s,
                       rescue_mode_until = %s,
                       total_active_days = %s,
                       pending_freeze_notice = %s
                 WHERE user_id = %s
                """,
                (
                    current,
                    longest,
                    tokens,
                    last_active,
                    day,
                    rescue_until,
                    total_active,
                    pending_notice,
                    user_id,
                ),
            )

            return StreakResult(
                user_id=user_id,
                day=day,
                outcome=outcome,
                current_streak=current,
                longest_streak=longest,
                freeze_tokens=tokens,
                freeze_consumed=freeze_consumed,
                rescue_started=rescue_started,
                rescue_mode_until=rescue_until,
                last_active_date=last_active,
                total_active_days=total_active,
            )


def evaluate_pending(
    user_id: int,
    *,
    timezone: str,
    now: datetime,
) -> list[StreakResult]:
    """Evaluate all closed days not yet processed, in chronological order."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    closed = closed_through_date(timezone, now)
    streak = get_streak(user_id)
    last_eval = streak.last_evaluated_date

    if last_eval is not None and last_eval >= closed:
        return []

    earliest_allowed = closed - timedelta(days=BACKFILL_MAX_DAYS - 1)
    if last_eval is None or last_eval < earliest_allowed - timedelta(days=1):
        # Cap: jump last_evaluated to just before the window, then evaluate.
        if last_eval is None or last_eval < earliest_allowed - timedelta(days=1):
            logger.warning(
                "streak backfill capped user_id=%s last_evaluated=%s "
                "closed_through=%s window_start=%s",
                user_id,
                last_eval,
                closed,
                earliest_allowed,
            )
            _set_last_evaluated(user_id, earliest_allowed - timedelta(days=1))
            last_eval = earliest_allowed - timedelta(days=1)

    start = last_eval + timedelta(days=1)
    results: list[StreakResult] = []
    day = start
    while day <= closed:
        results.append(roll_over_day(user_id, day))
        day += timedelta(days=1)
    return results


def reset_monthly_freezes(*, now: datetime) -> int:
    """Set freeze_tokens=2 for users whose local date is the 1st (idempotent)."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    with connection() as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.timezone, s.freeze_reset_on
              FROM users u
              JOIN streaks s ON s.user_id = u.id
             WHERE u.onboarded = TRUE
            """
        ).fetchall()

    updated = 0
    for row in rows:
        user_id = int(row["id"])
        tz = str(row["timezone"] or "Europe/Vilnius")
        local_day = local_today(tz, now)
        if local_day.day != 1:
            continue
        if row["freeze_reset_on"] is not None and row["freeze_reset_on"] == local_day:
            continue
        with connection() as conn:
            result = conn.execute(
                """
                UPDATE streaks
                   SET freeze_tokens = %s,
                       freeze_reset_on = %s
                 WHERE user_id = %s
                   AND (freeze_reset_on IS DISTINCT FROM %s)
                """,
                (DEFAULT_FREEZE_TOKENS, local_day, user_id, local_day),
            )
            if result.rowcount:
                updated += 1
    return updated


def list_onboarded_streak_users() -> list[tuple[int, str]]:
    """Return (user_id, timezone); oldest last_evaluated first so backfills run."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.timezone
              FROM users u
              JOIN streaks s ON s.user_id = u.id
             WHERE u.onboarded = TRUE
             ORDER BY s.last_evaluated_date NULLS FIRST,
                      u.id
            """
        ).fetchall()
    return [
        (int(r["id"]), str(r["timezone"] or "Europe/Vilnius"))
        for r in rows
    ]


def _set_last_evaluated(user_id: int, day: date) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE streaks
               SET last_evaluated_date = %s
             WHERE user_id = %s
            """,
            (day, user_id),
        )


def _day_is_missed(conn, user_id: int, day: date) -> bool:
    """True when the day is Missed under Active > Missed > Neutral precedence."""
    day_rows = conn.execute(
        """
        SELECT task_type, completed
          FROM sessions
         WHERE user_id = %s AND date = %s
        """,
        (user_id, day),
    ).fetchall()
    if any(bool(r["completed"]) for r in day_rows):
        return False
    return any(
        (not bool(r["completed"])) and str(r["task_type"]) == "quiz"
        for r in day_rows
    )


def _consecutive_missed_ending_at(conn, user_id: int, day: date) -> int:
    """Count consecutive Missed days ending at day (inclusive)."""
    count = 0
    cursor = day
    while _day_is_missed(conn, user_id, cursor):
        count += 1
        cursor -= timedelta(days=1)
    return count


def _row_to_streak(row) -> Streak:
    return Streak(
        user_id=int(row["user_id"]),
        current_streak=int(row["current_streak"]),
        longest_streak=int(row["longest_streak"]),
        freeze_tokens=int(row["freeze_tokens"]),
        last_active_date=row["last_active_date"],
        last_evaluated_date=row["last_evaluated_date"],
        rescue_mode_until=row["rescue_mode_until"],
        total_active_days=int(row["total_active_days"]),
        freeze_reset_on=row["freeze_reset_on"],
        pending_freeze_notice=bool(row["pending_freeze_notice"]),
    )
