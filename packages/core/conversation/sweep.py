"""`python -m core.conversation.sweep` — **deleter number three, human-run.**

The other two run inside the request: the close-out's own delete, and the
unconditional expiry sweep at the top of every entry point. This one exists for
the case neither reaches -- **#384's residual: if the surface is never reopened,
the last conversation's turns persist**, because a sweep driven by traffic needs
traffic.

**IT IS NOT A SCHEDULED JOB AND MUST NOT BECOME ONE HERE.** `english-worker` is
⬜ blocked and not installed (#69), nothing scheduled has ever fired on this
host, and a retention rule enforced by a worker that has never run is a hope
rather than a rule. It is also not billed: this command reaches no model.

Dry by default, like every other human-run command in this project.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from core.config import load_settings
from core.db import connection
from core.services.conversations import expired_turn_count, sweep_expired_turns


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="delete; without it, only report"
    )
    args = parser.parse_args(argv)
    cfg = load_settings()
    now = datetime.now(timezone.utc)
    with connection() as conn:
        if not args.apply:
            n = expired_turn_count(conn, now, cfg.conversation_timeout_minutes)
            print(f"would delete {n} turns (dry run)")
            return 0
        n = sweep_expired_turns(conn, now, cfg.conversation_timeout_minutes)
        conn.commit()
        print(f"deleted {n} turns")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
