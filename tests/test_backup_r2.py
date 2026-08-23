"""W1c — the Cloudflare R2 off-site copy, its retention, and its alarm.

Three rules from CLAUDE.md §3 shape this file, and each is a real failure:

* **rule 3 — test configuration the way it is really set.** Known issue #26:
  ``backup.sh`` read ``BACKUP_DIR`` from the process environment only, so
  configuring it in ``.env`` looked unset and the copy silently skipped.
  Eighteen tests passed because the harness *exported* the variables. Every R2
  test below that exercises configuration writes a temp ``.env`` and exports
  nothing.
* **rule 5 — never derive the expected value from the function under test.**
  The retention tests hand-write which keys survive. They never ask
  ``r2_prune_plan`` what it kept.
* **rule 6 — never depend on wall-clock date.** Every timestamp here is
  hardcoded on both sides.

Nothing here reaches Cloudflare. The shell tests put a recording ``aws`` stub
on PATH and the Python tests inject a runner, so the argv, the key layout and
the retention decision are all checked offline — and none of that proves the
provider contract (rule 2). The first real call is the human's server run.
"""

from __future__ import annotations

import ast
import asyncio
import os
import stat
import subprocess
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.bot import scheduler as bot_scheduler
from apps.bot.scheduler import run_r2_freshness_check
from apps.worker import jobs as worker_jobs
from core.services.backup_freshness import (
    R2Config,
    R2Object,
    check_r2_freshness,
    newest_r2_object,
    parse_r2_listing,
    r2_command,
    r2_config_from_settings,
    r2_env,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_SH = REPO_ROOT / "scripts" / "backup.sh"
RESTORE_R2_SH = REPO_ROOT / "scripts" / "restore_from_r2.sh"
DEPLOYMENT_MD = REPO_ROOT / "docs" / "DEPLOYMENT.md"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
UNIT_DIR = REPO_ROOT / "deploy" / "systemd"
MIN_BYTES = 10240

# Distinctive so a leak grep cannot pass by accident.
FAKE_SECRET = "R2SECRET_must_never_appear_anywhere_7f3a91"
FAKE_ACCESS_KEY = "R2ACCESSKEYID0001"
FAKE_ENDPOINT = "https://acct123.r2.cloudflarestorage.com"
FAKE_BUCKET = "english-bot-backups"

R2_ENV_KEYS = (
    "R2_ACCOUNT_ID",
    "R2_BUCKET",
    "R2_ENDPOINT",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
)

# Enough for load_settings() to succeed when the temp .env below is the only
# file it reads. Real process variables still win (override=False), so these are
# a floor, never an override.
_MINIMUM_ENV = {
    "DATABASE_URL": "postgresql://tests@127.0.0.1/hermetic",
    "ANTHROPIC_API_KEY": "test-dummy-anthropic-key",
}


def settings_from_dotenv(tmp_path: Path, **lines: str):
    """Load Settings from a `.env` holding exactly *lines*, and leave no trace.

    The restore matters as much as the load. ``load_dotenv`` writes straight
    into ``os.environ``, and ``monkeypatch`` only reverses changes *it* made —
    so without this, values from one test's temp `.env` survive into every test
    that runs after it. That is not hypothetical: it made a later test read a
    fake R2 endpoint and attempt a real network call.
    """
    path = write_dotenv(tmp_path, **lines)
    from core import config as config_mod

    before = os.environ.copy()
    try:
        return config_mod.load_settings(dotenv_path=path)
    finally:
        os.environ.clear()
        os.environ.update(before)


def write_dotenv(tmp_path: Path, **lines: str) -> Path:
    """Write a `.env` holding exactly *lines*, and return its path.

    **Why these tests write a file instead of only setting variables.**
    ``load_dotenv()`` searches upward from ``packages/core/config.py``, so it
    finds the repo-root `.env` regardless of the caller (known issue #64). A
    test that does ``monkeypatch.delenv("BACKUP_R2_REQUIRED")`` and then calls
    ``load_settings()`` therefore has the value put straight back from the
    developer's own `.env` — the default it means to exercise is never
    exercised, and the suite passes or fails depending on whose machine it runs
    on. That is exactly what happened once #72's ``BACKUP_R2_REQUIRED=0`` line
    was added to the Mac's `.env`: five tests turned red on one machine and
    stayed green on the server.

    Naming the file makes the answer hermetic *and* keeps CLAUDE.md §3 rule 3
    satisfied for the right reason: configuration is exercised through the only
    path it is really set by, a `.env` file, rather than through a process
    variable no operator uses.
    """
    path = tmp_path / ".env"
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in {**_MINIMUM_ENV, **lines}.items())
        + "\n",
        encoding="utf-8",
    )
    return path


def forget_r2_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop every R2 variable from the process environment.

    Paired with :func:`write_dotenv`: process variables win over the file, so
    both halves are needed before a default can be observed at all.
    """
    for key in R2_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("BACKUP_R2_REQUIRED", raising=False)


# --- helpers ------------------------------------------------------------------


def _configured() -> R2Config:
    return R2Config(
        account_id="acct123",
        bucket=FAKE_BUCKET,
        endpoint=FAKE_ENDPOINT,
        access_key_id=FAKE_ACCESS_KEY,
        secret_access_key=FAKE_SECRET,
    )


def _run_bash(script: str, *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )


def _source_call(
    fn_and_args: str, *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Source backup.sh (main does not run) and call one function."""
    full = os.environ.copy()
    if env:
        full.update(env)
    script = textwrap.dedent(
        f"""
        set -euo pipefail
        source "{BACKUP_SH}"
        {fn_and_args}
        """
    )
    return _run_bash(script, env=full)


