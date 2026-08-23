"""In-process scheduled jobs via PTB JobQueue (APScheduler).

S3: morning poll. S4: streak rollover + monthly freeze reset.
S9a: evening reading poll (Mon/Wed/Fri).
S13: evening diary poll (Tue/Thu).
S7: Sunday Anki export poll (at evening_time or later).
S10: nudge ladder + Sunday report (report before Anki for ceiling priority).
S12: M13 fossil sweep on the monthly freeze poll (per-user local 1st).
S18: heartbeat. S4c: off-site backup freshness.
S15a: watched-folder CSV import.
S8: couple challenge poll (18:00 Vilnius; chat-level).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from apps.bot import texts
from core.config import load_settings
from core.db import connection
from apps.bot.handlers import couple as couple_handler
from apps.bot.handlers import diary as diary_handler
from apps.bot.handlers import quiz as quiz_handler
from apps.bot.handlers import reading as reading_handler
from core.services import anki as anki_service
from core.services import motivation as motivation_service
from core.services.alerts import notify_operator
from core.services import backup_freshness as backup_freshness_service
from core.services.errors import run_monthly_fossil_sweep
from core.services import heartbeat as heartbeat_service
from core.services.sessions import (
    has_anki_session_on,
    has_diary_session_on,
    has_reading_session_on,
    has_session_on,
    increment_bot_messages,
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
from core.services.watch_import import (
    WatchConfigError,
    collect_root_orphans,
    ensure_all_user_layouts,
    list_registered_user_ids,
    resolve_watch_root,
    scan_user_inbox,
    warn_root_orphans,
    watch_dir_configured,
)

if TYPE_CHECKING:
    from telegram.ext import Application, ContextTypes

logger = logging.getLogger(__name__)

POLL_SECONDS = 5 * 60
STREAK_POLL_SECONDS = 15 * 60
HEARTBEAT_POLL_SECONDS = 60 * 60
HEARTBEAT_FIRST_SECONDS = 60
BACKUP_FRESHNESS_FIRST_SECONDS = 90
WATCH_FIRST_SECONDS = 120
# Offset evening from morning within the same interval so a slow morning
# LLM cannot land in APScheduler's misfire window for the evening tick.
EVENING_FIRST_SECONDS = POLL_SECONDS // 2
# Diary between reading and Sunday report; weekdays never overlap reading.
DIARY_FIRST_SECONDS = EVENING_FIRST_SECONDS + 10
# Sunday report offset; Anki is Saturday (S11) so they no longer compete.
SUNDAY_REPORT_FIRST_SECONDS = EVENING_FIRST_SECONDS + 15
ANKI_FIRST_SECONDS = EVENING_FIRST_SECONDS + 30
NUDGE_FIRST_SECONDS = EVENING_FIRST_SECONDS + 45
COUPLE_FIRST_SECONDS = EVENING_FIRST_SECONDS + 55
# Monday=0, Wednesday=2, Friday=4 in the user's local timezone.
READING_WEEKDAYS = frozenset({0, 2, 4})
# Tuesday=1, Thursday=3 — remaining evenings without reading/Anki/report (S13).
DIARY_WEEKDAYS = frozenset({1, 3})
# Saturday=5 — moved off Sunday so weekly test + report fit under the ceiling (S11).
ANKI_WEEKDAY = 5
_MORNING_JOB = "morning_poll"
_EVENING_JOB = "evening_poll"
_DIARY_JOB = "diary_poll"
_SUNDAY_REPORT_JOB = "sunday_report_poll"
_ANKI_JOB = "anki_poll"
_NUDGE_JOB = "nudge_poll"
_COUPLE_JOB = "couple_poll"
_STREAK_JOB = "streak_rollover"
_FREEZE_JOB = "monthly_freeze_reset"
_HEARTBEAT_JOB = "heartbeat"
_BACKUP_FRESHNESS_JOB = "backup_freshness"
_WATCH_JOB = "watch_poll"


def _touch_job_fire_success() -> None:
    """Record successful completion of a delivery/maintenance job."""
    settings = load_settings()
    heartbeat_service.touch_job_fire(
        settings.heartbeat_file, now=datetime.now(timezone.utc)
    )


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
    """Approved onboarded users (pause filtered per local date in eligibility)."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT telegram_user_id, timezone, morning_time, evening_time,
                   paused_until
              FROM approved_onboarded_users
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
    if has_diary_session_on(user.telegram_user_id, day):
        return False
    if not under_message_ceiling(user.telegram_user_id, day):
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


