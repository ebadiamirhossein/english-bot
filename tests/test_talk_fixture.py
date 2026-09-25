"""W15 — the committed `/talk` fixture against the real wire (#190).

`apps/web/components/session/talk.fixture.json` is what Vitest and Playwright
render. These tests hold its key sets to what the routes actually serve, through
the ASGI transport against the development database, with the model mocked at
the provider SDK (the harness is `test_conversation_rungs.py`'s).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_conversation_rungs import (  # noqa: F401 -- fixtures
    ANSWER, RETELL_REPLY, RETELLING, TRANSCRIPT, _SDK, _close, _open, _say, _video_today,
    app, auth_env, clock, db, jar, learner, request,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "apps" / "web" / "components" / "session" / "talk.fixture.json"


def _committed() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_the_committed_talk_fixture_is_current() -> None:
    """**Red method:** edit one string in the committed JSON — `--check` exits 1."""
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_talk_fixture.py"), "--check"],
        capture_output=True, text=True,
    )
    assert run.returncode == 0, run.stderr


def test_the_committed_talk_fixture_matches_the_wire(app, db, learner, monkeypatch) -> None:
    """Rungs, a rung's open, its one turn and both close-outs, compared key for
    key with real ASGI bodies. **Red method:** add a field to `CloseOut` without
    regenerating — the close's key set differs from the committed one."""
    committed = _committed()
    _video_today(db, learner, transcript=TRANSCRIPT)

    rungs = request(app, "GET", "/conversation/rungs", cookies=jar(learner)).json()
    assert set(rungs) == set(committed["rungs_both"])
    assert set(rungs["answer"]) == set(committed["rungs_both"]["answer"])
    assert set(rungs["retell"]) == set(committed["rungs_both"]["retell"])
    assert rungs["answer"] == committed["rungs_both"]["answer"], "the task, verbatim"

    _SDK({"is_english": True, "corrections": [], "did_well": None}).install(monkeypatch)
    opened = _open(app, learner, "answer").json()
    assert set(opened) == set(committed["open_answer"])
    assert opened["reply"] == committed["open_answer"]["reply"]
    turned = _say(app, learner, ANSWER).json()
    assert set(turned) == set(committed["turn_rung"])
    assert (turned["reply"], turned["state"]) == ("", "closing")
    closed = _close(app, learner).json()
    assert set(closed) == set(committed["close_answer"])
    offer_keys = {k for o in closed["word_offers"] for k in o}
    assert offer_keys == {k for o in committed["close_answer"]["word_offers"] for k in o}

    _SDK(RETELL_REPLY).install(monkeypatch)
    _open(app, learner, "retell")
    _say(app, learner, RETELLING)
    retold = _close(app, learner).json()
    assert set(retold) == set(committed["close_retell"])
    assert set(retold["corrections"][0]) == set(committed["close_retell"]["corrections"][0])
