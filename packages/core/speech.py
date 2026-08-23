"""Provider-agnostic STT/TTS wrapper.

Every speech call in the product goes through this module. Provider SDKs are
imported here and nowhere else. Audio never touches the filesystem.
"""

from __future__ import annotations

import io
import logging
import time
from typing import Any

import openai

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
