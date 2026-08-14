"""Chunk inserts + spaced review (S9a / S15 / S14 / S7a) + presentation (S25).

All queries scoped by user_id. Export state (exported_to_anki) is independent
of review state (next_review / ladder counters) and of presentation
(presented_at). Graded due selection requires presented_at IS NOT NULL.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Sequence

from app.db import connection
from app.services.errors import spacing_step

logger = logging.getLogger(__name__)

# Single predicate for every graded due-chunk consumer (S25 — same lesson as
# spacing_step / approved_onboarded_users). Interpolate into SQL; never copy.
CHUNK_PRESENTED_AND_DUE_SQL = (
    "presented_at IS NOT NULL AND (next_review IS NULL OR next_review <= %s)"
)


@dataclass(frozen=True)
class Chunk:
    id: int
    user_id: int
    chunk: str
    full_sentence: str | None
    meaning: str | None
    source: str | None
    track: str | None
    exported_to_anki: bool
    next_review: date | None
    times_right: int
    times_wrong: int
    streak_right: int
    created_at: datetime | None = None
    presented_at: datetime | None = None


def insert_chunks(
    conn: Any,
    user_id: int,
    *,
    source: str,
    track: str | None,
    chunks: Sequence[dict[str, str]],
    presented: bool = True,
) -> None:
    """Insert chunk rows on an open connection (caller owns the transaction).

    Each item in ``chunks`` must have keys ``chunk``, ``full_sentence``,
    ``meaning``. Values are stored as provided (not normalised).
    ``track`` may be NULL (S15 capture when classification is uncertain).
    New rows get ``next_review = CURRENT_DATE + 1`` (S7a / same as S2 errors).
    ``presented=True`` (default) sets ``presented_at = NOW()`` — user-sourced
    content. Fan-out via shared_content_deliveries passes ``presented=False``.
    """
    for item in chunks:
        if presented:
            conn.execute(
                """
                INSERT INTO chunks (
                    user_id, chunk, full_sentence, meaning, source, track,
                    exported_to_anki, next_review, presented_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, FALSE, CURRENT_DATE + 1, NOW()
                )
                """,
                (
                    user_id,
                    item["chunk"],
                    item.get("full_sentence") or None,
                    item.get("meaning") or None,
                    source,
                    track,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO chunks (
                    user_id, chunk, full_sentence, meaning, source, track,
                    exported_to_anki, next_review, presented_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, FALSE, CURRENT_DATE + 1, NULL
                )
                """,
                (
                    user_id,
                    item["chunk"],
                    item.get("full_sentence") or None,
                    item.get("meaning") or None,
                    source,
                    track,
                ),
            )


def _row_to_chunk(row: Any) -> Chunk:
    return Chunk(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        chunk=str(row["chunk"]),
        full_sentence=(
            str(row["full_sentence"])
            if row["full_sentence"] is not None
            else None
        ),
        meaning=str(row["meaning"]) if row["meaning"] is not None else None,
        source=str(row["source"]) if row["source"] is not None else None,
        track=str(row["track"]) if row["track"] is not None else None,
        exported_to_anki=bool(row["exported_to_anki"]),
        next_review=row["next_review"],
        times_right=int(row["times_right"] or 0),
        times_wrong=int(row["times_wrong"] or 0),
        streak_right=int(row["streak_right"] or 0),
        created_at=row["created_at"],
        presented_at=row["presented_at"] if row.get("presented_at") is not None else None,
    )


