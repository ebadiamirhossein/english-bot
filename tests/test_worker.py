"""W1b: the APScheduler worker — the lock, the job table, the job bodies.

Known issue #54 is the reason this file asserts registration and not just
predicates: five v2 scheduler tests passed while checking only the "is this
user due" functions, so all five would have passed against a scheduler that
registered nothing at all. The expected table below is written out by hand —
deriving it from ``jobs.JOBS`` would assert that the table equals itself
(CLAUDE.md §3 rule 5).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from apscheduler.triggers.interval import IntervalTrigger

from apps.worker import jobs as worker_jobs
from apps.worker.main import (
    build_scheduler,
    main,
    worker_lock_path,
    worker_log_path,
)
from core.config import load_settings
from core.instance_lock import InstanceLock

# name -> interval in seconds.
EXPECTED_JOBS = {
    "streak_rollover": 900,
    "monthly_freeze_reset": 900,
    "monthly_reset": 900,
    "heartbeat": 3600,
    "backup_freshness": 3600,
}

# The delivery jobs still belong to apps/bot until W20: each one sends a
# Telegram message, and moving the job without the channel means moving
# Telegram into the worker.
BOT_ONLY_JOBS = {
    "morning_poll",
    "evening_poll",
    "diary_poll",
    "sunday_report_poll",
    "anki_poll",
    "nudge_poll",
    "couple_poll",
    "watch_poll",
}


@pytest.fixture
def runtime_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("INSTANCE_LOCK_FILE", str(tmp_path / "bot.lock"))
    monkeypatch.setenv("HEARTBEAT_FILE", str(tmp_path / "last_job_fire"))
    return tmp_path


# --- registration -------------------------------------------------------------


def test_worker_registers_every_job_by_name() -> None:
    registered = {job.id for job in build_scheduler().get_jobs()}
    assert registered == set(EXPECTED_JOBS)


def test_worker_jobs_use_an_interval_trigger_with_the_right_period() -> None:
    for job in build_scheduler().get_jobs():
        trigger = job.trigger
        assert isinstance(trigger, IntervalTrigger), (
            f"{job.id} is scheduled with {type(trigger).__name__}"
        )
        assert trigger.interval.total_seconds() == EXPECTED_JOBS[job.id], (
            f"{job.id} interval={trigger.interval}"
        )


def test_worker_does_not_take_the_delivery_jobs() -> None:
    """They stay in apps/bot until W20 — with the channel that sends them."""
    registered = {job.id for job in build_scheduler().get_jobs()}
    assert registered & BOT_ONLY_JOBS == set()


def test_every_job_runs_at_most_one_instance() -> None:
    """A poll that overruns its interval must not stack up behind itself."""
    for job in build_scheduler().get_jobs():
        assert job.max_instances == 1
        assert job.coalesce is True


def test_job_table_entries_are_callable_with_no_arguments() -> None:
    for job in worker_jobs.JOBS:
        assert callable(job.func)
        assert job.func.__code__.co_argcount == 0


# --- the instance lock --------------------------------------------------------


def test_worker_lock_is_not_the_bot_lock(runtime_dir: Path) -> None:
    """Sharing one lock file would mean the bot and the worker exclude each other."""
    settings = load_settings()
    assert worker_lock_path(settings) != Path(settings.instance_lock_file)
    assert worker_lock_path(settings).parent == Path(
        settings.instance_lock_file
    ).parent
    assert worker_lock_path(settings).name == "worker.lock"


def test_worker_logs_to_its_own_file(runtime_dir: Path) -> None:
    """Two processes rotating one RotatingFileHandler lose each other's lines."""
    settings = load_settings()
    assert worker_log_path(settings) != Path(settings.log_file)
    assert worker_log_path(settings).name == "worker.log"