def _clean_env(extra: dict[str, str]) -> dict[str, str]:
    """A subprocess environment where nothing R2-shaped is exported.

    This is the rule 3 guard: if a test could pass because pytest's own
    environment happened to carry ``R2_BUCKET``, it would be testing a path
    production never takes.
    """
    full = os.environ.copy()
    for key in (
        *R2_ENV_KEYS,
        "BACKUP_DIR",
        "BACKUP_OFFSITE_DIR",
        "BACKUP_OFFSITE_KEEP",
        "DATABASE_URL",
    ):
        full.pop(key, None)
    full.update(extra)
    return full


def _fake_pg_dump(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "pg_dump"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            outfile=""
            while [[ $# -gt 0 ]]; do
              if [[ "$1" == "-f" ]]; then
                outfile="$2"
                shift 2
                continue
              fi
              shift
            done
            python3 -c "import pathlib; pathlib.Path('$outfile').write_bytes(b'x' * {MIN_BYTES + 64})"
            """
        ),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)


def _fake_aws(
    bin_dir: Path,
    log_path: Path,
    *,
    listing: str = "None",
    cp_exit: int = 0,
    head_size: int = MIN_BYTES + 64,
    head_exit: int = 0,
    delete_exit: int = 0,
) -> None:
    """An ``aws`` stub that records every invocation and answers predictably.

    It records ``$@`` and the credential environment variables it was handed,
    so a test can assert both the argv and that the secret was passed rather
    than printed.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "aws"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            {{
              echo "ARGV: $*"
              echo "ENV_KEY_ID: ${{AWS_ACCESS_KEY_ID:-}}"
              echo "ENV_SECRET_SET: ${{AWS_SECRET_ACCESS_KEY:+yes}}"
            }} >> "{log_path}"
            for arg in "$@"; do
              case "$arg" in
                list-objects-v2)
                  # %b so the \t separators in the fixture become real tabs,
                  # which is what `aws --output text` emits.
                  printf '%b\\n' {listing!r}
                  exit 0
                  ;;
                head-object)
                  [[ {head_exit} -eq 0 ]] || exit {head_exit}
                  echo {head_size}
                  exit 0
                  ;;
                delete-object)
                  exit {delete_exit}
                  ;;
                cp)
                  exit {cp_exit}
                  ;;
              esac
            done
            exit 0
            """
        ),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)


def _write_env_file(path: Path, body: str) -> Path:
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _stub_runner(code: int, stdout: str, stderr: str = ""):
    """A runner that records the argv it was given and answers canned output."""
    seen: list[tuple[list[str], dict[str, str]]] = []

    def run(argv: list[str], env: dict[str, str]) -> tuple[int, str, str]:
        seen.append((argv, env))
        return code, stdout, stderr

    run.seen = seen  # type: ignore[attr-defined]
    return run


# --- shell: object key layout -------------------------------------------------


def test_object_key_uses_dated_prefixes() -> None:
    """english_bot/<YYYY>/<MM>/<dump> — a human can find one day by browsing."""
    result = _source_call('r2_object_key english_bot_2026-08-23_0400.dump')
    assert result.returncode == 0, result.stderr
    assert (
        result.stdout.strip()
        == "english_bot/2026/08/english_bot_2026-08-23_0400.dump"
    )


def test_object_key_refuses_a_name_it_did_not_write() -> None:
    result = _source_call('r2_object_key backup.tar.gz || echo REFUSED')
    assert "REFUSED" in result.stdout


# --- shell: retention (CLAUDE.md §3 rule 5 — survivors are hand-written) ------

# Fourteen days back from 2026-08-23 is 2026-08-09; anything strictly before
# that is due for deletion. Both sides of every retention test are literals.
CUTOFF = "2026-08-09"

RETENTION_FIXTURE = [
    "english_bot/2026/08/english_bot_2026-08-23_0400.dump",  # newest
    "english_bot/2026/08/english_bot_2026-08-22_0400.dump",
    "english_bot/2026/08/english_bot_2026-08-09_0400.dump",  # == cutoff, keep
    "english_bot/2026/08/english_bot_2026-08-08_0400.dump",  # older, delete
    "english_bot/2026/08/english_bot_2026-08-01_0400.dump",  # older, delete
    "english_bot/2026/07/english_bot_2026-07-30_0400.dump",  # older, delete
]

RETENTION_SURVIVORS = {
    "english_bot/2026/08/english_bot_2026-08-23_0400.dump",
    "english_bot/2026/08/english_bot_2026-08-22_0400.dump",
    "english_bot/2026/08/english_bot_2026-08-09_0400.dump",
}

RETENTION_DOOMED = {
    "english_bot/2026/08/english_bot_2026-08-08_0400.dump",
    "english_bot/2026/08/english_bot_2026-08-01_0400.dump",
    "english_bot/2026/07/english_bot_2026-07-30_0400.dump",
}


def _prune_plan(keys: list[str], cutoff: str) -> set[str]:
    # Deliberately no trailing newline: `aws --output text | tr` can end that
    # way, and a plain `read` loop would drop the last key.
    payload = "\n".join(keys)
    result = _source_call(
        f'printf %s "$KEYS" | r2_prune_plan "{cutoff}"',
        env={"KEYS": payload},
    )
    assert result.returncode == 0, result.stderr
    return {line for line in result.stdout.splitlines() if line.strip()}


def test_retention_deletes_exactly_the_hand_written_doomed_set() -> None:
    assert _prune_plan(RETENTION_FIXTURE, CUTOFF) == RETENTION_DOOMED


def test_retention_keeps_exactly_the_hand_written_survivor_set() -> None:
    doomed = _prune_plan(RETENTION_FIXTURE, CUTOFF)
    assert set(RETENTION_FIXTURE) - doomed == RETENTION_SURVIVORS


def test_retention_boundary_day_is_kept_not_deleted() -> None:
    """A dump dated exactly on the cutoff is inside the window."""
    keys = ["english_bot/2026/08/english_bot_2026-08-09_0400.dump"]
    assert _prune_plan(keys, CUTOFF) == set()


def test_retention_never_deletes_the_newest_however_old_it_is() -> None:
    """Uploads broken for a month must not end with zero copies."""
    keys = [
        "english_bot/2026/01/english_bot_2026-01-04_0400.dump",
        "english_bot/2026/01/english_bot_2026-01-03_0400.dump",
        "english_bot/2026/01/english_bot_2026-01-02_0400.dump",
    ]
    assert _prune_plan(keys, CUTOFF) == {
        "english_bot/2026/01/english_bot_2026-01-03_0400.dump",
        "english_bot/2026/01/english_bot_2026-01-02_0400.dump",
    }


def test_retention_keeps_the_only_object_even_when_ancient() -> None:
    keys = ["english_bot/2020/01/english_bot_2020-01-01_0400.dump"]
    assert _prune_plan(keys, CUTOFF) == set()


def test_retention_ignores_objects_this_script_did_not_write() -> None:
    """Never delete something whose key does not match the layout."""
    keys = [
        "english_bot/2026/08/english_bot_2026-08-23_0400.dump",
        "english_bot/2026/01/english_bot_2026-01-01_0400.dump",
        "english_bot/notes.txt",
        "somebody-elses-prefix/2026/01/english_bot_2026-01-01_0400.dump",
        "None",
        "",
    ]
    assert _prune_plan(keys, CUTOFF) == {
        "english_bot/2026/01/english_bot_2026-01-01_0400.dump"
    }


def test_retention_orders_same_day_dumps_by_time() -> None:
    """Two dumps on one day: the later one is the newest and survives."""
    keys = [
        "english_bot/2026/01/english_bot_2026-01-01_0400.dump",
        "english_bot/2026/01/english_bot_2026-01-01_1600.dump",
    ]
    assert _prune_plan(keys, CUTOFF) == {
        "english_bot/2026/01/english_bot_2026-01-01_0400.dump"
    }


# --- shell: upload, configured through .env (CLAUDE.md §3 rule 3) -------------


def _run_backup_with_env_file(
    tmp_path: Path,
    *,
    r2_lines: str,
    cp_exit: int = 0,
    head_size: int | None = None,
    listing: str = "None",
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    local = tmp_path / "local"
    local.mkdir()
    bin_dir = tmp_path / "bin"
    aws_log = tmp_path / "aws-calls.log"
    aws_log.write_text("", encoding="utf-8")
    _fake_pg_dump(bin_dir)
    _fake_aws(
        bin_dir,
        aws_log,
        listing=listing,
        cp_exit=cp_exit,
        head_size=MIN_BYTES + 64 if head_size is None else head_size,
    )
    env_file = _write_env_file(
        tmp_path / ".env",
        f"""\
        DATABASE_URL=postgresql://u:p@127.0.0.1:5433/english_bot
        BACKUP_DIR={local}
        BACKUP_OFFSITE_DIR=
        {r2_lines}
        """,
    )
    env = _clean_env(
        {
            "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
            "ENV_FILE": str(env_file),
        }
    )
    result = subprocess.run(
        ["bash", str(BACKUP_SH)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    return result, local, aws_log


ALL_FIVE = textwrap.dedent(
    f"""\
    R2_ACCOUNT_ID=acct123
    R2_BUCKET={FAKE_BUCKET}
    R2_ENDPOINT={FAKE_ENDPOINT}
    R2_ACCESS_KEY_ID={FAKE_ACCESS_KEY}
    R2_SECRET_ACCESS_KEY={FAKE_SECRET}
    """
).strip()


def test_r2_keys_are_read_from_the_env_file_not_the_environment(
    tmp_path: Path,
) -> None:
    """The #26 regression. Nothing is exported; the .env file is the only source."""
    result, local, aws_log = _run_backup_with_env_file(
        tmp_path, r2_lines=ALL_FIVE
    )
    assert result.returncode == 0, result.stderr
    assert "R2 SUCCESS" in result.stderr
    assert "R2 copy skipped" not in result.stderr

    calls = aws_log.read_text(encoding="utf-8")
    assert f"--endpoint-url {FAKE_ENDPOINT}" in calls
    assert f"s3://{FAKE_BUCKET}/english_bot/" in calls
    assert f"ENV_KEY_ID: {FAKE_ACCESS_KEY}" in calls
    assert "ENV_SECRET_SET: yes" in calls
    # Local dump is a second copy, never replaced by the remote one.
    assert len(list(local.glob("english_bot_*.dump"))) == 1


