"""Shared content ledger + per-user fan-out (S24).

Fan-out writes one chunks/book_units row per approved onboarded user.
``shared_content`` + ``shared_content_deliveries`` are the idempotency ledger.
Never writes the error journal. Recipients: ``approved_onboarded_users`` only.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Sequence

from psycopg.types.json import Jsonb

from core.db import connection
from core.services.books import MergedUnit, upsert_unit_shared
from core.services.chunks import insert_chunks
from core.services.reading import normalize_for_match

logger = logging.getLogger(__name__)

OUTCOME_DELIVERED = "delivered"
OUTCOME_SKIPPED_OWNED = "skipped_owned"
KIND_CHUNK = "chunk"
KIND_BOOK_UNIT = "book_unit"


@dataclass(frozen=True)
class FanoutStats:
    """Sender-centric counts plus how many recipients were touched this run."""

    imported: int
    duplicates: int
    rejected: int
    users_reached: int


def list_recipients() -> list[int]:
    """Approved onboarded telegram ids — sole recipient list (S18d view)."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT telegram_user_id
              FROM approved_onboarded_users
             ORDER BY telegram_user_id
            """
        ).fetchall()
    return [int(r["telegram_user_id"]) for r in rows]


def book_content_key(book: str, unit_number: str) -> str:
    """Stable ledger key — no NUL bytes; normalised book slug."""
    return f"{normalize_for_match(book)}:{unit_number.strip()}"


def chunk_content_key(chunk: str) -> str:
    return normalize_for_match(chunk)


def _existing_chunk_norms(conn: Any, user_id: int) -> set[str]:
    rows = conn.execute(
        "SELECT chunk FROM chunks WHERE user_id = %s",
        (user_id,),
    ).fetchall()
    return {normalize_for_match(str(r["chunk"])) for r in rows if r["chunk"]}


def _has_delivery(conn: Any, shared_id: int, user_id: int) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM shared_content_deliveries
         WHERE shared_content_id = %s AND user_id = %s
        """,
        (shared_id, user_id),
    ).fetchone()
    return row is not None


def _shared_id_for_key(conn: Any, kind: str, content_key: str) -> int | None:
    row = conn.execute(
        """
        SELECT id FROM shared_content
         WHERE kind = %s AND content_key = %s
        """,
        (kind, content_key),
    ).fetchone()
    return int(row["id"]) if row else None


def _upsert_shared_chunk(
    conn: Any,
    *,
    item: dict[str, str],
    created_by: int,
    source: str,
) -> int:
    """Insert chunk ledger row; first-write-wins on conflict. Returns id."""
    key = chunk_content_key(item["chunk"])
    payload = {
        "chunk": item["chunk"],
        "full_sentence": item["full_sentence"],
        "meaning": item["meaning"],
    }
    row = conn.execute(
        """
        INSERT INTO shared_content (
            kind, content_key, payload, source, created_by
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (kind, content_key) DO NOTHING
        RETURNING id
        """,
        (KIND_CHUNK, key, Jsonb(payload), source, created_by),
    ).fetchone()
    if row is not None:
        return int(row["id"])
    existing = _shared_id_for_key(conn, KIND_CHUNK, key)
    assert existing is not None
    return existing


