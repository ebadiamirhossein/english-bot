"""Regenerate `apps/web/components/session/session-today.fixture.json`.

    python scripts/export_session_fixture.py            # write
    python scripts/export_session_fixture.py --check    # exit 1 if stale

**This file exists because of #190, and it exists in the shape
`scripts/export_item_projections.py` already established.**

W10 shipped a daily session whose block 1 crashed on the first card a learner
graded: the block serialised `Card.face()`, which has no `intervals`, while the
client's `CardFace` type declares `intervals` and `GradeButtons` reads it
unguarded. **Both suites were green.** Vitest hand-wrote its card fixtures, so
what the client *expected* and what the server *produced* were two independent
inventions that had never met.

So the Vitest session tests read a card face that Python generated through the
real `core.services.cards.card_face`, and
`tests/test_session_route.py::test_the_committed_session_fixture_matches_the_wire`
compares this committed file against a real ASGI response body. That is what
makes the seam fail in **both** directions:

* a component reading a field the face does not carry fails on the TypeScript
  side;
* a serialiser change that is not re-exported fails on the Python side;
* and a fixture that has drifted from what the route actually serves fails too —
  which is the assertion that stops this file describing a function while the
  wire describes something else.

**No database is touched.** The card is built in memory and passed through the
same `card_face` the route and the session both call, which is the whole point:
a fixture generated from a *different* path than production would agree with
itself forever (`tests/test_items_route.py` records that mistake being made once
in this repository already).

`id` is a fixed number and not a database id: nothing renders on it, and a real
id would change on every seeding run.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.cards.fsrs import CardState  # noqa: E402
from core.services.cards import Card, card_face  # noqa: E402

TARGET = (
    REPO_ROOT / "apps" / "web" / "components" / "session" / "session-today.fixture.json"
)

#: Frozen, so the intervals in the committed file do not change on a re-run.
#: `core.cards.fsrs` runs with `enable_fuzzing=False`, so a due date is
#: reproducible and this is the only other source of drift.
NOW = datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc)


def _mature(now: datetime) -> CardState:
    return CardState(
        fsrs_state="review",
        fsrs_step=None,
        stability=10.0,
        difficulty=5.0,
        due=now,
        last_review=now,
        lapses=0,
        reps=4,
    )


def _card(**over) -> Card:
    spec = dict(
        id=41,
        user_id=3,
        card_type="production",
        source_chunk_id=None,
        source_ref="vocabulary",
        # A real production front: a Farsi gloss above an English hint, in one
        # field — `migrate_chunks.py:245`'s shape, which is what makes the
        # per-line bidi handling worth rendering against.
        front="احساس گیر افتادن\nI _____ in this job.",
        back="feel trapped",
        context_sentence=None,
        meaning="احساس گیر افتادن",
        neutral_equivalent=None,
        neutral_lexeme_id=None,
        who_says_this=None,
        lexeme_id=None,
        cue_text=None,
        register="neutral",
        register_source="import_default",
        neutral_mastered_at=None,
        state=_mature(NOW),
        leech_at=None,
    )
    spec.update(over)
    return Card(**spec)


def faces() -> list[dict]:
    """One card per behaviour the session renders, through the real serialiser.

    Two, and both are needed: a `production` card takes a typed answer and a
    `recognition` card keeps the self-mark (#157), and **#190 crashed on both**
    — the split was never typed-versus-reveal, it was session-versus-`/review`.
    """
    return [
        card_face(_card(), now=NOW),
        card_face(
            _card(
                id=42,
                card_type="recognition",
                front="So that's a hard pass from me.",
                back="hard pass",
                meaning="a firm refusal",
                context_sentence="So that's a hard pass from me.",
            ),
            now=NOW,
        ),
    ]


def rendered() -> str:
    return json.dumps(faces(), ensure_ascii=False, indent=2) + "\n"


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
    TARGET.write_text(current, encoding="utf-8")
    print(f"wrote {len(faces())} card faces to {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
