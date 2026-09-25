"""Regenerate `apps/web/components/push/push.fixture.json`.

    python scripts/export_push_fixture.py            # write
    python scripts/export_push_fixture.py --check    # exit 1 if stale

**#190's shape, from the start.** Vitest and the Playwright harness draw W20's
reminder control against bodies built through the real route and schemas —
never a hand-written guess at the shape:

- ``key_set`` / ``key_unset`` are what `GET /push/key` returns, produced by
  calling the route function itself (`apps.api.routers.push.key`) with two
  `Settings` values: one carrying a VAPID pair, one carrying none.
- ``on`` / ``off`` are `PushStateOut`, the only body `/push/subscribe`,
  `/push/unsubscribe` and `/push/state` return. Those three routes write or read
  the database, so their bodies are built from the schema the route declares as
  its ``response_model`` rather than by calling them.
- ``subscription`` is a browser's `PushSubscription.toJSON()` as the Playwright
  stub hands it over, validated by `PushSubscriptionIn` — so the harness posts a
  body the real route would accept, not one it would 422.

A Python test holding the committed keys to a real ASGI body is owed alongside
this file (the `tests/test_progress_fixture.py` pattern).

**No database is touched and no push is sent.** The VAPID pair is derived from
a fixed scalar so the output is byte-stable for ``--check``; it is a test
constant that signs nothing, and it is never a production key (production's
lives in the server's `.env`, CLAUDE.md §5).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

from apps.api.routers.push import key as key_route  # noqa: E402
from apps.api.schemas import PushStateOut, PushSubscriptionIn  # noqa: E402
from core.config import Settings  # noqa: E402
from core.push import b64url_encode  # noqa: E402

TARGET = REPO_ROOT / "apps" / "web" / "components" / "push" / "push.fixture.json"

# A fixed, obviously-not-secret scalar: the fixture must be byte-stable.
_FIXTURE_SCALAR = 0x57_20_57_20_57_20_57_20
# Likewise fixed: a browser-side key pair and auth secret for the stub's
# subscription. `p256dh` is a real P-256 point, so the body is a shape the
# route accepts and a push could in principle be encrypted to.
_BROWSER_SCALAR = 0x0B_0B_0B_0B_0B_0B_0B_0B


def _point(scalar: int) -> tuple[str, str]:
    private = ec.derive_private_key(scalar, ec.SECP256R1())
    raw = private.private_numbers().private_value.to_bytes(32, "big")
    public = private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return b64url_encode(raw), b64url_encode(public)


def _settings(**vapid: str) -> Settings:
    # Every field the route does not read is left at its empty default: no
    # database URL, no token, no key.
    return Settings(database_url="", telegram_bot_token="", llm_api_key="", **vapid)


def bodies() -> dict:
    private, public = _point(_FIXTURE_SCALAR)
    _, browser_public = _point(_BROWSER_SCALAR)
    subscription = PushSubscriptionIn.model_validate(
        {
            # `.invalid` (RFC 2606): a host that can never resolve, so nothing
            # built from this fixture can reach a real push service.
            "endpoint": "https://push.example.invalid/w20-fixture-endpoint",
            "expirationTime": None,
            "keys": {"p256dh": browser_public, "auth": b64url_encode(bytes(range(16)))},
        }
    )
    return {
        "key_set": key_route(
            session=None,
            settings=_settings(
                vapid_private_key=private,
                vapid_public_key=public,
                vapid_subject="mailto:fixture@example.invalid",
            ),
        ).model_dump(mode="json"),
        "key_unset": key_route(session=None, settings=_settings()).model_dump(mode="json"),
        "on": PushStateOut(on=True).model_dump(mode="json"),
        "off": PushStateOut(on=False).model_dump(mode="json"),
        "subscription": subscription.model_dump(mode="json"),
    }


def rendered() -> str:
    return json.dumps(bodies(), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if stale")
    args = parser.parse_args(argv)
    current = rendered()
    if args.check:
        on_disk = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else ""
        if on_disk != current:
            print(f"{TARGET} is stale — re-run without --check", file=sys.stderr)
            return 1
        print(f"{TARGET} is current")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(current, encoding="utf-8")
    print(f"wrote {len(bodies())} bodies to {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
