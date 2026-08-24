"""Scheduling predicates — who is due for what, and when.

Lifted unchanged from ``apps/bot/scheduler.py`` at W1. Channel-neutral by
construction: these answer eligibility questions from the database and the
clock and never send anything. The APScheduler wiring and the job bodies
stay with the bot until W1b hands them to the worker.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from core.db import connection
from core.services.errors import run_monthly_fossil_sweep
from core.services.sessions import (
    has_anki_session_on,
    has_diary_session_on,
    has_reading_session_on,
    has_session_on,
    local_time_hhmm,
    local_today,
    under_message_ceiling,
)
from core.services.streaks import (
    USERS_PER_POLL_TICK,
    evaluate_pending,
    list_onboarded_streak_users,
    reset_monthly_freezes,
)

logger = logging.getLogger(__name__)

# Monday=0, Wednesday=2, Friday=4 in the user's local timezone.
READING_WEEKDAYS = frozenset({0, 2, 4})
# Tuesday=1, Thursday=3 — remaining evenings without reading/Anki/report (S13).
DIARY_WEEKDAYS = frozenset({1, 3})
# Saturday=5 — moved off Sunday so weekly test + report fit under the ceiling (S11).
ANKI_WEEKDAY = 5


@dataclass(frozen=True)
class EligibleUser:
    """A learner the scheduler may act on.

    ``id`` is who they are; ``telegram_address`` is where a Telegram message
    goes, and is ``None`` for a web-only learner who has no Telegram account at
    all. Kept as two fields since W4b precisely so a caller cannot use one as the
    other -- which is what ``chat_id=user_id`` did throughout the bot.

    A ``None`` address means this bot cannot reach them; delivery skips them.
    See known issue #95 -- that skip is silent by construction and W20 must make
    it loud once the web has a channel of its own.
    """

    id: int
    telegram_address: int | None
    timezone: str
    morning_time: time
    paused_until: date | None
    evening_time: time = time(21, 0)


def _time_reached(local_hhmm: tuple[int, int], slot: time) -> bool:
    """True when local hour:minute is at or past slot (minute precision)."""
    hour, minute = local_hhmm
    return (hour, minute) >= (slot.hour, slot.minute)


def list_candidate_users() -> list[EligibleUser]:
    """Approved onboarded users (pause filtered per local date in eligibility)."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, telegram_user_id, timezone, morning_time, evening_time,
                   paused_until
              FROM approved_onboarded_users
            """
        ).fetchall()
    return [
        EligibleUser(
            id=int(row["id"]),
            telegram_address=(
                None
                if row["telegram_user_id"] is None
                else int(row["telegram_user_id"])
            ),
            timezone=str(row["timezone"] or "Europe/Vilnius"),
            morning_time=row["morning_time"],
            paused_until=row["paused_until"],
            evening_time=row["evening_time"] or time(21, 0),
        )
        for row in rows
    ]


def is_user_due_for_morning(user: EligibleUser, now: datetime) -> bool:
    """Whether this user should receive a morning delivery at ``now``."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    day = local_today(user.timezone, now)
    if user.paused_until is not None and user.paused_until >= day:
        return False
    if not _time_reached(local_time_hhmm(user.timezone, now), user.morning_time):
        return False
    if has_session_on(user.id, day):
        return False
    if not under_message_ceiling(user.id, day):
        return False
    return True


def is_user_due_for_evening(user: EligibleUser, now: datetime) -> bool:
    """Whether this user should receive a reading delivery at ``now``."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    day = local_today(user.timezone, now)
    local_dt = now.astimezone(ZoneInfo(user.timezone))
    if local_dt.weekday() not in READING_WEEKDAYS:
        return False
    if user.paused_until is not None and user.paused_until >= day:
        return False
    if not _time_reached(local_time_hhmm(user.timezone, now), user.evening_time):
        return False
    if has_reading_session_on(user.id, day):
        return False
    if not under_message_ceiling(user.id, day):
        return False
    return True


def is_user_due_for_diary(user: EligibleUser, now: datetime) -> bool:
    """Whether this user should receive a diary prompt at ``now`` (Tue/Thu)."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    day = local_today(user.timezone, now)
    local_dt = now.astimezone(ZoneInfo(user.timezone))
    if local_dt.weekday() not in DIARY_WEEKDAYS:
        return False
    if user.paused_until is not None and user.paused_until >= day:
        return False
    if not _time_reached(local_time_hhmm(user.timezone, now), user.evening_time):
        return False
    if has_diary_session_on(user.id, day):
        return False
    if not under_message_ceiling(user.id, day):
        return False
    return True


def is_user_due_for_anki(user: EligibleUser, now: datetime) -> bool:
    """Whether this user should receive a Saturday Anki export at ``now``."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    day = local_today(user.timezone, now)
    local_dt = now.astimezone(ZoneInfo(user.timezone))
    if local_dt.weekday() != ANKI_WEEKDAY:
        return False
    if user.paused_until is not None and user.paused_until >= day:
        return False
    if not _time_reached(local_time_hhmm(user.timezone, now), user.evening_time):
        return False
    if has_anki_session_on(user.id, day):
        return False
    if not under_message_ceiling(user.id, day):
        return False
    return True


def run_streak_rollover(
    now: datetime | None = None,
    *,
    max_users: int = USERS_PER_POLL_TICK,
) -> list[tuple[int, int]]:
    """Evaluate pending streak days. Returns (user_id, days_evaluated) list."""
    instant = now or datetime.now(timezone.utc)
    users = list_onboarded_streak_users()[:max_users]
    logger.info("Streak rollover poll: %s user(s)", len(users))
    results: list[tuple[int, int]] = []
    for user_id, tz in users:
        try:
            outcomes = evaluate_pending(user_id, timezone=tz, now=instant)
            results.append((user_id, len(outcomes)))
            if outcomes:
                logger.info(
                    "Streak rollover user_id=%s days=%s",
                    user_id,
                    len(outcomes),
                )
        except Exception:
            logger.exception("Streak rollover failed user_id=%s", user_id)
    return results


def run_monthly_freeze_reset(now: datetime | None = None) -> int:
    """Reset freeze tokens for users whose local date is the 1st."""
    instant = now or datetime.now(timezone.utc)
    updated = reset_monthly_freezes(now=instant)
    if updated:
        logger.info("Monthly freeze reset: %s user(s)", updated)
    return updated


def run_monthly_reset(now: datetime | None = None) -> tuple[int, int]:
    """Freeze token reset + M13 fossil sweep (ARCHITECTURE monthly_reset)."""
    instant = now or datetime.now(timezone.utc)
    freezes = run_monthly_freeze_reset(now=instant)
    sweeps = run_monthly_fossil_sweep(now=instant)
    if sweeps:
        logger.info("Monthly fossil sweep: %s user(s)", sweeps)
    return freezes, sweeps
