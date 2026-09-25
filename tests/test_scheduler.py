"""The bot's one scheduled job, and the 24-hour two-timezone simulation (W22).

**Before W22** this file tested the bot's eleven registered jobs and the morning
quiz's selection: who is due at their local ``morning_time``, over 24 hours of
five-minute polls, for a learner in Tokyo and one in Vilnius. **W22 deleted the
morning quiz with the rest of the Telegram teaching path, and moved four jobs to
the worker** (#69's remainder; their registration is ``tests/test_worker.py``'s).

**THE SIMULATION MOVED WITH THE JOB, NOT WITH THE FILE.** What fires at a
learner's local ``morning_time`` now is the worker's ``push_poll`` — W20's
reminder ladder (``core.services.push.run_push_pass``). So the simulation below
runs THAT pass on every five-minute tick for 24 hours, over the same two
learners, and asserts the same thing: **one reminder each, at their own local
07:00**. #448's row forbids closing it by shortening the 24 hours or the
five-minute tick, and neither is shortened.

**The pass reads the WHOLE ``approved_onboarded_users`` view on every tick** —
the property that made this test take 352.78 s on 2026-09-25, when the dev
database had accumulated 8,071 users (#448). It is kept: a learner list read once
and reused would make the test fast by testing less. Only the DECISIONS are
limited to the two learners made here (``list_push_learners`` is wrapped, not
replaced), because a real pass over the dev database would write
``push_deliveries`` rows for every other learner in it.

**RED DEMONSTRATIONS (2026-09-25, ``python -B``, caches cleared):**
``test_tokyo_vilnius_24h_five_minute_polls`` went red with
``core.services.push.due_kind``'s ``learner.timezone`` replaced by
``"Europe/Vilnius"`` (a learner reminded twice in the window — ``2 == 1``);
``test_start_scheduler_registers_only_the_couple_poll`` went red with a
``morning_poll`` registration put back into ``start_scheduler``. Both restored.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest
from telegram.ext import ApplicationBuilder

from apps.bot import scheduler
from core.config import load_settings
from core.push import generate_vapid_keys
from core.services import push as push_svc
from tests.support import progress_seed as seed
from tests.test_push_ladder import Browser, _e


# ── the bot's scheduler ──────────────────────────────────────────────────────


@pytest.fixture
def scheduled_app():
    app = ApplicationBuilder().token("1:FAKE-W22-SCHEDULER").build()
    scheduler.start_scheduler(app)
    yield app
    scheduler.stop_scheduler(app)


def test_start_scheduler_registers_only_the_couple_poll(scheduled_app) -> None:
    """Literal: every other job the bot ran was deleted or moved to the worker."""
    registered = [job.name for job in scheduled_app.job_queue.jobs()]
    assert registered == ["couple_poll"]


def test_the_couple_poll_runs_every_five_minutes(scheduled_app) -> None:
    (job,) = scheduled_app.job_queue.jobs()
    assert type(job.job.trigger).__name__ == "IntervalTrigger"
    assert job.job.trigger.interval.total_seconds() == 300


def test_start_scheduler_is_idempotent(scheduled_app) -> None:
    """A second call must not double-register — restarts happen."""
    scheduler.start_scheduler(scheduled_app)
    assert [job.name for job in scheduled_app.job_queue.jobs()] == ["couple_poll"]


@pytest.mark.parametrize(
    "legacy",
    ["morning_poll", "nudge_poll", "sunday_report_poll", "streak_rollover", "heartbeat"],
)
def test_a_pre_w22_job_still_in_the_queue_is_removed_on_start(legacy: str) -> None:
    """#348's reasoning, kept: a process whose queue already holds an old job —
    a soft restart, a re-entrant ``start_scheduler`` — must lose it here, or it
    runs for ever with nothing to remove it. The moved four would then run in
    two processes again, which is #69."""
    app = ApplicationBuilder().token("1:FAKE-W22-LEGACY").build()

    async def _noop(context) -> None:
        return None

    app.job_queue.run_repeating(_noop, interval=300, first=10, name=legacy)
    assert legacy in {job.name for job in app.job_queue.jobs()}
    scheduler.start_scheduler(app)
    try:
        assert [job.name for job in app.job_queue.jobs()] == ["couple_poll"]
    finally:
        scheduler.stop_scheduler(app)


