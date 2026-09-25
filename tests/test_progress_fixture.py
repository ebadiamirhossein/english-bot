"""W19: `apps/web/components/progress/progress.fixture.json` describes the wire.

#190's contract: Vitest and Playwright render `/progress` from this file, so it
is checked two ways — the exporter's own `--check` (the command a person runs)
and the committed keys against a REAL ASGI body. A fixture compared only with
its own exporter agrees with itself forever.

**RED DEMONSTRATIONS (2026-09-25):** a `units_mastered: int = 0` field added to
`ProgressOut` without re-exporting turned
`test_the_committed_progress_fixture_matches_the_wire` red; one digit edited in
the committed JSON turned `test_the_committed_progress_fixture_is_current` red.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from apps.api.deps import SESSION_COOKIE_SECURE
from tests.test_progress_route import (  # noqa: F401 — fixtures used by name
    app,
    auth_env,
    db,
    learners,
    request,
)

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "apps" / "web" / "components" / "progress" / "progress.fixture.json"
EXPORTER = REPO / "scripts" / "export_progress_fixture.py"


def test_the_committed_progress_fixture_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(EXPORTER), "--check"], capture_output=True, text=True, cwd=REPO
    )
    assert result.returncode == 0, (
        "progress.fixture.json is stale — re-run `python scripts/export_progress_fixture.py`\n"
        + result.stderr
    )


def test_the_committed_progress_fixture_matches_the_wire(app, learners) -> None:
    learner = learners()
    wire = request(
        app, "GET", "/progress", cookies={SESSION_COOKIE_SECURE: learner.cookie}
    ).json()
    committed = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert set(committed) == {"empty", "first_day", "weeks_in", "no_freezes"}
    for name, body in committed.items():
        assert set(body) == set(wire), name
        for point in body["known_history"]:
            assert set(point) == set(wire["known_history"][0]), name