def test_uploaded_key_has_the_dated_prefix_layout(tmp_path: Path) -> None:
    _, local, aws_log = _run_backup_with_env_file(tmp_path, r2_lines=ALL_FIVE)
    dump = next(local.glob("english_bot_*.dump"))
    day = dump.name[len("english_bot_") :][:10]
    year, month, _ = day.split("-")
    expected = f"s3://{FAKE_BUCKET}/english_bot/{year}/{month}/{dump.name}"
    assert expected in aws_log.read_text(encoding="utf-8")


def test_r2_unset_skips_at_info_and_keeps_the_local_dump(tmp_path: Path) -> None:
    """No R2 in .env → one INFO line, exit 0, local dump still made."""
    result, local, aws_log = _run_backup_with_env_file(tmp_path, r2_lines="")
    assert result.returncode == 0, result.stderr
    assert "R2 copy skipped (R2_* not configured)" in result.stderr
    assert "R2 SUCCESS" not in result.stderr
    assert len(list(local.glob("english_bot_*.dump"))) == 1
    assert aws_log.read_text(encoding="utf-8") == ""


def test_r2_partially_configured_dies_loudly(tmp_path: Path) -> None:
    """Three of five is a mistake, and it must not look like 'skipped'."""
    partial = textwrap.dedent(
        f"""\
        R2_ACCOUNT_ID=acct123
        R2_BUCKET={FAKE_BUCKET}
        R2_ENDPOINT={FAKE_ENDPOINT}
        """
    ).strip()
    result, local, _ = _run_backup_with_env_file(tmp_path, r2_lines=partial)
    assert result.returncode != 0
    assert "R2 partially configured" in result.stderr
    assert "R2_ACCESS_KEY_ID" in result.stderr
    assert "R2_SECRET_ACCESS_KEY" in result.stderr
    # The local dump is still on disk — a failed R2 leg never destroys it.
    assert len(list(local.glob("english_bot_*.dump"))) == 1


