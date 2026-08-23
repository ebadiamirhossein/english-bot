"""Off-site backup freshness helpers (S4c, extended at W1c).

Two destinations, checked separately:

* a cloud-synced **folder** (S4c) — ``BACKUP_OFFSITE_DIR``, still supported,
  still silent when unset because a folder was always optional;
* **Cloudflare R2** (W1c) — the real off-site copy, and the one production
  runs on. Unset R2 is *not* silent: known issue #31 was that an unconfigured
  backup and a healthy one looked identical from the outside, so the check
  reported nothing on the exact machine where nothing was being backed up.

In-process check only — it detects a stopped backup while the process running
it is alive, and nothing at all when that process is down too (same honesty as
the S18 heartbeat).

iCloud "Optimise Mac Storage" may replace dumps with
``.english_bot_*.dump.icloud`` placeholders. Those count as present: the file
is safely in iCloud, not missing.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_AGE_HOURS = 48.0

# W1c — R2. 26 hours is a 24-hour cycle plus slack for a late cron.
R2_MAX_AGE_HOURS = 26.0
# Must match R2_PREFIX in scripts/backup.sh. The trailing slash keeps the
# listing to objects this project wrote.
R2_PREFIX = "english_bot/"
R2_KEY_NAMES = (
    "R2_ACCOUNT_ID",
    "R2_BUCKET",
    "R2_ENDPOINT",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
)
# The listing is one round trip against an object store; if it has not answered
# in this long, something is wrong and hanging the scheduler is worse.
R2_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class NewestOffsite:
    """Metadata for the newest off-site dump or iCloud placeholder."""

    path: Path
    name: str
    mtime: datetime
    size: int | None


def list_offsite_candidates(directory: Path) -> list[Path]:
    """Return dump files and iCloud eviction placeholders in *directory*."""
    if not directory.is_dir():
        return []
    found: list[Path] = []
    for path in directory.iterdir():
        name = path.name
        if name.startswith("english_bot_") and name.endswith(".dump"):
            found.append(path)
        elif (
            name.startswith(".english_bot_")
            and name.endswith(".dump.icloud")
        ):
            found.append(path)
    return found


def newest_offsite(directory: Path) -> NewestOffsite | None:
    """Pick the candidate with the newest mtime, or None if empty/unreadable."""
    newest: NewestOffsite | None = None
    for path in list_offsite_candidates(directory):
        try:
            stat = path.stat()
        except OSError as exc:
            logger.error(
                "Off-site candidate unreadable path=%s err=%s", path, exc
            )
            continue
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        size: int | None
        try:
            size = int(stat.st_size)
        except (OSError, AttributeError):
            size = None
        candidate = NewestOffsite(
            path=path, name=path.name, mtime=mtime, size=size
        )
        if newest is None or candidate.mtime > newest.mtime:
            newest = candidate
    return newest


def check_offsite_freshness(
    directory: str | None,
    *,
    now: datetime,
    max_age_hours: float = MAX_AGE_HOURS,
) -> str:
    """Return 'skipped', 'ok', or 'stale'.

    Empty / unset directory → skipped (caller must not alert).
    Missing dir, no candidates, or newest older than max_age → stale.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if not directory or not str(directory).strip():
        return "skipped"
    target = Path(directory)
    if not target.is_dir():
        return "stale"
    newest = newest_offsite(target)
    if newest is None:
        return "stale"
    if now - newest.mtime > timedelta(hours=max_age_hours):
        return "stale"
    return "ok"


# --- Cloudflare R2 (W1c) ------------------------------------------------------


