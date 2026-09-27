"""W24r (D): the weekly automatic video refresh, `refresh_videos`.

**The user action:** none — the operator asked for no manual weekly step
(2026-09-27). A learner's daily video (W24d) is drawn from a pool that empties
itself after 30 days (`purge_stale`), so the pool is refreshed by the worker
every Monday at about 04:00 Europe/Vilnius, **with the same code as
`core.video.refresh --live --apply`**, at most 40 transcripts a run, and only
while `VIDEO_AUTO_REFRESH=1` is in `.env`.

**A billed call the system makes on a schedule**, on the operator's explicit
ruling of 2026-09-27 (cost measured under $1 a run) — an exception to #196's
*billed runs are operator-run*, for this job only. **Nothing here spends
anything:** every YouTube and Apify function is replaced in process, and the
session-scoped `netguard` (`tests/conftest.py`) refuses any socket.

**The flag is read the way it is really set — from a `.env` file**
(CLAUDE.md §3 rule 3). **The clock is fixed** at a Monday in 2030 (rule 6): a
refresh that read the wall clock instead would stamp and purge against
2026, and the assertions below would see it.

**RED BEFORE THE CODE (2026-09-27):** `Settings.video_auto_refresh`,
`apps.worker.jobs.jobs_for`, `refresh_videos` and `core.video.refresh.run_scheduled`
did not exist — every test failed on the attribute or the import. The ceiling
and fixed-now tests are also shown red by mutation (decisions log, W24r (D)).
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg
import pytest
from apscheduler.triggers.cron import CronTrigger

from apps.worker import jobs as worker_jobs
from apps.worker.main import build_scheduler
from core import video_api
from core.config import load_settings
from core.services import video as video_svc
from core.video import refresh
from tests.test_backup_r2 import write_dotenv

VILNIUS = ZoneInfo("Europe/Vilnius")
#: A Monday, 04:00 in Vilnius — the job's own slot, far from the wall clock.
FIXED = datetime(2030, 1, 7, 4, 0, tzinfo=VILNIUS).astimezone(timezone.utc)
PREFIX = "w24rrf"
KEY = "VIDEO_AUTO_REFRESH"


# ── the flag, from `.env` ───────────────────────────────────────────────────


@pytest.fixture
def no_flag_left_behind(monkeypatch: pytest.MonkeyPatch):
    """`load_dotenv` writes the file's value into `os.environ`; `setenv` first
    records the true original so teardown restores it (test_monitoring's
    `no_dsn_left_behind`, the same trap)."""
    monkeypatch.setenv(KEY, "")
    monkeypatch.delenv(KEY)
    yield


def test_the_flag_is_off_unless_the_env_file_sets_it(tmp_path, no_flag_left_behind) -> None:
    from core import config as config_mod

    assert config_mod.load_settings(dotenv_path=write_dotenv(tmp_path)).video_auto_refresh is False


def test_the_flag_is_read_from_the_env_file(tmp_path, no_flag_left_behind) -> None:
    from core import config as config_mod

    settings = config_mod.load_settings(dotenv_path=write_dotenv(tmp_path, **{KEY: "1"}))
    assert settings.video_auto_refresh is True


# ── registration ────────────────────────────────────────────────────────────


def _registered(settings) -> dict:
    return {job.id: job for job in build_scheduler(worker_jobs.jobs_for(settings)).get_jobs()}


def test_the_job_is_not_registered_without_the_flag() -> None:
    settings = dataclasses.replace(load_settings(), video_auto_refresh=False)
    assert set(_registered(settings)) == {"push_poll", "assign_video"}


def test_the_job_is_registered_weekly_monday_0400_vilnius_with_the_flag() -> None:
    settings = dataclasses.replace(load_settings(), video_auto_refresh=True)
    registered = _registered(settings)
    assert set(registered) == {"push_poll", "assign_video", "refresh_videos"}
    trigger = registered["refresh_videos"].trigger
    assert isinstance(trigger, CronTrigger)
    # From a Sunday noon (2026-09-27, summer time) the next fire is Monday
    # 04:00 Vilnius = 01:00 UTC; from a winter Sunday it is 02:00 UTC.
    sunday = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    assert trigger.get_next_fire_time(None, sunday) == datetime(
        2026, 9, 28, 4, 0, tzinfo=VILNIUS)
    assert trigger.get_next_fire_time(None, sunday).astimezone(timezone.utc) == datetime(
        2026, 9, 28, 1, 0, tzinfo=timezone.utc)
    winter = datetime(2026, 12, 6, 12, 0, tzinfo=timezone.utc)
    assert trigger.get_next_fire_time(None, winter).astimezone(timezone.utc) == datetime(
        2026, 12, 7, 2, 0, tzinfo=timezone.utc)
    assert registered["refresh_videos"].max_instances == 1


def test_the_worker_entrypoint_registers_it_from_the_environment(
        tmp_path, monkeypatch) -> None:
    """`main()` builds its scheduler from `jobs_for(load_settings())`, so the
    flag in the environment decides — checked through the real entrypoint, with
    the scheduler's `start` stubbed (CLAUDE.md §5b: no loop is run)."""
    from apps.worker import main as worker_main

    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("INSTANCE_LOCK_FILE", str(tmp_path / "bot.lock"))
    monkeypatch.setenv("HEARTBEAT_FILE", str(tmp_path / "last_job_fire"))
    monkeypatch.setenv(KEY, "1")
    built: list[set[str]] = []
    real_build = worker_main.build_scheduler

    def _build(jobs):
        scheduler = real_build(jobs)
        built.append({job.id for job in scheduler.get_jobs()})
        monkeypatch.setattr(scheduler, "start", lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
        monkeypatch.setattr(scheduler, "shutdown", lambda wait=True: None)
        return scheduler

    monkeypatch.setattr(worker_main, "build_scheduler", _build)
    monkeypatch.setattr(worker_main, "configure_logging", lambda settings: None)
    monkeypatch.setattr(worker_main.monitoring, "init_monitoring", lambda *a, **k: None)
    assert worker_main.main() == 0
    assert built == [{"push_poll", "assign_video", "refresh_videos"}]


# ── the run: the same code as `--live --apply`, stubbed at the network ──────


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn
        conn.rollback()
        conn.execute(
            "DELETE FROM video_coverage WHERE video_id IN "
            "(SELECT id FROM videos WHERE youtube_id LIKE %s)", (PREFIX + "%",))
        conn.execute("DELETE FROM videos WHERE youtube_id LIKE %s", (PREFIX + "%",))
        conn.commit()


@pytest.fixture
def network(monkeypatch):
    """YouTube lists four new videos per channel; the Apify listing finds
    nothing; every fetch fails retryably. Records what the fetch was asked for."""
    seen: dict[str, list] = {"fetched": [], "handles": []}

    def resolve(handle, *, api_key):
        seen["handles"].append(handle)
        return video_api.ChannelRef(handle=handle, channel_id="UC" + handle[1:9],
                                    title="t", uploads_playlist_id="UU" + handle[1:9])

    def list_videos(playlist, *, api_key, max_videos):
        n = len(seen["handles"])
        return [f"{PREFIX}{n:02d}{i}" for i in range(4)]

    def metadata(ids, *, api_key):
        return {v: video_api.VideoMeta(youtube_id=v, title=f"W24R PROBE TITLE {v}",
                                       duration_s=300, published_at=FIXED) for v in ids}

    def fetch(ids, *, token, actor, listings, dump_to):
        seen["fetched"].extend(ids)
        return {v: video_api.TranscriptFetchFailed("stub: no network in tests") for v in ids}

    monkeypatch.setattr(video_api, "resolve_handle", resolve)
    monkeypatch.setattr(video_api, "list_channel_videos", list_videos)
    monkeypatch.setattr(video_api, "fetch_video_metadata", metadata)
    monkeypatch.setattr(video_api, "list_transcripts", lambda ids, **k: {})
    monkeypatch.setattr(video_api, "fetch_transcripts", fetch)
    return seen


def _keyed():
    return dataclasses.replace(load_settings(), youtube_api_key="yt-test", apify_token="apify-test")


def test_the_ceiling_is_forty_transcripts_whatever_is_asked(db, network) -> None:
    """Twelve channels × four listed = 48 pending; asked for 500, the run
    fetches 40 — `AUTO_TRANSCRIPT_CEILING`, hardcoded here (§3 rule 5)."""
    refresh.run_scheduled(_keyed(), now=FIXED, limit=500)
    assert len(network["handles"]) == 12
    assert len(network["fetched"]) == 40
    assert all(v.startswith(PREFIX) for v in network["fetched"])


def test_it_runs_over_the_fixed_now_and_purges_against_it(db, network) -> None:
    """The rows it writes are stamped with `now`, and the 30-day purge is
    measured from `now`: a row read 31 days before it loses its title, one read
    29 days before keeps it. Against the wall clock (2026) neither would be old."""
    old = video_svc.upsert_video(
        db, youtube_id=f"{PREFIX}old", channel_id="UCold", accent="british", track="life",
        title="old", duration_s=300, published_at=None, now=FIXED - timedelta(days=31))
    recent = video_svc.upsert_video(
        db, youtube_id=f"{PREFIX}new", channel_id="UCnew", accent="british", track="life",
        title="recent", duration_s=300, published_at=None, now=FIXED - timedelta(days=29))
    db.commit()
    summary = refresh.run_scheduled(_keyed(), now=FIXED)
    stamps = {r[0] for r in db.execute(
        "SELECT DISTINCT metadata_refreshed_at FROM videos WHERE youtube_id LIKE %s "
        "AND youtube_id NOT IN (%s, %s)", (PREFIX + "%", f"{PREFIX}old", f"{PREFIX}new"))}
    assert stamps == {FIXED}
    titles = dict(db.execute("SELECT id, title FROM videos WHERE id IN (%s, %s)",
                             (old, recent)).fetchall())
    assert titles == {old: None, recent: "recent"}
    assert summary["purged"] == 1


def test_the_job_logs_one_line_of_counts_and_no_title(db, network, monkeypatch, caplog, capsys) -> None:
    monkeypatch.setattr(worker_jobs, "load_settings", _keyed)
    monkeypatch.setattr(worker_jobs, "_now", lambda: FIXED)
    with caplog.at_level(logging.INFO, logger="apps.worker.jobs"):
        worker_jobs.refresh_videos()
    lines = [r.getMessage() for r in caplog.records if r.name == "apps.worker.jobs"]
    assert len(lines) == 1
    line = lines[0]
    assert line.startswith("refresh_videos ok ")
    for key in ("ok=", "pending=", "unavailable=", "failed=", "stored=0", "channels_failed=0",
                "purged="):
        assert key in line, (key, line)
    assert "PROBE TITLE" not in caplog.text
    assert capsys.readouterr().out == "", "the CLI's printout is not the worker's log"


def test_a_run_that_cannot_start_raises_so_the_worker_reports_it(monkeypatch) -> None:
    """No keys → `_live` refuses (exit 1) → `run_scheduled` raises, and
    `run_job` sends it to Sentry as `job:refresh_videos`."""
    settings = dataclasses.replace(load_settings(), youtube_api_key="", apify_token="")
    monkeypatch.setattr(worker_jobs, "load_settings", lambda: settings)
    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(worker_jobs.monitoring, "capture_exception",
                        lambda exc, *, user_id, route: captured.append((type(exc).__name__, route)))
    worker_jobs.run_job(worker_jobs.REFRESH_VIDEOS)
    assert captured == [("RefreshFailed", "job:refresh_videos")]
