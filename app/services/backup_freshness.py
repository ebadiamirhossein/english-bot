"""Off-site backup freshness helpers (S4c).

In-process check only — detects a stopped backup while the bot is alive.
Cannot detect anything if the bot process is also down (same honesty as S18
heartbeat).

iCloud "Optimise Mac Storage" may replace dumps with
``.english_bot_*.dump.icloud`` placeholders. Those count as present: the file
is safely in iCloud, not missing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_AGE_HOURS = 48.0


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
