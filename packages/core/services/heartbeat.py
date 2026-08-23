"""Heartbeat last-fire file helpers (S18).

Touch only after successful completion of delivery/maintenance jobs.
The hourly checker must not refresh the file.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_AGE_HOURS = 26


def touch_job_fire(path: str | Path, *, now: datetime) -> None:
    """Record that a scheduled job completed successfully."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(now.isoformat() + "\n", encoding="utf-8")


def read_last_fire(path: str | Path) -> datetime | None:
    """Parse last-fire timestamp from file, or None if missing/invalid."""
    target = Path(path)
    if not target.is_file():
        return None
    try:
        raw = target.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        instant = datetime.fromisoformat(raw)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        return instant
    except (OSError, ValueError) as exc:
        logger.error("Heartbeat file unreadable (%s): %s", target, exc)
        return None


def check_heartbeat(
    path: str | Path,
    *,
    now: datetime,
    max_age_hours: float = MAX_AGE_HOURS,
) -> str:
    """Return 'ok' or 'stale'."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    last = read_last_fire(path)
    if last is None:
        return "stale"
    if now - last > timedelta(hours=max_age_hours):
        return "stale"
    return "ok"
