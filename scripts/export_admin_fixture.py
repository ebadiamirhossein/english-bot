"""Regenerate `apps/web/components/admin/admin.fixture.json`.

    python scripts/export_admin_fixture.py            # write
    python scripts/export_admin_fixture.py --check    # exit 1 if stale

**#190's shape.** Vitest and the Playwright harness render `/admin` against
bodies built through the route's own serialiser (`apps.api.routers.admin.admin_out`)
from `core.services.admin_panel` values — never a hand-written guess at the
shape. `tests/test_admin_fixture.py` holds the committed keys to a real ASGI body.

**No database is touched**, and **the names are invented** — the two real
learners' names do not belong in a committed file.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from apps.api.routers.admin import admin_out  # noqa: E402
from core.services.admin_panel import AdminUserRow, OperatorActivity  # noqa: E402

TARGET = REPO_ROOT / "apps" / "web" / "components" / "admin" / "admin.fixture.json"

TODAY = date(2026, 10, 14)


def _user(**fields) -> AdminUserRow:
    base = dict(
        id=1,
        telegram_user_id=None,
        name="Rasa",
        cefr_level="B1",
        current_streak=0,
        active_days=0,
        last_active=None,
        paused=False,
        revoked=False,
    )
    base.update(fields)
    return AdminUserRow(**base)


def _body(users: list[AdminUserRow], pending: int = 0) -> dict:
    return admin_out(
        OperatorActivity(
            pending_requests=pending,
            weekly_goal_days=5,
            lookback_days=7,
            users=users,
        )
    ).model_dump(mode="json")


def bodies() -> dict:
    return {
        # Two learners on an ordinary week: one practising daily, one paused.
        "two": _body(
            [
                _user(id=11, name="Darius", cefr_level="B2", current_streak=23,
                      active_days=6, last_active=TODAY),
                _user(id=12, name="Rasa", current_streak=4, active_days=3,
                      last_active=date(2026, 10, 12), paused=True),
            ]
        ),
        # A revoked learner, one who never practised, a long name, and a request waiting.
        "mixed": _body(
            [
                _user(id=21, name="Konstantinas-Aleksandras Vaitkevičius-Žemaitis",
                      current_streak=1, active_days=1, last_active=TODAY),
                _user(id=22, name="Mehrnoosh", cefr_level="A2"),
                _user(id=23, name="Tomas", current_streak=0, active_days=0,
                      last_active=date(2026, 9, 1), revoked=True),
            ],
            pending=1,
        ),
        "none": _body([]),
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