def test_stop_scheduler_removes_every_job(scheduled_app) -> None:
    scheduler.stop_scheduler(scheduled_app)
    assert [j for j in scheduled_app.job_queue.jobs() if not j.removed] == []


# ── the simulation, now over the worker's reminder ───────────────────────────


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def two_learners(db, monkeypatch):
    """A Vilnius and a Tokyo learner, both at 07:00, each with one browser."""
    made: list[int] = []
    for tz in ("Europe/Vilnius", "Asia/Tokyo"):
        learner = seed.make_learner(db, "Sched Test")
        made.append(learner.user_id)
        db.execute(
            "UPDATE users SET timezone = %s, morning_time = '07:00' WHERE id = %s",
            (tz, learner.user_id),
        )
        browser = Browser()
        db.execute(
            "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) "
            "VALUES (%s, %s, %s, %s)",
            (learner.user_id, browser.endpoint, _e(browser.point), _e(browser.auth)),
        )
    db.commit()

    real = push_svc.list_push_learners
    mine = set(made)
    monkeypatch.setattr(
        push_svc,
        "list_push_learners",
        lambda: [l for l in real() if l.id in mine],
    )
    # The provider, at its door (standing rule 7): every push answers 201.
    monkeypatch.setattr(
        "core.push_api.httpx.post",
        lambda url, *, headers, content, timeout: httpx.Response(201),
    )
    yield {"Europe/Vilnius": made[0], "Asia/Tokyo": made[1]}
    for user_id in made:
        db.rollback()
        db.execute("DELETE FROM bot_message_counts WHERE user_id = %s", (user_id,))
        db.execute("DELETE FROM push_deliveries WHERE user_id = %s", (user_id,))
        db.commit()
        seed.drop_learner(db, user_id)


def test_tokyo_vilnius_24h_five_minute_polls(two_learners) -> None:
    """Both at 07:00; each reminded once, at their OWN local 07:00, over 24h.

    Starts at 21:55 UTC on 2026-08-03, five minutes before Tokyo's 07:00 on
    2026-08-04 (JST, UTC+9), and runs 289 ticks to 21:55 UTC on 2026-08-04 —
    which is 06:55 in Tokyo and 00:55 in Vilnius (EEST, UTC+3) the next day, so
    neither learner reaches a second 07:00 inside the window.
    """
    private, public = generate_vapid_keys()
    settings = replace(
        load_settings(),
        vapid_private_key=private,
        vapid_public_key=public,
        vapid_subject="mailto:op@example.invalid",
    )
    start = datetime(2026, 8, 3, 21, 55, tzinfo=timezone.utc)
    end = start + timedelta(hours=24)
    reminders: dict[int, list[datetime]] = {uid: [] for uid in two_learners.values()}
    ticks = 0
    tick = start
    while tick <= end:
        report = push_svc.run_push_pass(settings, tick)
        for user_id, kind, outcome in report.decisions:
            if kind == "reminder":
                assert outcome == "sent"
                reminders[user_id].append(tick)
        ticks += 1
        tick += timedelta(minutes=5)

    assert ticks == 289
    for tz, user_id in two_learners.items():
        assert len(reminders[user_id]) == 1, tz
        local = reminders[user_id][0].astimezone(ZoneInfo(tz))
        # The first tick at or after 07:00 local — exactly 07:00, since both
        # 07:00s fall on a tick of this grid.
        assert (local.hour, local.minute) == (7, 0), tz
    tokyo = reminders[two_learners["Asia/Tokyo"]][0]
    vilnius = reminders[two_learners["Europe/Vilnius"]][0]
    assert tokyo == datetime(2026, 8, 3, 22, 0, tzinfo=timezone.utc)
    assert vilnius == datetime(2026, 8, 4, 4, 0, tzinfo=timezone.utc)
