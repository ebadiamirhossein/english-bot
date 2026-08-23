"""Load-up mode validation + persist-after-send (S14 / M10).

Persists the 10 prep chunks into ``chunks`` for the weekly Anki export.
Never writes ``errors`` or ``sessions``. Frames are reply-only.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Sequence

from app import texts
from app.db import connection
from app.services.chunks import insert_chunks
from app.services.reading import normalize_for_match

logger = logging.getLogger(__name__)

EXPECTED_CHUNKS = 10
MAX_FRAMES = 3
_VALID_TRACKS = frozenset({"work", "life", "curiosity"})
_SLUG_MAX = 48
_SOURCE_PREFIX = "prep_"


class PrepValidationError(ValueError):
    """Raised when an LLM prep payload yields nothing usable."""


@dataclass(frozen=True)
class PrepPayload:
    source: str
    track: str | None
    chunks: list[dict[str, str]]
    frames: list[str]


def slugify_topic(topic: str) -> str:
    """Lowercase slug for the Anki source marker (not for logs)."""
    s = topic.strip().casefold()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "topic"
    return s[:_SLUG_MAX].rstrip("_")


def prep_source(topic: str) -> str:
    """Source marker: ``prep_<slug>`` — distinct from capture / reading_N / book_unit_N."""
    return f"{_SOURCE_PREFIX}{slugify_topic(topic)}"


def _normalise_track(raw: Any) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if not value or value in ("null", "none"):
        return None
    if value in _VALID_TRACKS:
        return value
    return None


def validate_prep_payload(raw: dict[str, Any], *, topic: str) -> PrepPayload:
    """Validate LLM JSON. Raises PrepValidationError when no valid chunks remain."""
    if not isinstance(raw, dict):
        raise PrepValidationError("payload is not an object")

    track = _normalise_track(raw.get("track"))
    source = prep_source(topic)

    raw_chunks = list(raw.get("chunks") or [])
    cleaned: list[dict[str, str]] = []
    for i, item in enumerate(raw_chunks):
        if len(cleaned) >= EXPECTED_CHUNKS:
            break
        if not isinstance(item, dict):
            logger.warning(
                "prep drop chunk index=%s reason=not_object",
                i,
            )
            continue
        chunk = str(item.get("chunk") or "").strip()
        full_sentence = str(item.get("full_sentence") or "").strip()
        meaning = str(item.get("meaning") or "").strip()
        if not chunk or not full_sentence or not meaning:
            logger.warning(
                "prep drop chunk index=%s reason=missing_fields",
                i,
            )
            continue
        chunk_norm = normalize_for_match(chunk)
        sentence_norm = normalize_for_match(full_sentence)
        if not chunk_norm or chunk_norm not in sentence_norm:
            logger.warning(
                "prep drop chunk index=%s reason=chunk_not_in_sentence",
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
        raise PrepValidationError("no valid chunks")

    frames: list[str] = []
    for i, item in enumerate(raw.get("frames") or []):
        if len(frames) >= MAX_FRAMES:
            break
        if not isinstance(item, str):
            logger.warning(
                "prep drop frame index=%s reason=not_string",
                i,
            )
            continue
        frame = item.strip()
        if not frame:
            logger.warning(
                "prep drop frame index=%s reason=empty",
                i,
            )
            continue
        frames.append(frame)

    return PrepPayload(
        source=source,
        track=track,
        chunks=cleaned,
        frames=frames,
    )


async def persist_and_send(
    *,
    user_id: int,
    payload: PrepPayload,
    send: Callable[[], Awaitable[None]],
) -> int:
    """Insert prep chunks, send reply, then commit.

    ``send`` is awaited inside the open transaction. If it raises, the
    transaction rolls back and zero rows remain. Returns the number of
    chunks inserted. Never writes to ``errors`` or ``sessions``.
    """
    with connection() as conn:
        with conn.transaction():
            insert_chunks(
                conn,
                user_id,
                source=payload.source,
                track=payload.track,
                chunks=payload.chunks,
            )
            await send()
    return len(payload.chunks)


def format_prep_reply(
    *,
    topic: str,
    chunks: Sequence[dict[str, str]],
    frames: Sequence[str],
) -> str:
    """Phone-scannable prep list: chunks and frames clearly separated."""
    lines: list[str] = [
        texts.PREP_TITLE.format(topic=topic.strip()),
        "",
        texts.PREP_SECTION_CHUNKS,
    ]
    for i, item in enumerate(chunks, start=1):
        lines.append(f"{i}. {item['chunk']} — {item['meaning']}")

    if frames:
        lines.append("")
        lines.append(texts.PREP_SECTION_FRAMES)
        for frame in frames:
            lines.append(f"▸ {frame}")

    return "\n".join(lines).strip()
