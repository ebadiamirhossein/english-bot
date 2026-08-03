"""In-process scheduled jobs via PTB JobQueue (APScheduler).

S3: morning poll. S4: streak rollover + monthly freeze reset.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING

from app.db import connection
from app.handlers import quiz as quiz_handler
from app.services.sessions import (
    has_session_on,
    local_time_hhmm,
    local_today,
    under_message_ceiling,
)
from app.services.streaks import (
    USERS_PER_POLL_TICK,
    evaluate_pending,
    list_onboarded_streak_users,
    reset_monthly_freezes,
)

if TYPE_CHECKING:
    from telegram.ext import Application, ContextTypes

logger = logging.getLogger(__name__)

POLL_SECONDS = 5 * 60
STREAK_POLL_SECONDS = 15 * 60
_MORNING_JOB = "morning_poll"
_STREAK_JOB = "streak_rollover"
_FREEZE_JOB = "monthly_freeze_reset"


@dataclass(frozen=True)
class EligibleUser:
    telegram_user_id: int
    timezone: str
    morning_time: time
    paused_until: date | None


def _time_reached(local_hhmm: tuple[int, int], morning: time) -> bool:
    """True when local hour:minute is at or past morning_time (minute precision)."""
    hour, minute = local_hhmm
    return (hour, minute) >= (morning.hour, morning.minute)


def list_candidate_users() -> list[EligibleUser]:
    """All onboarded users (pause filtered per local date in eligibility)."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT telegram_user_id, timezone, morning_time, paused_until
              FROM users
             WHERE onboarded = TRUE
            """
        ).fetchall()
    return [
        EligibleUser(
            telegram_user_id=int(row["telegram_user_id"]),
            timezone=str(row["timezone"] or "Europe/Vilnius"),
            morning_time=row["morning_time"],
            paused_until=row["paused_until"],
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
    if has_session_on(user.telegram_user_id, day):
        return False
    if not under_message_ceiling(user.telegram_user_id, day):
        return False
    return True


def users_due_for_morning(now: datetime) -> list[EligibleUser]:
    """Users whose local morning slot is due and who have no session today."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return [u for u in list_candidate_users() if is_user_due_for_morning(u, now)]


async def run_morning_poll(
    application: Application,
    now: datetime | None = None,
) -> list[tuple[int, str]]:
    """Run one poll. Returns list of (user_id, action) for tests."""
    instant = now or datetime.now(timezone.utc)
    due = users_due_for_morning(instant)
    logger.info("Morning poll: %s user(s) due", len(due))
    results: list[tuple[int, str]] = []
    for user in due:
        try:
            action = await quiz_handler.deliver_morning(
                application,
                user.telegram_user_id,
                now=instant,
            )
            results.append((user.telegram_user_id, action))
            logger.info(
                "Morning delivery user_id=%s action=%s",
                user.telegram_user_id,
                action,
            )
        except Exception:
            logger.exception(
                "Morning delivery failed user_id=%s",
                user.telegram_user_id,
            )
            results.append((user.telegram_user_id, "error"))
    return results


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


async def _morning_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_morning_poll(context.application)


async def _streak_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    run_streak_rollover()


async def _freeze_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    run_monthly_freeze_reset()


def start_scheduler(application: Application) -> None:
    """Register morning, streak, and freeze jobs on the PTB JobQueue."""
    jq = application.job_queue
    if jq is None:
        raise RuntimeError(
            "JobQueue unavailable — install apscheduler "
            "(see requirements.txt)"
        )
    known = {_MORNING_JOB, _STREAK_JOB, _FREEZE_JOB}
    for job in jq.jobs():
        if job.name in known:
            job.schedule_removal()

    jq.run_repeating(
        _morning_job,
        interval=POLL_SECONDS,
        first=10,
        name=_MORNING_JOB,
    )
    jq.run_repeating(
        _streak_job,
        interval=STREAK_POLL_SECONDS,
        first=20,
        name=_STREAK_JOB,
    )
    jq.run_repeating(
        _freeze_job,
        interval=STREAK_POLL_SECONDS,
        first=30,
        name=_FREEZE_JOB,
    )
    logger.info(
        "Scheduler started jobs=%s,%s,%s "
        "(morning every %ss; streak/freeze every %ss)",
        _MORNING_JOB,
        _STREAK_JOB,
        _FREEZE_JOB,
        POLL_SECONDS,
        STREAK_POLL_SECONDS,
    )


def stop_scheduler(application: Application | None = None) -> None:
    """Remove scheduler jobs if present."""
    if application is None or application.job_queue is None:
        return
    known = {_MORNING_JOB, _STREAK_JOB, _FREEZE_JOB}
    for job in application.job_queue.jobs():
        if job.name in known:
            job.schedule_removal()
    logger.info("Scheduler stopped")
