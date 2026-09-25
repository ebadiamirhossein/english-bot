"""The worker's job table.

One entry per job: a name, a callable that takes no arguments, and an
interval. The table is data, so ``tests/test_worker.py`` can assert what is
registered by name and trigger — five v2 scheduler tests passed while
asserting only the predicates, which means they would also have passed
against a worker that registered nothing (known issue #54).

Scope at W1b: the maintenance jobs whose bodies are already channel-neutral
predicates in ``core``. The delivery jobs — morning, evening, nudge, Sunday
report, Anki — stayed in ``apps/bot`` because they sent Telegram messages.

**W20 — #69 RESOLVED BY MAKING THE TWO TABLES DISJOINT FROM THIS SIDE.** The
worker registered ONE job, ``push_poll``, and held the four the bot also ran.

**W22 — THE FOUR HELD JOBS ARE REGISTERED HERE (#69's remainder).** The bot's
scheduler is down to ``couple_poll`` (``apps/bot/scheduler.py``), so
``streak_rollover``, ``monthly_freeze_reset``, ``heartbeat`` and
``backup_freshness`` run in this process and nowhere else. **The tables stay
disjoint** — ``tests/test_backup_r2.py::test_bot_and_worker_job_tables_are_disjoint``
fails the commit that registers a name in both. **The deploy restarts
``english-bot`` BEFORE ``english-worker``**, so the old bot process (which
still holds the four in memory) is gone before this one starts running them.

**THE WORKER NOW WRITES THE HEARTBEAT FILE (#438).** It used to read it only,
because the bot's deliveries were what the file meant; a worker that touched it
would have kept it fresh while the bot lay dead. The deliveries are gone from
the bot, so the file now means *this worker's jobs are succeeding*:
``run_job`` touches it after every successful run of a job in
``TOUCHES_HEARTBEAT`` — never after ``heartbeat`` or ``backup_freshness``
themselves, which would make the alarm check its own pulse.

**The two alarms reach the operator through Sentry, not Telegram.** The bot's
copies sent a Telegram message to ``OPERATOR_TELEGRAM_ID``; these capture a
typed exception (``HeartbeatStale``, ``BackupStale``) through ``core.monitoring``
— the type is the alarm, because the scrubber drops every message (#65, W23).
**Until ``SENTRY_DSN`` is set they reach the journal only**, which is why W22's
deploy is gated on W23's DSN step having run (the launch pass).

**TWO JOBS ARE STILL HELD** (``HELD_JOBS``). ``assign_daily`` has never run on
production and would start pre-creating tomorrow's session at night (#437).
``monthly_reset`` is freeze reset PLUS the M13 fossil sweep — **and W22 found
that the bot's job NAMED ``monthly_freeze_reset`` called ``run_monthly_reset``,
so production has been running the sweep on every local 1st all along**; #437's
"for the first time" was wrong. The sweep queues retests that only the Telegram
morning quiz ever delivered, and that quiz is deleted here, so the worker takes
the freeze half (``monthly_freeze_reset``) and the sweep stays held with its
consumer gone (#452). Bodies kept and still tested.

**W24d ADDS `assign_video`** (a video every day, operator decision 2 of
2026-09-27): registered rather than held, because the operator's ruling is the
behaviour change the held jobs are waiting for. It shares nothing with the bot.

**W24r ADDS `refresh_videos`, AND ONLY BEHIND A FLAG** (`jobs_for`): the weekly
video refresh, Monday ~04:00 Europe/Vilnius, is a BILLED run the system makes on
a schedule. The operator ruled it on 2026-09-27 (cost measured under $1 a run) --
**an exception to #196's "billed runs are operator-run", scoped to this job
only** -- and it registers only while `VIDEO_AUTO_REFRESH=1` is in `.env`, so no
deploy can start spending by itself.

**W31c ADDS TWO MORE BILLED JOBS, EACH BEHIND ITS OWN FLAG** (`OPTIONAL_JOBS`):
`fill_word_glosses` (`WORD_GLOSS_JOB`, every 15 min, ≤20 a run and ≤60 a UTC
day) explains the words learners saved with no meaning and only then writes
their cards; `pregen_glosses` (`VIDEO_PREGEN_GLOSSES`, hourly, ≤20 per learner
and ≤40 a UTC day) explains today's assigned video ahead of the taps. Rulings
Q5, Q6 and C2 of 2026-09-27: both are switched on only after the operator has
read the first manual `explain --apply`, and the ceilings live in
`core.services.words`, not here.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import monitoring
from core.config import Settings, load_settings
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

# The cadences the bot's scheduler used for these jobs until W22 moved them
# here. Poll rather than schedule per-user cron entries, because every one of
# these fires on the user's *local* date and two users can sit in different
# timezones.
STREAK_POLL_SECONDS = 15 * 60
MAINTENANCE_POLL_SECONDS = 60 * 60
#: W20. The reminder fires within five minutes of a learner's `morning_time` —
#: the bot's own poll interval (`apps/bot/scheduler.py::POLL_SECONDS`).
PUSH_POLL_SECONDS = 5 * 60
#: W24r. `refresh_videos` runs on a calendar, not a poll: Monday 04:00 in
#: Vilnius, where both learners are. The pool is shared, so one timezone is the
#: right one -- unlike the per-learner jobs above.
REFRESH_VIDEOS_CRON = "0 4 * * mon"
REFRESH_VIDEOS_TIMEZONE = "Europe/Vilnius"
WEEK_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True)
class Job:
    """A registered job. ``func`` takes no arguments and returns nothing useful."""

    name: str
    func: Callable[[], None]
    interval_seconds: int
    # Seconds after start-up for the first run. Staggered so the jobs do not
    # all wake in the same second on a cold start.
    first_seconds: int
    # W24r. A crontab line, read in `REFRESH_VIDEOS_TIMEZONE`, for the one job
    # that runs on a calendar. When set, `interval_seconds` and `first_seconds`
    # describe the cadence for the record and are not what schedules it.
    cron: str | None = None


def _now() -> datetime:
    """The jobs' clock, one seam for a test to fix (CLAUDE.md §3 rule 6)."""
    return datetime.now(timezone.utc)


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


