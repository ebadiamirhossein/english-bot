"""W20's probe: does a real push service accept the request `core.push` builds?

    python -m core.push_probe --user N           # dry: prints what --live would send
    python -m core.push_probe --user N --live    # sends ONE push to N's browsers

**Dry by default, and the dry run makes no network call and writes nothing.**
It prints, for each of the learner's subscriptions: the push service's HOST
(never the endpoint's path, which is a capability — `core.push.endpoint_host`),
the headers with the VAPID token's CLAIMS decoded in place of the token itself,
the body's size, and the message. That is everything `--live` sends.

**What `--live` spends: no money** — Web Push is free — **but it puts a real
notification on a real phone** (CLAUDE.md §5b). It is the operator's, at the
launch pass, against the operator's OWN user id, after turning reminders on on
their phone. It asks for the user id to be typed back. It does not touch
`push_deliveries` or the day's message ceiling: a probe is not a reminder.

**Why it exists (CLAUDE.md §3 rule 2):** RFC 8291's test vector proves the
encryption byte for byte, and a test proves the VAPID signature verifies — but
only Apple's, Google's or Mozilla's own service can say whether they accept
this request. A mismatch found here is a fix and a re-probe, not a rebuild.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime, timezone

from core import copy, push_api
from core.config import load_settings
from core.db import connection
from core.push import PushConfigError, build_request, endpoint_host
from core.services import push as push_service


def _claims(authorization: str) -> dict:
    token = authorization.split("t=", 1)[1].split(",", 1)[0]
    claims = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Web Push probe (W20). Dry by default.")
    parser.add_argument("--user", type=int, required=True, help="users.id — your own")
    parser.add_argument("--live", action="store_true", help="send ONE real push")
    args = parser.parse_args(argv)

    settings = load_settings()
    vapid = push_service.vapid_from(settings)
    if vapid is None:
        print("VAPID keys are not set in .env — `python -m core.push keys` makes them.")
        return 1
    try:
        vapid.check()
    except PushConfigError as exc:
        print(f"VAPID configuration refused: {exc}")
        return 1

    with connection() as conn:
        subs = push_service._subscriptions(conn, args.user)
    if not subs:
        print(f"learner {args.user} has no subscription. Turn reminders on in the "
              "app's menu on your phone first, then re-run.")
        return 1

    now = datetime.now(timezone.utc)
    message = {
        "title": copy.PUSH_TITLE,
        "body": copy.PUSH_REMINDER,
        "url": push_service.SESSION_URL,
    }
    requests = [build_request(sub, message, vapid, now=now) for sub in subs]

    print(f"calls --live will make: {len(requests)} (not billed; each is a real notification)")
    print(f"message: {json.dumps(message, ensure_ascii=False)}")
    for request in requests:
        headers = dict(request.headers)
        claims = _claims(headers.pop("Authorization"))
        print(f"\n=== POST https://{endpoint_host(request.endpoint)}/…")
        print(f"  Authorization: vapid t=<ES256 JWT {json.dumps(claims)}>, k=<VAPID_PUBLIC_KEY>")
        for name, value in headers.items():
            print(f"  {name}: {value}")
        print(f"  body: {len(request.body)} bytes (aes128gcm)")

    if not args.live:
        print("\nDRY: nothing was sent. Re-run with --live to send.")
        return 0

    typed = input(f"\nType the user id ({args.user}) to send {len(requests)} push(es): ")
    if typed.strip() != str(args.user):
        print("Stopped. Nothing was sent.")
        return 1
    for request in requests:
        result = push_api.send(request)
        print(f"  {endpoint_host(request.endpoint)}: {result.outcome} (HTTP {result.status})")
    print("\nRead: `sent` with 201 from every host, and the notification on the phone; "
          "a tap opens today's session. Anything else is a SHAPE MISMATCH — fix and re-probe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