def due_chunks(
    user_id: int,
    limit: int,
    *,
    now: date,
) -> list[Chunk]:
    """Due presented chunks for quiz review, oldest next_review first (NULL first).

    Within the same ``next_review``, prefer newer chunks (``id DESC``) so a
    bulk subtitle import cannot starve later captures. Errors keep oldest-first
    (``due_errors``) — different data, different rule (S15a).

    Unpresented rows (``presented_at IS NULL``) are never returned (S25).
    Skips rows whose ``full_sentence`` cannot host a gap; pulls replacements
    until ``limit`` is filled or the pool is exhausted. Does not filter on
    ``exported_to_anki``.
    """
    if limit <= 0:
        return []
    # Lazy import — anki → reading → chunks would cycle at module load.
    from app.services.anki import make_sentence_with_gap

    # Over-fetch so ungapable rows can be replaced without a second round-trip
    # pattern that races; still bounded.
    fetch = max(limit * 4, limit + 8)
    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id, user_id, chunk, full_sentence, meaning, source, track,
                   exported_to_anki, next_review, times_right, times_wrong,
                   streak_right, created_at, presented_at
              FROM chunks
             WHERE user_id = %s
               AND {CHUNK_PRESENTED_AND_DUE_SQL}
             ORDER BY next_review ASC NULLS FIRST, id DESC
             LIMIT %s
            """,
            (user_id, now, fetch),
        ).fetchall()

    selected: list[Chunk] = []
    for row in rows:
        chunk = _row_to_chunk(row)
        if not chunk.full_sentence or not str(chunk.full_sentence).strip():
            logger.warning(
                "due_chunks skip user_id=%s chunk_id=%s reason=empty_full_sentence",
                user_id,
                chunk.id,
            )
            continue
        if make_sentence_with_gap(str(chunk.full_sentence), chunk.chunk) is None:
            logger.warning(
                "due_chunks skip user_id=%s chunk_id=%s reason=chunk_not_in_sentence",
                user_id,
                chunk.id,
            )
            continue
        selected.append(chunk)
        if len(selected) >= limit:
            break
    return selected


def count_due_chunks(user_id: int, *, now: date) -> int:
    """Count presented chunks due for review (NULL next_review counts as due)."""
    with connection() as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*)::int AS n
              FROM chunks
             WHERE user_id = %s
               AND {CHUNK_PRESENTED_AND_DUE_SQL}
            """,
            (user_id, now),
        ).fetchone()
    assert row is not None
    return int(row["n"])


def unpresented_chunks(user_id: int, limit: int = 2) -> list[Chunk]:
    """Oldest-first unpresented chunks for morning presentation (S25).

    Ignores ``next_review``. Cap defaults to 2 (match S7a chunk cap). Ordering
    is FIFO by ``created_at ASC, id ASC`` — not the graded ``id DESC`` tie-break.
    """
    if limit <= 0:
        return []
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, chunk, full_sentence, meaning, source, track,
                   exported_to_anki, next_review, times_right, times_wrong,
                   streak_right, created_at, presented_at
              FROM chunks
             WHERE user_id = %s
               AND presented_at IS NULL
             ORDER BY created_at ASC, id ASC
             LIMIT %s
            """,
            (user_id, limit),
        ).fetchall()
    return [_row_to_chunk(row) for row in rows]


def mark_presented(chunk_id: int, *, now: date) -> bool:
    """Mark a chunk presented and schedule first graded review for tomorrow.

    Leaves ``times_*`` / ``streak_right`` unchanged. Idempotent: if already
    presented, returns False and does not rewrite ``next_review``.
    """
    tomorrow = now + timedelta(days=1)
    with connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """
                UPDATE chunks
                   SET presented_at = NOW(),
                       next_review = %s
                 WHERE id = %s
                   AND presented_at IS NULL
             RETURNING id
                """,
                (tomorrow, chunk_id),
            ).fetchone()
    return row is not None


def mark_chunk_result(
    chunk_id: int,
    correct: bool,
    *,
    now: date,
) -> None:
    """Apply one chunk review result via the shared spacing ladder."""
    with connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """
                SELECT id, streak_right
                  FROM chunks
                 WHERE id = %s
                 FOR UPDATE
                """,
                (chunk_id,),
            ).fetchone()
            if row is None:
                logger.warning("mark_chunk_result: unknown chunk_id=%s", chunk_id)
                return
            step = spacing_step(
                correct=correct,
                streak_right=int(row["streak_right"] or 0),
                today=now,
            )
            if correct:
                conn.execute(
                    """
                    UPDATE chunks
                       SET streak_right = %s,
                           times_right = times_right + 1,
                           next_review = %s
                     WHERE id = %s
                    """,
                    (step.streak_right, step.next_review, chunk_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE chunks
                       SET streak_right = %s,
                           times_wrong = times_wrong + 1,
                           next_review = %s
                     WHERE id = %s
                    """,
                    (step.streak_right, step.next_review, chunk_id),
                )


def chunk_due_predicate_sites() -> dict[str, Callable[..., Any]]:
    """Canonical graded-due call sites for the S25 drift test.

    Every consumer of presented-and-due chunk counts must appear here and must
    reference ``CHUNK_PRESENTED_AND_DUE_SQL`` in its source.
    """
    from app.services import stats

    return {
        "due_chunks": due_chunks,
        "count_due_chunks": count_due_chunks,
        "_chunk_counts": stats._chunk_counts,
    }
