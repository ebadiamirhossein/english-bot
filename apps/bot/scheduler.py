"""In-process scheduled jobs via PTB JobQueue (APScheduler).

**W22: ONE JOB — the couple challenge poll (S8: 18:00 Vilnius, chat-level).**

What the bot ran before W22, and where each went:

* **Deleted with the teaching path:** ``morning_poll`` (the quiz), ``evening_poll``
  (reading), ``diary_poll``, ``anki_poll`` (the weekly Telegram deck export),
  ``nudge_poll`` (v2's Telegram ladder — W20's push ladder in the worker is its
  replacement), ``watch_poll`` (the watched-folder CSV import's Telegram
  notice), and the Sunday report, unscheduled since #348.
* **Moved to the worker (#69's remainder):** ``streak_rollover``,
  ``monthly_freeze_reset``, ``heartbeat`` and ``backup_freshness``
  (``apps/worker/jobs.py::JOBS``). The worker now writes the heartbeat file as
  well as reading it (#438).

**The two job tables are disjoint by construction** — this one names only
``couple_poll``, which the worker does not have —
``tests/test_backup_r2.py::test_bot_and_worker_job_tables_are_disjoint``.

**The couple poll does not touch the heartbeat file.** The file now means "the
worker's jobs are succeeding"; a daily group message cannot keep it fresh
without hiding a dead worker, which is the defect #438 describes the other way
round.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apps.bot.handlers import couple as couple_handler

if TYPE_CHECKING:
    from telegram.ext import Application, ContextTypes

logger = logging.getLogger(__name__)

POLL_SECONDS = 5 * 60
COUPLE_FIRST_SECONDS = 60
_COUPLE_JOB = "couple_poll"

#: Every name this module has EVER registered. The removal loop below takes
#: each one out of the queue before registering, so a process whose queue
#: still holds a pre-W22 job — a soft restart, a re-entrant ``start_scheduler``
#: — loses it here rather than keeping it alive. (#348's reasoning, for the
#: same reason the Sunday report's name stayed in this set after it stopped
#: being registered.)
_EVERY_JOB_NAME_EVER = frozenset(
    {
        "morning_poll",
        "evening_poll",
        "diary_poll",
        "sunday_report_poll",
        "anki_poll",
        "nudge_poll",
        _COUPLE_JOB,
        "streak_rollover",
        "monthly_freeze_reset",
        "heartbeat",
        "backup_freshness",
        "watch_poll",
    }
)


async def run_couple_poll(
    application: Application,
    now: datetime | None = None,
) -> list[str]:
    """Run one couple-challenge poll (chat-level). Returns action tags."""
    instant = now or datetime.now(timezone.utc)
    actions = await couple_handler.run_couple_poll(application, now=instant)
    logger.info("Couple poll: actions=%s", actions)
    return actions


async def _couple_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_couple_poll(context.application)


def _remove_known_jobs(application: Application) -> None:
    for job in application.job_queue.jobs():
        if job.name in _EVERY_JOB_NAME_EVER:
            job.schedule_removal()


def start_scheduler(application: Application) -> None:
    """Register the couple poll."""
    jq = application.job_queue
    if jq is None:
        raise RuntimeError(
            "JobQueue unavailable — install apscheduler "
            "(see requirements.txt)"
        )
    _remove_known_jobs(application)
    jq.run_repeating(
        _couple_job,
        interval=POLL_SECONDS,
        first=COUPLE_FIRST_SECONDS,
        name=_COUPLE_JOB,
    )
    logger.info(
        "Scheduler started jobs=%s (poll every %ss; first=%ss)",
        _COUPLE_JOB,
        POLL_SECONDS,
        COUPLE_FIRST_SECONDS,
    )


def stop_scheduler(application: Application | None = None) -> None:
    """Remove scheduler jobs if present."""
    if application is None or application.job_queue is None:
        return
    _remove_known_jobs(application)
    logger.info("Scheduler stopped")
