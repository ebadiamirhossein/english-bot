"""W23: `apps/web/components/admin/admin.fixture.json` describes the wire.

#190's contract, as `tests/test_progress_fixture.py` holds it for `/progress`:
the exporter's own `--check`, and the committed keys against a REAL ASGI body.

**RED DEMONSTRATIONS (2026-09-25):** a `last_seen: str | None = None` field
added to `AdminUserOut` without re-exporting turned
`test_the_committed_admin_fixture_matches_the_wire` red; one digit edited in
the committed JSON turned `test_the_committed_admin_fixture_is_current` red.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.test_admin_route import (  # noqa: F401 — fixtures used by name
    _get,
    auth_env,
    db,
    learners,
    operator,
)

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "apps" / "web" / "components" / "admin" / "admin.fixture.json"
EXPORTER = REPO / "scripts" / "export_admin_fixture.py"


def test_the_committed_admin_fixture_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(EXPORTER), "--check"], capture_output=True, text=True, cwd=REPO
    )
    assert result.returncode == 0, (
        "admin.fixture.json is stale — re-run `python scripts/export_admin_fixture.py`\n"
        + result.stderr
    )


def test_the_committed_admin_fixture_matches_the_wire(operator) -> None:
    wire = _get(operator).json()
    committed = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert set(committed) == {"two", "mixed", "none"}
    for name, body in committed.items():
        assert set(body) == set(wire), name
        for user in body["users"]:
            assert set(user) == set(wire["users"][0]), name
