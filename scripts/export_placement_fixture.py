"""Regenerate `apps/web/components/placement/placement.fixture.json`.

    python scripts/export_placement_fixture.py            # write
    python scripts/export_placement_fixture.py --check    # exit 1 if stale

**#190's shape, from the start** (W19's exporter is the model). Vitest and the
Playwright harness render `/placement` against bodies built through the routes'
own serialisers (`apps.api.routers.placement.overview_out`, `step_out`,
`result_out`) from `core.services.placement` values — never a hand-written
guess at the shape. `tests/test_placement_fixture.py` holds the committed keys
to real ASGI bodies.

**No database is touched.** Each body is one state the screen draws: nothing
offered yet (no bank), ready to start, a step in each of the four parts, the
result of a first sitting, the result of a sitting that RAISED the band, and a
finished learner waiting for the next check.
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

from apps.api.routers.placement import overview_out, result_out, step_out  # noqa: E402
from core.placement.scoring import Sitting, next_sitting_from, shown  # noqa: E402
from core.services.placement import Overview, Result, Step  # noqa: E402

TARGET = REPO_ROOT / "apps" / "web" / "components" / "placement" / "placement.fixture.json"

TODAY = date(2026, 10, 14)

FIRST = Sitting(TODAY, "B1",
                {"vocabulary": "B2", "grammar": "B1", "listening": "B1", "speaking": "B1"},
                vocab_estimate=3300)
RAISED = (
    Sitting(TODAY - timedelta(days=30), "B1",
            {"vocabulary": "B1", "grammar": "B1", "listening": "B2", "speaking": None},
            vocab_estimate=2900),
    Sitting(TODAY, "B2",
            {"vocabulary": "B2", "grammar": "B2", "listening": "B1", "speaking": "B2"},
            vocab_estimate=3500),
)

STEPS = {
    "vocabulary": Step("vocabulary", {"id": 101, "word": "cupboard"}),
    "grammar": Step("grammar", {
        "id": 202, "response_mode": "typed",
        "projection": {"item_type": "cloze_cued",
                       "prompt_text": "By the time we got there, the film ___ already started."},
    }),
    "grammar_tap": Step("grammar", {
        "id": 203, "response_mode": "tap",
        "projection": {"item_type": "error_spot", "prompt_text": "Tap the word that is wrong.",
                       "tiles": ["She", "don't", "like", "coffee", "in", "the", "evening"]},
    }),
    "listening": Step("listening", {
        "id": 303, "response_mode": "typed",
        "projection": {"item_type": "listening_gap",
                       "prompt_text": "If I'd known, I ___ have come earlier."},
    }),
    "speaking": Step("speaking", {
        "id": 404, "prompt_text": "Describe a meal you remember well. Where were you, and who were you with?",
        "voice": False,
    }),
    "speaking_voice": Step("speaking", {
        "id": 404, "prompt_text": "Describe a meal you remember well. Where were you, and who were you with?",
        "voice": True,
    }),
    "done": Step("done"),
}


def bodies() -> dict:
    out: dict = {
        "not_ready": overview_out(Overview("none", False, False, None)).model_dump(mode="json"),
        "ready": overview_out(Overview("none", True, True, None)).model_dump(mode="json"),
        "open": overview_out(
            Overview("open", True, False, None, STEPS["grammar"])).model_dump(mode="json"),
        "waiting": overview_out(Overview(
            "finished", True, False, next_sitting_from(FIRST.finished_on), None,
            shown((FIRST,)))).model_dump(mode="json"),
        "steps": {k: step_out(v).model_dump(mode="json") for k, v in STEPS.items()},
        "result_first": result_out(Result(
            shown((FIRST,)), next_sitting_from(FIRST.finished_on))).model_dump(mode="json"),
        "result_raised": result_out(Result(
            shown(RAISED), next_sitting_from(RAISED[-1].finished_on))).model_dump(mode="json"),
    }
    return out


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
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