def test_failed_upload_exits_non_zero_and_keeps_the_local_dump(
    tmp_path: Path,
) -> None:
    result, local, _ = _run_backup_with_env_file(
        tmp_path, r2_lines=ALL_FIVE, cp_exit=1
    )
    assert result.returncode != 0
    assert "R2 upload failed" in result.stderr
    assert "R2 SUCCESS" not in result.stderr
    assert len(list(local.glob("english_bot_*.dump"))) == 1


def test_failed_upload_prunes_nothing(tmp_path: Path) -> None:
    """Pruning on a failed run is how you end up with neither copy."""
    _, _, aws_log = _run_backup_with_env_file(
        tmp_path, r2_lines=ALL_FIVE, cp_exit=1
    )
    calls = aws_log.read_text(encoding="utf-8")
    assert "delete-object" not in calls
    assert "list-objects-v2" not in calls


def test_size_mismatch_after_upload_is_refused(tmp_path: Path) -> None:
    """The object is read back; a short write must not be reported as success."""
    result, _, _ = _run_backup_with_env_file(
        tmp_path, r2_lines=ALL_FIVE, head_size=17
    )
    assert result.returncode != 0
    assert "R2 size mismatch" in result.stderr
    assert "R2 SUCCESS" not in result.stderr


def test_successful_upload_then_prunes(tmp_path: Path) -> None:
    listing = (
        "english_bot/2026/08/english_bot_2026-08-23_0400.dump\t"
        "english_bot/2020/01/english_bot_2020-01-01_0400.dump"
    )
    result, _, aws_log = _run_backup_with_env_file(
        tmp_path, r2_lines=ALL_FIVE, listing=listing
    )
    assert result.returncode == 0, result.stderr
    calls = aws_log.read_text(encoding="utf-8")
    assert "list-objects-v2" in calls
    deleted = {
        line.split("--key ")[-1].strip()
        for line in calls.splitlines()
        if "delete-object" in line
    }
    assert deleted == {"english_bot/2020/01/english_bot_2020-01-01_0400.dump"}


def test_secret_never_reaches_stdout_stderr_or_the_backup_log(
    tmp_path: Path,
) -> None:
    """CLAUDE.md §5 — logs carry user ids and route names, never credentials."""
    result, local, _ = _run_backup_with_env_file(tmp_path, r2_lines=ALL_FIVE)
    assert result.returncode == 0, result.stderr
    assert FAKE_SECRET not in result.stdout
    assert FAKE_SECRET not in result.stderr
    log_file = local / "backup.log"
    assert log_file.is_file()
    assert FAKE_SECRET not in log_file.read_text(encoding="utf-8")


def test_secret_never_reaches_the_log_on_the_failure_path(
    tmp_path: Path,
) -> None:
    """Not at DEBUG, not in an error path — the failure path is where it leaks."""
    result, local, _ = _run_backup_with_env_file(
        tmp_path, r2_lines=ALL_FIVE, cp_exit=1
    )
    assert result.returncode != 0
    assert FAKE_SECRET not in result.stdout
    assert FAKE_SECRET not in result.stderr
    assert FAKE_SECRET not in (local / "backup.log").read_text(encoding="utf-8")


