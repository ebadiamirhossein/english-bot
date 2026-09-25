"""Worker entrypoint: take the lock, register the jobs, run the scheduler.

    python -m apps.worker.main

The lock comes first and the scheduler second, deliberately. The API runs
several uvicorn workers and each one is a whole process; if the scheduler
lived there, every job would fire once per worker (W0 risk R3). Here there is
one process by construction: a second start finds the lock held, says so, and
exits non-zero.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from apps.worker.jobs import JOBS, Job, run_job
from core import monitoring
from core.config import ConfigError, Settings, load_settings
from core.instance_lock import InstanceLock, InstanceLockError
from core.logging import configure_logging

logger = logging.getLogger(__name__)


def worker_lock_path(settings: Settings) -> Path:
    """The worker's own lock file, beside the bot's in RUNTIME_DIR.

    Derived rather than configured: the bot and the worker are separate
    processes that must be able to run at the same time, so they cannot share
    ``INSTANCE_LOCK_FILE`` — and a second environment variable is a second
    thing to forget on a deploy.
    """
    return Path(settings.instance_lock_file).with_name("worker.lock")


def worker_log_path(settings: Settings) -> Path:
    """The worker's own log file, beside the bot's.

    Not shared: ``configure_logging`` installs a ``RotatingFileHandler``, and
    two processes rotating one file lose lines from whichever one is not
    holding it at the moment it rolls over.
    """
    return Path(settings.log_file).with_name("worker.log")


def build_scheduler(jobs: tuple[Job, ...] = JOBS) -> BlockingScheduler:
    """Return a scheduler with every job registered, not yet started."""
    scheduler = BlockingScheduler(timezone="UTC")
    now = datetime.now(timezone.utc)
    for job in jobs:
        scheduler.add_job(
            run_job,
            trigger=IntervalTrigger(seconds=job.interval_seconds),
            args=[job],
            id=job.name,
            name=job.name,
            next_run_time=now + timedelta(seconds=job.first_seconds),
            # One run at a time, and never a pile-up of catch-up runs after
            # the machine sleeps: every job here is a poll, so the next tick
            # does the same work as the one that was missed.
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )
    logger.info(
        "Scheduler built jobs=%s", ",".join(job.name for job in jobs)
    )
    return scheduler


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    lock = InstanceLock(worker_lock_path(settings))
    try:
        lock.acquire()
    except InstanceLockError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    configure_logging(replace(settings, log_file=str(worker_log_path(settings))))
    # W23. After logging, so its one line ("Monitoring on/off") reaches the log.
    monitoring.init_monitoring(settings, component="worker")
    scheduler = build_scheduler()
    logger.info("Worker starting (lock=%s)", worker_lock_path(settings))
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopping")
    finally:
        scheduler.shutdown(wait=False)
        lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
