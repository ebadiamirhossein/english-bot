"""S4c off-site backup copy + freshness alerting."""

from __future__ import annotations

import asyncio
import os
import stat
import subprocess
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.scheduler import run_backup_freshness_check
from app.services.backup_freshness import (
    check_offsite_freshness,
    list_offsite_candidates,
    newest_offsite,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_SH = REPO_ROOT / "scripts" / "backup.sh"
MIN_BYTES = 10240
SECRET_PAYLOAD = b"SECRET_JOURNAL_PAYLOAD_SHOULD_NEVER_APPEAR_IN_LOGS_991\n"


def _write_fake_dump(path: Path, *, size: int = MIN_BYTES + 64) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Distinct payload so privacy greps can catch leaks; pad to size floor.
    body = SECRET_PAYLOAD + (b"x" * max(0, size - len(SECRET_PAYLOAD)))
    path.write_bytes(body[:size])
    return path


def _run_bash(script: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=str(REPO_ROOT),
    )


def _source_call(fn_and_args: str, *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Source backup.sh (no main) and run a function call."""
    script = textwrap.dedent(
        f"""
        set -euo pipefail
        source "{BACKUP_SH}"
        {fn_and_args}
        """
    )
    return _run_bash(script, env=env)


# --- shell: off-site copy -----------------------------------------------------


def test_offsite_copy_after_success_size_matches(tmp_path: Path) -> None:
    local = tmp_path / "local"
    offsite = tmp_path / "offsite"
    local.mkdir()
    offsite.mkdir()
    dump = _write_fake_dump(local / "english_bot_2026-08-10_0400.dump")
    env = {
        "BACKUP_DIR": str(local),
        "BACKUP_OFFSITE_DIR": str(offsite),
        "BACKUP_OFFSITE_KEEP": "14",
    }
    result = _source_call(f'offsite_copy "{dump}"', env=env)
    assert result.returncode == 0, result.stderr
    dest = offsite / dump.name
    assert dest.is_file()
    assert dest.stat().st_size == dump.stat().st_size
    assert SECRET_PAYLOAD.decode() not in result.stderr
    assert SECRET_PAYLOAD.decode() not in result.stdout


def test_local_below_floor_no_offsite_via_main(tmp_path: Path) -> None:
    """Fake pg_dump writes a tiny file → main dies before offsite_copy."""
    local = tmp_path / "local"
    offsite = tmp_path / "offsite"
    local.mkdir()
    offsite.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_pg = bin_dir / "pg_dump"
    fake_pg.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            # Honor -f outfile (last arg after -f).
            outfile=""
            while [[ $# -gt 0 ]]; do
              if [[ "$1" == "-f" ]]; then
                outfile="$2"
                shift 2
                continue
              fi
              shift
            done
            printf 'tiny' > "$outfile"
            """
        ),
        encoding="utf-8",
    )
    fake_pg.chmod(fake_pg.stat().st_mode | stat.S_IXUSR)
    env = {
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "BACKUP_DIR": str(local),
        "BACKUP_OFFSITE_DIR": str(offsite),
        "DATABASE_URL": "postgresql://u:p@127.0.0.1:5433/english_bot",
    }
    result = _run_bash(f'bash "{BACKUP_SH}"', env=env)
    assert result.returncode != 0
    assert "too small" in result.stderr
    assert list(offsite.glob("english_bot_*.dump")) == []


def test_offsite_path_inside_repo_refused(tmp_path: Path) -> None:
    local = tmp_path / "local"
    local.mkdir()
    dump = _write_fake_dump(local / "english_bot_2026-08-10_0400.dump")
    inside = REPO_ROOT / "tmp-s4c-offsite-test"
    inside.mkdir(exist_ok=True)
    try:
        env = {
            "BACKUP_DIR": str(local),
            "BACKUP_OFFSITE_DIR": str(inside),
        }
        result = _source_call(f'offsite_copy "{dump}"', env=env)
        assert result.returncode != 0
        assert "inside the git repo" in result.stderr
    finally:
        # Leave no leftover if empty; ignore if something else landed.
        try:
            inside.rmdir()
        except OSError:
            pass


def test_offsite_path_inside_backup_dir_refused(tmp_path: Path) -> None:
    local = tmp_path / "local"
    nested = local / "nested-offsite"
    local.mkdir()
    nested.mkdir()
    dump = _write_fake_dump(local / "english_bot_2026-08-10_0400.dump")
    env = {
        "BACKUP_DIR": str(local),
        "BACKUP_OFFSITE_DIR": str(nested),
    }
    result = _source_call(f'offsite_copy "{dump}"', env=env)
    assert result.returncode != 0
    assert "inside BACKUP_DIR" in result.stderr or "must not equal" in result.stderr


