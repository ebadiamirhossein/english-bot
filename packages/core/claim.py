"""Operator CLI for first-enrolment claim tokens.

    python -m core.claim create --email a@b.c --name "Ada" --native-language lt
    python -m core.claim issue --telegram-user-id 123456789 [--hours 24]
    python -m core.claim issue --user-id 4 [--hours 24]
    python -m core.claim list
    python -m core.claim revoke --telegram-user-id 123456789

**Argparse and printing only. Every query is in ``core.services.auth``** —
``tests/test_core_boundary.py::test_no_sql_outside_services`` exempts
``core/services/`` and ``migrations/`` and nothing else, so a query here would
fail on the commit that added it.

**A Telegram learner is addressed by ``telegram_user_id``, never by email**, so
no address enters shell history, a terminal scrollback or a screen share for the
people who already exist.

``create`` is the exception and has to be: since W4b a learner can exist without
a Telegram account, and such a person has no Telegram id to be addressed by. The
address is typed once, here, at the moment the account is made -- which is also
the moment ``auth_email`` stops being something the operator sets by hand in
psql. ``--user-id`` on ``issue`` and ``revoke`` exists for the same reason.

This is the whole of W4b's web sign-up: a service function and an operator
command. There is no public route and no sign-up screen -- that is a
learner-facing surface and belongs to a later slice.

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
from core.services import auth, identity


def _resolve(args: argparse.Namespace) -> tuple[int, str]:
    """(internal user id, how it was named) from --user-id or --telegram-user-id.

    Exactly one is required. The translation happens through
    ``core.services.identity`` like every other one in the codebase -- a CLI is
    not a reason for a second path.
    """
    if getattr(args, "user_id", None) is not None:
        return int(args.user_id), f"user_id={args.user_id}"
    telegram_user_id = int(args.telegram_user_id)
    user_id = identity.user_id_for_telegram(telegram_user_id)
    if user_id is None:
        raise SystemExit(f"no user with telegram_user_id={telegram_user_id}")
    return user_id, f"telegram_user_id={telegram_user_id}"


def _create(args: argparse.Namespace) -> int:
    user_id = identity.create_web_user(
        email=args.email,
        name=args.name,
        native_language=args.native_language,
        cefr_level=args.cefr_level,
    )
    print(f"Created user_id={user_id} with no telegram_user_id.")
    print()
    print("They are approved and onboarded. Next:")
    print(f"    python -m core.claim issue --user-id {user_id}")
    print("then hand the token over in person.")
    return 0


def _issue(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    user_id, named = _resolve(args)
    token = auth.issue_claim_token(user_id=user_id, now=now, hours=args.hours)
    hours = args.hours or load_settings().auth_claim_token_hours
    print(f"Claim token for {named}:")
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
    user_id, named = _resolve(args)
    count = auth.revoke_claim_tokens(
        user_id=user_id, now=datetime.now(timezone.utc)
    )
    print(f"Spent {count} outstanding token(s) for {named}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m core.claim",
        description="Issue and manage one-time passkey enrolment tokens.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser(
        "create", help="make a learner who has no Telegram account"
    )
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--native-language", required=True)
    create.add_argument("--cefr-level", default="B1")
    create.set_defaults(func=_create)

    issue = sub.add_parser("issue", help="mint a token and print it once")
    issue_who = issue.add_mutually_exclusive_group(required=True)
    issue_who.add_argument("--telegram-user-id", type=int)
    issue_who.add_argument("--user-id", type=int)
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
    revoke_who = revoke.add_mutually_exclusive_group(required=True)
    revoke_who.add_argument("--telegram-user-id", type=int)
    revoke_who.add_argument("--user-id", type=int)
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
