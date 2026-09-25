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

**W20 — #69 RESOLVED BY MAKING THE TWO TABLES DISJOINT FROM THIS SIDE.** The
worker registers ONE job, ``push_poll``, and nothing the bot also runs. The
four overlapping jobs (``streak_rollover``, ``monthly_freeze_reset``,
``heartbeat``, ``backup_freshness``) stay the bot's until W22 deletes it; W22
moves them here. Resolving it from the bot's side instead would edit
``apps/bot/scheduler.py``, which stays byte-identical until W22.

**TWO JOBS THAT HAVE NEVER RUN ON PRODUCTION ARE HELD, NOT SWITCHED ON AS A
SIDE EFFECT OF INSTALLING THE UNIT** (``HELD_JOBS``): ``assign_daily`` would
start pre-creating tomorrow's session at night, and ``monthly_reset`` would run
the M13 fossil sweep for the first time. Each is a behaviour change on
production that no slice has asked for, so each waits for its own ruling. Their
bodies are kept and still tested.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import monitoring
from core.config import load_settings
from core.services import push as push_service
from core.scheduling import (
    list_candidate_users,
    run_monthly_freeze_reset,
    run_monthly_reset,
    run_streak_rollover,
)
from core.services import sessions as sessions_service
from core.services import backup_freshness as backup_freshness_service
from core.services import heartbeat as heartbeat_service

logger = logging.getLogger(__name__)

