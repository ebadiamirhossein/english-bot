"""Shadowing (M12 / S16): sentence select, word-level ASR intelligibility diff.

No LLM. No ``errors`` rows. Attempt transcripts are never persisted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app import texts
from app.db import connection
from app.services.reading import normalize_for_match

SHADOW_EXCLUDE_RECENT_K = 10

_PUNCT_IN_TOKEN = re.compile(r"[^\w']+", re.UNICODE)


@dataclass(frozen=True)
class ShadowChunk:
    id: int
    full_sentence: str


@dataclass(frozen=True)
class WordDiffResult:
    target_words: list[str]
    attempt_words: list[str]
    missed: list[str]
    added: list[str]
    altered: list[tuple[str, str]]
    matched: int

    @property
    def score(self) -> float:
        n = len(self.target_words)
        if n <= 0:
            return 1.0
        return self.matched / n


def words_for_compare(text: str) -> list[str]:
    """Tokenise for shadow compare: ``normalize_for_match`` then strip punct."""
    s = normalize_for_match(text)
    out: list[str] = []
    for raw in s.split():
        cleaned = _PUNCT_IN_TOKEN.sub("", raw).strip("'")
        if cleaned:
            out.append(cleaned)
    return out


def diff_words(target: str, attempt: str) -> WordDiffResult:
    """Align target vs attempt word-by-word (deterministic, no LLM)."""
    t_words = words_for_compare(target)
    a_words = words_for_compare(attempt)
    matcher = SequenceMatcher(a=t_words, b=a_words, autojunk=False)
    missed: list[str] = []
    added: list[str] = []
    altered: list[tuple[str, str]] = []
    matched = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            matched += i2 - i1
        elif tag == "delete":
            missed.extend(t_words[i1:i2])
        elif tag == "insert":
            added.extend(a_words[j1:j2])
        elif tag == "replace":
            t_span = t_words[i1:i2]
            a_span = a_words[j1:j2]
            # Pair up as alterations; leftovers are miss/add.
            n = min(len(t_span), len(a_span))
            for k in range(n):
                altered.append((t_span[k], a_span[k]))
            if len(t_span) > n:
                missed.extend(t_span[n:])
            if len(a_span) > n:
                added.extend(a_span[n:])
    return WordDiffResult(
        target_words=t_words,
        attempt_words=a_words,
        missed=missed,
        added=added,
        altered=altered,
        matched=matched,
    )


def format_shadow_feedback(
    target_sentence: str,
    attempt_transcript: str,
    result: WordDiffResult,
) -> str:
    """Fixed visual shape; ASR-intelligibility framing, never guilt."""
    tip = _tip_for(result)
    return texts.format_shadow_feedback(
        target_sentence.strip(),
        attempt_transcript.strip(),
        tip,
    )


def _tip_for(result: WordDiffResult) -> str:
    if (
        not result.missed
        and not result.added
        and not result.altered
        and result.matched == len(result.target_words)
    ):
        return texts.SHADOW_TIP_CLEAR

    parts: list[str] = []
    for tgt, att in result.altered[:3]:
        parts.append(f"{tgt} → {att}")
    for w in result.missed[:3]:
        parts.append(f"{w} didn't come through")
    for w in result.added[:2]:
        parts.append(f"extra: {w}")
    if not parts:
        return texts.SHADOW_TIP_AGAIN
    detail = "; ".join(parts)
    return texts.SHADOW_TIP_PART.format(detail=detail)


def recent_shadowed_chunk_ids(
    user_id: int, *, limit: int = SHADOW_EXCLUDE_RECENT_K
) -> list[int]:
    """Most recent distinct chunk_ids from shadow session payloads (newest first)."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT payload
              FROM sessions
             WHERE user_id = %s
               AND task_type = 'shadow'
             ORDER BY id DESC
             LIMIT %s
            """,
            (user_id, max(limit * 3, 30)),
        ).fetchall()
    out: list[int] = []
    seen: set[int] = set()
    for row in rows:
        payload = row["payload"]
        if payload is not None and not isinstance(payload, dict):
            payload = dict(payload)
        if not isinstance(payload, dict):
            continue
        raw = payload.get("chunk_id")
        if raw is None:
            continue
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            continue
        if cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
        if len(out) >= limit:
            break
    return out


def list_eligible_chunks(user_id: int) -> list[ShadowChunk]:
    """Chunks with a non-empty full_sentence, newest first."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, full_sentence
              FROM chunks
             WHERE user_id = %s
               AND full_sentence IS NOT NULL
               AND btrim(full_sentence) <> ''
             ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
    return [
        ShadowChunk(id=int(r["id"]), full_sentence=str(r["full_sentence"]))
        for r in rows
    ]


def select_shadow_sentence(user_id: int) -> ShadowChunk | None:
    """Pick a sentence: exclude last K shadowed chunk_ids, then recency.

    Fallback when the whole pool is in the exclude set: skip only the single
    most-recent shadowed chunk_id when possible.
    """
    eligible = list_eligible_chunks(user_id)
    if not eligible:
        return None

    excluded = set(recent_shadowed_chunk_ids(user_id, limit=SHADOW_EXCLUDE_RECENT_K))
    for chunk in eligible:
        if chunk.id not in excluded:
            return chunk

    # Pool exhausted relative to K — avoid immediate repeat of the last one.
    last_ids = recent_shadowed_chunk_ids(user_id, limit=1)
    last = last_ids[0] if last_ids else None
    if last is not None:
        for chunk in eligible:
            if chunk.id != last:
                return chunk
    return eligible[0]


def abandon_open_shadow_sessions(user_id: int) -> int:
    """Complete-as-abandoned any incomplete shadow rows (score NULL)."""
    with connection() as conn:
        rows = conn.execute(
            """
            UPDATE sessions
               SET completed = TRUE,
                   completed_at = NOW(),
                   score = NULL
             WHERE user_id = %s
               AND task_type = 'shadow'
               AND completed = FALSE
            RETURNING id
            """,
            (user_id,),
        ).fetchall()
    return len(rows)


def utc_now_iso(now: Any) -> str:
    """Serialize an aware datetime for ``clip_sent_at``."""
    return now.isoformat()
