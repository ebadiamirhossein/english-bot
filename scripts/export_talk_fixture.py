"""Regenerate `apps/web/components/session/talk.fixture.json`. **W15.**

    python scripts/export_talk_fixture.py            # write
    python scripts/export_talk_fixture.py --check    # exit 1 if stale

**#190's shape, for `/talk` and its two rungs.** The Vitest test
(`components/session/talk-rungs.test.tsx`) and the Playwright spec
(`e2e/talk.spec.ts`) both render THESE bodies, and `tests/test_talk_fixture.py`
compares their key sets against real ASGI responses. Every body is built by the
route's own response model (`RungsOut`, `TurnOut`, `CloseOut`), so the fixture
cannot describe a shape the routes do not serve.

**No database is touched and nothing is generated.** The answer's task and
can-do are read from `data/syllabus_units.json` (unit 1), exactly as the route
serves them; everything else is fixture English written here. Tokens are fixed
placeholders — a real one is an HMAC under the host's secret, and the client
echoes it back unread.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from apps.api.routers.conversation import (  # noqa: E402
    CloseOut,
    CorrectionOut,
    RungOut,
    RungsOut,
    TurnOut,
    WordOfferOut,
)
from core.services.conversations import RETELL_OPENER  # noqa: E402

TARGET = REPO_ROOT / "apps" / "web" / "components" / "session" / "talk.fixture.json"
UNIT_1 = json.loads((REPO_ROOT / "data" / "syllabus_units.json").read_text(encoding="utf-8"))[0]
VIDEO_TITLE = "Why Londoners queue for everything"


def _dump(model) -> dict:
    return model.model_dump(mode="json")


def bodies() -> dict:
    turn = lambda **kw: _dump(TurnOut(conversation_id=41, **kw))  # noqa: E731
    return {
        "rungs_both": _dump(RungsOut(
            answer=RungOut(label=UNIT_1["can_do"], prompt=UNIT_1["output_task_spoken"]),
            retell=RungOut(label=VIDEO_TITLE, prompt=None),
            voice=False,
        )),
        "rungs_both_voice": _dump(RungsOut(
            answer=RungOut(label=UNIT_1["can_do"], prompt=UNIT_1["output_task_spoken"]),
            retell=RungOut(label=VIDEO_TITLE, prompt=None),
            voice=True,
        )),
        # No video today: the retell card is absent, never greyed.
        "rungs_answer_only": _dump(RungsOut(
            answer=RungOut(label=UNIT_1["can_do"], prompt=UNIT_1["output_task_spoken"]),
            retell=None,
            voice=False,
        )),
        "topics": {"topics": ["A wedding you went to recently", "Your favourite café in town",
                              "Something you cooked this week"], "voice": False},
        "open_talk": turn(topic_label="A wedding you went to recently",
                          reply="Oh, a wedding! Whose was it, and where?", state="open"),
        "turn_talk": turn(topic_label="A wedding you went to recently",
                          reply="Trakai is beautiful. Was it by the lake?", state="open"),
        # A spoken TALK turn: what was heard, then the app's reply (#427).
        "turn_talk_voice": turn(
            topic_label="A wedding you went to recently",
            reply="Trakai is beautiful. Was it by the lake?", state="open",
            heard="It was my girlfriend's cousin, in Trakai.",
        ),
        "open_answer": turn(topic_label=UNIT_1["can_do"], reply=UNIT_1["output_task_spoken"],
                            state="open"),
        "open_retell": turn(topic_label=VIDEO_TITLE, reply=RETELL_OPENER, state="open"),
        # A rung's one turn: no reply, and the client closes.
        "turn_rung": turn(topic_label=UNIT_1["can_do"], reply="", state="closing"),
        # A spoken rung turn: what was heard comes back as the learner's line.
        "turn_rung_voice": turn(
            topic_label=UNIT_1["can_do"], reply="", state="closing",
            heard="Yesterday I wake up at seven and I go to work by bus.",
        ),
        "close_answer": _dump(CloseOut(
            conversation_id=41,
            corrections=[
                CorrectionOut(you_said="I wake up at seven", correct_form="I woke up at seven",
                              explanation="It was yesterday, so the verb moves into the past: woke.",
                              label="Past tense"),
                CorrectionOut(you_said="I go to work by bus", correct_form="I went to work by bus",
                              explanation="Same reason: it's finished, so it's went.",
                              label="Past tense"),
            ],
            did_well="You kept the day in order, from the alarm to the film.",
            summary="",
            word_offers=[WordOfferOut(word="pasta", token="fixture-talk-0"),
                         WordOfferOut(word="alarm", token="fixture-talk-1")],
            is_english=True, covered=[], also=[],
        )),
        "close_retell": _dump(CloseOut(
            conversation_id=42,
            corrections=[
                CorrectionOut(you_said="people waits in a line",
                              correct_form="people wait in a line",
                              explanation="People is plural, so the verb has no s: wait.",
                              label="Subject and verb"),
            ],
            did_well="You started with the bus stop, which puts the listener right there.",
            summary="",
            word_offers=[],
            is_english=True,
            covered=["Londoners queue even when nobody tells them to.",
                     "Jumping the queue is seen as very rude."],
            also=["The habit grew during the Second World War, when food was rationed.",
                  "Visitors are often surprised by how quiet a queue is."],
        )),
        "close_not_english": _dump(CloseOut(
            conversation_id=43, corrections=[], did_well="", summary="", word_offers=[],
            is_english=False, covered=[], also=[],
        )),
    }


def rendered() -> str:
    return json.dumps(bodies(), ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    current = rendered()
    if args.check:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != current:
            print(f"{TARGET} is stale — run scripts/export_talk_fixture.py", file=sys.stderr)
            return 1
        print(f"{TARGET} is current")
        return 0
    TARGET.write_text(current, encoding="utf-8")
    print(f"wrote {len(bodies())} bodies to {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