# --- Python: config -----------------------------------------------------------


def test_settings_carry_the_five_keys_under_their_real_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Renaming any of these means a silent skip on the first real run."""
    from core import config as config_mod

    monkeypatch.setenv("R2_ACCOUNT_ID", "acct123")
    monkeypatch.setenv("R2_BUCKET", FAKE_BUCKET)
    monkeypatch.setenv("R2_ENDPOINT", FAKE_ENDPOINT)
    monkeypatch.setenv("R2_ACCESS_KEY_ID", FAKE_ACCESS_KEY)
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", FAKE_SECRET)
    settings = config_mod.load_settings()
    assert settings.r2_account_id == "acct123"
    assert settings.r2_bucket == FAKE_BUCKET
    assert settings.r2_endpoint == FAKE_ENDPOINT
    assert settings.r2_access_key_id == FAKE_ACCESS_KEY
    assert settings.r2_secret_access_key == FAKE_SECRET


def test_settings_repr_hides_the_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """`logger.info("%s", settings)` is one keystroke away in any file."""
    from core import config as config_mod

    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", FAKE_SECRET)
    settings = config_mod.load_settings()
    assert settings.r2_secret_access_key == FAKE_SECRET
    assert FAKE_SECRET not in repr(settings)


def test_r2_config_repr_hides_the_secret() -> None:
    assert FAKE_SECRET not in repr(_configured())
    assert FAKE_ACCESS_KEY in repr(_configured())


def test_r2_required_defaults_to_true_and_opts_out_explicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Silence is never the default; a dev machine has to ask for it.

    Both halves are read from a `.env` file, because that is the only way this
    variable is ever really set — on the server by its absence, on the Mac by
    #72's explicit ``BACKUP_R2_REQUIRED=0``. Asserting the default through a
    deleted process variable proved nothing: the repo `.env` put it back (#64).
    """
    from core import config as config_mod

    forget_r2_env(monkeypatch)

    # An operator who never wrote the line: the alarm is on.
    assert settings_from_dotenv(tmp_path).r2_required is True

    # A machine that opted out, spelled both ways operators actually write.
    for value in ("0", "false"):
        assert settings_from_dotenv(tmp_path, BACKUP_R2_REQUIRED=value).r2_required is False


def test_a_process_variable_still_beats_the_dotenv_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The precedence systemd and CI depend on, asserted rather than assumed.

    `load_dotenv(override=False)` is what lets a unit file override the checked-in
    file without editing it. It is also the half that made the five failures
    above possible, so it is worth having stated in one place.
    """
    from core import config as config_mod

    forget_r2_env(monkeypatch)
    assert settings_from_dotenv(tmp_path, BACKUP_R2_REQUIRED="0").r2_required is False

    monkeypatch.setenv("BACKUP_R2_REQUIRED", "1")
    assert settings_from_dotenv(tmp_path, BACKUP_R2_REQUIRED="0").r2_required is True


def test_the_default_dotenv_search_is_unchanged() -> None:
    """`dotenv_path=None` must still mean "find the repo-root .env".

    Every process in production relies on that search; the parameter was added
    for tests and must not have moved the default (known issue #64 documents
    the behaviour, it does not remove it).
    """
    import inspect

    from core import config as config_mod

    signature = inspect.signature(config_mod.load_settings)
    assert signature.parameters["dotenv_path"].default is None


def test_r2_max_age_default_is_26_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    """24-hour cycle plus slack for a late cron."""
    from core import config as config_mod

    monkeypatch.delenv("BACKUP_R2_MAX_AGE_HOURS", raising=False)
    assert config_mod.load_settings().r2_max_age_hours == 26.0


def test_bad_r2_required_is_a_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core import config as config_mod

    monkeypatch.setenv("BACKUP_R2_REQUIRED", "maybe")
    with pytest.raises(config_mod.ConfigError):
        config_mod.load_settings()


# --- Python: listing + freshness ----------------------------------------------


def test_command_targets_the_endpoint_bucket_and_prefix() -> None:
    argv = r2_command(_configured())
    assert argv[0] == "aws"
    assert "--endpoint-url" in argv
    assert argv[argv.index("--endpoint-url") + 1] == FAKE_ENDPOINT
    assert argv[argv.index("--bucket") + 1] == FAKE_BUCKET
    assert argv[argv.index("--prefix") + 1] == "english_bot/"


def test_credentials_go_in_the_environment_never_the_argv() -> None:
    """An argv is visible in `ps`; a child's environment is not."""
    assert FAKE_SECRET not in " ".join(r2_command(_configured()))
    assert r2_env(_configured())["AWS_SECRET_ACCESS_KEY"] == FAKE_SECRET


def test_listing_parses_tab_separated_rows() -> None:
    text = (
        "english_bot/2026/08/english_bot_2026-08-23_0400.dump\t"
        "2026-08-23T04:00:11+00:00\t524288\n"
        "english_bot/2026/08/english_bot_2026-08-22_0400.dump\t"
        "2026-08-22T04:00:09+00:00\t524000\n"
    )
    objects = parse_r2_listing(text)
    assert [obj.key for obj in objects] == [
        "english_bot/2026/08/english_bot_2026-08-23_0400.dump",
        "english_bot/2026/08/english_bot_2026-08-22_0400.dump",
    ]
    assert objects[0].size == 524288
    newest = newest_r2_object(objects)
    assert newest is not None
    assert newest.key.endswith("2026-08-23_0400.dump")


