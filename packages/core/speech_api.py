"""The one door to Azure Speech. W14.

**This is the second file in `packages/core` permitted an HTTP client**, and
like `video_api.py` the exemption is written BY NAME in
`tests/test_core_boundary.py` rather than added quietly to a frozenset. Every
other file in core still fails on an `httpx` import.

**WHY A SECOND DOOR RATHER THAN AN `httpx` IMPORT IN `speech.py`.** The boundary
test caught the first attempt, which put the call in `speech.py` directly, and
the test was right. The tree's stated rule is **one declared door per external
provider** -- that is `video_api.py`'s own docstring -- and Azure is a new
external provider reached over raw HTTP rather than through an SDK. `speech.py`
stays what it is: the provider-agnostic wrapper that holds POLICY (validation,
retry, error mapping) and imports provider SDKs. This file holds the REQUEST.

**WHY NOT THE AZURE SDK, WHICH WOULD HAVE NEEDED NO EXEMPTION AT ALL.**
`azure-cognitiveservices-speech` is a binary wheel whose non-WAV codec support
needs GStreamer installed system-wide, and **the production host is shared with
`fonderis-worker` and a PostgreSQL serving both projects** (CLAUDE.md §5). An
exemption that is visible is worth more than a system package that is not.
`httpx>=0.27` is already a runtime dependency (W12b promoted it), so this adds
nothing to install and **no licence gate is owed**.

**NOTHING HERE IS CALLED DURING A TEST.** `tests/conftest.py` installs a
session-scoped network guard that fails any test opening a socket to a
non-loopback address. The tests exercise this against a patched `httpx.post` --
**at the transport, never at the service function** (standing rule 7) -- so
request construction, status mapping and JSON decoding all execute.

**BILLING, STATED WHERE THE CALL IS: THIS ONE IS FREE.** Azure pronunciation
assessment is included in Speech-to-Text, and the resource is on the **Free (F0)
tier: 5 audio hours per month, no charge.** So #320/#321's cost-model caution
does not carry over -- there is no per-call charge to under-report. **The risk
is a QUOTA**, counted in `speech_attempts.audio_seconds` from our own bytes and
never from anything this file returns (CLAUDE.md §3 rule 5).

**NO KEY, ENDPOINT OR REGION LITERAL LIVES HERE.** The endpoint is derived from
`settings.azure_speech_region` so there is one place a region can be wrong, and
both values come from the host's `.env`.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:  # pragma: no cover
    from core.config import Settings

logger = logging.getLogger(__name__)

#: Assessment request configuration. `Granularity: Phoneme` is what makes
#: `speech_attempts.phonemes` -- W17's only input -- non-empty; anything coarser
#: returns words alone and the table accumulates nothing worth reading.
#: **Prosody is NOT requested: the add-on is not bought**, so
#: `speech_attempts.prosody` stays NULL meaning *not measured*, never zero.
ASSESS_GRADING = "HundredMark"
ASSESS_GRANULARITY = "Phoneme"
ASSESS_DIMENSION = "Comprehensive"

ASSESS_TIMEOUT_SECONDS = 20.0

#: **EVERY CONSTANT ABOVE AND THE PATH BELOW ARE UNVERIFIED UNTIL P0a RUNS.**
#: CLAUDE.md §3 rule 2 owes one real call before shipping, `core.speech_probe`
#: is it, and it is free. If the probe shows the shape differs, **the plan is
#: wrong and says so** (W10c's precedent).
_RECOGNITION_PATH = "/speech/recognition/conversation/cognitiveservices/v1"


class ProviderRefused(Exception):
    """Quota, concurrency or credentials. **A stated condition, not a fault.**"""


class Retriable(Exception):
    """Timeout, connection error or 5xx. `speech.py` owns the backoff."""


def assessment_header(reference_text: str) -> str:
    """The base64 `Pronunciation-Assessment` header value.

    Its own function so a test can assert what we CONSTRUCT by value, without
    reaching the network -- what Azure RETURNS is P0a's to establish.
    """
    config = {
        "ReferenceText": reference_text,
        "GradingSystem": ASSESS_GRADING,
        "Granularity": ASSESS_GRANULARITY,
        "Dimension": ASSESS_DIMENSION,
        "EnableMiscue": True,
    }
    raw = json.dumps(config, ensure_ascii=False).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def post_pronunciation_assessment(
    audio: bytes,
    reference_text: str,
    *,
    sample_rate_hz: int,
    language: str,
    settings: "Settings",
) -> dict:
    """One request. Returns the provider's decoded JSON, **unchanged**.

    **NOTHING IS WRITTEN TO DISK ON ANY PATH THROUGH THIS FUNCTION** -- no
    `open`, no `tempfile`, no `Path.write_*`, on the success path or on any
    error path. Asserted by `tests/test_speech_no_disk.py` rather than promised
    by this sentence (CLAUDE.md §5, PRD §8).

    **The recognised transcript in the response is the CALLER's to discard.** It
    is never persisted and never logged, and `speech_attempts` has no column
    that could hold one.
    """
    started = time.perf_counter()
    url = (
        f"https://{settings.azure_speech_region}.stt.speech.microsoft.com"
        f"{_RECOGNITION_PATH}"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": settings.azure_speech_key,
        "Content-Type": f"audio/wav; codecs=audio/pcm; samplerate={sample_rate_hz}",
        "Accept": "application/json",
        "Pronunciation-Assessment": assessment_header(reference_text),
    }
    try:
        response = httpx.post(
            url,
            params={"language": language},
            headers=headers,
            content=audio,
            timeout=ASSESS_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        raise Retriable(f"timeout: {exc}") from exc
    except httpx.TransportError as exc:
        raise Retriable(f"connection: {exc}") from exc

    status = response.status_code
    if status in (401, 403, 429):
        # 403 on F0 is the quota refusal, 401 a bad key, 429 concurrency
        # between the two learners. **None is retried** -- see the policy note
        # on `speech.assess_pronunciation`.
        raise ProviderRefused(f"provider refused: status {status}")
    if status >= 500:
        raise Retriable(f"status {status}")
    if status != 200:
        raise RuntimeError(f"Azure pronunciation error {status}")

    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("response JSON was not an object")

    duration_ms = int((time.perf_counter() - started) * 1000)
    # **Shape only.** No audio, no transcript, no reference sentence -- the
    # reference is the learner's own card content and CLAUDE.md §5 says logs
    # carry user ids and route names, never message bodies. No key, no region.
    logger.info(
        "pronunciation call bytes=%s rate=%s duration_ms=%s",
        len(audio),
        sample_rate_hz,
        duration_ms,
    )
    return payload