def _upsert_shared_book_unit(
    conn: Any,
    *,
    book: str,
    unit: MergedUnit,
    created_by: int,
) -> int:
    """Insert or refresh book ledger payload (title/items). Returns id."""
    key = book_content_key(book, unit.unit_number)
    payload = {
        "book": book,
        "unit_number": unit.unit_number,
        "unit_title": unit.unit_title,
        "target_items": list(unit.target_items),
    }
    row = conn.execute(
        """
        INSERT INTO shared_content (
            kind, content_key, payload, source, created_by
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (kind, content_key) DO UPDATE SET
            payload = EXCLUDED.payload,
            updated_at = NOW(),
            source = EXCLUDED.source
        RETURNING id
        """,
        (KIND_BOOK_UNIT, key, Jsonb(payload), book, created_by),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def _deliver_chunk(
    conn: Any,
    *,
    shared_id: int,
    user_id: int,
    payload: dict[str, Any],
    source: str,
) -> str | None:
    """Insert copy or skip-owned; always write delivery. None if already settled."""
    if _has_delivery(conn, shared_id, user_id):
        return None

    existing = _existing_chunk_norms(conn, user_id)
    key = chunk_content_key(str(payload["chunk"]))
    if key in existing:
        conn.execute(
            """
            INSERT INTO shared_content_deliveries (
                shared_content_id, user_id, outcome
            ) VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (shared_id, user_id, OUTCOME_SKIPPED_OWNED),
        )
        return OUTCOME_SKIPPED_OWNED

    insert_chunks(
        conn,
        user_id,
        source=source,
        track=None,
        chunks=[
            {
                "chunk": str(payload["chunk"]),
                "full_sentence": str(payload["full_sentence"]),
                "meaning": str(payload["meaning"]),
            }
        ],
        presented=False,
    )
    conn.execute(
        """
        INSERT INTO shared_content_deliveries (
            shared_content_id, user_id, outcome
        ) VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (shared_id, user_id, OUTCOME_DELIVERED),
    )
    return OUTCOME_DELIVERED


def _deliver_book_unit(
    conn: Any,
    *,
    shared_id: int,
    user_id: int,
    payload: dict[str, Any],
) -> str | None:
    """Upsert unit content; write delivery if new. Refresh never touches studied_at."""
    book = str(payload["book"])
    unit = MergedUnit(
        unit_number=str(payload["unit_number"]),
        unit_title=str(payload.get("unit_title") or ""),
        target_items=[str(x) for x in (payload.get("target_items") or [])],
    )
    had_delivery = _has_delivery(conn, shared_id, user_id)
    upsert_unit_shared(conn, user_id, book, unit)
    if had_delivery:
        return None
    conn.execute(
        """
        INSERT INTO shared_content_deliveries (
            shared_content_id, user_id, outcome
        ) VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (shared_id, user_id, OUTCOME_DELIVERED),
    )
    return OUTCOME_DELIVERED


def backfill_shared_library(user_id: int) -> int:
    """Deliver every ledger item missing a delivery for this user.

    No-op when the user has no ``users`` row (FK) or nothing is pending.
    Returns number of new delivery rows written.
    """
    with connection() as conn:
        user_row = conn.execute(
            "SELECT 1 FROM users WHERE telegram_user_id = %s",
            (user_id,),
        ).fetchone()
        if user_row is None:
            return 0

        pending = conn.execute(
            """
            SELECT sc.id, sc.kind, sc.payload, sc.source
              FROM shared_content sc
             WHERE NOT EXISTS (
                   SELECT 1 FROM shared_content_deliveries d
                    WHERE d.shared_content_id = sc.id
                      AND d.user_id = %s
             )
             ORDER BY sc.id
            """,
            (user_id,),
        ).fetchall()

        written = 0
        for row in pending:
            shared_id = int(row["id"])
            kind = str(row["kind"])
            payload = row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            if not isinstance(payload, dict):
                logger.error(
                    "shared backfill bad payload id=%s user_id=%s",
                    shared_id,
                    user_id,
                )
                continue
            with conn.transaction():
                if kind == KIND_CHUNK:
                    source = str(row["source"] or "slang")
                    outcome = _deliver_chunk(
                        conn,
                        shared_id=shared_id,
                        user_id=user_id,
                        payload=payload,
                        source=source,
                    )
                elif kind == KIND_BOOK_UNIT:
                    outcome = _deliver_book_unit(
                        conn,
                        shared_id=shared_id,
                        user_id=user_id,
                        payload=payload,
                    )
                else:
                    continue
                if outcome is not None:
                    written += 1
        return written


def record_and_fanout_chunks(
    items: Sequence[dict[str, str]],
    *,
    created_by: int,
    source: str = "slang",
    rejected: int = 0,
) -> FanoutStats:
    """Upsert chunk ledger (first-write-wins), reconcile recipients, fan out.

    ``imported`` / ``duplicates`` are the **sender's** outcomes for this run
    only (already-delivered keys count as duplicate).
    ``rejected`` is file-level (caller-supplied).
    ``users_reached`` counts recipients who gained at least one new delivery
    for this batch's keys (re-import → 0).
    """
    batch_keys = [chunk_content_key(i["chunk"]) for i in items]

    with connection() as conn:
        with conn.transaction():
            for item in items:
                _upsert_shared_chunk(
                    conn, item=item, created_by=created_by, source=source
                )

    recipients = list_recipients()
    before_counts = {
        uid: _delivery_count_for_keys(uid, batch_keys) for uid in recipients
    }
    before_sender = _outcomes_for_keys(created_by, batch_keys)

    for uid in recipients:
        backfill_shared_library(uid)

    users_reached = sum(
        1
        for uid in recipients
        if _delivery_count_for_keys(uid, batch_keys) > before_counts[uid]
    )

    after_sender = _outcomes_for_keys(created_by, batch_keys)
    sender_imported = 0
    sender_duplicates = 0
    for key in batch_keys:
        if key in before_sender:
            sender_duplicates += 1
            continue
        outcome = after_sender.get(key)
        if outcome == OUTCOME_SKIPPED_OWNED:
            sender_duplicates += 1
        elif outcome == OUTCOME_DELIVERED:
            sender_imported += 1

    return FanoutStats(
        imported=sender_imported,
        duplicates=sender_duplicates,
        rejected=rejected,
        users_reached=users_reached,
    )


def _outcomes_for_keys(
    user_id: int, keys: Sequence[str]
) -> dict[str, str]:
    if not keys:
        return {}
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT sc.content_key, d.outcome
              FROM shared_content sc
              JOIN shared_content_deliveries d
                ON d.shared_content_id = sc.id
             WHERE sc.kind = %s
               AND sc.content_key = ANY(%s)
               AND d.user_id = %s
            """,
            (KIND_CHUNK, list(keys), user_id),
        ).fetchall()
    return {str(r["content_key"]): str(r["outcome"]) for r in rows}


def _delivery_count_for_keys(user_id: int, keys: Sequence[str]) -> int:
    if not keys:
        return 0
    with connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)::int AS n
              FROM shared_content sc
              JOIN shared_content_deliveries d
                ON d.shared_content_id = sc.id
             WHERE sc.kind = %s
               AND sc.content_key = ANY(%s)
               AND d.user_id = %s
            """,
            (KIND_CHUNK, list(keys), user_id),
        ).fetchone()
    return int(row["n"]) if row else 0


def record_and_fanout_book_units(
    book: str,
    units: Sequence[MergedUnit],
    *,
    created_by: int,
) -> FanoutStats:
    """Upsert book ledger (refresh payload), reconcile, fan out via shared upsert."""
    if not units:
        return FanoutStats(0, 0, 0, 0)

    keys = [book_content_key(book, u.unit_number) for u in units]

    with connection() as conn:
        with conn.transaction():
            for unit in units:
                _upsert_shared_book_unit(
                    conn, book=book, unit=unit, created_by=created_by
                )

    recipients = list_recipients()
    before_counts = {
        uid: _book_delivery_count_for_keys(uid, keys) for uid in recipients
    }

    for uid in recipients:
        backfill_shared_library(uid)
        # Recipients who already had deliveries still need content refresh.
        _refresh_book_units_for_user(uid, book, units)

    users_reached = sum(
        1
        for uid in recipients
        if _book_delivery_count_for_keys(uid, keys) > before_counts[uid]
        or before_counts[uid] > 0
    )

    return FanoutStats(
        imported=0,
        duplicates=len(units),
        rejected=0,
        users_reached=users_reached,
    )


def _book_delivery_count_for_keys(user_id: int, keys: Sequence[str]) -> int:
    if not keys:
        return 0
    with connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)::int AS n
              FROM shared_content sc
              JOIN shared_content_deliveries d
                ON d.shared_content_id = sc.id
             WHERE sc.kind = %s
               AND sc.content_key = ANY(%s)
               AND d.user_id = %s
            """,
            (KIND_BOOK_UNIT, list(keys), user_id),
        ).fetchone()
    return int(row["n"]) if row else 0


def _refresh_book_units_for_user(
    user_id: int, book: str, units: Sequence[MergedUnit]
) -> None:
    """Push latest title/items without bumping studied_at."""
    with connection() as conn:
        with conn.transaction():
            for unit in units:
                upsert_unit_shared(conn, user_id, book, unit)


def try_backfill_soft(user_id: int) -> bool:
    """Run backfill; log on failure. Returns True on success.

    Callers that can reach Telegram should alert the operator when False.
    Never raises — onboarding must not break on backfill failure.
    """
    try:
        backfill_shared_library(user_id)
        return True
    except Exception:
        logger.exception(
            "shared backfill failed user_id=%s — will reconcile on next fan-out",
            user_id,
        )
        return False