def test_missing_offsite_dir_loud_no_mkdir(tmp_path: Path) -> None:
    local = tmp_path / "local"
    local.mkdir()
    missing = tmp_path / "does-not-exist"
    dump = _write_fake_dump(local / "english_bot_2026-08-10_0400.dump")
    env = {
        "BACKUP_DIR": str(local),
        "BACKUP_OFFSITE_DIR": str(missing),
    }
    result = _source_call(f'offsite_copy "{dump}"', env=env)
    assert result.returncode != 0
    assert "does not exist" in result.stderr
    assert not missing.exists()


def test_unwritable_offsite_dir_loud(tmp_path: Path) -> None:
    local = tmp_path / "local"
    offsite = tmp_path / "offsite"
    local.mkdir()
    offsite.mkdir()
    offsite.chmod(0o555)
    dump = _write_fake_dump(local / "english_bot_2026-08-10_0400.dump")
    try:
        env = {
            "BACKUP_DIR": str(local),
            "BACKUP_OFFSITE_DIR": str(offsite),
        }
        result = _source_call(f'offsite_copy "{dump}"', env=env)
        assert result.returncode != 0
        assert "not writable" in result.stderr
    finally:
        offsite.chmod(0o755)


def test_retention_keeps_n_and_counts_icloud_placeholders(tmp_path: Path) -> None:
    local = tmp_path / "local"
    offsite = tmp_path / "offsite"
    local.mkdir()
    offsite.mkdir()
    # Three existing generations: two real dumps + one iCloud placeholder.
    for stamp in ("2026-08-01_0400", "2026-08-02_0400"):
        _write_fake_dump(offsite / f"english_bot_{stamp}.dump", size=100)
    (offsite / ".english_bot_2026-08-03_0400.dump.icloud").write_bytes(b"placeholder")
    dump = _write_fake_dump(local / "english_bot_2026-08-10_0400.dump")
    env = {
        "BACKUP_DIR": str(local),
        "BACKUP_OFFSITE_DIR": str(offsite),
        "BACKUP_OFFSITE_KEEP": "2",
    }
    result = _source_call(f'offsite_copy "{dump}"', env=env)
    assert result.returncode == 0, result.stderr
    remaining = sorted(
        p.name
        for p in offsite.iterdir()
        if p.name.startswith("english_bot_")
        or p.name.startswith(".english_bot_")
    )
    assert len(remaining) == 2
    assert "english_bot_2026-08-10_0400.dump" in remaining
    # Oldest real dump should be gone.
    assert "english_bot_2026-08-01_0400.dump" not in remaining


def test_failed_offsite_prunes_nothing(tmp_path: Path) -> None:
    local = tmp_path / "local"
    offsite = tmp_path / "offsite"
    local.mkdir()
    offsite.mkdir()
    keep_me = offsite / "english_bot_2026-08-01_0400.dump"
    _write_fake_dump(keep_me, size=100)
    # Unwritable destination after files already exist → fail; keep_me stays.
    offsite.chmod(0o555)
    dump = _write_fake_dump(local / "english_bot_2026-08-10_0400.dump")
    try:
        env = {
            "BACKUP_DIR": str(local),
            "BACKUP_OFFSITE_DIR": str(offsite),
            "BACKUP_OFFSITE_KEEP": "1",
        }
        result = _source_call(f'offsite_copy "{dump}"', env=env)
        assert result.returncode != 0
        assert keep_me.is_file()
    finally:
        offsite.chmod(0o755)


def test_stale_partial_cleaned_at_start(tmp_path: Path) -> None:
    local = tmp_path / "local"
    offsite = tmp_path / "offsite"
    local.mkdir()
    offsite.mkdir()
    stale = offsite / "english_bot_2026-08-09_0400.dump.partial"
    stale.write_bytes(b"orphan")
    dump = _write_fake_dump(local / "english_bot_2026-08-10_0400.dump")
    env = {
        "BACKUP_DIR": str(local),
        "BACKUP_OFFSITE_DIR": str(offsite),
    }
    result = _source_call(f'offsite_copy "{dump}"', env=env)
    assert result.returncode == 0, result.stderr
    assert not stale.exists()
    assert (offsite / dump.name).is_file()


def test_unset_offsite_is_silent_skip(tmp_path: Path) -> None:
    local = tmp_path / "local"
    local.mkdir()
    dump = _write_fake_dump(local / "english_bot_2026-08-10_0400.dump")
    env = {
        "BACKUP_DIR": str(local),
        "BACKUP_OFFSITE_DIR": "",
    }
    result = _source_call(f'offsite_copy "{dump}"', env=env)
    assert result.returncode == 0, result.stderr
    assert "OFFSITE" not in result.stderr


