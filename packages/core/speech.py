"""Provider-agnostic STT/TTS wrapper.

Every speech call in the product goes through this module. Provider SDKs are
imported here and nowhere else. Audio never touches the filesystem.
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass
from typing import Any

import openai

from core import speech_api
from core.config import Settings, load_settings

logger = logging.getLogger(__name__)

_RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)


class SpeechError(Exception):
    """Raised after retries are exhausted or on a non-retriable provider error."""


class _RetriableError(Exception):
    """Internal: signal that speech should back off and retry."""


def transcribe(
    audio: bytes,
    *,
    language: str = "en",
    settings: Settings | None = None,
) -> str:
    """Transcribe audio bytes. Provider chosen by settings.stt_provider.

    Retries 3x with backoff. Raises SpeechError on final failure.
    """
    cfg = settings or load_settings()
    if not cfg.openai_api_key:
        raise SpeechError("OPENAI_API_KEY is not set")
    if cfg.stt_provider != "openai":
        raise SpeechError(f"Unsupported STT provider: {cfg.stt_provider!r}")
    return _transcribe_openai(audio, language=language, settings=cfg)


def synthesize(
    text: str,
    *,
    voice: str | None = None,
    settings: Settings | None = None,
) -> bytes:
    """Synthesize speech bytes. Provider chosen by settings.tts_provider.

    Retries 3x with backoff. Raises SpeechError on final failure.
    """
    cfg = settings or load_settings()
    if not cfg.openai_api_key:
        raise SpeechError("OPENAI_API_KEY is not set")
    if cfg.tts_provider != "openai":
        raise SpeechError(f"Unsupported TTS provider: {cfg.tts_provider!r}")
    return _synthesize_openai(
        text, voice=voice or cfg.tts_voice, settings=cfg
    )


def _transcribe_openai(
    audio: bytes,
    *,
    language: str,
    settings: Settings,
) -> str:
    client = openai.OpenAI(api_key=settings.openai_api_key)
    last_error: Exception | None = None
    for attempt, delay in enumerate(_RETRY_BACKOFF_SECONDS):
        try:
            return _openai_transcribe_once(
                client, audio, language=language, model=settings.whisper_model
            )
        except _RetriableError as exc:
            last_error = exc
            logger.warning(
                "STT retriable failure attempt=%s/%s: %s",
                attempt + 1,
                len(_RETRY_BACKOFF_SECONDS),
                exc,
            )
            if attempt < len(_RETRY_BACKOFF_SECONDS) - 1:
                time.sleep(delay)
        except SpeechError:
            raise
        except Exception as exc:  # noqa: BLE001 — wrap unknown provider errors
            raise SpeechError(str(exc)) from exc

    assert last_error is not None
    raise SpeechError(str(last_error)) from last_error


def _synthesize_openai(
    text: str,
    *,
    voice: str,
    settings: Settings,
) -> bytes:
    client = openai.OpenAI(api_key=settings.openai_api_key)
    last_error: Exception | None = None
    for attempt, delay in enumerate(_RETRY_BACKOFF_SECONDS):
        try:
            return _openai_synthesize_once(
                client,
                text,
                voice=voice,
                model=settings.tts_model,
                response_format=settings.tts_format,
            )
        except _RetriableError as exc:
            last_error = exc
            logger.warning(
                "TTS retriable failure attempt=%s/%s: %s",
                attempt + 1,
                len(_RETRY_BACKOFF_SECONDS),
                exc,
            )
            if attempt < len(_RETRY_BACKOFF_SECONDS) - 1:
                time.sleep(delay)
        except SpeechError:
            raise
        except Exception as exc:  # noqa: BLE001 — wrap unknown provider errors
            raise SpeechError(str(exc)) from exc

    assert last_error is not None
    raise SpeechError(str(last_error)) from last_error


def _openai_transcribe_once(
    client: openai.OpenAI,
    audio: bytes,
    *,
    language: str,
    model: str,
) -> str:
    started = time.perf_counter()
    # Filename tells the SDK the container; Telegram voice is OGG/Opus.
    file_tuple = ("voice.ogg", io.BytesIO(audio))
    try:
        result = client.audio.transcriptions.create(
            model=model,
            file=file_tuple,
            language=language,
        )
    except openai.APITimeoutError as exc:
        raise _RetriableError(f"timeout: {exc}") from exc
    except openai.APIStatusError as exc:
        status = exc.status_code
        if status == 429 or status >= 500:
            raise _RetriableError(f"status {status}: {exc}") from exc
        raise SpeechError(f"OpenAI STT error {status}: {exc}") from exc
    except openai.APIConnectionError as exc:
        raise _RetriableError(f"connection: {exc}") from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    text = getattr(result, "text", None)
    if text is None:
        text = str(result)
    logger.info(
        "stt call model=%s bytes=%s duration_ms=%s",
        model,
        len(audio),
        duration_ms,
    )
    return str(text)


def _openai_synthesize_once(
    client: openai.OpenAI,
    text: str,
    *,
    voice: str,
    model: str,
    response_format: str,
) -> bytes:
    started = time.perf_counter()
    try:
        response = client.audio.speech.create(
            model=model,
            voice=voice,
            input=text,
            response_format=response_format,
        )
    except openai.APITimeoutError as exc:
        raise _RetriableError(f"timeout: {exc}") from exc
    except openai.APIStatusError as exc:
        status = exc.status_code
        if status == 429 or status >= 500:
            raise _RetriableError(f"status {status}: {exc}") from exc
        raise SpeechError(f"OpenAI TTS error {status}: {exc}") from exc
    except openai.APIConnectionError as exc:
        raise _RetriableError(f"connection: {exc}") from exc

    audio = _speech_response_bytes(response)
    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "tts call model=%s chars=%s bytes=%s duration_ms=%s",
        model,
        len(text),
        len(audio),
        duration_ms,
    )
    return audio


def _speech_response_bytes(response: Any) -> bytes:
    """Extract raw audio bytes from an OpenAI speech response."""
    if hasattr(response, "content") and isinstance(response.content, (bytes, bytearray)):
        return bytes(response.content)
    if hasattr(response, "read"):
        data = response.read()
        return bytes(data)
    raise SpeechError("TTS response contained no audio bytes")


# ---------------------------------------------------------------------------
# W14 -- Azure pronunciation assessment
# ---------------------------------------------------------------------------
#
# **THIS IS THE REQUEST HALF ONLY. THE PARSER IS DELIBERATELY NOT HERE.**
#
# CLAUDE.md §3 rule 2 fires: new provider, new request construction. Azure's
# pronunciation-assessment RESPONSE SHAPE is the one thing in this slice no test
# can establish from our side -- the nesting of the four aggregates, the
# per-word list, the per-phoneme list, and what a quota refusal looks like on
# the wire. **A mock built from a guessed shape is a mocked suite passing over a
# malformed request, which is rule 2's originating failure verbatim.**
#
# So `assess_pronunciation` returns the provider's decoded JSON UNCHANGED, and
# normalisation into `speech_attempts`' columns is written against a RECORDED
# response from `python -m core.speech_probe` (P0a), not against this file's
# assumptions. **On F0 that call is free, so there is no reason to defer it and
# every reason to make it a stop point.**
#
# EVERY CONSTANT BELOW IS UNVERIFIED UNTIL P0a RUNS. If the probe shows the
# shape differs from what the plan assumed, **the plan is wrong and says so**
# (W10c's precedent, where one real call found a bug that would otherwise have
# failed at `--apply` on production after a whole run was paid for).

#: The only audio shape this wrapper sends: **mono 16-bit PCM WAV**, produced in
#: the browser (§1c) because the two learners' phones emit mp4/AAC and
#: webm/Opus, neither natively accepted, and putting GStreamer or ffmpeg on a
#: SHARED production host is refused outright (CLAUDE.md §5).
#:
#: **THE SAMPLE RATE IS A PARAMETER AND NOT A CONSTANT, AND THAT IS S2.** P0a
#: sends 16 kHz *and* 48 kHz: if the native rate is accepted there is no
#: resample in the browser at all and WebKit's `OfflineAudioContext` refusal
#: (#362) stops mattering. This default is the conservative one.
DEFAULT_SAMPLE_RATE_HZ = 16000


class SpeechQuotaExceeded(SpeechError):
    """The provider refused for quota or concurrency reasons.

    **Its own type because the surface must behave differently.** Every other
    `SpeechError` is a fault; this one is a stated, expected condition on a free
    tier and the screen says *scoring is off today* rather than showing an
    error. Separating them is what stops a quota refusal being rendered as a
    failure of the learner's attempt.
    """


def assess_pronunciation(
    audio: bytes,
    reference_text: str,
    *,
    sample_rate_hz: int = DEFAULT_SAMPLE_RATE_HZ,
    language: str = "en-US",
    settings: Settings | None = None,
) -> dict:
    """Score `audio` against `reference_text`. Returns the provider's raw JSON.

    **NOTHING IS WRITTEN TO DISK ON ANY PATH THROUGH THIS FUNCTION.** The bytes
    arrive in memory, go out as a request body, and are dropped. There is no
    `open`, no `tempfile`, no `Path.write_*` and no `shutil` here or anywhere
    below it -- asserted by an AST test rather than promised by this sentence
    (CLAUDE.md §5, PRD §8, W14 test 4).

    **THE RECOGNISED TRANSCRIPT IN THE RESPONSE IS THE CALLER'S TO DISCARD.**
    It is never persisted and never logged; `speech_attempts` has no column that
    could hold one.

    **RETRY POLICY DIVERGES FROM `transcribe`/`synthesize` DELIBERATELY.** Those
    retry 429 with backoff. This does not: on F0 a 429 is concurrency between
    two learners, a backoff would extend a wait a learner is sitting through
    (§1a bounds it at ~1-2 s), and the surface's answer to *unavailable* is to
    say so plainly rather than to stall. **Timeouts, connection errors and 5xx
    still retry** -- those are faults, not refusals.
    """
    cfg = settings or load_settings()
    if not cfg.azure_speech_key or not cfg.azure_speech_region:
        raise SpeechError(
            "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION are not both set"
        )
    if not reference_text.strip():
        raise SpeechError("reference_text is empty")
    if not audio:
        raise SpeechError("no audio bytes")

    last_error: Exception | None = None
    for attempt, delay in enumerate(_RETRY_BACKOFF_SECONDS):
        try:
            return speech_api.post_pronunciation_assessment(
                audio,
                reference_text,
                sample_rate_hz=sample_rate_hz,
                language=language,
                settings=cfg,
            )
        except speech_api.ProviderRefused as exc:
            # A stated condition, not a fault: re-raised as this module's own
            # type so callers depend on `core.speech` and never on the door.
            raise SpeechQuotaExceeded(str(exc)) from exc
        except speech_api.Retriable as exc:
            last_error = exc
            logger.warning(
                "pronunciation retriable failure attempt=%s/%s: %s",
                attempt + 1,
                len(_RETRY_BACKOFF_SECONDS),
                exc,
            )
            if attempt < len(_RETRY_BACKOFF_SECONDS) - 1:
                time.sleep(delay)
        except SpeechError:
            raise
        except Exception as exc:  # noqa: BLE001 — wrap unknown provider errors
            raise SpeechError(str(exc)) from exc

    assert last_error is not None
    raise SpeechError(str(last_error)) from last_error


# ---------------------------------------------------------------------------
# W14 -- the parser. WRITTEN AGAINST P0a's RECORDED RESPONSES, NOT AGAINST A
# GUESS. Fixtures: tests/fixtures/azure_pronunciation/*.json, 2026-09-03.
# ---------------------------------------------------------------------------
#
# **WHAT THE RECORDING CHANGED, recorded because the plan said it would say so
# if the shape differed:**
#
# 1. **THE FOUR AGGREGATES ARE FLAT ON `NBest[0]`** -- `AccuracyScore`,
#    `FluencyScore`, `CompletenessScore`, `PronScore` -- and are **NOT** nested
#    under a `PronunciationAssessment` object. The plan named this nesting as
#    the one thing no test could establish from our side, and it was right to.
# 2. **`ProsodyScore` IS ABSENT ENTIRELY, not null.** The add-on is not bought,
#    so `.get()` yields None and `speech_attempts.prosody` stays NULL meaning
#    *not measured* -- exactly what 024 reserved it for.
# 3. **`ErrorType` IS THE STRING `"None"`, NOT JSON null.** A trap worth naming:
#    `if word["ErrorType"]:` is TRUE for a perfectly pronounced word. Compared
#    by value here, and `NO_ERROR` exists so no caller re-derives it.
# 4. **`Phonemes` NEST UNDER EACH WORD**, so the flat per-phoneme array 024
#    stores is a flatten across words. `Syllables` are also returned and are
#    **deliberately not stored**: W17 reads phonemes, and a third granularity
#    nobody reads is rows that could be computed (PRODUCT-PRINCIPLES §3).
# 5. **`RecognitionStatus` sits at the TOP level**, beside `NBest`. Anything but
#    `Success` is a real state -- a learner who said nothing -- and is refused
#    here rather than stored as a zero.

#: `ErrorType` when the word is fine. **A string, not null** -- see (3) above.
NO_ERROR = "None"


class NotRecognised(SpeechError):
    """The provider heard no usable speech.

    **Its own type because it is not a fault and not a low score.** A learner
    who tapped record and said nothing has produced no measurement, and storing
    a zero would be inventing one. The surface says *I didn't catch that* and
    writes no row.
    """


@dataclass(frozen=True)
class WordScore:
    word: str
    accuracy: float
    error_type: str

    @property
    def is_clean(self) -> bool:
        return self.error_type == NO_ERROR


@dataclass(frozen=True)
class PhonemeScore:
    phoneme: str
    accuracy: float


@dataclass(frozen=True)
class PronunciationResult:
    """**Scores only. There is deliberately no field for what Azure HEARD.**

    The response carries `DisplayText`, `Lexical`, `ITN` and `MaskedITN` -- four
    spellings of a recognised transcript of the learner's voice. **None of them
    is carried past this parser**, so no caller can persist or log one by
    accident and `speech_attempts` has no column that could hold one
    (CLAUDE.md §5, PRD §8, ARCHITECTURE §5:133).
    """

    accuracy: float
    fluency: float
    completeness: float
    pron_score: float
    prosody: float | None
    words: tuple[WordScore, ...]
    phonemes: tuple[PhonemeScore, ...]


def _score(raw: Any, field: str) -> float:
    value = raw.get(field)
    if not isinstance(value, (int, float)):
        raise SpeechError(f"missing or non-numeric {field}")
    number = float(value)
    if not 0.0 <= number <= 100.0:
        # 024's CHECK would refuse it anyway; failing here names the field.
        raise SpeechError(f"{field} out of the HundredMark range: {number}")
    return number


def parse_assessment(payload: dict) -> PronunciationResult:
    """Normalise one recorded response. **Raises rather than guessing.**

    Every refusal below is a shape this parser has never seen. A parser that
    filled a default would put a number into `speech_attempts` that no
    measurement produced -- and a fabricated score is indistinguishable from a
    measured one a month later (W7's NULL-stability reasoning, same shape).
    """
    status = payload.get("RecognitionStatus")
    if status != "Success":
        raise NotRecognised(f"RecognitionStatus={status!r}")
    nbest = payload.get("NBest")
    if not isinstance(nbest, list) or not nbest:
        raise SpeechError("NBest missing or empty")
    best = nbest[0]
    if not isinstance(best, dict):
        raise SpeechError("NBest[0] is not an object")

    words: list[WordScore] = []
    phonemes: list[PhonemeScore] = []
    for entry in best.get("Words") or ():
        if not isinstance(entry, dict):
            raise SpeechError("Words[] contained a non-object")
        words.append(
            WordScore(
                word=str(entry.get("Word", "")),
                accuracy=_score(entry, "AccuracyScore"),
                # Verbatim, including the literal string "None".
                error_type=str(entry.get("ErrorType", NO_ERROR)),
            )
        )
        for item in entry.get("Phonemes") or ():
            if not isinstance(item, dict):
                raise SpeechError("Phonemes[] contained a non-object")
            phonemes.append(
                PhonemeScore(
                    phoneme=str(item.get("Phoneme", "")),
                    accuracy=_score(item, "AccuracyScore"),
                )
            )
    if not words:
        # Success with no words is not a score of zero; it is no measurement.
        raise NotRecognised("Success but no words were returned")

    completeness = _score(best, "CompletenessScore")
    if completeness == 0:
        # **#366. `CompletenessScore` is HOW MUCH OF THE REFERENCE WAS SAID, so
        # zero means NOTHING matched -- the app did not hear the learner.**
        #
        # This is not caught by either guard above: the live attempt that found
        # it returned `RecognitionStatus: Success` **with all seven words
        # present at accuracy 0**, and W14 rendered per-word colouring for it --
        # a verdict on an utterance nobody heard, on the surface most likely in
        # this product to read as judgement (CLAUDE.md §4).
        #
        # **THE THRESHOLD IS EXACTLY ZERO, CHOSEN FROM THE THREE REAL ATTEMPTS**
        # (52/79/50, 82/86/75, 0/0/0). There is no observation between 0 and 50,
        # so any band in that interval would be a number this project cannot
        # defend (rule 7) -- and zero is categorical rather than a tuning knob:
        # *nothing matched* and *something matched* are different events.
        #
        # **THE ASYMMETRY POINTS THE SAME WAY.** Erring high would suppress a
        # genuinely poor attempt, and **a poor attempt is information the
        # learner should get**; erring at zero suppresses only the case that is
        # not about the learner at all.
        #
        # **AND IT KEEPS W17's INPUT CLEAN**, which outlives the screen: a
        # capture failure contributes ~23 phonemes at accuracy 0 and would read
        # as catastrophic pronunciation of every sound in the sentence.
        raise NotRecognised("CompletenessScore=0 -- nothing of the reference matched")

    prosody = best.get("ProsodyScore")
    return PronunciationResult(
        accuracy=_score(best, "AccuracyScore"),
        fluency=_score(best, "FluencyScore"),
        completeness=completeness,
        pron_score=_score(best, "PronScore"),
        prosody=float(prosody) if isinstance(prosody, (int, float)) else None,
        words=tuple(words),
        phonemes=tuple(phonemes),
    )
