"""W16a: `apps/web/components/write/write.fixture.json` describes the wire.

**#190's contract, applied before the defect rather than after it.** Vitest and
Playwright render `/write` against this file. If it were hand-written, what the
client expects and what the server sends would be two independent inventions —
which is how block 1 crashed on the first graded card with both suites green.

Two checks, the session fixture's exactly:

1. **Current** — the exporter's own `--check`, in a subprocess, so what is
   verified is the command a person runs.
2. **The wire** — the committed keys against REAL ASGI response bodies. A
   fixture compared only with its own exporter agrees with itself forever.

**RED DEMONSTRATIONS:** a key added to `CorrectionResult` without re-exporting
turned `test_the_committed_write_fixture_matches_the_wire` red; one character
edited in the committed JSON turned `test_the_committed_write_fixture_is_current`
red.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_writing_route import (  # noqa: F401 — fixtures used by name
    CLEAN,
    THREE,
    app,
    auth_env,
    db,
    jar,
    learner,
    no_provider,
    post,
    request,
    stub_model,
)

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "apps" / "web" / "components" / "write" / "write.fixture.json"
EXPORTER = REPO / "scripts" / "export_write_fixture.py"


def _committed() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_the_committed_write_fixture_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(EXPORTER), "--check"], capture_output=True, text=True, cwd=REPO
    )
    assert result.returncode == 0, (
        "write.fixture.json is stale — re-run `python scripts/export_write_fixture.py`\n"
        + result.stderr
    )


def test_the_committed_write_fixture_matches_the_wire(app, learner, monkeypatch) -> None:
    committed = _committed()

    today = request(app, "GET", "/write/today", cookies=jar(learner)).json()
    assert set(committed["today"]) == set(today)

    stub_model(monkeypatch, THREE)
    served = post(app, learner).json()
    assert set(committed["two"]) == set(served)
    assert set(committed["two"]["corrections"][0]) == set(served["corrections"][0])

    stub_model(monkeypatch, CLEAN)
    clean = post(app, learner).json()
    assert set(committed["clean_no_line"]) == set(clean)

    session = request(app, "GET", "/session/today", cookies=jar(learner)).json()
    assert set(committed["session"]) == set(session)
    served_four = next(b for b in session["blocks"] if b["kind"] == "output")
    committed_four = next(b for b in committed["session"]["blocks"] if b["kind"] == "output")
    assert committed_four["payload"] == served_four["payload"]


@pytest.mark.parametrize("name", ["two", "one", "clean_no_line", "no_label", "not_english"])
def test_no_committed_body_carries_a_null(name) -> None:
    """Absent means absent (Ruling 2): the route serialises with exclude_none."""

    def walk(value):
        if value is None:
            return True
        if isinstance(value, dict):
            return any(walk(v) for v in value.values())
        if isinstance(value, list):
            return any(walk(v) for v in value)
        return False

    assert not walk(_committed()[name])
