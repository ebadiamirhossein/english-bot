"""Operator CLI for first-enrolment claim tokens.

    python -m core.claim issue --telegram-user-id 123456789 [--hours 24]
    python -m core.claim list
    python -m core.claim revoke --telegram-user-id 123456789

**Argparse and printing only. Every query is in ``core.services.auth``** —
``tests/test_core_boundary.py::test_no_sql_outside_services`` exempts
``core/services/`` and ``migrations/`` and nothing else, so a query here would
fail on the commit that added it.

**Learners are addressed by ``telegram_user_id``, never by email**, so no
address ever enters shell history, a terminal scrollback or a screen share. The
operator sets ``auth_email`` once, by hand, from psql; this command never needs
to see it.

Why a token at all: with no email sender in this slice there is no way to prove
someone owns an address, so a pre-seeded ``auth_email`` is an identifier and not
an authentication factor. If typing an existing address were enough, whoever
typed it first would own the error journal behind it. The token is the factor
that stands in for verification, and it is handed over **out of band** — in
person or by voice, never through the channel the app is reached on.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from core.config import ConfigError, load_settings
from core.services import auth


def _issue(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    token = auth.issue_claim_token(
        user_id=args.telegram_user_id, now=now, hours=args.hours
    )
    hours = args.hours or load_settings().auth_claim_token_hours
    print(f"Claim token for telegram_user_id={args.telegram_user_id}:")
    print()
    print(f"    {token}")
    print()
    print(f"Valid for {hours}h. Single use. Only its SHA-256 digest is stored,")
    print("so this is the one and only time it can be read — hand it over in")
    print("person, not through Telegram or the app.")
    return 0


def _list(_: argparse.Namespace) -> int:
    records = auth.list_claim_tokens()
    if not records:
        print("No claim tokens.")
        return 0
    print(f"{'user_id':>12}  {'created':<20} {'expires':<20} used")
    for record in records:
        used = record.used_at.strftime("%Y-%m-%d %H:%M") if record.used_at else "—"
        print(
            f"{record.user_id:>12}  "
            f"{record.created_at.strftime('%Y-%m-%d %H:%M'):<20} "
            f"{record.expires_at.strftime('%Y-%m-%d %H:%M'):<20} {used}"
        )
    # Neither the token nor the address is printed, by design: this output is
    # for deciding whether to issue another one, not for recovering one.
    return 0


def _revoke(args: argparse.Namespace) -> int:
    count = auth.revoke_claim_tokens(
        user_id=args.telegram_user_id, now=datetime.now(timezone.utc)
    )
    print(f"Spent {count} outstanding token(s) for {args.telegram_user_id}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m core.claim",
        description="Issue and manage one-time passkey enrolment tokens.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    issue = sub.add_parser("issue", help="mint a token and print it once")
    issue.add_argument("--telegram-user-id", type=int, required=True)
    issue.add_argument(
        "--hours",
        type=int,
        default=None,
        help="lifetime in hours (default: AUTH_CLAIM_TOKEN_HOURS, 24)",
    )
    issue.set_defaults(func=_issue)

    listing = sub.add_parser("list", help="show outstanding and spent tokens")
    listing.set_defaults(func=_list)

    revoke = sub.add_parser("revoke", help="spend every outstanding token")
    revoke.add_argument("--telegram-user-id", type=int, required=True)
    revoke.set_defaults(func=_revoke)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001 — a CLI reports, it does not traceback
        print(f"Failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
