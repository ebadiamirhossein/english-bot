"""Real-life capture validation + persist-after-send (S15 / M11)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Sequence

from core.db import connection
from core.services.chunks import insert_chunks
from core.services.reading import normalize_for_match, word_count

logger = logging.getLogger(__name__)

CAPTURE_SOURCE = "capture"
_MAX_CHUNKS = 5
_MAX_EXPLANATION_WORDS = 25
_VALID_TRACKS = frozenset({"work", "life", "curiosity"})


class CaptureValidationError(ValueError):
    """Raised when an LLM capture payload yields nothing usable."""


@dataclass(frozen=True)
class CapturePayload:
    explanation: str
    track: str | None
    chunks: list[dict[str, str]]


def target_chunk_count(passage: str) -> int:
    """Soft target for the prompt / tests: 1–5 from ~40 words each."""
    words = word_count(passage)
    return min(_MAX_CHUNKS, max(1, words // 40))


def _normalise_track(raw: Any) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if not value or value in ("null", "none"):
        return None
    if value in _VALID_TRACKS:
        return value
    return None


def validate_capture_payload(raw: dict[str, Any]) -> CapturePayload:
    """Validate LLM JSON. Raises CaptureValidationError when unusable."""
    if not isinstance(raw, dict):
        raise CaptureValidationError("payload is not an object")

    ok = raw.get("ok")
    if ok is False:
        raise CaptureValidationError("ok=false")
    if ok is not True and ok is not None:
        # Tolerate missing ok if chunks are present; reject explicit non-true.
        if ok not in (1, "true", "True"):
            raise CaptureValidationError(f"ok={ok!r}")

    explanation = str(raw.get("explanation") or "").strip()
    if explanation and word_count(explanation) > _MAX_EXPLANATION_WORDS:
        # Soft-trim is not worth inventing; keep but operators can tune prompt.
        # Still accept — PRD is a prompt contract; do not fail the whole capture.
        pass

    track = _normalise_track(raw.get("track"))

    raw_chunks = list(raw.get("chunks") or [])
    cleaned: list[dict[str, str]] = []
    for i, item in enumerate(raw_chunks):
        if len(cleaned) >= _MAX_CHUNKS:
            break
        if not isinstance(item, dict):
            logger.warning(
                "capture drop chunk index=%s reason=not_object",
                i,
            )
            continue
        chunk = str(item.get("chunk") or "").strip()
        full_sentence = str(item.get("full_sentence") or "").strip()
        meaning = str(item.get("meaning") or "").strip()
        if not chunk or not full_sentence or not meaning:
            logger.warning(
                "capture drop chunk index=%s reason=missing_fields",
                i,
            )
            continue
        chunk_norm = normalize_for_match(chunk)
        sentence_norm = normalize_for_match(full_sentence)
        if not chunk_norm or chunk_norm not in sentence_norm:
            logger.warning(
                "capture drop chunk index=%s reason=chunk_not_in_sentence",
                i,
            )
            continue
        cleaned.append(
            {
                "chunk": chunk,
                "full_sentence": full_sentence,
                "meaning": meaning,
            }
        )

    if not cleaned:
        raise CaptureValidationError("no valid chunks")

    if not explanation:
        explanation = "Useful phrases from what you sent."

    return CapturePayload(
        explanation=explanation,
        track=track,
        chunks=cleaned,
    )


async def persist_and_send(
    *,
    user_id: int,
    payload: CapturePayload,
    send: Callable[[], Awaitable[None]],
) -> int:
    """Insert capture chunks, send reply, then commit.

    ``send`` is awaited inside the open transaction. If it raises, the
    transaction rolls back and zero rows remain. Returns the number of
    chunks inserted. Never writes to ``errors``.
    """
    with connection() as conn:
        with conn.transaction():
            insert_chunks(
                conn,
                user_id,
                source=CAPTURE_SOURCE,
                track=payload.track,
                chunks=payload.chunks,
            )
            await send()
    return len(payload.chunks)


def format_capture_reply(
    *,
    explanation: str,
    chunks: Sequence[dict[str, str]],
    hint: str,
) -> str:
    """Build the user-facing capture message (under ~400 chars when possible)."""
    lines = [explanation.strip(), ""]
    for item in chunks:
        lines.append(f"• {item['chunk']} — {item['meaning']}")
    body = "\n".join(lines).strip()
    if hint:
        candidate = f"{body}\n\n{hint}"
        if len(candidate) <= 400:
            return candidate
    return body
