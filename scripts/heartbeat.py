#!/usr/bin/env python3
"""CLI heartbeat check — alert path for optional external cron (S18).

Logic lives in app.services.heartbeat. In-process JobQueue also calls that
module; this script is for a future Hetzner cron that can detect process death.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from app.config import ConfigError, load_settings  # noqa: E402
from app.services.heartbeat import (  # noqa: E402
    MAX_AGE_HOURS,
    check_heartbeat,
)

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    status = check_heartbeat(settings.heartbeat_file, now=now)
    if status == "ok":
        logger.info("Heartbeat ok file=%s", settings.heartbeat_file)
        return 0
    logger.error(
        "Heartbeat STALE — no successful job fire within %sh file=%s",
        MAX_AGE_HOURS,
        settings.heartbeat_file,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