class HeartbeatStale(Exception):
    """No job in ``TOUCHES_HEARTBEAT`` has succeeded for ``MAX_AGE_HOURS``.

    Captured, never raised: the heartbeat job itself ran fine. The TYPE is the
    alarm Sentry groups and emails on; it carries no message, and the scrubber
    would drop one anyway (``core.monitoring.scrub_event``).
    """


class BackupStale(Exception):
    """An off-site destination is stale, empty, or unset when required. Captured, never raised."""


def heartbeat() -> None:
    """Alarm when no job has recorded a success lately. Reads; never writes.

    **W22: this process owns both halves now** — ``run_job`` writes the file and
    this job reads it (#438). It is excluded from ``TOUCHES_HEARTBEAT``: a check
    that refreshed the file it checks could never go stale.

    Stale → one line at ERROR and one ``HeartbeatStale`` to Sentry. The bot's
    copy sent the operator a Telegram message instead; the worker has no
    Telegram and must not grow one (PRODUCT-PRINCIPLES §1).
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
        monitoring.capture_exception(
            HeartbeatStale(), user_id=None, route="job:heartbeat"
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

    **Delivery (W22):** both halves log at ERROR, and a stale result also sends
    one ``BackupStale`` to Sentry — #65's channel since W23, and off until
    ``SENTRY_DSN`` is set. The bot's copy of this check sent the operator a
    Telegram message, with a 24-hour cooldown; Sentry groups every
    ``BackupStale`` into one issue and emails when it opens, which is the same
    once-not-hourly shape.
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
        monitoring.capture_exception(
            BackupStale(), user_id=None, route="job:backup_freshness"
        )
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
        monitoring.capture_exception(
            BackupStale(), user_id=None, route="job:backup_freshness"
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


def assign_video() -> None:
    """W24d: give every learner their day's video, if the pool has one for them.

    **Operator decision 2 of 2026-09-27 (a video every day) and R3 (Sunday
    too).** Each learner's LOCAL today, idempotently: a day that has its video is
    left alone, and a day the pool cannot serve -- nothing in band and unseen --
    stays without one and is tried again next hour. **Never a repeat, never below
    band** (`core.video.assign.choose`). No model, no network, no billed call:
    coverage is computed locally over stored transcripts.

    **Registered, not held (unlike `assign_daily`),** because the operator's
    ruling is the behaviour change `HELD_JOBS` waits for. The log line carries
    counts only (CLAUDE.md §5); `none_in_band` above zero is the pool running
    short, and the fix is a refresh, never a wider band.
    """
    from core.video.assign import assign_today_for_all

    report = assign_today_for_all(datetime.now(timezone.utc))
    logger.info(
        "assign_video ok %s", " ".join(f"{k}={v}" for k, v in report.items())
    )


def refresh_videos() -> None:
    """W24r: the weekly video refresh -- `core.video.refresh --live --apply`,
    unattended. **BILLED** (Apify, measured under $1 a run), at most 40
    transcripts, the same purge. Registered only behind `VIDEO_AUTO_REFRESH`.

    **One line of counts, no titles** (CLAUDE.md §5). A run that cannot start
    raises, and `run_job` sends it to Sentry as `job:refresh_videos`.
    """
    from core.video.refresh import run_scheduled

    summary = run_scheduled(load_settings(), now=_now())
    logger.info(
        "refresh_videos ok %s", " ".join(f"{k}={v}" for k, v in summary.items())
    )


def fill_word_glosses() -> None:
    """W31c: explain the words learners saved with no meaning, then card them.

    **BILLED** (one model call per word), registered only behind
    `WORD_GLOSS_JOB`. Every 15 min; at most 20 calls a run and 60 a UTC day,
    enforced inside `core.services.words.fill_pending` whatever this passes.
    **One line of counts, never a word** (CLAUDE.md §5).
    """
    from core.services import words as words_service

    counts = words_service.fill_pending(_now())
    logger.info(
        "fill_word_glosses ok carded=%s generated=%s refused=%s no_meaning=%s names=%s "
        "at_ceiling=%s",
        counts.carded, counts.generated, counts.refused, counts.no_meaning, counts.names,
        counts.skipped_ceiling,
    )


def pregen_glosses() -> None:
    """W31c: explain today's assigned video ahead of the taps (ruling Q5 (b)).

    **BILLED**, registered only behind `VIDEO_PREGEN_GLOSSES`. Hourly, after
    `assign_video`; at most 20 lemmas per learner and 40 a UTC day, enforced
    inside `core.services.words.pregen_today`. One line of counts.
    """
    from core.services import words as words_service

    counts = words_service.pregen_today(_now())
    logger.info(
        "pregen_glosses ok generated=%s refused=%s at_ceiling=%s",
        counts.generated, counts.refused, counts.skipped_ceiling,
    )


def fill_word_dictionary() -> None:
    """W32c: fill the dictionary for the videos learners are about to watch.

    **BILLED**, registered only behind `WORD_DICTIONARY_JOB`. Hourly; at most
    60 words a run and 300 a UTC day, enforced inside
    `core.services.dictionary.topup` whatever this passes; it never waits on a
    busy provider (the next hour takes the words). **One line of counts, never
    a word** (CLAUDE.md §5).
    """
    from core.services import dictionary as dictionary_service

    report = dictionary_service.topup(_now())
    logger.info(
        "fill_word_dictionary ok planned=%s written=%s refused=%s deferred=%s at_ceiling=%s",
        report.planned, report.written, report.refused, report.deferred, report.at_ceiling,
    )


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
#: (#69); `tests/test_backup_r2.py` asserts the intersection is empty. W22 moved
#: the four middle rows here from `HELD_JOBS`, with the periods and start-up
#: offsets they had there (and in the bot's scheduler before that).
JOBS: tuple[Job, ...] = (
    Job("streak_rollover", streak_rollover, STREAK_POLL_SECONDS, 20),
    Job("monthly_freeze_reset", monthly_freeze_reset, STREAK_POLL_SECONDS, 30),
    Job("push_poll", push_poll, PUSH_POLL_SECONDS, 45),
    Job("heartbeat", heartbeat, MAINTENANCE_POLL_SECONDS, 60),
    Job("backup_freshness", backup_freshness, MAINTENANCE_POLL_SECONDS, 90),
    Job("assign_video", assign_video, MAINTENANCE_POLL_SECONDS, 150),
)

#: W24r. Registered by `jobs_for` only when the flag is set.
REFRESH_VIDEOS = Job(
    "refresh_videos", refresh_videos, WEEK_SECONDS, 0, cron=REFRESH_VIDEOS_CRON
)


#: W31c. The pending-word job, every 15 minutes (ruling Q6).
FILL_WORD_GLOSSES = Job("fill_word_glosses", fill_word_glosses, 15 * 60, 120)
#: W31c. Pre-generation for today's video, hourly, after `assign_video` (150 s).
PREGEN_GLOSSES = Job("pregen_glosses", pregen_glosses, MAINTENANCE_POLL_SECONDS, 210)

#: W32c. The dictionary top-up, hourly, after `assign_video` (150 s).
FILL_WORD_DICTIONARY = Job(
    "fill_word_dictionary", fill_word_dictionary, MAINTENANCE_POLL_SECONDS, 270
)

#: **The billed jobs, each behind its own `.env` flag and none on by default**
#: (W24r's shape, extended by W31c). `(Settings attribute, Job)`.
OPTIONAL_JOBS: tuple[tuple[str, Job], ...] = (
    ("video_auto_refresh", REFRESH_VIDEOS),
    ("word_gloss_job", FILL_WORD_GLOSSES),
    ("video_pregen_glosses", PREGEN_GLOSSES),
    ("word_dictionary_job", FILL_WORD_DICTIONARY),
)


def jobs_for(settings: Settings) -> tuple[Job, ...]:
    """What this worker registers: `JOBS`, plus each billed job whose flag is
    set (`VIDEO_AUTO_REFRESH`, `WORD_GLOSS_JOB`, `VIDEO_PREGEN_GLOSSES`,
    `WORD_DICTIONARY_JOB`) --
    a billed job is never on by default."""
    return JOBS + tuple(job for flag, job in OPTIONAL_JOBS if getattr(settings, flag))

#: The jobs whose success refreshes the heartbeat file (#438): the ones that
#: do the product's work. Not `heartbeat` or `backup_freshness` — an alarm
#: that refreshed its own pulse could never fire.
TOUCHES_HEARTBEAT = frozenset({"streak_rollover", "monthly_freeze_reset", "push_poll"})

#: Built, kept, tested — and NOT registered. Each needs something before it runs
#: on production; the reason is data so the test and the record say the same.
HELD_JOBS: dict[str, tuple[Job, str]] = {
    "monthly_reset": (
        Job("monthly_reset", monthly_reset, STREAK_POLL_SECONDS, 40),
        "the fossil sweep's only consumer, the Telegram morning quiz, was deleted "
        "at W22: it would queue retests nothing delivers (#452)",
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


def _touch_heartbeat(job_name: str) -> None:
    """Record one successful run (#438). A failure to write is logged, not raised:
    the job succeeded, and the heartbeat going stale is the alarm for this."""
    try:
        heartbeat_service.touch_job_fire(
            load_settings().heartbeat_file, now=datetime.now(timezone.utc)
        )
    except Exception:
        logger.exception("Heartbeat touch failed after name=%s", job_name)


def run_job(job: Job) -> None:
    """Run one job, swallowing its exception so the scheduler survives it.

    APScheduler removes nothing on error, but an unlogged traceback in a
    process with no operator channel is an invisible failure.

    **W22: a successful run of a job in ``TOUCHES_HEARTBEAT`` refreshes the
    heartbeat file** — the write the bot's scheduler used to do (#438).

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
    if ok and job.name in TOUCHES_HEARTBEAT:
        _touch_heartbeat(job.name)
    if job.name == LIVENESS_JOB:
        monitoring.check_in(
            monitoring.WORKER_MONITOR_SLUG,
            ok=ok,
            duration_s=time.monotonic() - started,
            interval_minutes=job.interval_seconds // 60,
        )
