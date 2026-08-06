"""Chunk inserts (S9a). All queries scoped by user_id."""

from __future__ import annotations

from typing import Any, Sequence


def insert_chunks(
    conn: Any,
    user_id: int,
    *,
    source: str,
    track: str,
    chunks: Sequence[dict[str, str]],
) -> None:
    """Insert chunk rows on an open connection (caller owns the transaction).

    Each item in ``chunks`` must have keys ``chunk``, ``full_sentence``,
    ``meaning``. Values are stored as provided (not normalised).
    """
    for item in chunks:
        conn.execute(
            """
            INSERT INTO chunks (
                user_id, chunk, full_sentence, meaning, source, track,
                exported_to_anki
            ) VALUES (
                %s, %s, %s, %s, %s, %s, FALSE
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