def test_second_worker_refuses_and_exits_non_zero(
    runtime_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """W0 risk R3: exactly one scheduler process, or every job fires twice."""

    def _must_not_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("scheduler was built despite the held lock")

    monkeypatch.setattr("apps.worker.main.build_scheduler", _must_not_run)

    held = InstanceLock(worker_lock_path(load_settings()))
    held.acquire()
    try:
        assert main() == 1
    finally:
        held.release()
    assert "holds the lock" in capsys.readouterr().err


# --- job bodies ---------------------------------------------------------------


def test_streak_rollover_job_calls_the_core_predicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(
        worker_jobs, "run_streak_rollover", lambda: calls.append(1)
    )
    worker_jobs.streak_rollover()
    assert calls == [1]


def test_monthly_jobs_call_their_core_functions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        worker_jobs, "run_monthly_freeze_reset", lambda: calls.append("freeze")
    )
    monkeypatch.setattr(
        worker_jobs, "run_monthly_reset", lambda: calls.append("reset")
    )
    worker_jobs.monthly_freeze_reset()
    worker_jobs.monthly_reset()
    assert calls == ["freeze", "reset"]


def test_heartbeat_job_reads_but_never_writes(runtime_dir: Path) -> None:
    """The bot owns the heartbeat file until W20.

    A worker that touched it would keep the file fresh while the bot was dead,
    and the staleness alarm would never fire again.
    """
    heartbeat_file = runtime_dir / "last_job_fire"
    assert not heartbeat_file.exists()
    worker_jobs.heartbeat()
    assert not heartbeat_file.exists()


def test_heartbeat_job_logs_stale_when_nothing_has_fired(
    runtime_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="apps.worker.jobs"):
        worker_jobs.heartbeat()
    assert any("STALE" in r.getMessage() for r in caplog.records)


def test_backup_freshness_folder_half_is_silent_while_unset(
    runtime_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An unset BACKUP_OFFSITE_DIR skips quietly — a synced folder was always
    optional. The R2 half, checked below, is the one that must not be quiet."""
    monkeypatch.setenv("BACKUP_OFFSITE_DIR", "")
    monkeypatch.setenv("BACKUP_R2_REQUIRED", "0")
    with caplog.at_level(logging.INFO, logger="apps.worker.jobs"):
        worker_jobs.backup_freshness()
    messages = [r.getMessage() for r in caplog.records]
    assert any("skipped" in m for m in messages)
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)


def test_backup_freshness_r2_half_is_loud_while_unset(
    runtime_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """W1c closes known issue #31, and this is the assertion that changed.

    Until W1c an unconfigured backup and a healthy one produced the same
    output, which made the check worthless on the one machine where nothing
    was being backed up. Unset R2 is now an ERROR unless the machine has
    explicitly opted out.
    """
    from core import config as config_mod
    from tests.test_backup_r2 import forget_r2_env, write_dotenv

    monkeypatch.setenv("BACKUP_OFFSITE_DIR", "")
    forget_r2_env(monkeypatch)

    # The job calls load_settings() itself, so the `.env` it reads has to be
    # pinned here or the repo's own file answers instead — which is how this
    # test came to pass on the server and fail on the Mac (#64).
    settings = config_mod.load_settings(dotenv_path=write_dotenv(runtime_dir))
    monkeypatch.setattr("apps.worker.jobs.load_settings", lambda: settings)
    with caplog.at_level(logging.INFO, logger="apps.worker.jobs"):
        worker_jobs.backup_freshness()
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("R2 UNCONFIGURED" in r.getMessage() for r in errors)


def test_backup_freshness_job_reports_a_stale_directory(
    runtime_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    empty = runtime_dir / "offsite"
    empty.mkdir()
    monkeypatch.setenv("BACKUP_OFFSITE_DIR", str(empty))
    with caplog.at_level(logging.ERROR, logger="apps.worker.jobs"):
        worker_jobs.backup_freshness()
    assert any("STALE" in r.getMessage() for r in caplog.records)


def test_run_job_swallows_and_logs_a_failing_job(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One broken job must not take the scheduler down with it."""

    def _boom() -> None:
        raise RuntimeError("job exploded")

    job = worker_jobs.Job("explodes", _boom, 60, 1)
    with caplog.at_level(logging.ERROR, logger="apps.worker.jobs"):
        worker_jobs.run_job(job)  # must not raise
    assert any("name=explodes" in r.getMessage() for r in caplog.records)