def test_listing_of_an_empty_bucket_is_no_objects() -> None:
    assert parse_r2_listing("None\n") == []
    assert parse_r2_listing("") == []
    assert newest_r2_object([]) is None


def test_listing_drops_a_row_it_cannot_parse_rather_than_guessing() -> None:
    text = "some/key\tnot-a-timestamp\t123\ngood/key\t2026-08-23T04:00:00Z\t9\n"
    objects = parse_r2_listing(text)
    assert [obj.key for obj in objects] == ["good/key"]


def _listing_at(moment: datetime) -> str:
    return (
        "english_bot/2026/08/english_bot_2026-08-23_0400.dump\t"
        f"{moment.isoformat()}\t524288"
    )


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def test_fresh_object_is_ok_and_silent() -> None:
    runner = _stub_runner(0, _listing_at(NOW - timedelta(hours=8)))
    health = check_r2_freshness(_configured(), now=NOW, runner=runner)
    assert health.status == "ok"
    assert health.should_alert is False


def test_object_at_25_hours_is_still_ok() -> None:
    """Hardcoded on both sides — no wall clock (CLAUDE.md §3 rule 6)."""
    runner = _stub_runner(0, _listing_at(NOW - timedelta(hours=25)))
    assert check_r2_freshness(_configured(), now=NOW, runner=runner).status == "ok"


def test_object_at_27_hours_is_stale_and_alerts() -> None:
    runner = _stub_runner(0, _listing_at(NOW - timedelta(hours=27)))
    health = check_r2_freshness(_configured(), now=NOW, runner=runner)
    assert health.status == "stale"
    assert health.should_alert is True
    assert "27.0h" in health.detail


def test_empty_bucket_alerts() -> None:
    runner = _stub_runner(0, "None")
    health = check_r2_freshness(_configured(), now=NOW, runner=runner)
    assert health.status == "empty"
    assert health.should_alert is True


def test_a_failing_aws_call_alerts_rather_than_reporting_ok() -> None:
    runner = _stub_runner(255, "", "An error occurred (AccessDenied)")
    health = check_r2_freshness(_configured(), now=NOW, runner=runner)
    assert health.status == "error"
    assert health.should_alert is True
    assert "AccessDenied" in health.detail


def test_unconfigured_alerts_when_required() -> None:
    """Known issue #31: silence is no longer a valid state in production."""
    health = check_r2_freshness(R2Config(), now=NOW, required=True)
    assert health.status == "unconfigured"
    assert health.should_alert is True


def test_unconfigured_stays_quiet_when_not_required() -> None:
    """A dev machine is not expected to hold backups — it opts out explicitly."""
    health = check_r2_freshness(R2Config(), now=NOW, required=False)
    assert health.status == "unconfigured"
    assert health.should_alert is False


def test_partial_configuration_alerts_even_when_not_required() -> None:
    """Nobody sets three of five on purpose; that is the silent-skip shape."""
    config = R2Config(account_id="a", bucket="b", endpoint=FAKE_ENDPOINT)
    health = check_r2_freshness(config, now=NOW, required=False)
    assert health.status == "partial"
    assert health.should_alert is True
    assert "R2_ACCESS_KEY_ID" in health.detail


def test_unconfigured_and_partial_never_call_aws() -> None:
    runner = _stub_runner(0, "None")
    check_r2_freshness(R2Config(), now=NOW, runner=runner)
    check_r2_freshness(
        R2Config(account_id="a"), now=NOW, runner=runner, required=False
    )
    assert runner.seen == []  # type: ignore[attr-defined]


def test_no_health_detail_ever_contains_the_secret() -> None:
    cases = [
        check_r2_freshness(R2Config(), now=NOW),
        check_r2_freshness(
            R2Config(account_id="a", secret_access_key=FAKE_SECRET), now=NOW
        ),
        check_r2_freshness(
            _configured(),
            now=NOW,
            runner=_stub_runner(1, "", f"failed with {FAKE_SECRET}? no"),
        ),
        check_r2_freshness(
            _configured(), now=NOW, runner=_stub_runner(0, "None")
        ),
        check_r2_freshness(
            _configured(),
            now=NOW,
            runner=_stub_runner(0, _listing_at(NOW - timedelta(hours=40))),
        ),
    ]
    for health in cases:
        assert FAKE_SECRET not in health.detail
        assert FAKE_SECRET not in repr(health)


def test_config_is_built_from_settings_field_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core import config as config_mod

    for key, value in (
        ("R2_ACCOUNT_ID", "acct123"),
        ("R2_BUCKET", FAKE_BUCKET),
        ("R2_ENDPOINT", FAKE_ENDPOINT),
        ("R2_ACCESS_KEY_ID", FAKE_ACCESS_KEY),
        ("R2_SECRET_ACCESS_KEY", FAKE_SECRET),
    ):
        monkeypatch.setenv(key, value)
    config = r2_config_from_settings(config_mod.load_settings())
    assert config.state() == "configured"
    assert config.bucket == FAKE_BUCKET


