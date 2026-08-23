"""Provider-agnostic LLM chat wrapper.

Every LLM call in the product goes through this module. Provider SDKs are
imported here and nowhere else.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from typing import Any

import anthropic

from core.config import Settings, load_settings

logger = logging.getLogger(__name__)

_DEFAULT_PROVIDER = "anthropic"
_RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_JSON_RAW_LOG_LIMIT = 300
_JSON_REPAIR_INSTRUCTION = (
    "Your previous response was not valid JSON. "
    "Reply with only the JSON object, no markdown fences or commentary."
)
_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$",
    re.DOTALL | re.IGNORECASE,
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
    reject_truncation: bool = False,
) -> str | dict:
    """Provider chosen by settings.llm_provider. Retries 3x with backoff.

    Raises LLMError on final failure — callers must handle.

    When ``images`` is provided, they are attached to the last user message
    before the first call so the json_mode repair path still sees them.

    When ``json_mode=True``, the response is parsed as a JSON object. Parsing
    tolerates markdown fences and prose around a ``{...}`` span. Every request
    ends on a user message — assistant prefill is not used (claude-sonnet-5
    rejects trailing assistant turns).

    When ``reject_truncation=True``, a ``stop_reason`` of ``max_tokens`` raises
    LLMError (do not send mid-sentence or truncated JSON to the user).
    """
    cfg = settings or load_settings()
    provider = cfg.llm_provider or _DEFAULT_PROVIDER

    # Embed images into messages so repair re-sends the same multimodal content.
    msgs = _attach_images(list(messages), images)

    if provider != "anthropic":
        raise LLMError(f"Unsupported LLM provider: {provider!r}")

    if not json_mode:
        return _chat_anthropic(
            msgs,
            system=system,
            max_tokens=max_tokens,
            settings=cfg,
            reject_truncation=reject_truncation,
        )

    text = _chat_anthropic(
        msgs,
        system=system,
        max_tokens=max_tokens,
        settings=cfg,
        reject_truncation=reject_truncation,
    )
    try:
        return _parse_json(text)
    except LLMError:
        repair_messages = list(msgs) + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": _JSON_REPAIR_INSTRUCTION},
        ]
        repaired = _chat_anthropic(
            repair_messages,
            system=system,
            max_tokens=max_tokens,
            settings=cfg,
            reject_truncation=reject_truncation,
        )
        return _parse_json(repaired)


def _truncate_raw(text: str, limit: int = _JSON_RAW_LOG_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _strip_code_fences(text: str) -> str:
    match = _FENCE_RE.match(text.strip())
    if match:
        return match.group(1).strip()
    return text


def _extract_json_object_span(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    return text[start : end + 1]


def _attach_images(
    messages: list[dict],
    images: list[bytes] | None,
) -> list[dict]:
    """Return messages with image blocks on the last user turn (in-place copy)."""
    if not images:
        return messages

    # Find last user message index; append one if missing.
    last_user = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user = i
            break
    if last_user is None:
        messages.append({"role": "user", "content": ""})
        last_user = len(messages) - 1

    msg = dict(messages[last_user])
    existing = msg.get("content", "")
    blocks: list[dict[str, Any]] = []
    for raw in images:
        media_type = _sniff_media_type(raw)
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.standard_b64encode(raw).decode("ascii"),
                },
            }
        )
    if isinstance(existing, list):
        # Already multimodal — prepend images, keep existing blocks.
        blocks.extend(existing)
    elif isinstance(existing, str) and existing:
        blocks.append({"type": "text", "text": existing})
    elif not blocks:
        blocks.append({"type": "text", "text": ""})
    # If only images and empty text, Anthropic still accepts image-only user turns
    # but a short prompt helps — callers usually supply text already.
    if not any(b.get("type") == "text" for b in blocks):
        blocks.append({"type": "text", "text": "Extract the requested information."})
    msg["content"] = blocks
    messages[last_user] = msg
    return messages


def _sniff_media_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    return "image/jpeg"


def _parse_json(text: str) -> dict:
    candidates = [text]
    stripped = _strip_code_fences(text)
    if stripped != text:
        candidates.append(stripped)
    for candidate in list(candidates):
        span = _extract_json_object_span(candidate)
        if span is not None and span not in candidates:
            candidates.append(span)

    last_exc: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_exc = exc
            continue
        if not isinstance(parsed, dict):
            raw = _truncate_raw(text)
            logger.warning(
                "json_mode non-object response; raw=%r",
                raw,
            )
            raise LLMError(
                f"JSON response must be an object; raw={raw!r}"
            )
        return parsed

    raw = _truncate_raw(text)
    logger.warning(
        "json_mode parse failure: %s; raw=%r",
        last_exc,
        raw,
    )
    raise LLMError(
        f"Response was not valid JSON: {last_exc}; raw={raw!r}"
    )


def _chat_anthropic(
    messages: list[dict],
    *,
    system: str | None,
    max_tokens: int,
    settings: Settings,
    reject_truncation: bool = False,
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
            return _anthropic_once(
                client,
                kwargs,
                settings.llm_model,
                reject_truncation=reject_truncation,
            )
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
    *,
    reject_truncation: bool = False,
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
    stop_reason = getattr(response, "stop_reason", None)
    logger.info(
        "llm call model=%s input_tokens=%s output_tokens=%s "
        "cache_read=%s cache_creation=%s stop_reason=%s duration_ms=%s",
        model,
        input_tokens,
        output_tokens,
        cache_read,
        cache_creation,
        stop_reason,
        duration_ms,
    )
    if reject_truncation and stop_reason == "max_tokens":
        raise LLMError(
            f"response truncated stop_reason={stop_reason}"
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
