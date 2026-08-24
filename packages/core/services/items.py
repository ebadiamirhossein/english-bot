"""Every query against `items` and `item_attempts`. The only place SQL lives.

`core.items.*` is pure — it turns a draft into a verdict without touching a
database. This module is the other half: it resolves a target lemma to a
`lexeme_id`, writes a validated item, and records what a learner did. The split
is what lets the whole validator be tested without Postgres and what keeps
`tests/test_core_boundary.py::test_no_sql_outside_services` unexempted
(CLAUDE.md §2; known issue #59 stays the only exemption).

**`insert_item` refuses to write an item whose report is not `ok`.** That is the
second of three layers behind "no item reaches a learner without a validation
record" — migration 012's `validation JSONB NOT NULL` plus its
`? 'deterministic'` CHECK is the first, and a parse test asserting exactly one
`INSERT INTO items` in the tree is the third. The third is the one that survives
a refactor.

`user_id` means `users.id` throughout (011, #92). There is no `telegram_user_id`
anywhere in this file, and `tests/test_identity_boundary.py` walks every `.py`
under `packages/core`, so it covers this module from the commit that adds it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from psycopg.rows import tuple_row

from core.db import connection, cursor
from core.items import RESPONSE_MODE, VALIDATOR_VERSION
from core.items.gates import ValidationReport
from core.items.schema import BaseItem, content_hash, payload_of
from core.services.lexicon import ensure_lexeme

logger = logging.getLogger(__name__)


class ItemWriteError(Exception):
    """Raised rather than writing an item that has not earned its place."""


@dataclass(frozen=True, slots=True)
class StoredItem:
    """An `items` row, as much of it as a caller needs."""

    id: int
    user_id: int
    item_type: str
    track: str
    register: str
    prompt_text: str
    answer: str | None
    accepted_variants: tuple[str, ...]
    cue_type: str | None
    payload: dict

    @property
    def response_mode(self) -> str:
        return RESPONSE_MODE[self.item_type]


# Every cursor below pins `tuple_row`: the shared pool is opened with
# `dict_row`, a test connection usually is not, and a service that reads by
# position must not depend on which one it was handed.


def insert_item(
    user_id: int,
    item: BaseItem,
    report: ValidationReport,
    *,
    model: str,
    source_chunk_id: int | None = None,
    error_id: int | None = None,
) -> int | None:
    """Write a validated item. Returns its id, or None if it already existed.

    ``None`` rather than an exception on a duplicate: `UNIQUE (user_id,
    content_hash)` firing means the generator produced something this learner
    already has, which is a normal outcome of asking for fresh items, not a
    fault. The caller counts it and moves on.
    """
    if not report.ok:
        raise ItemWriteError(
            f"refusing to write an item with verdict {report.verdict!r}: "
            f"{report.as_json()}"
        )

    # One connection for both writes, so a grown lexeme and the item that needs
    # it commit together. `ensure_lexeme` takes a connection because W4 made
    # growth a deliberate act with a named caller; passing the same one keeps a
    # failed INSERT from leaving an orphan lemma behind.
    with connection() as conn:
        # A target word outside the seed list is created rather than dropped —
        # W4's growable-`lexemes` rule. `ensure_lexeme` writes `origin='grown'`
        # with a NULL `freq_rank`, and 010's convention holds: NULL rank means
        # "rarer than the seed tail", never "missing", so a grown target is
        # never assumed known by the frequency floor.
        lexeme_id = ensure_lexeme(conn, item.lexeme) if item.lexeme else None
        cur = conn.cursor(row_factory=tuple_row)
        cur.execute(
            """
            INSERT INTO items (
                user_id, item_type, track, register, prompt_text, answer,
                accepted_variants, cue_type, repair_count, lexeme_id,
                error_type, error_id, unit_number, source_chunk_id,
                payload, validation, validator_version, model, content_hash
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            ON CONFLICT (user_id, content_hash) DO NOTHING
            RETURNING id
            """,
            (
                user_id,
                item.item_type,
                item.track,
                item.register_tag,
                item.prompt_text,
                item.answer,
                list(item.accepted_variants),
                item.cue_type,
                report.repair_count,
                lexeme_id,
                item.error_type,
                error_id,
                item.unit_number,
                source_chunk_id,
                json.dumps(payload_of(item), ensure_ascii=False),
                json.dumps(report.as_json(), ensure_ascii=False),
                VALIDATOR_VERSION,
                model,
                content_hash(item),
            ),
        )
        row = cur.fetchone()
        conn.commit()

    if row is None:
        # PRD §10: logs carry ids and route names, never message bodies. The
        # hash is not a body — it is the reason the write was a no-op.
        logger.info(
            "item duplicate user_id=%s type=%s hash=%s",
            user_id,
            item.item_type,
            content_hash(item)[:12],
        )
        return None

    logger.info(
        "item written user_id=%s id=%s type=%s repairs=%s",
        user_id,
        row[0],
        item.item_type,
        report.repair_count,
    )
    return int(row[0])


def record_attempt(
    user_id: int,
    item_id: int,
    *,
    correct: bool,
    graded_by: str,
    session_id: int | None = None,
    response_text: str | None = None,
    response_payload: dict | None = None,
    chosen_option: str | None = None,
    grade: int | None = None,
    latency_ms: int | None = None,
    cue_shown: str | None = None,
    hint_used: bool = False,
    attempt_no: int = 1,
    model_feedback: dict | None = None,
    audio_seconds: float | None = None,
) -> int:
    """Record one attempt. Every column that cannot be reconstructed later.

    `latency_ms`, `cue_shown`, `chosen_option`, `grade`, `graded_by` and
    `audio_seconds` have no reader in W5. They ship anyway: adding a column at
    013 or 015 is one line, but the months of history in between would be blank
    exactly where FSRS and the generator-quality signal need it most.

    **The audio itself is never passed here and never stored** (CLAUDE.md §5) —
    only its duration.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            """
            INSERT INTO item_attempts (
                item_id, user_id, session_id, response_text, response_payload,
                chosen_option, correct, grade, latency_ms, cue_shown,
                hint_used, attempt_no, graded_by, model_feedback, audio_seconds
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            RETURNING id
            """,
            (
                item_id,
                user_id,
                session_id,
                response_text,
                json.dumps(response_payload or {}, ensure_ascii=False),
                chosen_option,
                correct,
                grade,
                latency_ms,
                cue_shown,
                hint_used,
                attempt_no,
                graded_by,
                json.dumps(model_feedback or {}, ensure_ascii=False),
                audio_seconds,
            ),
        )
        row = cur.fetchone()
    assert row is not None
    return int(row[0])