# --- Python: the alarm, through its real callers -------------------------------


def _settings_with(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **env: str):
    """Settings for an R2 alarm test, read from a `.env` this test owns.

    The `.env` is explicit rather than ambient so that "R2 is unconfigured"
    means the same thing on every machine. Before this, the repo `.env` was
    reloaded underneath the deletions and the answer depended on whose laptop
    was running (#64).
    """
    runtime = tmp_path / "runtime"
    runtime.mkdir(exist_ok=True)
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("ALERT_THROTTLE_FILE", str(runtime / "throttle.json"))
    monkeypatch.setenv("BACKUP_OFFSITE_DIR", "")
    forget_r2_env(monkeypatch)

    from core import config as config_mod

    settings = settings_from_dotenv(tmp_path, **env)
    monkeypatch.setattr("apps.bot.scheduler.load_settings", lambda: settings)
    monkeypatch.setattr("core.services.alerts.load_settings", lambda: settings)
    return settings


def test_unconfigured_r2_reaches_the_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The #31 closure, exercised through the job's real caller."""
    _settings_with(monkeypatch, tmp_path, OPERATOR_TELEGRAM_ID="999911")
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    status = asyncio.run(run_r2_freshness_check(app, now=NOW))
    assert status == "unconfigured"
    assert app.bot.send_message.await_count == 1
    sent = app.bot.send_message.await_args.kwargs["text"]
    assert "UNCONFIGURED" in sent
    assert "BACKUP_R2_REQUIRED=0" in sent


def test_dev_machine_opt_out_sends_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings_with(
        monkeypatch,
        tmp_path,
        OPERATOR_TELEGRAM_ID="999912",
        BACKUP_R2_REQUIRED="0",
    )
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    status = asyncio.run(run_r2_freshness_check(app, now=NOW))
    assert status == "unconfigured"
    assert app.bot.send_message.await_count == 0


def test_the_alarm_is_one_a_day_not_one_every_fifteen_minutes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken backup is a daily fact; four alerts an hour teach people to
    ignore them. Every instant here is hardcoded."""
    _settings_with(monkeypatch, tmp_path, OPERATOR_TELEGRAM_ID="999913")
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    asyncio.run(run_r2_freshness_check(app, now=NOW))
    assert app.bot.send_message.await_count == 1

    # The next scheduler tick, an hour later, and six hours later: silent.
    asyncio.run(run_r2_freshness_check(app, now=NOW + timedelta(hours=1)))
    asyncio.run(run_r2_freshness_check(app, now=NOW + timedelta(hours=6)))
    assert app.bot.send_message.await_count == 1

    # A day later it says so again — the problem has not gone away.
    asyncio.run(run_r2_freshness_check(app, now=NOW + timedelta(hours=25)))
    assert app.bot.send_message.await_count == 2
    assert "suppressed=2" in app.bot.send_message.await_args.kwargs["text"]


def test_stale_r2_reaches_the_operator_and_names_the_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings_with(
        monkeypatch,
        tmp_path,
        OPERATOR_TELEGRAM_ID="999914",
        R2_ACCOUNT_ID="acct123",
        R2_BUCKET=FAKE_BUCKET,
        R2_ENDPOINT=FAKE_ENDPOINT,
        R2_ACCESS_KEY_ID=FAKE_ACCESS_KEY,
        R2_SECRET_ACCESS_KEY=FAKE_SECRET,
    )
    monkeypatch.setattr(
        "core.services.backup_freshness._run_aws",
        _stub_runner(0, _listing_at(NOW - timedelta(hours=40))),
    )
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    status = asyncio.run(run_r2_freshness_check(app, now=NOW))
    assert status == "stale"
    assert app.bot.send_message.await_count == 1
    sent = app.bot.send_message.await_args.kwargs["text"]
    assert "STALE" in sent
    assert "english_bot_2026-08-23_0400.dump" in sent
    assert FAKE_SECRET not in sent


def test_a_healthy_r2_says_nothing_to_the_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings_with(
        monkeypatch,
        tmp_path,
        OPERATOR_TELEGRAM_ID="999915",
        R2_ACCOUNT_ID="acct123",
        R2_BUCKET=FAKE_BUCKET,
        R2_ENDPOINT=FAKE_ENDPOINT,
        R2_ACCESS_KEY_ID=FAKE_ACCESS_KEY,
        R2_SECRET_ACCESS_KEY=FAKE_SECRET,
    )
    monkeypatch.setattr(
        "core.services.backup_freshness._run_aws",
        _stub_runner(0, _listing_at(NOW - timedelta(hours=8))),
    )
    app = MagicMock()
    app.bot.send_message = AsyncMock()

    assert asyncio.run(run_r2_freshness_check(app, now=NOW)) == "ok"
    assert app.bot.send_message.await_count == 0


def test_the_scheduled_job_runs_both_halves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The folder check and the R2 check, from the job the scheduler registers.

    Rule 4: the user action here is "the hourly backup_freshness tick fires".
    """
    called: list[str] = []

    async def _folder(app, **kwargs):
        called.append("folder")
        return "skipped"

    async def _r2(app, **kwargs):
        called.append("r2")
        return "unconfigured"

    monkeypatch.setattr(bot_scheduler, "run_backup_freshness_check", _folder)
    monkeypatch.setattr(bot_scheduler, "run_r2_freshness_check", _r2)
    context = MagicMock()
    asyncio.run(bot_scheduler._backup_freshness_job(context))
    assert called == ["folder", "r2"]


