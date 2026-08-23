"""Morning poll eligibility — local dates, timezones, idempotency (S3)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from telegram.ext import ApplicationBuilder

from apps.bot import scheduler
from core.db import close_pool, connection
from apps.bot.scheduler import (
    EligibleUser,
    is_user_due_for_morning,
    users_due_for_morning,
)
from core.services.sessions import insert_session, local_today
from core.services.users import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_320_000_000


@pytest.fixture
def fake_telegram_id() -> int:
    return FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)


@pytest.fixture(autouse=True)
def _close_pool_after_test() -> None:
    yield
    close_pool()


def _delete_user(telegram_user_id: int) -> None:
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM users WHERE telegram_user_id = %s",
                (telegram_user_id,),
            )


@pytest.fixture
def cleanup_user(fake_telegram_id: int):
    yield fake_telegram_id
    _delete_user(fake_telegram_id)


def _onboard(
    tid: int,
    *,
    morning: str = "07:00",
    tz: str = "Europe/Vilnius",
) -> None:
    save_onboarding(
        tid,
        {
            "name": "Sched Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": morning,
            "evening_time": "21:00",
        },
    )
    with connection() as conn:
        conn.execute(
            "UPDATE users SET timezone = %s WHERE telegram_user_id = %s",
            (tz, tid),
        )


def _eligible(tid: int, tz: str, morning: str) -> EligibleUser:
    h, m = map(int, morning.split(":"))
    return EligibleUser(
        telegram_user_id=tid,
        timezone=tz,
        morning_time=time(h, m),
        paused_until=None,
    )


def test_before_morning_not_selected(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid, morning="08:00", tz="Europe/Vilnius")
    # 07:30 Vilnius on a fixed day
    now = datetime(2026, 8, 3, 4, 30, tzinfo=timezone.utc)  # 07:30 EEST (UTC+3)
    # Wait — Aug 3 2026: Lithuania is EEST UTC+3, so 04:30 UTC = 07:30 local.
    # morning is 08:00 → should NOT be selected.
    user = _eligible(tid, "Europe/Vilnius", "08:00")
    assert local_today("Europe/Vilnius", now) == date(2026, 8, 3)
    assert is_user_due_for_morning(user, now) is False


def test_past_morning_no_session_selected(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid, morning="08:00", tz="Europe/Vilnius")
    now = datetime(2026, 8, 3, 5, 15, tzinfo=timezone.utc)  # 08:15 Vilnius
    user = _eligible(tid, "Europe/Vilnius", "08:00")
    assert is_user_due_for_morning(user, now) is True
    due_ids = [u.telegram_user_id for u in users_due_for_morning(now)]
    assert tid in due_ids


def test_not_selected_twice_same_local_day(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid, morning="08:00", tz="Europe/Vilnius")
    now = datetime(2026, 8, 3, 5, 15, tzinfo=timezone.utc)
    day = local_today("Europe/Vilnius", now)
    insert_session(tid, "quiz", day, completed=False)
    user = _eligible(tid, "Europe/Vilnius", "08:00")
    assert is_user_due_for_morning(user, now) is False
    later = now + timedelta(hours=3)
    assert is_user_due_for_morning(user, later) is False


def test_two_timezones_own_local_morning() -> None:
    tid_vil = FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)
    tid_tok = FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)
    try:
        _onboard(tid_vil, morning="07:00", tz="Europe/Vilnius")
        _onboard(tid_tok, morning="07:00", tz="Asia/Tokyo")

        # 07:00 Tokyo = 22:00 previous day UTC (JST=UTC+9)
        tokyo_morning = datetime(2026, 8, 3, 22, 0, tzinfo=timezone.utc)
        # Actually 2026-08-03 22:00 UTC = 2026-08-04 07:00 JST
        tokyo_morning = datetime(2026, 8, 3, 22, 0, tzinfo=timezone.utc)
        assert (
            datetime(2026, 8, 3, 22, 0, tzinfo=timezone.utc)
            .astimezone(ZoneInfo("Asia/Tokyo"))
            .strftime("%Y-%m-%d %H:%M")
            == "2026-08-04 07:00"
        )
        due = {u.telegram_user_id for u in users_due_for_morning(tokyo_morning)}
        assert tid_tok in due
        assert tid_vil not in due  # Vilnius is 01:00 on Aug 4

        # 07:00 Vilnius = 04:00 UTC in summer (EEST UTC+3)
        vilnius_morning = datetime(2026, 8, 4, 4, 0, tzinfo=timezone.utc)
        assert (
            vilnius_morning.astimezone(ZoneInfo("Europe/Vilnius")).strftime(
                "%Y-%m-%d %H:%M"
            )
            == "2026-08-04 07:00"
        )
        # Tokyo already got a session? Not yet in DB — but local time in Tokyo
        # at this instant is 16:00, so past morning; without a session they'd
        # also be due. Insert Tokyo's morning delivery first to isolate.
        insert_session(
            tid_tok,
            "quiz",
            local_today("Asia/Tokyo", tokyo_morning),
            completed=False,
        )
        due2 = {u.telegram_user_id for u in users_due_for_morning(vilnius_morning)}
        assert tid_vil in due2
        assert tid_tok not in due2
    finally:
        _delete_user(tid_vil)
        _delete_user(tid_tok)


def test_tokyo_vilnius_24h_five_minute_polls() -> None:
    """Both morning_time 07:00; each selected once at own local 07:00 over 24h."""
    tid_vil = FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)
    tid_tok = FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)
    try:
        _onboard(tid_vil, morning="07:00", tz="Europe/Vilnius")
        _onboard(tid_tok, morning="07:00", tz="Asia/Tokyo")

        # Start just before Tokyo's 07:00 on 2026-08-04 (21:55 UTC Aug 3)
        start = datetime(2026, 8, 3, 21, 55, tzinfo=timezone.utc)
        end = start + timedelta(hours=24)

        selections: dict[int, list[datetime]] = {tid_vil: [], tid_tok: []}
        tick = start
        while tick <= end:
            due = users_due_for_morning(tick)
            for u in due:
                if u.telegram_user_id in selections:
                    selections[u.telegram_user_id].append(tick)
                    # Claim the slot the way delivery would
                    day = local_today(u.timezone, tick)
                    insert_session(
                        u.telegram_user_id, "quiz", day, completed=False
                    )
            tick += timedelta(minutes=5)

        assert len(selections[tid_tok]) == 1
        assert len(selections[tid_vil]) == 1

        tok_local = selections[tid_tok][0].astimezone(ZoneInfo("Asia/Tokyo"))
        vil_local = selections[tid_vil][0].astimezone(ZoneInfo("Europe/Vilnius"))
        assert (tok_local.hour, tok_local.minute) >= (7, 0)
        assert (vil_local.hour, vil_local.minute) >= (7, 0)
        # First selection should be the first poll at or after 07:00 local
        assert tok_local.hour == 7
        assert vil_local.hour == 7
    finally:
        _delete_user(tid_vil)
        _delete_user(tid_tok)


# --- job registration (W0 known issue #54) ------------------------------------
#
# Until W1 these five modules asserted only that the *predicates* answer
# correctly. All five would have gone on passing against a process that
# registered no jobs at all — which is exactly what the API/worker split
# risks. This asserts the wiring itself: every job present, by name, with its
# trigger and interval.


_EXPECTED_JOBS = {
    "morning_poll": scheduler.POLL_SECONDS,
    "evening_poll": scheduler.POLL_SECONDS,
    "diary_poll": scheduler.POLL_SECONDS,
    "sunday_report_poll": scheduler.POLL_SECONDS,
    "anki_poll": scheduler.POLL_SECONDS,
    "nudge_poll": scheduler.POLL_SECONDS,
    "couple_poll": scheduler.POLL_SECONDS,
    "streak_rollover": scheduler.STREAK_POLL_SECONDS,
    "monthly_freeze_reset": scheduler.STREAK_POLL_SECONDS,
    "heartbeat": scheduler.HEARTBEAT_POLL_SECONDS,
    "backup_freshness": scheduler.HEARTBEAT_POLL_SECONDS,
    "watch_poll": scheduler.POLL_SECONDS,
}


@pytest.fixture
def scheduled_app():
    app = ApplicationBuilder().token("1:FAKE-W1-SCHEDULER").build()
    scheduler.start_scheduler(app)
    yield app
    scheduler.stop_scheduler(app)


def test_start_scheduler_registers_every_job_by_name(scheduled_app) -> None:
    registered = {job.name for job in scheduled_app.job_queue.jobs()}
    assert registered == set(_EXPECTED_JOBS), (
        f"missing={set(_EXPECTED_JOBS) - registered} "
        f"unexpected={registered - set(_EXPECTED_JOBS)}"
    )


def test_start_scheduler_uses_interval_triggers(scheduled_app) -> None:
    for job in scheduled_app.job_queue.jobs():
        trigger = job.job.trigger
        assert type(trigger).__name__ == "IntervalTrigger", (
            f"{job.name} is scheduled with {type(trigger).__name__}"
        )
        assert (
            trigger.interval.total_seconds() == _EXPECTED_JOBS[job.name]
        ), f"{job.name} interval={trigger.interval}"


def test_start_scheduler_is_idempotent(scheduled_app) -> None:
    """A second call must not double-register — restarts happen."""
    scheduler.start_scheduler(scheduled_app)
    names = [job.name for job in scheduled_app.job_queue.jobs()]
    assert sorted(names) == sorted(_EXPECTED_JOBS)


def test_stop_scheduler_removes_every_job(scheduled_app) -> None:
    scheduler.stop_scheduler(scheduled_app)
    remaining = {
        job.name
        for job in scheduled_app.job_queue.jobs()
        if job.name in _EXPECTED_JOBS and not job.removed
    }
    assert remaining == set()