def users_due_for_diary(now: datetime) -> list[EligibleUser]:
    """Users whose local evening diary slot is due."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return [u for u in list_candidate_users() if is_user_due_for_diary(u, now)]


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


async def run_diary_poll(
    application: Application,
    now: datetime | None = None,
) -> list[tuple[int, str]]:
    """Run one evening diary poll. Returns list of (user_id, action)."""
    instant = now or datetime.now(timezone.utc)
    due = users_due_for_diary(instant)
    logger.info("Diary poll: %s user(s) due", len(due))
    results: list[tuple[int, str]] = []
    for user in due:
        try:
            action = await diary_handler.deliver_diary(
                application,
                user.telegram_user_id,
                now=instant,
            )
            results.append((user.telegram_user_id, action))
            logger.info(
                "Diary delivery user_id=%s action=%s",
                user.telegram_user_id,
                action,
            )
        except Exception:
            logger.exception(
                "Diary delivery failed user_id=%s",
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


async def run_couple_poll(
    application: Application,
    now: datetime | None = None,
) -> list[str]:
    """Run one couple-challenge poll (chat-level). Returns action tags."""
    instant = now or datetime.now(timezone.utc)
    actions = await couple_handler.run_couple_poll(application, now=instant)
    logger.info("Couple poll: actions=%s", actions)
    return actions


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


async def _morning_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_morning_poll(context.application)
    _touch_job_fire_success()


async def _evening_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_evening_poll(context.application)
    _touch_job_fire_success()


async def _diary_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_diary_poll(context.application)
    _touch_job_fire_success()


async def _anki_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_anki_poll(context.application)
    _touch_job_fire_success()


async def _sunday_report_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_sunday_report_poll(context.application)
    _touch_job_fire_success()


async def _nudge_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_nudge_poll(context.application)
    _touch_job_fire_success()


async def _couple_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_couple_poll(context.application)
    _touch_job_fire_success()


async def _streak_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    run_streak_rollover()
    _touch_job_fire_success()


async def _freeze_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    run_monthly_reset()
    _touch_job_fire_success()


async def run_heartbeat_check(
    application: Application,
    *,
    now: datetime | None = None,
) -> str:
    """Check last successful job fire; alert operator if stale. Does not touch."""
    instant = now or datetime.now(timezone.utc)
    settings = load_settings()
    status = heartbeat_service.check_heartbeat(
        settings.heartbeat_file, now=instant
    )
    if status == "stale":
        last = heartbeat_service.read_last_fire(settings.heartbeat_file)
        last_s = last.isoformat() if last is not None else "never"
        await notify_operator(
            application,
            key="heartbeat",
            text=(
                f"Heartbeat STALE: no successful scheduled job in "
                f"{heartbeat_service.MAX_AGE_HOURS}h (last_fire={last_s})"
            ),
            now=instant,
        )
        logger.error("Heartbeat stale last_fire=%s", last_s)
    return status


async def _heartbeat_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_heartbeat_check(context.application)


async def run_backup_freshness_check(
    application: Application,
    *,
    now: datetime | None = None,
) -> str:
    """Check newest off-site dump age; alert if stale. Does not touch heartbeat."""
    instant = now or datetime.now(timezone.utc)
    settings = load_settings()
    directory = settings.backup_offsite_dir
    status = backup_freshness_service.check_offsite_freshness(
        directory,
        now=instant,
        max_age_hours=settings.backup_offsite_max_age_hours,
    )
    if status == "skipped":
        return status
    if status == "stale":
        newest = None
        if directory:
            newest = backup_freshness_service.newest_offsite(
                Path(directory)
            )
        if newest is None:
            detail = "missing_or_empty"
        else:
            age_h = (instant - newest.mtime).total_seconds() / 3600.0
            size_s = (
                f" size={newest.size}" if newest.size is not None else ""
            )
            detail = (
                f"newest={newest.name} mtime={newest.mtime.isoformat()}"
                f"{size_s} age_h={age_h:.1f}"
            )
        await notify_operator(
            application,
            key="backup_offsite",
            text=(
                f"Off-site backup STALE: dir={directory} "
                f"threshold_h={settings.backup_offsite_max_age_hours} "
                f"({detail})"
            ),
            now=instant,
        )
        logger.error("Off-site backup stale dir=%s %s", directory, detail)
    return status


async def _backup_freshness_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_backup_freshness_check(context.application)


async def run_watch_poll(
    application: Application,
    *,
    now: datetime | None = None,
) -> str:
    """Scan WATCH_DIR inboxes for all registered users. Silent if unset."""
    if not watch_dir_configured():
        return "skipped_unset"
    instant = now or datetime.now(timezone.utc)
    try:
        root = resolve_watch_root()
    except WatchConfigError as exc:
        logger.error("WATCH_DIR unusable: %s", exc)
        await notify_operator(
            application,
            key="watch_dir",
            text=f"WATCH_DIR unusable: {exc}",
            now=instant,
        )
        return "error_config"

    ensure_all_user_layouts(root)
    orphans = collect_root_orphans(root)
    newly = warn_root_orphans(orphans)
    if newly:
        await notify_operator(
            application,
            key="watch_orphan",
            text=(
                "Subtitle CSV in inbox/ root (not attributed). "
                f"Move into inbox/<telegram_user_id>/: {', '.join(newly)}"
            ),
            now=instant,
        )

    bot = application.bot
    for user_id in list_registered_user_ids():
        result = scan_user_inbox(root, user_id, now=instant)
        for f in result.files:
            if f.status == "failed_headers":
                await notify_operator(
                    application,
                    key=f"watch_headers:{user_id}:{f.filename}",
                    text=(
                        f"watch import failed_headers user_id={user_id} "
                        f"file={f.filename} headers={list(f.headers_seen)}"
                    ),
                    now=instant,
                )
        imported_files = [f for f in result.files if f.status == "imported"]
        if not imported_files:
            continue
        with connection() as conn:
            row = conn.execute(
                "SELECT timezone FROM users WHERE telegram_user_id = %s",
                (user_id,),
            ).fetchone()
        tz = (
            str(row["timezone"])
            if row is not None and row["timezone"]
            else "Europe/Vilnius"
        )
        day = local_today(tz, instant)
        if not under_message_ceiling(user_id, day):
            logger.info(
                "watch import notify skipped user_id=%s reason=ceiling",
                user_id,
            )
            continue
        due = imported_files[-1].due_after if imported_files else 0
        try:
            await bot.send_message(
                chat_id=user_id,
                text=texts.IMPORT_POLL_RESULT.format(
                    imported=result.total_imported,
                    duplicates=result.total_duplicates,
                    invalid=result.total_invalid,
                    due=due if due is not None else 0,
                ),
            )
            increment_bot_messages(user_id, day)
        except Exception:
            logger.exception(
                "watch import notify failed user_id=%s", user_id
            )
    return "ok"


async def _watch_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_watch_poll(context.application)
    _touch_job_fire_success()


def start_scheduler(application: Application) -> None:
    """Register morning, evening, sunday report, anki, nudge, couple, streak, freeze, heartbeat, backup_freshness, watch."""
    jq = application.job_queue
    if jq is None:
        raise RuntimeError(
            "JobQueue unavailable — install apscheduler "
            "(see requirements.txt)"
        )
    known = {
        _MORNING_JOB,
        _EVENING_JOB,
        _DIARY_JOB,
        _SUNDAY_REPORT_JOB,
        _ANKI_JOB,
        _NUDGE_JOB,
        _COUPLE_JOB,
        _STREAK_JOB,
        _FREEZE_JOB,
        _HEARTBEAT_JOB,
        _BACKUP_FRESHNESS_JOB,
        _WATCH_JOB,
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
        _diary_job,
        interval=POLL_SECONDS,
        first=DIARY_FIRST_SECONDS,
        name=_DIARY_JOB,
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
        _couple_job,
        interval=POLL_SECONDS,
        first=COUPLE_FIRST_SECONDS,
        name=_COUPLE_JOB,
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
    jq.run_repeating(
        _heartbeat_job,
        interval=HEARTBEAT_POLL_SECONDS,
        first=HEARTBEAT_FIRST_SECONDS,
        name=_HEARTBEAT_JOB,
    )
    jq.run_repeating(
        _backup_freshness_job,
        interval=HEARTBEAT_POLL_SECONDS,
        first=BACKUP_FRESHNESS_FIRST_SECONDS,
        name=_BACKUP_FRESHNESS_JOB,
    )
    jq.run_repeating(
        _watch_job,
        interval=POLL_SECONDS,
        first=WATCH_FIRST_SECONDS,
        name=_WATCH_JOB,
    )
    logger.info(
        "Scheduler started jobs=%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s "
        "(poll every %ss; evening first=%ss; diary first=%ss; "
        "sunday_report first=%ss; anki first=%ss; nudge first=%ss; "
        "couple first=%ss; streak/freeze every %ss; heartbeat every %ss; "
        "backup_freshness first=%ss; watch first=%ss)",
        _MORNING_JOB,
        _EVENING_JOB,
        _DIARY_JOB,
        _SUNDAY_REPORT_JOB,
        _ANKI_JOB,
        _NUDGE_JOB,
        _COUPLE_JOB,
        _STREAK_JOB,
        _FREEZE_JOB,
        _HEARTBEAT_JOB,
        _BACKUP_FRESHNESS_JOB,
        _WATCH_JOB,
        POLL_SECONDS,
        EVENING_FIRST_SECONDS,
        DIARY_FIRST_SECONDS,
        SUNDAY_REPORT_FIRST_SECONDS,
        ANKI_FIRST_SECONDS,
        NUDGE_FIRST_SECONDS,
        COUPLE_FIRST_SECONDS,
        STREAK_POLL_SECONDS,
        HEARTBEAT_POLL_SECONDS,
        BACKUP_FRESHNESS_FIRST_SECONDS,
        WATCH_FIRST_SECONDS,
    )


def stop_scheduler(application: Application | None = None) -> None:
    """Remove scheduler jobs if present."""
    if application is None or application.job_queue is None:
        return
    known = {
        _MORNING_JOB,
        _EVENING_JOB,
        _DIARY_JOB,
        _SUNDAY_REPORT_JOB,
        _ANKI_JOB,
        _NUDGE_JOB,
        _COUPLE_JOB,
        _STREAK_JOB,
        _FREEZE_JOB,
        _HEARTBEAT_JOB,
        _BACKUP_FRESHNESS_JOB,
        _WATCH_JOB,
    }
    for job in application.job_queue.jobs():
        if job.name in known:
            job.schedule_removal()
    logger.info("Scheduler stopped")