# --- Python freshness ---------------------------------------------------------


def test_freshness_unset_skipped() -> None:
    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    assert check_offsite_freshness("", now=now) == "skipped"
    assert check_offsite_freshness(None, now=now) == "skipped"


def test_freshness_fresh_ok(tmp_path: Path) -> None:
    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    dump = _write_fake_dump(tmp_path / "english_bot_2026-08-10_0400.dump")
    os.utime(dump, (now.timestamp(), now.timestamp()))
    assert check_offsite_freshness(str(tmp_path), now=now) == "ok"


def test_freshness_stale_beyond_threshold(tmp_path: Path) -> None:
    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    dump = _write_fake_dump(tmp_path / "english_bot_2026-08-01_0400.dump")
    old = now - timedelta(hours=49)
    os.utime(dump, (old.timestamp(), old.timestamp()))
    assert check_offsite_freshness(str(tmp_path), now=now) == "stale"


def test_freshness_icloud_placeholder_counts_as_present(tmp_path: Path) -> None:
    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    placeholder = tmp_path / ".english_bot_2026-08-10_0400.dump.icloud"
    placeholder.write_bytes(b"icloud-stub")
    os.utime(placeholder, (now.timestamp(), now.timestamp()))
    assert list_offsite_candidates(tmp_path)
    assert newest_offsite(tmp_path) is not None
    assert check_offsite_freshness(str(tmp_path), now=now) == "ok"


def test_freshness_missing_dir_stale(tmp_path: Path) -> None:
    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    assert (
        check_offsite_freshness(str(tmp_path / "nope"), now=now) == "stale"
    )


def test_freshness_alert_throttled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPERATOR_TELEGRAM_ID", "999901")
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv(
        "ALERT_THROTTLE_FILE", str(tmp_path / "runtime" / "throttle.json")
    )
    monkeypatch.setenv("BACKUP_OFFSITE_DIR", str(tmp_path / "empty-offsite"))
    (tmp_path / "empty-offsite").mkdir()
    (tmp_path / "runtime").mkdir()

    from app import config as config_mod

    settings = config_mod.load_settings()
    monkeypatch.setattr("app.scheduler.load_settings", lambda: settings)
    monkeypatch.setattr("app.services.alerts.load_settings", lambda: settings)

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)

    status1 = asyncio.run(run_backup_freshness_check(app, now=now))
    assert status1 == "stale"
    assert app.bot.send_message.await_count == 1
    sent = app.bot.send_message.await_args.kwargs["text"]
    assert SECRET_PAYLOAD.decode().strip() not in sent
    assert "STALE" in sent

    status2 = asyncio.run(
        run_backup_freshness_check(app, now=now + timedelta(minutes=5))
    )
    assert status2 == "stale"
    assert app.bot.send_message.await_count == 1  # throttled


def test_freshness_unset_no_alert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPERATOR_TELEGRAM_ID", "999902")
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv(
        "ALERT_THROTTLE_FILE", str(tmp_path / "runtime" / "throttle.json")
    )
    monkeypatch.setenv("BACKUP_OFFSITE_DIR", "")
    (tmp_path / "runtime").mkdir()

    from app import config as config_mod

    settings = config_mod.load_settings()
    monkeypatch.setattr("app.scheduler.load_settings", lambda: settings)
    monkeypatch.setattr("app.services.alerts.load_settings", lambda: settings)

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    status = asyncio.run(run_backup_freshness_check(app, now=now))
    assert status == "skipped"
    assert app.bot.send_message.await_count == 0


def test_freshness_fresh_silent_no_alert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    offsite = tmp_path / "offsite"
    offsite.mkdir()
    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    dump = _write_fake_dump(offsite / "english_bot_2026-08-10_0400.dump")
    os.utime(dump, (now.timestamp(), now.timestamp()))

    monkeypatch.setenv("OPERATOR_TELEGRAM_ID", "999903")
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv(
        "ALERT_THROTTLE_FILE", str(tmp_path / "runtime" / "throttle.json")
    )
    monkeypatch.setenv("BACKUP_OFFSITE_DIR", str(offsite))
    (tmp_path / "runtime").mkdir()

    from app import config as config_mod

    settings = config_mod.load_settings()
    monkeypatch.setattr("app.scheduler.load_settings", lambda: settings)
    monkeypatch.setattr("app.services.alerts.load_settings", lambda: settings)

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    status = asyncio.run(run_backup_freshness_check(app, now=now))
    assert status == "ok"
    assert app.bot.send_message.await_count == 0
