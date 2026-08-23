"""The worker's job table.

One entry per job: a name, a callable that takes no arguments, and an
interval. The table is data, so ``tests/test_worker.py`` can assert what is
registered by name and trigger — five v2 scheduler tests passed while
asserting only the predicates, which means they would also have passed
against a worker that registered nothing (known issue #54).

Scope at W1b: the maintenance jobs whose bodies are already channel-neutral
predicates in ``core``. The delivery jobs — morning, evening, nudge, Sunday
report, Anki — stay in ``apps/bot`` until W20, because they send Telegram
messages and moving them means moving the channel too.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.config import load_settings
from core.scheduling import (
    run_monthly_freeze_reset,
    run_monthly_reset,
    run_streak_rollover,
)
from core.services import backup_freshness as backup_freshness_service
from core.services import heartbeat as heartbeat_service

logger = logging.getLogger(__name__)

# Same cadences the bot's scheduler uses (apps/bot/scheduler.py). Both
# processes poll rather than schedule per-user cron entries, because every
# one of these fires on the user's *local* date and two users can sit in
# different timezones.
STREAK_POLL_SECONDS = 15 * 60
MAINTENANCE_POLL_SECONDS = 60 * 60


@dataclass(frozen=True)
class Job:
    """A registered job. ``func`` takes no arguments and returns nothing useful."""

    name: str
    func: Callable[[], None]
    interval_seconds: int
    # Seconds after start-up for the first run. Staggered so the jobs do not
    # all wake in the same second on a cold start.
    first_seconds: int


def streak_rollover() -> None:
    """Evaluate pending streak days for users whose local 03:00 has passed."""
    run_streak_rollover()


def monthly_freeze_reset() -> None:
    """Top freeze tokens back to 2 for users whose local date is the 1st."""
    run_monthly_freeze_reset()


def monthly_reset() -> None:
    """Freeze reset plus the M13 anti-fossilisation sweep.

    Overlaps ``monthly_freeze_reset`` by design: both are idempotent per user
    per local day (``freeze_reset_on`` and the ``fossil_sweep`` session guard
    them), and the two names are the two units ARCHITECTURE-v3 §7 names. When
    W20 retires the bot's own scheduler the overlap should collapse to one.
    """
    run_monthly_reset()


def heartbeat() -> None:
    """Report whether *any* process has recorded a successful job lately.

    Read-only at W1b: this worker deliberately does not touch the heartbeat
    file. The bot still owns every delivery job, so the file means "deliveries
    are alive"; a worker that touched it would keep the file fresh while the
    bot lay dead, and the staleness alarm would never fire again. W20 moves
    the deliveries here and the writing with them.

    No operator channel exists in this process, so a stale heartbeat is logged
    at ERROR rather than sent (see ``apps/api/main.py::send_operator_alert``).
    """
    settings = load_settings()
    now = datetime.now(timezone.utc)
    status = heartbeat_service.check_heartbeat(settings.heartbeat_file, now=now)
    if status == "stale":
        last = heartbeat_service.read_last_fire(settings.heartbeat_file)
        logger.error(
            "Heartbeat STALE: no successful scheduled job in %sh (last_fire=%s)",
            heartbeat_service.MAX_AGE_HOURS,
            last.isoformat() if last is not None else "never",
        )
    else:
        logger.info("Heartbeat ok")


def backup_freshness() -> None:
    """Alert when the newest off-site dump is too old. Silent while unset.

    ``BACKUP_OFFSITE_DIR`` is unset in production (known issues #6 / #31), so
    this logs 'skipped' today. W1c is what makes it say something.
    """
    settings = load_settings()
    now = datetime.now(timezone.utc)
    status = backup_freshness_service.check_offsite_freshness(
        settings.backup_offsite_dir,
        now=now,
        max_age_hours=settings.backup_offsite_max_age_hours,
    )
    if status == "skipped":
        logger.info("Off-site backup freshness skipped (BACKUP_OFFSITE_DIR unset)")
        return
    if status == "stale":
        newest = backup_freshness_service.newest_offsite(
            Path(settings.backup_offsite_dir)
        )
        detail = "missing_or_empty"
        if newest is not None:
            age_hours = (now - newest.mtime).total_seconds() / 3600.0
            detail = f"newest={newest.path.name} age={age_hours:.1f}h"
        logger.error("Off-site backup STALE: %s", detail)
        return
    logger.info("Off-site backup fresh")


JOBS: tuple[Job, ...] = (
    Job("streak_rollover", streak_rollover, STREAK_POLL_SECONDS, 20),
    Job("monthly_freeze_reset", monthly_freeze_reset, STREAK_POLL_SECONDS, 30),
    Job("monthly_reset", monthly_reset, STREAK_POLL_SECONDS, 40),
    Job("heartbeat", heartbeat, MAINTENANCE_POLL_SECONDS, 60),
    Job("backup_freshness", backup_freshness, MAINTENANCE_POLL_SECONDS, 90),
)


def run_job(job: Job) -> None:
    """Run one job, swallowing its exception so the scheduler survives it.

    APScheduler removes nothing on error, but an unlogged traceback in a
    process with no operator channel is an invisible failure.
    """
    try:
        job.func()
    except Exception:
        logger.exception("Scheduled job failed name=%s", job.name)
