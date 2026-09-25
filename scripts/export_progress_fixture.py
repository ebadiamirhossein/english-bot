"""Regenerate `apps/web/components/progress/progress.fixture.json`.

    python scripts/export_progress_fixture.py            # write
    python scripts/export_progress_fixture.py --check    # exit 1 if stale

**#190's shape, from the start.** Vitest and the Playwright harness render
`/progress` against bodies built through the route's own serialiser
(`apps.api.routers.progress.progress_out`) from `core.services.progress.Progress`
values — never a hand-written guess at the shape.
`tests/test_progress_fixture.py` holds the committed keys to a real ASGI body.

**No database is touched.** The values are fixed inputs, chosen so each drawn
state exists: a learner in their first week (every number zero, one point), a
learner with a single day read (numbers, no line yet), and a learner some weeks
in (a line of several points, and one lapse so the line has a dip in it).

**W18:** `weeks_in` carries two finished placements — the second raised the
band from B1 to B2, and read LOWER on listening, which the radar does not show
(drops are silent) — built through `core.placement.scoring.shown`, the function
the service calls. The other three bodies have none (`placement: null`).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from apps.api.routers.progress import progress_out  # noqa: E402
from core.placement.scoring import Sitting, shown  # noqa: E402
from core.services.progress import KnownPoint, Progress  # noqa: E402

TARGET = REPO_ROOT / "apps" / "web" / "components" / "progress" / "progress.fixture.json"

TODAY = date(2026, 10, 14)


def _body(**fields) -> dict:
    return progress_out(Progress(**fields)).model_dump(mode="json")


def _placement():
    return shown((
        Sitting(TODAY - timedelta(days=35), "B1",
                {"vocabulary": "B1", "grammar": "B1", "listening": "B2", "speaking": "B1"},
                vocab_estimate=2900),
        Sitting(TODAY - timedelta(days=3), "B2",
                {"vocabulary": "B2", "grammar": "B2", "listening": "B1", "speaking": None},
                vocab_estimate=3300),
    ))


def bodies() -> dict:
    # Six reads over five weeks; the fourth is one word below the third — a
    # card graded *Again* moves a word back to `learning`, and the line shows it.
    counts = (41, 67, 88, 87, 120, 164)
    days = (35, 28, 21, 14, 7, 0)
    return {
        "empty": _body(
            known_words=0,
            known_history=(KnownPoint(TODAY, 0),),
            xp=0,
            streak_days=0,
            freezes=2,
            units_passed=0,
        ),
        "first_day": _body(
            known_words=12,
            known_history=(KnownPoint(TODAY, 12),),
            xp=38,
            streak_days=1,
            freezes=2,
            units_passed=0,
        ),
        "weeks_in": _body(
            known_words=164,
            known_history=tuple(
                KnownPoint(TODAY - timedelta(days=d), n) for d, n in zip(days, counts)
            ),
            xp=1246,
            streak_days=23,
            freezes=1,
            units_passed=2,
            placement=_placement(),
        ),
        "no_freezes": _body(
            known_words=164,
            known_history=tuple(
                KnownPoint(TODAY - timedelta(days=d), n) for d, n in zip(days, counts)
            ),
            xp=1246,
            streak_days=23,
            freezes=0,
            units_passed=1,
        ),
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
