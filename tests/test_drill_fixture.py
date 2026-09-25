"""W17 — the committed drill fixture against the real wire (#190).

`apps/web/components/session/drill.fixture.json` is what Vitest and Playwright
render. These tests hold it to what `GET /session/today` actually serves.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_drills import (  # noqa: F401 -- fixtures
    _focus, _item, _journal, app, auth_env, db, learner,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "apps" / "web" / "components" / "session" / "drill.fixture.json"


def test_the_committed_drill_fixture_is_current() -> None:
    """**Red method:** edit one string in the committed JSON — `--check` exits 1."""
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_drill_fixture.py"), "--check"],
        capture_output=True, text=True,
    )
    assert run.returncode == 0, run.stderr


def test_the_committed_drill_fixture_matches_the_wire(app, db, learner) -> None:
    """Block 3's payload keys, a unit item's keys and a drill's keys, compared
    with a real ASGI body for a learner holding one unit item and one evidenced
    drill. **Red method:** rename `pattern` in `focus_item_out` — the fixture is
    stale and the drill's key set here no longer matches."""
    _item(db, learner, cohort="focus", error_type=None, unit_number=1,
          prompt="I ___ my keys at the café yesterday.")
    _item(db, learner, error_type="article_wrong")
    _journal(db, learner, "article_wrong", 3)
    wire = _focus(app, learner)
    committed = json.loads(FIXTURE.read_text())["session_unit_first"]["blocks"][2]

    assert wire["state"] == committed["state"] == "ready"
    assert set(wire["payload"]) == set(committed["payload"])
    unit_w, drill_w = wire["payload"]["items"]
    unit_c, drill_c = committed["payload"]["items"][:2]
    assert set(unit_w) == set(unit_c)
    assert set(drill_w) == set(drill_c)
    assert drill_w["pattern"] == drill_c["pattern"] == "Articles"
    assert "pattern" not in unit_w and "pattern" not in unit_c