@dataclass(frozen=True)
class R2Config:
    """The five R2 keys. All five or none — see :meth:`state`.

    ``secret_access_key`` is ``repr=False`` on purpose: every other field is
    safe in a log line and that one never is (CLAUDE.md §5).
    """

    account_id: str = ""
    bucket: str = ""
    endpoint: str = ""
    access_key_id: str = ""
    secret_access_key: str = field(default="", repr=False)

    def missing(self) -> tuple[str, ...]:
        """Names — never values — of the keys that are unset or blank."""
        values = (
            self.account_id,
            self.bucket,
            self.endpoint,
            self.access_key_id,
            self.secret_access_key,
        )
        return tuple(
            name
            for name, value in zip(R2_KEY_NAMES, values)
            if not (value or "").strip()
        )

    def state(self) -> str:
        """``'configured'``, ``'unconfigured'`` or ``'partial'``.

        ``partial`` is its own state rather than a synonym for unconfigured,
        because a half-set group is how known issue #26 happened: something
        that looks unset silently skips, and the operator believes it ran.
        """
        missing = self.missing()
        if not missing:
            return "configured"
        if len(missing) == len(R2_KEY_NAMES):
            return "unconfigured"
        return "partial"


@dataclass(frozen=True)
class R2Object:
    """One object in the bucket."""

    key: str
    last_modified: datetime
    size: int


@dataclass(frozen=True)
class R2Health:
    """The verdict, plus whether the caller should raise an alert.

    ``detail`` is written to be pasted into an alert body, so it names the
    bucket and the newest key and never a credential.
    """

    status: str
    should_alert: bool
    detail: str
    newest: R2Object | None = None


def r2_config_from_settings(settings: object) -> R2Config:
    """Build an :class:`R2Config` from a ``core.config.Settings``."""
    return R2Config(
        account_id=getattr(settings, "r2_account_id", "") or "",
        bucket=getattr(settings, "r2_bucket", "") or "",
        endpoint=getattr(settings, "r2_endpoint", "") or "",
        access_key_id=getattr(settings, "r2_access_key_id", "") or "",
        secret_access_key=getattr(settings, "r2_secret_access_key", "") or "",
    )


def r2_command(config: R2Config) -> list[str]:
    """The ``aws`` argv that lists every dump under the prefix.

    Key, LastModified and Size per object, tab separated, newest picked in
    Python — ``--query`` sorting is applied per page when the CLI paginates,
    and a bucket that outgrows one page must not quietly start answering with
    the newest object *of the last page*.
    """
    return [
        "aws",
        "--endpoint-url",
        config.endpoint,
        "s3api",
        "list-objects-v2",
        "--bucket",
        config.bucket,
        "--prefix",
        R2_PREFIX,
        "--query",
        "Contents[].[Key,LastModified,Size]",
        "--output",
        "text",
    ]


def r2_env(config: R2Config) -> dict[str, str]:
    """Credential environment for the ``aws`` child process.

    Returned rather than exported: it goes into one subprocess call and is
    never put on this process's environment, where anything that dumps
    ``os.environ`` would pick it up.
    """
    return {
        "AWS_ACCESS_KEY_ID": config.access_key_id,
        "AWS_SECRET_ACCESS_KEY": config.secret_access_key,
        "AWS_DEFAULT_REGION": "auto",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_REQUEST_CHECKSUM_CALCULATION": "when_required",
        "AWS_RESPONSE_CHECKSUM_VALIDATION": "when_required",
    }


