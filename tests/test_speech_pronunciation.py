"""W14 — `speech.assess_pronunciation`'s REQUEST half.

**MOCKED AT THE TRANSPORT, NEVER AT THE SERVICE FUNCTION — standing rule 7.**
Every test here patches `httpx.post`, which is the seam *below* request
construction, so the endpoint derivation, the headers, the base64 assessment
config, the retry policy and the status mapping all EXECUTE. Patching
`assess_pronunciation` itself, or a service that calls it, would leave every one
of those unexercised — the shape that produced #345's fifth instance in W13-ii.

**THE RESPONSE SHAPE IS NOT ASSERTED HERE AND THAT IS DELIBERATE.** CLAUDE.md §3
rule 2 fires on this new provider, the owed real call is `python -m
core.speech_probe --live` (P0a, free on F0), and **the parser is written against
that recording, not against a guess.** These tests cover what we CONSTRUCT,
which is knowable from our side; what Azure RETURNS is not.

`netguard` is armed session-wide, so a test that reached the provider would
raise rather than consume quota. Structural, not a promise.
"""

from __future__ import annotations

import base64
import json
import logging
from unittest.mock import patch

import httpx
import pytest

from core.config import Settings
from core.speech import (
    SpeechError,
    SpeechQuotaExceeded,
    assess_pronunciation,
)

REFERENCE = "I'll grab a coffee first."
AUDIO = b"RIFF....WAVEfake-pcm-bytes"


def _settings(**over) -> Settings:
    base = dict(
        database_url="postgresql://x/y",
        telegram_bot_token="",
        llm_api_key="k",
        azure_speech_key="test-key",
        azure_speech_region="test-region",
    )
    base.update(over)
    return Settings(**base)


