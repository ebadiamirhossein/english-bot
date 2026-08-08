"""In-process scheduled jobs via PTB JobQueue (APScheduler).

S3: morning poll. S4: streak rollover + monthly freeze reset.
S9a: evening reading poll (Mon/Wed/Fri).
S7: Sunday Anki export poll (at evening_time or later).
S10: nudge ladder + Sunday report (report before Anki for ceiling priority).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.db import connection
from app.handlers import quiz as quiz_handler
from app.handlers import reading as reading_handler
from app.services import anki as anki_service
from app.services import motivation as motivation_service
from app.services.sessions import (
    has_anki_session_on,
    has_reading_session_on,
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
# Offset evening from morning within the same interval so a slow morning
# LLM cannot land in APScheduler's misfire window for the evening tick.
EVENING_FIRST_SECONDS = POLL_SECONDS // 2
# Sunday report before Anki so report wins the last ceiling slot (S10).
SUNDAY_REPORT_FIRST_SECONDS = EVENING_FIRST_SECONDS + 15
ANKI_FIRST_SECONDS = EVENING_FIRST_SECONDS + 30
NUDGE_FIRST_SECONDS = EVENING_FIRST_SECONDS + 45
# Monday=0, Wednesday=2, Friday=4 in the user's local timezone.
READING_WEEKDAYS = frozenset({0, 2, 4})
# Sunday=6
ANKI_WEEKDAY = 6
_MORNING_JOB = "morning_poll"
_EVENING_JOB = "evening_poll"
_SUNDAY_REPORT_JOB = "sunday_report_poll"
_ANKI_JOB = "anki_poll"
_NUDGE_JOB = "nudge_poll"
_STREAK_JOB = "streak_rollover"
_FREEZE_JOB = "monthly_freeze_reset"


@dataclass(frozen=True)
class EligibleUser:
    telegram_user_id: int
    timezone: str
    morning_time: time
    paused_until: date | None
    evening_time: time = time(21, 0)


def _time_reached(local_hhmm: tuple[int, int], slot: time) -> bool:
    """True when local hour:minute is at or past slot (minute precision)."""
    hour, minute = local_hhmm
    return (hour, minute) >= (slot.hour, slot.minute)


def list_candidate_users() -> list[EligibleUser]:
    """All onboarded users (pause filtered per local date in eligibility)."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT telegram_user_id, timezone, morning_time, evening_time,
                   paused_until
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
    if has_session_on(user.telegram_user_id, day):
        return False
    if not under_message_ceiling(user.telegram_user_id, day):
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
    if has_reading_session_on(user.telegram_user_id, day):
        return False
    if not under_message_ceiling(user.telegram_user_id, day):
        return False
    return True


def is_user_due_for_anki(user: EligibleUser, now: datetime) -> bool:
    """Whether this user should receive a Sunday Anki export at ``now``."""
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
    if has_anki_session_on(user.telegram_user_id, day):
        return False
    if not under_message_ceiling(user.telegram_user_id, day):
        return False
    return True


def users_due_for_morning(now: datetime) -> list[EligibleUser]:
    """Users whose local morning slot is due and who have no session today."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return [u for u in list_candidate_users() if is_user_due_for_morning(u, now)]


def users_due_for_evening(now: datetime) -> list[EligibleUser]:
    """Users whose local evening reading slot is due."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return [u for u in list_candidate_users() if is_user_due_for_evening(u, now)]


