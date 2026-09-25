"""W18: `apps/web/components/placement/placement.fixture.json` describes the wire.

#190's contract, W19's shape: Vitest and Playwright render `/placement` from
this file, so it is checked two ways — the exporter's own `--check` and the
committed keys against REAL ASGI bodies from a sitting driven through the routes.

**RED DEMONSTRATIONS (2026-09-25):** one field added to `PlacementItemOut`
without re-exporting turned `test_the_committed_placement_fixture_matches_the_wire`
red; one character edited in the committed JSON turned
`test_the_committed_placement_fixture_is_current` red.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.support import placement_seed as ps
from tests.test_placement_route import bank  # noqa: F401 — fixture used by name
from tests.test_progress_route import (  # noqa: F401 — fixtures used by name
    app,
    auth_env,
    db,
    learners,
)

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "apps" / "web" / "components" / "placement" / "placement.fixture.json"
EXPORTER = REPO / "scripts" / "export_placement_fixture.py"


def test_the_committed_placement_fixture_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(EXPORTER), "--check"], capture_output=True, text=True, cwd=REPO
    )
    assert result.returncode == 0, (
        "placement.fixture.json is stale — re-run `python scripts/export_placement_fixture.py`\n"
        + result.stderr
    )


def test_the_committed_placement_fixture_matches_the_wire(app, db, bank, learners, monkeypatch) -> None:
    monkeypatch.setenv("VOICE_ALLOWED_USER_IDS", "")
    committed = json.loads(FIXTURE.read_text(encoding="utf-8"))
    learner = learners()
    overview = ps.call(app, "GET", "/placement", learner).json()
    for name in ("not_ready", "ready", "open", "waiting"):
        assert set(committed[name]) == set(overview), name
    step = ps.call(app, "POST", "/placement/start", learner, body={}).json()
    for name, body in committed["steps"].items():
        assert set(body) == set(step), name
        if body["item"] is not None:
            assert set(body["item"]) == set(step["item"]), name
    ps.run_sitting(app, db, learner)  # resumes the open sitting to the end
    result = ps.call(app, "POST", "/placement/finish", learner, body={}).json()
    for name in ("result_first", "result_raised"):
        assert set(committed[name]) == set(result), name
        assert set(committed[name]["shown"]) == set(result["shown"]), name
        for axis in committed[name]["shown"]["radar"]:
            assert set(axis) == set(result["shown"]["radar"][0]), name