def _to_stored(row: tuple) -> StoredItem:
    return StoredItem(
        id=int(row[0]),
        user_id=int(row[1]),
        item_type=row[2],
        track=row[3],
        register=row[4],
        prompt_text=row[5],
        answer=row[6],
        accepted_variants=tuple(row[7] or ()),
        cue_type=row[8],
        payload=row[9] or {},
    )


_SELECT = """
    SELECT id, user_id, item_type, track, register, prompt_text, answer,
           accepted_variants, cue_type, payload
      FROM items
"""


def list_bank(
    user_id: int, *, item_type: str | None = None, limit: int = 50
) -> list[StoredItem]:
    """This learner's validated stock. What W10 draws from without generating.

    PRD §4.3: "a validated item bank grows over time". Nothing here filters on a
    status column, because rejected items are never written — see migration
    012's note on why a `status` column was refused.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        if item_type is None:
            cur.execute(
                _SELECT + " WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                (user_id, limit),
            )
        else:
            cur.execute(
                _SELECT
                + " WHERE user_id = %s AND item_type = %s"
                + " ORDER BY created_at DESC LIMIT %s",
                (user_id, item_type, limit),
            )
        return [_to_stored(row) for row in cur.fetchall()]


def bank_for_session(user_id: int, *, unit_number: int, limit: int = 20) -> list[StoredItem]:
    """Unit-scoped stock, least recently attempted first.

    W10 owns the session mix; this is only the read it will need. Ordering by
    last attempt rather than by creation is what stops the same freshly-written
    items being served every night while older validated stock is never seen.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            _SELECT
            + """
              WHERE user_id = %s AND unit_number = %s
              ORDER BY (
                  SELECT MAX(a.attempted_at) FROM item_attempts a
                   WHERE a.item_id = items.id
              ) ASC NULLS FIRST, created_at ASC
              LIMIT %s
            """,
            (user_id, unit_number, limit),
        )
        return [_to_stored(row) for row in cur.fetchall()]


def attempt_counts(user_id: int) -> dict[str, int]:
    """Attempts and correct attempts, for W19's progress line."""
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            """
            SELECT count(*), count(*) FILTER (WHERE correct)
              FROM item_attempts WHERE user_id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
    total, right = (row or (0, 0))
    return {"attempts": int(total or 0), "correct": int(right or 0)}