def users_due_for_anki(now: datetime) -> list[EligibleUser]:
    """Users whose local Sunday Anki slot is due."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return [u for u in list_candidate_users() if is_user_due_for_anki(u, now)]


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


async def run_evening_poll(
    application: Application,
    now: datetime | None = None,
) -> list[tuple[int, str]]:
    """Run one evening reading poll. Returns list of (user_id, action)."""
    instant = now or datetime.now(timezone.utc)
    due = users_due_for_evening(instant)
    logger.info("Evening poll: %s user(s) due", len(due))
    results: list[tuple[int, str]] = []
    for user in due:
        try:
            action = await reading_handler.deliver_evening(
                application,
                user.telegram_user_id,
                now=instant,
            )
            results.append((user.telegram_user_id, action))
            logger.info(
                "Evening delivery user_id=%s action=%s",
                user.telegram_user_id,
                action,
            )
        except Exception:
            logger.exception(
                "Evening delivery failed user_id=%s",
                user.telegram_user_id,
            )
            results.append((user.telegram_user_id, "error"))
    return results


async def run_anki_poll(
    application: Application,
    now: datetime | None = None,
) -> list[tuple[int, str]]:
    """Run one Sunday Anki export poll. Returns list of (user_id, action)."""
    instant = now or datetime.now(timezone.utc)
    due = users_due_for_anki(instant)
    logger.info("Anki poll: %s user(s) due", len(due))
    results: list[tuple[int, str]] = []
    for user in due:
        try:
            action = await anki_service.deliver_weekly(
                application,
                user.telegram_user_id,
                now=instant,
            )
            results.append((user.telegram_user_id, action))
            logger.info(
                "Anki delivery user_id=%s action=%s",
                user.telegram_user_id,
                action,
            )
        except Exception:
            logger.exception(
                "Anki delivery failed user_id=%s",
                user.telegram_user_id,
            )
            results.append((user.telegram_user_id, "error"))
    return results


async def run_sunday_report_poll(
    application: Application,
    now: datetime | None = None,
) -> list[tuple[int, str]]:
    """Run one Sunday progress-report poll. Returns (user_id, action)."""
    instant = now or datetime.now(timezone.utc)
    results = await motivation_service.run_sunday_report_pass(
        application, now=instant
    )
    logger.info("Sunday report poll: %s result(s)", len(results))
    return results


async def run_nudge_poll(
    application: Application,
    now: datetime | None = None,
) -> list[tuple[int, list[str]]]:
    """Run one nudge-ladder poll. Returns (user_id, actions)."""
    instant = now or datetime.now(timezone.utc)
    results = await motivation_service.run_nudge_pass(application, now=instant)
    logger.info("Nudge poll: %s user(s) with actions", len(results))
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


async def _evening_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_evening_poll(context.application)


async def _anki_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_anki_poll(context.application)


async def _sunday_report_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_sunday_report_poll(context.application)


async def _nudge_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_nudge_poll(context.application)


async def _streak_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    run_streak_rollover()


async def _freeze_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    run_monthly_freeze_reset()


def start_scheduler(application: Application) -> None:
    """Register morning, evening, sunday report, anki, nudge, streak, freeze."""
    jq = application.job_queue
    if jq is None:
        raise RuntimeError(
            "JobQueue unavailable — install apscheduler "
            "(see requirements.txt)"
        )
    known = {
        _MORNING_JOB,
        _EVENING_JOB,
        _SUNDAY_REPORT_JOB,
        _ANKI_JOB,
        _NUDGE_JOB,
        _STREAK_JOB,
        _FREEZE_JOB,
    }
    for job in jq.jobs():
        if job.name in known:
            job.schedule_removal()

    jq.run_repeating(
        _morning_job,
        interval=POLL_SECONDS,
        first=10,
        name=_MORNING_JOB,
    )
    # Mid-interval offset so morning and evening never share a 5s window.
    # (LLM also runs via asyncio.to_thread; this is belt-and-suspenders.)
    jq.run_repeating(
        _evening_job,
        interval=POLL_SECONDS,
        first=EVENING_FIRST_SECONDS,
        name=_EVENING_JOB,
    )
    jq.run_repeating(
        _sunday_report_job,
        interval=POLL_SECONDS,
        first=SUNDAY_REPORT_FIRST_SECONDS,
        name=_SUNDAY_REPORT_JOB,
    )
    jq.run_repeating(
        _anki_job,
        interval=POLL_SECONDS,
        first=ANKI_FIRST_SECONDS,
        name=_ANKI_JOB,
    )
    jq.run_repeating(
        _nudge_job,
        interval=POLL_SECONDS,
        first=NUDGE_FIRST_SECONDS,
        name=_NUDGE_JOB,
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
        "Scheduler started jobs=%s,%s,%s,%s,%s,%s,%s "
        "(poll every %ss; evening first=%ss; sunday_report first=%ss; "
        "anki first=%ss; nudge first=%ss; streak/freeze every %ss)",
        _MORNING_JOB,
        _EVENING_JOB,
        _SUNDAY_REPORT_JOB,
        _ANKI_JOB,
        _NUDGE_JOB,
        _STREAK_JOB,
        _FREEZE_JOB,
        POLL_SECONDS,
        EVENING_FIRST_SECONDS,
        SUNDAY_REPORT_FIRST_SECONDS,
        ANKI_FIRST_SECONDS,
        NUDGE_FIRST_SECONDS,
        STREAK_POLL_SECONDS,
    )


def stop_scheduler(application: Application | None = None) -> None:
    """Remove scheduler jobs if present."""
    if application is None or application.job_queue is None:
        return
    known = {
        _MORNING_JOB,
        _EVENING_JOB,
        _SUNDAY_REPORT_JOB,
        _ANKI_JOB,
        _NUDGE_JOB,
        _STREAK_JOB,
        _FREEZE_JOB,
    }
    for job in application.job_queue.jobs():
        if job.name in known:
            job.schedule_removal()
    logger.info("Scheduler stopped")
