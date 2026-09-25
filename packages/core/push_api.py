"""W20 — the door to the browsers' push services. The only file that sends a push.

`video_api.py`/`speech_api.py`'s shape and exemption (`tests/test_core_boundary.py`):
**one declared door per external provider.** The provider here is the Web Push
service the learner's browser chose — Apple's, Google's or Mozilla's — and the
request is fully built by `core/push.py`; this file only posts it and maps the
answer to one of three outcomes.

**A push is a real message on a learner's phone (CLAUDE.md §5b).** No test and
no acceptance check reaches this function with a real endpoint: tests replace
`httpx.post` here, at the provider boundary (standing rule 7), and the one live
send is the operator's probe at the launch pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx

from core.push import PushRequest

#: A push service answers in well under a second; ten is generous and keeps one
#: dead endpoint from holding the worker's tick.
TIMEOUT_SECONDS = 10.0

Outcome = Literal["sent", "gone", "failed"]


@dataclass(frozen=True)
class PushResult:
    outcome: Outcome
    #: The service's status code, or None when no answer came back. Logged; it
    #: carries nothing about the learner.
    status: int | None


def send(request: PushRequest) -> PushResult:
    """Post one push. Never raises for a network or service failure.

    `201 Created` is the RFC 8030 answer; some services say 200 or 202. **404
    and 410 mean the subscription is gone** — the learner turned reminders off
    in the browser, or reinstalled — and the caller deletes it. Anything else is
    a failure for this one message and nothing more: no retry, because a
    reminder sent twice is worse than one not sent.
    """
    try:
        response = httpx.post(
            request.endpoint,
            headers=request.headers,
            content=request.body,
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError:
        return PushResult("failed", None)
    if response.status_code in (200, 201, 202):
        return PushResult("sent", response.status_code)
    if response.status_code in (404, 410):
        return PushResult("gone", response.status_code)
    return PushResult("failed", response.status_code)
