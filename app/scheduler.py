"""In-process scheduled jobs via PTB JobQueue (APScheduler) — S3 morning poll."""

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

if TYPE_CHECKING:
    from telegram.ext import Application, ContextTypes

logger = logging.getLogger(__name__)

POLL_SECONDS = 5 * 60
_JOB_NAME = "morning_poll"


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


async def _job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_morning_poll(context.application)


def start_scheduler(application: Application) -> None:
    """Register the 5-minute morning poll on the PTB JobQueue (APScheduler)."""
    jq = application.job_queue
    if jq is None:
        raise RuntimeError(
            "JobQueue unavailable — install apscheduler "
            "(see requirements.txt)"
        )
    # Replace any prior registration (e.g. reload).
    for job in jq.jobs():
        if job.name == _JOB_NAME:
            job.schedule_removal()
    jq.run_repeating(
        _job,
        interval=POLL_SECONDS,
        first=10,
        name=_JOB_NAME,
    )
    logger.info("Scheduler started (morning poll every %ss)", POLL_SECONDS)


def stop_scheduler(application: Application | None = None) -> None:
    """Remove the morning poll job if present."""
    if application is None or application.job_queue is None:
        return
    for job in application.job_queue.jobs():
        if job.name == _JOB_NAME:
            job.schedule_removal()
    logger.info("Scheduler stopped")