def _run_aws(argv: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    """Default runner. Injected in tests so no test needs a network or a key."""
    child_env = os.environ.copy()
    child_env.pop("AWS_SESSION_TOKEN", None)
    child_env.pop("AWS_PROFILE", None)
    child_env.update(env)
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            env=child_env,
            timeout=R2_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return 127, "", "aws: command not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"aws timed out after {R2_TIMEOUT_SECONDS}s"
    return completed.returncode, completed.stdout, completed.stderr


def redact_secrets(text: str, config: R2Config) -> str:
    """Replace any credential that appears in *text* with a placeholder.

    Defence in depth. Nothing in this module puts a credential into a message
    on purpose; this is for the paths where a provider's own error text hands
    one back and it would otherwise be forwarded into an alert.
    """
    cleaned = text
    for secret in (config.secret_access_key, config.access_key_id):
        value = (secret or "").strip()
        if len(value) >= 8:
            cleaned = cleaned.replace(value, "[redacted]")
    return cleaned


def parse_r2_listing(text: str) -> list[R2Object]:
    """Parse ``aws --output text`` rows into objects, skipping junk lines.

    ``None`` is what the CLI prints for an empty bucket, and a row whose
    timestamp or size will not parse is dropped rather than guessed at.
    """
    objects: list[R2Object] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line == "None":
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            parts = line.split()
        if len(parts) != 3:
            logger.error("Unparsable R2 listing row (%d fields)", len(parts))
            continue
        key, stamp, size = parts
        try:
            moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            logger.error("Unparsable LastModified in R2 listing key=%s", key)
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        try:
            byte_count = int(size)
        except ValueError:
            logger.error("Unparsable Size in R2 listing key=%s", key)
            continue
        objects.append(
            R2Object(key=key, last_modified=moment, size=byte_count)
        )
    return objects


def newest_r2_object(objects: list[R2Object]) -> R2Object | None:
    """The most recently modified object, or None for an empty list."""
    if not objects:
        return None
    return max(objects, key=lambda obj: obj.last_modified)


def check_r2_freshness(
    config: R2Config,
    *,
    now: datetime,
    max_age_hours: float = R2_MAX_AGE_HOURS,
    required: bool = True,
    runner=None,
) -> R2Health:
    """Return the verdict for the R2 copy.

    Statuses: ``ok``, ``stale``, ``empty``, ``error``, ``partial``,
    ``unconfigured``.

    ``required`` is what separates a server from a laptop, and it is a
    configuration value rather than a hostname test: production leaves
    ``BACKUP_R2_REQUIRED`` unset and gets the alarm, a dev machine sets it to
    0 and stays quiet. Forgetting it produces one extra alert, never silence
    (known issue #31).

    ``partial`` alerts on every machine, ``required`` or not. Nobody sets three
    of five keys on purpose, and the half-set group is precisely what skips
    without saying so.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    state = config.state()
    if state == "partial":
        return R2Health(
            status="partial",
            should_alert=True,
            detail=(
                "R2 is partly configured — missing "
                f"{', '.join(config.missing())}. The backup will skip the "
                "off-site copy without failing."
            ),
        )
    if state == "unconfigured":
        return R2Health(
            status="unconfigured",
            should_alert=required,
            detail=(
                "R2 is not configured — there is no off-site copy of the "
                "error journal. Set the five R2_* keys in .env, or set "
                "BACKUP_R2_REQUIRED=0 if this machine is not meant to hold "
                "backups."
            ),
        )

    # Resolved here rather than as a default argument so the module attribute
    # can be replaced in a test — a default binds at def time and would keep
    # the original function whatever the test patched.
    run = runner if runner is not None else _run_aws
    code, stdout, stderr = run(r2_command(config), r2_env(config))
    if code != 0:
        # Truncated and redacted: an unbounded blob of someone else's stderr
        # does not belong in an alert body, and if a provider ever echoes a
        # credential back at us it must not be forwarded (CLAUDE.md §5).
        reason = redact_secrets(" ".join(stderr.split())[:300], config) or (
            f"exit {code}"
        )
        return R2Health(
            status="error",
            should_alert=True,
            detail=(
                f"Could not list bucket {config.bucket!r} (exit {code}): "
                f"{reason}"
            ),
        )

    newest = newest_r2_object(parse_r2_listing(stdout))
    if newest is None:
        return R2Health(
            status="empty",
            should_alert=True,
            detail=(
                f"Bucket {config.bucket!r} holds no object under "
                f"{R2_PREFIX!r} — the backup has never landed."
            ),
        )

    age_hours = (now - newest.last_modified).total_seconds() / 3600.0
    if age_hours > max_age_hours:
        return R2Health(
            status="stale",
            should_alert=True,
            detail=(
                f"Newest object {newest.key} is {age_hours:.1f}h old "
                f"(threshold {max_age_hours:.0f}h, bucket {config.bucket!r})."
            ),
            newest=newest,
        )
    return R2Health(
        status="ok",
        should_alert=False,
        detail=(
            f"Newest object {newest.key} is {age_hours:.1f}h old "
            f"({newest.size} bytes)."
        ),
        newest=newest,
    )