def test_worker_job_reports_unconfigured_r2_at_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The worker has no channel, so it logs — honestly, at ERROR (issue #65)."""
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("BACKUP_OFFSITE_DIR", "")
    forget_r2_env(monkeypatch)

    from core import config as config_mod

    # An explicit `.env` with no R2 keys, so "unconfigured" means the same
    # thing here as it does on the server (#64).
    settings = settings_from_dotenv(tmp_path)
    monkeypatch.setattr("apps.worker.jobs.load_settings", lambda: settings)
    with caplog.at_level("INFO"):
        worker_jobs.backup_freshness()
    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert any("R2 UNCONFIGURED" in r.getMessage() for r in errors)


# --- the worker unit must not be installed while the job tables overlap -------


def _bot_job_names() -> set[str]:
    """Job names the bot's scheduler registers, read from its source.

    Parsed rather than imported-and-run: registering them for real needs a
    running PTB Application, and this only has to know the names.
    """
    source = (REPO_ROOT / "apps" / "bot" / "scheduler.py").read_text()
    tree = ast.parse(source)
    constants: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(
                    node.value.value, str
                ):
                    constants[target.id] = node.value.value
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "run_repeating"):
            continue
        for keyword in node.keywords:
            if keyword.arg != "name":
                continue
            if isinstance(keyword.value, ast.Name):
                names.add(constants[keyword.value.id])
            elif isinstance(keyword.value, ast.Constant):
                names.add(str(keyword.value.value))
    return names


# Hand-written, never derived: what W1c actually found when it checked.
KNOWN_JOB_OVERLAP = {
    "streak_rollover",
    "monthly_freeze_reset",
    "heartbeat",
    "backup_freshness",
}


def test_bot_and_worker_job_tables_still_overlap() -> None:
    """W1c's Part 5 guard, recorded so it cannot be forgotten.

    Two processes running ``streak_rollover`` against one database is a
    data-integrity problem. While this set is non-empty, english-worker must
    not be enabled on the server. When someone makes the tables disjoint this
    test fails, which is the point: the fix and the install decision belong in
    the same change.
    """
    worker_names = {job.name for job in worker_jobs.JOBS}
    assert _bot_job_names() & worker_names == KNOWN_JOB_OVERLAP


def test_the_worker_unit_says_it_must_not_be_installed_yet() -> None:
    unit = (UNIT_DIR / "english-worker.service").read_text(encoding="utf-8")
    assert "NOT INSTALLED" in unit
    for name in sorted(KNOWN_JOB_OVERLAP):
        assert name in unit


def test_the_api_unit_binds_to_loopback_only() -> None:
    """Caddy holds 80/443 on a shared host; the API must not face the internet."""
    unit = (UNIT_DIR / "english-api.service").read_text(encoding="utf-8")
    exec_start = next(
        line for line in unit.splitlines() if line.startswith("ExecStart=")
    )
    assert "--host 127.0.0.1" in exec_start
    assert "0.0.0.0" not in exec_start
    assert "apps.api.main:app" in exec_start


def test_both_units_run_as_bot_from_the_deploy_directory() -> None:
    for name in ("english-api.service", "english-worker.service"):
        unit = (UNIT_DIR / name).read_text(encoding="utf-8")
        assert "User=bot" in unit
        assert "WorkingDirectory=/home/bot/english-bot" in unit
        assert "Restart=always" in unit
        assert "RestartSec=10" in unit
        assert "StandardOutput=journal" in unit


# --- documentation is part of the deploy --------------------------------------


def test_env_example_documents_all_five_keys_under_their_real_names() -> None:
    body = ENV_EXAMPLE.read_text(encoding="utf-8")
    for key in R2_ENV_KEYS:
        assert f"\n{key}=" in body, key


def test_deployment_doc_no_longer_shows_the_pre_w1_module_paths() -> None:
    """W1 moved `app` to `core`/`apps`; a runbook that still says `app.db`
    is a runbook that fails at the one moment it is being followed."""
    body = DEPLOYMENT_MD.read_text(encoding="utf-8")
    assert "app.db migrate" not in body
    assert "-m app.main" not in body
    assert "python -m core.db migrate" in body
    assert "python -m core.db status" in body
    assert "python -m apps.bot.main" in body


def test_deployment_doc_records_the_settled_deploy_sequence() -> None:
    body = DEPLOYMENT_MD.read_text(encoding="utf-8")
    assert "backup → pull → `pip install -e packages/core` → migrate → restart" in body


def test_restore_from_r2_refuses_the_live_database() -> None:
    body = RESTORE_R2_SH.read_text(encoding="utf-8")
    assert 'LIVE_DB_NAME="english_bot"' in body
    # No --force option: unlike scripts/restore.sh this is meant to be run
    # casually, and a flag that can overwrite the error journal does not belong
    # in something you run casually. Comments may mention it; the parser must
    # not accept it.
    code = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
    assert '"--force"' not in code
    assert "FORCE=" not in code
    assert RESTORE_R2_SH.stat().st_mode & stat.S_IXUSR
