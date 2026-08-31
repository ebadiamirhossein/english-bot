"""A credential must never reach a URL, and therefore never a log line.

**This file exists because of a leak that no test caught and a person did.**
`core.video.resolve_channels` was run on production on 2026-08-31 and its
console output carried, once per handle, eleven times:

    INFO httpx: HTTP Request: GET https://www.googleapis.com/youtube/v3/
    channels?part=...&forHandle=%40Vox&key=AIzaSy...  "HTTP/1.1 200 OK"

The key was sent as a query parameter and `httpx._client` logs the full URL at
INFO. The key reached the operator's shell history and a chat transcript, and
was rotated.

**WHY THE EXISTING GUARD DID NOT HOLD.** `_youtube_get` already carried the
comment *"The key is in `params` and must never reach a log line or an exception
message (CLAUDE.md §5)"* — and the exception path it guards was correct. The
leak came out of the HTTP library, which the comment could not see. **A comment
asserting an invariant is not the invariant**, which is why this is a test.

**WHAT IS ASSERTED, AND IT IS THE STRONGER OF THE TWO AVAILABLE CLAIMS.** These
tests do not merely assert that our own code does not log the credential. They
assert the credential **is not in the request URL at all**, and separately that
it appears in no log record emitted while the request is made. The first is what
makes the second durable: a credential absent from the URL cannot be logged by
any library, present or future, whatever its log level. Setting httpx's logger
to WARNING would silence today's line and leave the credential in the URL for
the next thing that prints one.

CLAUDE.md §5 says logs carry user ids and route names, never message bodies. **A
credential in a log is worse than a message body**, because it is live until
somebody notices, and the noticing here was a person reading eleven lines of
console output.

No socket is opened: `httpx.MockTransport` answers in-process, so the
session-scoped `netguard` in `tests/conftest.py` is satisfied.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from core import video_api

#: Shaped like the real thing so a substring match cannot pass by accident, and
#: obviously fake so nobody reads this file as a leak of its own.
YOUTUBE_SENTINEL = "AIzaSyFAKE_test_credential_sentinel_0000"
APIFY_SENTINEL = "apify_api_FAKE_test_credential_sentinel_00000"


@pytest.fixture
def captured(monkeypatch):
    """Answer every request in-process and record what was actually sent."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        if "youtube" in str(request.url):
            return httpx.Response(200, json={
                "items": [{
                    "id": "UC-test",
                    "snippet": {"title": "Test Channel"},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UU-test"}},
                }]
            })
        return httpx.Response(200, json=[])

    real_client = httpx.Client

    def client_on_mock_transport(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(video_api.httpx, "Client", client_on_mock_transport)
    return seen


def _log_text(caplog) -> str:
    return "\n".join(
        record.getMessage() for record in caplog.records
    ) + "\n" + caplog.text


def test_the_youtube_key_is_never_in_the_url_and_so_never_in_a_log(
    captured, caplog
) -> None:
    """**The leak of 2026-08-31, as a test.**

    Red against the shipped code: `_youtube_get` sent `key` in `params`, so the
    sentinel appeared both in `request.url` and in httpx's own INFO line.
    """
    with caplog.at_level(logging.INFO, logger="httpx"):
        ref = video_api.resolve_handle("@Vox", api_key=YOUTUBE_SENTINEL)

    assert ref.channel_id == "UC-test"

    assert YOUTUBE_SENTINEL not in str(captured["url"]), (
        "the API key is in the request URL, so any library that logs a URL "
        "leaks it -- which is exactly what httpx did on production"
    )
    assert "key=" not in str(captured["url"])
    assert YOUTUBE_SENTINEL not in _log_text(caplog), (
        "the API key reached a log record"
    )


def test_the_youtube_key_is_sent_as_the_header_the_api_documents(
    captured,
) -> None:
    """Verified against the live API before it was written, not assumed.

    `X-goog-api-key` alone: **400 `API key expired`**. No credential at all:
    **403 `Method doesn't allow unregistered callers`**. The 403 → 400 move is
    the proof the header was read and identity established -- the request got
    far enough to be told *this particular key* is stale.
    """
    video_api.resolve_handle("@Vox", api_key=YOUTUBE_SENTINEL)
    headers = captured["headers"]
    assert headers["x-goog-api-key"] == YOUTUBE_SENTINEL


def test_the_apify_token_is_never_in_the_url_and_so_never_in_a_log(
    captured, caplog
) -> None:
    """**The same defect, found by looking for its class rather than for it.**

    `_run_actor` sent `token` in `params`. It has never been seen in a log
    because no actor run has been made outside a test -- so this half was a leak
    waiting for its first production run, not a leak that had happened.
    """
    with caplog.at_level(logging.INFO, logger="httpx"):
        video_api.list_transcript_kinds(
            ["abc123"], token=APIFY_SENTINEL, actor="johnvc/YoutubeTranscripts"
        )

    assert APIFY_SENTINEL not in str(captured["url"]), (
        "the Apify token is in the request URL"
    )
    assert "token=" not in str(captured["url"])
    assert APIFY_SENTINEL not in _log_text(caplog), (
        "the Apify token reached a log record"
    )


def test_the_apify_token_is_sent_as_a_bearer_header(captured) -> None:
    """Verified against the live API: `GET /v2/users/me` with
    `Authorization: Bearer` returns **200**, and without it **401**. That
    endpoint is free and is not an actor run, so the check cost nothing.
    """
    video_api.list_transcript_kinds(
        ["abc123"], token=APIFY_SENTINEL, actor="johnvc/YoutubeTranscripts"
    )
    assert captured["headers"]["authorization"] == f"Bearer {APIFY_SENTINEL}"


def test_no_module_in_core_puts_a_credential_in_a_query_string() -> None:
    """**The seam, not the instance.** Two credentials were in query strings and
    only one had leaked; the other was one production run away.

    This scans for the shape rather than for the two known names, so a third
    credential added to a `params` dict fails here instead of on a console.
    **It is deliberately dumb about which key is secret** -- any `params` entry
    whose name looks like a credential is refused, and a false positive is
    cheaper than the failure this file was written after.

    **It reads the AST and not the text, and that is not a refinement -- the
    first draft was a regex and it went red on the FIX, because the comment
    explaining the defect quotes the defective line.** A scanner that cannot
    tell code from prose gets deleted the first time it cries wolf, and #257 is
    this record's note that a scanner enforcing the FORM of a claim rather than
    its truth is worth little. This one looks at `params=` keyword arguments in
    real call nodes; comments and docstrings are not in the tree at all.
    """
    import ast
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    secretish = {
        "key", "api_key", "apikey", "token", "access_token", "auth",
        "secret", "password", "passwd", "pwd", "signature", "sig",
    }

    offenders: list[str] = []
    for path in sorted((repo / "packages" / "core").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "params":
                    continue
                if not isinstance(keyword.value, ast.Dict):
                    continue
                for key in keyword.value.keys:
                    # `{**other, "key": v}` puts None here for the `**`.
                    if (
                        isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                        and key.value.lower() in secretish
                    ):
                        offenders.append(
                            f"{path.relative_to(repo)}:{node.lineno} "
                            f"params[{key.value!r}]"
                        )

    assert not offenders, (
        "a credential-shaped name is being sent as a URL query parameter, "
        f"which is how the 2026-08-31 key leak happened: {offenders}"
    )
