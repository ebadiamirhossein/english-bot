"""Provider-agnostic LLM chat wrapper.

Every LLM call in the product goes through this module. Provider SDKs are
imported here and nowhere else.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import anthropic

from app.config import Settings, load_settings

logger = logging.getLogger(__name__)

_DEFAULT_PROVIDER = "anthropic"
_RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_JSON_REPAIR_INSTRUCTION = (
    "Your previous response was not valid JSON. "
    "Reply with only the JSON object, no markdown fences or commentary."
)


class LLMError(Exception):
    """Raised after retries are exhausted or on a non-retriable provider error."""


def chat(
    messages: list[dict],
    *,
    system: str | None = None,
    json_mode: bool = False,
    max_tokens: int = 1000,
    images: list[bytes] | None = None,
    settings: Settings | None = None,
) -> str | dict:
    """Provider chosen by settings.llm_provider. Retries 3x with backoff.

    Raises LLMError on final failure — callers must handle.
    """
    if images is not None:
        raise NotImplementedError("Vision/images support lands in S6")

    cfg = settings or load_settings()
    provider = cfg.llm_provider or _DEFAULT_PROVIDER
    if provider == "anthropic":
        text = _chat_anthropic(
            messages,
            system=system,
            max_tokens=max_tokens,
            settings=cfg,
        )
    else:
        raise LLMError(f"Unsupported LLM provider: {provider!r}")

    if not json_mode:
        return text

    try:
        return _parse_json(text)
    except LLMError:
        repair_messages = list(messages) + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": _JSON_REPAIR_INSTRUCTION},
        ]
        repaired = _chat_anthropic(
            repair_messages,
            system=system,
            max_tokens=max_tokens,
            settings=cfg,
        )
        return _parse_json(repaired)


def _parse_json(text: str) -> dict:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Response was not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMError("JSON response must be an object")
    return parsed


def _chat_anthropic(
    messages: list[dict],
    *,
    system: str | None,
    max_tokens: int,
    settings: Settings,
) -> str:
    client = anthropic.Anthropic(api_key=settings.llm_api_key)
    kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "max_tokens": max_tokens,
        "messages": _to_anthropic_messages(messages),
    }
    if system:
        kwargs["system"] = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    last_error: Exception | None = None
    for attempt, delay in enumerate(_RETRY_BACKOFF_SECONDS):
        try:
            return _anthropic_once(client, kwargs, settings.llm_model)
        except _RetriableError as exc:
            last_error = exc
            logger.warning(
                "LLM retriable failure attempt=%s/%s: %s",
                attempt + 1,
                len(_RETRY_BACKOFF_SECONDS),
                exc,
            )
            if attempt < len(_RETRY_BACKOFF_SECONDS) - 1:
                time.sleep(delay)
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 — wrap unknown provider errors
            raise LLMError(str(exc)) from exc

    assert last_error is not None
    raise LLMError(str(last_error)) from last_error


class _RetriableError(Exception):
    """Internal: signal that chat should back off and retry."""


def _anthropic_once(
    client: anthropic.Anthropic,
    kwargs: dict[str, Any],
    model: str,
) -> str:
    started = time.perf_counter()
    try:
        response = client.messages.create(**kwargs)
    except anthropic.APITimeoutError as exc:
        raise _RetriableError(f"timeout: {exc}") from exc
    except anthropic.APIStatusError as exc:
        status = exc.status_code
        if status == 429 or status >= 500:
            raise _RetriableError(f"status {status}: {exc}") from exc
        raise LLMError(f"Anthropic API error {status}: {exc}") from exc
    except anthropic.APIConnectionError as exc:
        raise _RetriableError(f"connection: {exc}") from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    usage = response.usage
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    logger.info(
        "llm call model=%s input_tokens=%s output_tokens=%s "
        "cache_read=%s cache_creation=%s duration_ms=%s",
        model,
        input_tokens,
        output_tokens,
        cache_read,
        cache_creation,
        duration_ms,
    )
    return _extract_text(response)


def _to_anthropic_messages(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for msg in messages:
        role = msg["role"]
        if role not in ("user", "assistant"):
            raise LLMError(f"Unsupported message role: {role!r}")
        out.append({"role": role, "content": msg["content"]})
    return out


def _extract_text(response: Any) -> str:
    parts: list[str] = []
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    if not parts:
        raise LLMError("Anthropic response contained no text blocks")
    return "".join(parts)