# Same cadences the bot's scheduler uses (apps/bot/scheduler.py). Both
# processes poll rather than schedule per-user cron entries, because every
# one of these fires on the user's *local* date and two users can sit in
# different timezones.
STREAK_POLL_SECONDS = 15 * 60
MAINTENANCE_POLL_SECONDS = 60 * 60
#: W20. The reminder fires within five minutes of a learner's `morning_time` —
#: the bot's own poll interval (`apps/bot/scheduler.py::POLL_SECONDS`).
PUSH_POLL_SECONDS = 5 * 60


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
    """Report on both off-site destinations: the S4c folder and R2.

    The folder half is unchanged and stays silent when ``BACKUP_OFFSITE_DIR``
    is unset — a synced folder was always optional.

    The R2 half (W1c) is not silent when unset. That was known issue #31: an
    unconfigured backup and a healthy one produced the same output, which is
    the one case where saying nothing is a lie.

    Delivery, honestly: this process has no operator channel, so both halves
    land in the journal at ERROR and nowhere else (known issue #65, the same
    limitation ``apps/api/main.py::send_operator_alert`` carries). The bot's
    copy of this check does reach Telegram. Nobody sees the lines below
    without ``journalctl -u english-worker``.
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
    elif status == "stale":
        newest = backup_freshness_service.newest_offsite(
            Path(settings.backup_offsite_dir)
        )
        detail = "missing_or_empty"
        if newest is not None:
            age_hours = (now - newest.mtime).total_seconds() / 3600.0
            detail = f"newest={newest.path.name} age={age_hours:.1f}h"
        logger.error("Off-site backup STALE: %s", detail)
    else:
        logger.info("Off-site backup fresh")

    health = backup_freshness_service.check_r2_freshness(
        backup_freshness_service.r2_config_from_settings(settings),
        now=now,
        max_age_hours=settings.r2_max_age_hours,
        required=settings.r2_required,
    )
    if health.should_alert:
        logger.error(
            "Off-site backup R2 %s: %s", health.status.upper(), health.detail
        )
    else:
        logger.info("Off-site backup R2 %s: %s", health.status, health.detail)


def assign_daily() -> None:
    """Pre-create tomorrow's daily session for every eligible learner.

    ARCHITECTURE §7 gives this job three things to do — build tomorrow's
    session, pick and pre-validate its items, choose the video. **Two of the
    three have no subject in W10, and the job ships doing one of them rather
    than being invented later under time pressure.**

    * There is **no generator**. Block 3's eight items need one, and building it
      inside a surface slice would put a billed content pipeline there. That is
      the item generation slice, and every generator-shaped issue targeted at W10
      (#102, #103, #105, #110, #120, #168) moves with it.
    * There is **no video engine**. `videos` and `video_assignments` arrive at
      W12.

    **So `docs/TASKS-v3-web.md`'s W10 criterion "report the item accept rate
    from the first `assign_daily` run" cannot be met by this slice.** Nothing is
    generated, so there is no accept rate. The number is reported as unmeasurable
    and the bar is not moved (CLAUDE.md §3 rule 7); the criterion is carried
    verbatim to the generation slice.

    **Each learner's LOCAL tomorrow**, from the `timezone` `EligibleUser` already
    carries. Computing it on server time would disagree with the lazy create in
    `GET /session/today` exactly once a day, at the boundary — and migration
    016's partial UNIQUE would accept both rows, because it enforces one row per
    date and cannot tell you the date was computed wrongly.

    Polls like every other job here rather than firing at 03:30: both learners'
    local dates are evaluated on each tick, which is how `streak_rollover` and
    the two monthly jobs already work and is what lets two learners sit in
    different timezones. Creating a row that already exists is a no-op.

    One learner failing must not stop the others — the loop logs and continues,
    the same shape `core.scheduling.run_streak_rollover` uses.
    """
    now = datetime.now(timezone.utc)
    created = 0
    for user in list_candidate_users():
        try:
            local_tomorrow = (
                sessions_service.local_today(user.timezone, now) + timedelta(days=1)
            )
            sessions_service.ensure_daily_session(
                user.id, local_tomorrow, now=now
            )
            created += 1
        except Exception:
            logger.exception("assign_daily failed user_id=%s", user.id)
    logger.info("assign_daily ok users=%s", created)


def push_poll() -> None:
    """W20: advance every learner's reminder ladder by at most one step.

    The decisions are counted, never itemised with anything but ids: the log
    carries user ids and outcomes (CLAUDE.md §5), never an endpoint or a body.
    """
    report = push_service.run_push_pass(load_settings(), datetime.now(timezone.utc))
    outcomes: dict[str, int] = {}
    for _user_id, _kind, outcome in report.decisions:
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    logger.info(
        "push_poll ok decisions=%s %s",
        len(report.decisions),
        " ".join(f"{k}={v}" for k, v in sorted(outcomes.items())),
    )


#: What the worker runs. **Disjoint from the bot's table by construction**
#: (#69); `tests/test_backup_r2.py` asserts the intersection is empty.
JOBS: tuple[Job, ...] = (
    Job("push_poll", push_poll, PUSH_POLL_SECONDS, 45),
)

#: Built, kept, tested — and NOT registered. Each needs something before it runs
#: on production; the reason is data so the test and the record say the same.
HELD_JOBS: dict[str, tuple[Job, str]] = {
    "streak_rollover": (
        Job("streak_rollover", streak_rollover, STREAK_POLL_SECONDS, 20),
        "the bot runs it until W22 (#69)",
    ),
    "monthly_freeze_reset": (
        Job("monthly_freeze_reset", monthly_freeze_reset, STREAK_POLL_SECONDS, 30),
        "the bot runs it until W22 (#69)",
    ),
    "heartbeat": (
        Job("heartbeat", heartbeat, MAINTENANCE_POLL_SECONDS, 60),
        "the bot runs it until W22 (#69)",
    ),
    "backup_freshness": (
        Job("backup_freshness", backup_freshness, MAINTENANCE_POLL_SECONDS, 90),
        "the bot runs it until W22 (#69)",
    ),
    "monthly_reset": (
        Job("monthly_reset", monthly_reset, STREAK_POLL_SECONDS, 40),
        "never run on production: the fossil sweep's first run is an operator ruling",
    ),
    "assign_daily": (
        Job("assign_daily", assign_daily, MAINTENANCE_POLL_SECONDS, 120),
        "never run on production: pre-creating tomorrow's session is an operator ruling",
    ),
}


#: W23 — the ONE job that checks in to Sentry Crons (#438). One because
#: Sentry's free plan allows one cron monitor (`core.monitoring`); `push_poll`
#: because it is the job that runs every five minutes and the one whose silence
#: costs a learner a reminder. A dead worker misses its check-in; a worker that
#: is up and failing every tick checks in `error`.
LIVENESS_JOB = "push_poll"


def run_job(job: Job) -> None:
    """Run one job, swallowing its exception so the scheduler survives it.

    APScheduler removes nothing on error, but an unlogged traceback in a
    process with no operator channel is an invisible failure.

    **W23: the exception also goes to Sentry** (type, frames and the job's name
    as the ``route`` tag — never the message), and ``LIVENESS_JOB`` reports each
    run to its cron monitor. Both are no-ops while ``SENTRY_DSN`` is unset.
    """
    started = time.monotonic()
    ok = True
    try:
        job.func()
    except Exception as exc:
        ok = False
        logger.exception("Scheduled job failed name=%s", job.name)
        monitoring.capture_exception(exc, user_id=None, route=f"job:{job.name}")
    if job.name == LIVENESS_JOB:
        monitoring.check_in(
            monitoring.WORKER_MONITOR_SLUG,
            ok=ok,
            duration_s=time.monotonic() - started,
            interval_minutes=job.interval_seconds // 60,
        )
