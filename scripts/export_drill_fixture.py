"""Regenerate `apps/web/components/session/drill.fixture.json`. **W17.**

    python scripts/export_drill_fixture.py            # write
    python scripts/export_drill_fixture.py --check    # exit 1 if stale

**#190's shape, for block 3 with a weak-spot drill in it.** The Vitest test
(`components/session/focus-drill.test.tsx`) and the Playwright spec
(`e2e/drills.spec.ts`) both render THIS body, and
`tests/test_drill_fixture.py` compares it against a real ASGI response from
`GET /session/today` for a seeded learner with a drill. Each item goes through
`core.services.sessions.focus_item_out` — the function the route uses — and each
projection through the real `visible_projection`, so the fixture cannot describe
a shape the route does not serve.

**No database is touched.** Ids are fixed numbers; nothing renders on them.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from apps.api.schemas import BlockOut, ItemAnswerResult, SessionTodayOut  # noqa: E402
from core.items import RESPONSE_MODE  # noqa: E402
from core.items.projection import visible_projection  # noqa: E402
from core.items.schema import parse  # noqa: E402
from core.services.items import ItemPresentation  # noqa: E402
from core.services.sessions import focus_item_out  # noqa: E402

TARGET = REPO_ROOT / "apps" / "web" / "components" / "session" / "drill.fixture.json"


def _presentation(item_id: int, draft: dict) -> ItemPresentation:
    item = parse(draft)
    return ItemPresentation(
        id=item_id,
        response_mode=RESPONSE_MODE[item.item_type],
        projection=visible_projection(item),
    )


UNIT_ITEM = {
    "item_type": "cloze_cued", "track": "life",
    "prompt_text": "I ___ my keys at the café yesterday.", "answer": "left",
    "accepted_variants": ["left"], "unit_number": 1,
    "grammar_target": "past simple: regular and irregular verbs", "cohort": "focus",
}
DRILL_ITEM = {
    "item_type": "cloze_cued", "track": "life",
    "prompt_text": "Can you pass me ___ umbrella by the door?", "answer": "the",
    "accepted_variants": ["the"], "error_type": "article_wrong",
    "grammar_target": "Articles: choosing between a, an, the and no article",
    "cohort": "drill",
}
DRILL_SPOT = {
    "item_type": "error_spot", "track": "life",
    "prompt_text": "Tap the word that is wrong.",
    "tiles": ["She", "go", "to", "the", "gym", "on", "Mondays."],
    "wrong_index": 1, "correction": "goes", "answer": "goes",
    "error_type": "subject_verb_agreement",
    "grammar_target": "Subject-verb agreement, including the third-person -s",
    "cohort": "drill",
}


def focus_payload(*, answered: int) -> dict:
    """Block 3's `ready` payload: the keys `_focus_block` returns, one unit item
    then two drills. `answered` positions the runner (#275)."""
    items = [
        focus_item_out(_presentation(501, UNIT_ITEM), seen=False, pattern=None),
        focus_item_out(_presentation(502, DRILL_ITEM), seen=False, pattern="Articles"),
        focus_item_out(_presentation(503, DRILL_SPOT), seen=True, pattern="Subject and verb"),
    ]
    return {
        "answered": answered,
        "unit_number": 1,
        "can_do": "Can tell a short story about something that happened yesterday.",
        "grammar_targets": [{"target": "past simple: regular and irregular verbs"}],
        "lesson": None,
        "lesson_section": None,
        "teaching_complete": False,
        "items": items,
    }


def session(*, answered: int) -> dict:
    blocks = [
        BlockOut(n=1, kind="review", state="empty", payload={}),
        BlockOut(n=2, kind="input", state="empty", payload={}),
        BlockOut(n=3, kind="focus", state="ready", payload=focus_payload(answered=answered)),
        BlockOut(n=4, kind="output", state="empty", payload={}),
        BlockOut(n=5, kind="close", state="ready",
                 payload={"cards_reviewed": 0, "blocks_completed": 0, "block_count": 5}),
    ]
    return SessionTodayOut(
        session_id=91, date=date(2026, 9, 25), l1_language="fa", current_block=3,
        completed=False, blocks=blocks,
    ).model_dump(mode="json")


def bodies() -> dict:
    return {
        # The runner opens on the unit item; the drills follow it.
        "session_unit_first": session(answered=0),
        # Resumed on the first drill (#275's position).
        "session_on_drill": session(answered=1),
        # Resumed on the second drill, which the learner met before (#276 c).
        "session_on_seen_drill": session(answered=2),
        # `POST /items/{id}/answer` for the article drill, through the route's
        # own response model. `murphy_units` is null here; on the real wire an
        # item with an `error_type` carries the column (#104) and nothing
        # renders it (W8h).
        "answer_drill": ItemAnswerResult(
            correct=True,
            graded_by="deterministic",
            canonical="the",
            explanation="The, because you both know which umbrella: the one by the door.",
            murphy_units=None,
        ).model_dump(mode="json"),
    }


def rendered() -> str:
    return json.dumps(bodies(), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    current = rendered()
    if args.check:
        on_disk = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else ""
        if on_disk != current:
            print(f"{TARGET} is stale — re-run without --check", file=sys.stderr)
            return 1
        print(f"{TARGET} is current")
        return 0
    TARGET.write_text(current, encoding="utf-8")
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
