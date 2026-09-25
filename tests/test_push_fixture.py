"""W20: `apps/web/components/push/push.fixture.json` describes the wire.

#190's contract: Vitest and Playwright draw the reminder control from this file,
so it is checked two ways — the exporter's own `--check`, and the committed keys
against REAL ASGI bodies from `/push/key`, `/push/subscribe` and `/push/state`.

**RED DEMONSTRATIONS (2026-09-25):** an extra `"time": "08:00"` key added to the
committed `on` body turned `test_the_committed_push_fixture_matches_the_wire`
red; the committed `key_set` edited by one character turned
`test_the_committed_push_fixture_is_current` red. Both restored.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.test_push_route import (  # noqa: F401 — fixtures used by name
    auth_env,
    browser,
    call,
    db,
    keys,
    learners,
)

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "apps" / "web" / "components" / "push" / "push.fixture.json"
EXPORTER = REPO / "scripts" / "export_push_fixture.py"


def test_the_committed_push_fixture_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(EXPORTER), "--check"], capture_output=True, text=True, cwd=REPO
    )
    assert result.returncode == 0, (
        "push.fixture.json is stale — re-run `python scripts/export_push_fixture.py`\n"
        + result.stderr
    )


def test_the_committed_push_fixture_matches_the_wire(learners, keys) -> None:
    me = learners()
    committed = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert set(committed) == {"key_set", "key_unset", "on", "off", "subscription"}

    key_body = call("GET", "/push/key", learner=me).json()
    assert set(committed["key_set"]) == set(key_body) == {"public_key"}
    assert isinstance(committed["key_set"]["public_key"], str)
    assert committed["key_unset"] == {"public_key": None}

    # The stub subscription is accepted by the real route, and what the route
    # answers has exactly the committed shape.
    subscribed = call("POST", "/push/subscribe", learner=me, body=committed["subscription"])
    assert subscribed.status_code == 200, subscribed.text
    assert subscribed.json() == committed["on"]
    state = call(
        "POST", "/push/state", learner=me,
        body={"endpoint": committed["subscription"]["endpoint"]},
    ).json()
    assert state == committed["on"]
    off = call(
        "POST", "/push/unsubscribe", learner=me,
        body={"endpoint": committed["subscription"]["endpoint"]},
    ).json()
    assert off == committed["off"]
