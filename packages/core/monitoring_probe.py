"""W23's probe: does one intentional exception reach Sentry with a user id and no body?

    python -m core.monitoring_probe --user N           # dry: prints what --send would send
    python -m core.monitoring_probe --user N --send    # sends ONE event to the SENTRY_DSN project

The exception is raised with a canary message standing in for learner text,
from a frame whose local variable holds the same canary — the two places
learner text would ride out on a real failure. **Both must be absent from what
is sent**, and the dry run checks it on the bytes the SDK serialised (the event
is captured after ``scrub_event``, by ``core.monitoring.CapturingTransport``).

**Dry by default: no network call, nothing written.** Without ``SENTRY_DSN``
the dry run uses a placeholder EU DSN, so it can be run on any machine.

**What ``--send`` spends: nothing billed** — one error event against the free
plan's monthly allowance (pricing page, read 2026-09-25: *"5k errors"*). It is
still a call to a live service (CLAUDE.md §5b), so it is the operator's, at the
launch pass, after ``SENTRY_DSN`` is in ``.env``. Then the issue is opened in
Sentry and read: the user id is there, the canary is not.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace

from core import monitoring
from core.config import load_settings

#: Stands in for a learner's sentence. It must never appear in what is sent.
CANARY = "probe-canary: I goed to the shop yesterday"

#: Used only by the dry run when SENTRY_DSN is unset. Passes the EU check.
PLACEHOLDER_DSN = "https://dry@o0.ingest.de.sentry.io/0"


class ProbeError(RuntimeError):
    """The intentional exception. Its name is what the Sentry issue is titled."""


def _fail(learner_text: str) -> None:
    raise ProbeError(f"learner text: {learner_text}")


def raise_and_capture(user_id: int) -> None:
    try:
        _fail(CANARY)
    except ProbeError as exc:
        monitoring.capture_exception(exc, user_id=user_id, route="monitoring_probe")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sentry probe (W23). Dry by default."
    )
    parser.add_argument("--user", type=int, required=True, help="users.id — your own")
    parser.add_argument("--send", action="store_true", help="send ONE event to Sentry")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.send:
        if not settings.sentry_dsn:
            print("SENTRY_DSN is not set in .env — nothing to send to.")
            return 1
        monitoring.init_monitoring(settings, component="probe")
        raise_and_capture(args.user)
        monitoring.flush(10.0)
        print(
            "Sent one ProbeError. In Sentry, open the newest issue and read it: "
            f"user id {args.user} is there, and the text {CANARY!r} is NOT."
        )
        return 0

    transport = monitoring.CapturingTransport()
    dry = replace(settings, sentry_dsn=settings.sentry_dsn or PLACEHOLDER_DSN)
    monitoring.init_monitoring(dry, component="probe", transport=transport)
    raise_and_capture(args.user)
    monitoring.flush(2.0)
    events = [p for p in transport.payloads() if p.get("type") != "check_in"]
    wire = transport.wire()
    print("DRY RUN — nothing sent. The event --send would send, as serialised:")
    for event in events:
        print(json.dumps(event, indent=2, sort_keys=True))
    user_ok = any(e.get("user", {}).get("id") == str(args.user) for e in events)
    canary_absent = "goed" not in wire and CANARY not in wire
    print(f"events={len(events)} user_id_present={user_ok} canary_absent={canary_absent}")
    return 0 if (len(events) == 1 and user_ok and canary_absent) else 1


if __name__ == "__main__":
    sys.exit(main())
