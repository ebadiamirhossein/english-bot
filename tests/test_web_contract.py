"""The web's requests, replayed byte-for-byte through the real API. W31a.

**WHY THIS FILE EXISTS: sixteen taps on production answered 422 and every test
was green.** On 2026-09-27 the operator tapped *mastodon*, *epoch*, *nickname*…
on `/watch` and read *"Could not add that just now."* sixteen times; the host's
journal shows `POST /video/44/save-word 422` for each. `saveWord` in
`apps/web/lib/api.ts` sent `JSON.stringify({word})` **without a
`Content-Type`**, so the browser labelled it `text/plain;charset=UTF-8`, and
FastAPI does not JSON-decode a body it was not told is JSON. The route never
ran.

**Nothing covered the seam.** `tests/test_video_route.py` posts with httpx's
`json=`, which sets the header the browser did not; `player.test.tsx` mocks
`saveWord` away entirely; the e2e mocks never looked at the header. Each side
was tested against its own idea of the other.

**The fix is a contract both sides read.** `apps/web/lib/web-requests.contract.json`
names, per call, the method, path, content type and body the web sends:

* `apps/web/lib/api.contract.test.ts` holds the **web** to it — it stubs
  `fetch`, calls the real client function, and compares what would go on the
  wire (a string body with no explicit header is what the browser labels
  `text/plain;charset=UTF-8`, and the test says so rather than pretending the
  header is absent);
* this file holds the **API** to it — every entry is replayed through the ASGI
  app with exactly those headers and bytes, and must not be refused as
  malformed.

Red was demonstrated by committing the entry first with the content type the web
actually sent (`text/plain;charset=UTF-8`): this file answered **422
`model_attributes_type`, `loc: ["body"]`**, the production response.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from apps.api.schemas import SaveWordIn
from tests.test_video_route import (  # noqa: F401 -- fixtures, by name
    ID_PREFIX,
    _as,
    _assign_today,
    app,
    auth_env,
    db,
    learner,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "apps" / "web" / "lib" / "web-requests.contract.json"

#: The request model each contract entry must satisfy. A new entry with no model
#: here fails `test_every_entry_names_a_model`, so the contract cannot grow a
#: call the API side never checks. `None` for a GET: it has no body — its query
#: is held by the replay below instead.
MODELS = {"save_word": SaveWordIn, "word_lookup": None, "my_words": None}


def _entries() -> list[dict]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _replay(app, entry: dict, path: str, cookies: dict) -> httpx.Response:
    """The entry, exactly: its header and its bytes, not httpx's `json=`."""

    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 51234))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as http:
            if entry["body"] is None:
                return await http.request(entry["method"], path)
            return await http.request(
                entry["method"],
                path,
                content=json.dumps(entry["body"]).encode("utf-8"),
                headers={"content-type": entry["content_type"]},
            )

    return asyncio.run(_go())


def test_the_contract_exists_and_is_not_empty() -> None:
    """A guard: an empty or missing file passes every loop below vacuously."""
    assert CONTRACT.is_file()
    assert [e["name"] for e in _entries()]


def test_every_entry_names_a_model() -> None:
    assert {e["name"] for e in _entries()} <= set(MODELS)


@pytest.mark.parametrize("name", sorted(n for n, m in MODELS.items() if m is not None))
def test_the_body_the_web_sends_fits_the_api_model(name: str) -> None:
    entry = next(e for e in _entries() if e["name"] == name)
    MODELS[name].model_validate(entry["body"])


def test_the_save_word_request_the_web_sends_is_accepted(app, db, learner) -> None:
    """User action: tapping a word under the player on `/watch`.

    Replayed against a real assigned video. **The state is not the point** — a
    word with no gloss answers `no_gloss`, which is a 200 and a real outcome;
    the point is that the API parsed the request at all.
    """
    import secrets

    video_id = _assign_today(
        db, learner, transcript="so this is a mastodon",
        youtube_id=f"{ID_PREFIX}{secrets.token_hex(3)}",
    )
    entry = next(e for e in _entries() if e["name"] == "save_word")
    response = _replay(
        app, entry, entry["path"].format(video_id=video_id), _as(learner)
    )
    assert response.status_code != 422, response.text
    assert response.status_code == 200, response.text
    # W31c adds `pending` (no gloss yet — kept, and filled later) and `no_line`.
    assert response.json()["state"] in {"saved", "already_saved", "no_gloss", "pending", "no_line"}


@pytest.mark.parametrize("name", ["word_lookup", "my_words"])
def test_the_reads_the_web_makes_are_accepted(app, db, learner, name: str) -> None:
    """W31c: the sheet's lookup and My words, replayed exactly — a query the
    API refused (a renamed parameter) would be a 422 here."""
    import secrets

    video_id = _assign_today(
        db, learner, transcript="so this is a mastodon",
        youtube_id=f"{ID_PREFIX}{secrets.token_hex(3)}",
    )
    entry = next(e for e in _entries() if e["name"] == name)
    response = _replay(app, entry, entry["path"].format(video_id=video_id), _as(learner))
    assert response.status_code == 200, response.text