class _Response:
    def __init__(self, status_code: int, payload=None, text="{}"):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def test_the_request_is_constructed_the_way_azure_documents_it() -> None:
    """Endpoint, headers and the base64 config — **all asserted by value.**

    No `in` checks and no "contains one of" sets: an assertion whose accepted
    values include its own failure mode passes whether the instrument works or
    is switched off (#345).
    """
    seen = {}

    def _fake_post(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return _Response(200, {"RecognitionStatus": "Success"})

    with patch.object(httpx, "post", _fake_post):
        out = assess_pronunciation(
            AUDIO, REFERENCE, sample_rate_hz=16000, settings=_settings()
        )

    assert out == {"RecognitionStatus": "Success"}
    assert seen["url"] == (
        "https://test-region.stt.speech.microsoft.com"
        "/speech/recognition/conversation/cognitiveservices/v1"
    )
    assert seen["params"] == {"language": "en-US"}
    assert seen["content"] is AUDIO, "the bytes must go out unmodified"

    headers = seen["headers"]
    assert headers["Ocp-Apim-Subscription-Key"] == "test-key"
    assert headers["Accept"] == "application/json"
    assert (
        headers["Content-Type"]
        == "audio/wav; codecs=audio/pcm; samplerate=16000"
    )
    config = json.loads(base64.b64decode(headers["Pronunciation-Assessment"]))
    assert config == {
        "ReferenceText": REFERENCE,
        "GradingSystem": "HundredMark",
        # Phoneme, not Word: `speech_attempts.phonemes` is W17's ONLY input and
        # anything coarser accumulates nothing worth reading.
        "Granularity": "Phoneme",
        "Dimension": "Comprehensive",
        "EnableMiscue": True,
    }


def test_the_sample_rate_reaches_the_content_type() -> None:
    """S2 / #362: the rate is a parameter, and P0a sends two of them.

    If the native rate is accepted there is no browser resample at all, so this
    must be genuinely variable rather than a constant with a parameter beside it.
    """
    seen = {}

    def _fake_post(url, **kwargs):
        seen.update(kwargs)
        return _Response(200, {})

    with patch.object(httpx, "post", _fake_post):
        assess_pronunciation(
            AUDIO, REFERENCE, sample_rate_hz=48000, settings=_settings()
        )
    assert (
        seen["headers"]["Content-Type"]
        == "audio/wav; codecs=audio/pcm; samplerate=48000"
    )


@pytest.mark.parametrize("status", [401, 403, 429])
def test_a_refusal_is_its_own_type_and_is_never_retried(status: int) -> None:
    """**Quota and concurrency are STATED CONDITIONS, not faults.**

    `SpeechQuotaExceeded` exists so the surface can say *scoring is off today*
    rather than rendering a refusal as a failure of the learner's attempt.

    **And the call count is asserted, not just the exception type.** A retry on
    429 would extend a wait a learner is sitting through (§1a bounds it at
    ~1–2 s), and on a two-learner system a 429 means the other learner is
    speaking — backing off would not help. `transcribe`/`synthesize` DO retry
    429; this divergence is deliberate and is what this assertion protects.
    """
    calls = []

    def _fake_post(url, **kwargs):
        calls.append(1)
        return _Response(status)

    with patch.object(httpx, "post", _fake_post):
        with pytest.raises(SpeechQuotaExceeded):
            assess_pronunciation(AUDIO, REFERENCE, settings=_settings())
    assert len(calls) == 1, f"status {status} must not be retried"


def test_a_server_error_is_retried_exactly_three_times() -> None:
    calls = []

    def _fake_post(url, **kwargs):
        calls.append(1)
        return _Response(503)

    with patch.object(httpx, "post", _fake_post), patch(
        "core.speech.time.sleep", return_value=None
    ):
        with pytest.raises(SpeechError) as excinfo:
            assess_pronunciation(AUDIO, REFERENCE, settings=_settings())
    assert len(calls) == 3
    assert not isinstance(excinfo.value, SpeechQuotaExceeded)


def test_a_timeout_is_retried_and_a_quota_refusal_inside_it_is_not() -> None:
    """Mixed sequence: two timeouts then a 403. **The 403 ends it immediately.**"""
    outcomes = [
        httpx.TimeoutException("t1"),
        httpx.TimeoutException("t2"),
        _Response(403),
    ]
    calls = []

    def _fake_post(url, **kwargs):
        item = outcomes[len(calls)]
        calls.append(1)
        if isinstance(item, Exception):
            raise item
        return item

    with patch.object(httpx, "post", _fake_post), patch(
        "core.speech.time.sleep", return_value=None
    ):
        with pytest.raises(SpeechQuotaExceeded):
            assess_pronunciation(AUDIO, REFERENCE, settings=_settings())
    assert len(calls) == 3


def test_missing_credentials_refuse_before_any_request() -> None:
    """**Absent means refuses to run, never runs degraded.**"""
    called = []

    def _fake_post(url, **kwargs):
        called.append(1)
        return _Response(200, {})

    with patch.object(httpx, "post", _fake_post):
        for over in ({"azure_speech_key": ""}, {"azure_speech_region": ""}):
            with pytest.raises(SpeechError):
                assess_pronunciation(
                    AUDIO, REFERENCE, settings=_settings(**over)
                )
    assert called == [], "no request may be built without both credentials"


def test_nothing_the_learner_said_or_was_asked_to_say_reaches_a_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """CLAUDE.md §5 — logs carry user ids and route names, never message bodies.

    **The reference sentence is the learner's own card content**, so it is a
    message body and stays out. So does the key, and so does the region.
    """
    def _fake_post(url, **kwargs):
        return _Response(200, {"DisplayText": "I'll grab a coffee first"})

    with caplog.at_level(logging.DEBUG), patch.object(httpx, "post", _fake_post):
        assess_pronunciation(AUDIO, REFERENCE, settings=_settings())

    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert blob, "the call must log something, or this test cannot fail"
    for secret in (REFERENCE, "coffee", "test-key", "test-region"):
        assert secret not in blob, f"{secret!r} reached a log line"
