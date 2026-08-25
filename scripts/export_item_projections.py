"""Regenerate `apps/web/lib/items/projections.fixture.json`.

    python scripts/export_item_projections.py           # write
    python scripts/export_item_projections.py --check    # exit 1 if stale

**Why a committed file rather than a fetch at test time.** It is the only thing
that makes the Python/TypeScript seam fail in *both* directions. A renderer that
reads a field the projection does not carry fails on the TypeScript side; a
projection change that is not re-exported fails on the Python side, in
`tests/test_items_web_contract.py`, which calls `--check`'s logic rather than
trusting a note in a README.

The envelope written here is the same shape `GET /items` puts on the wire —
`{id, response_mode, projection}` — and a second test asserts that per type
against a real ASGI response, so this file describes the wire and not merely a
function. `id` is the fixture's index and not a database id: nothing renders on
it and a real id would change on every seeding run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.items import RESPONSE_MODE  # noqa: E402
from core.items.grading import normalise_variants  # noqa: E402
from core.items.projection import visible_projection  # noqa: E402
from core.items.schema import parse  # noqa: E402

SOURCE = REPO_ROOT / "tests" / "fixtures" / "items" / "valid.json"
TARGET = REPO_ROOT / "apps" / "web" / "lib" / "items" / "projections.fixture.json"


def envelopes() -> list[dict]:
    rows = json.loads(SOURCE.read_text(encoding="utf-8"))
    out = []
    for index, row in enumerate(rows, start=1):
        draft = dict(row["item"])
        if draft.get("answer") is not None and "accepted_variants" not in draft:
            draft["accepted_variants"] = normalise_variants(draft["answer"])
        item = parse(draft)
        out.append(
            {
                "id": index,
                "response_mode": RESPONSE_MODE[item.item_type],
                "projection": visible_projection(item),
            }
        )
    return out


def rendered() -> str:
    return json.dumps(envelopes(), ensure_ascii=False, indent=2) + "\n"


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
    print(f"wrote {len(envelopes())} projections to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
