"""The Saturday checkpoint: one sitting, twelve items, 80% to pass. PRD §3.

**This module owns the SITTING.** `core.services.syllabus` owns every write to
`user_unit_state` and is the only module that touches it;
`core.services.items.checkpoint_items` owns the selection; and
`core.syllabus.checkpoint` is the pure half -- the quota map, the pass mark, the
slot plan -- with no SQL in it at all. Four files, one concern each, and the
boundary is enforced by `tests/test_core_boundary.py` rather than by habit.

**NOTHING IS GENERATED HERE.** A checkpoint's twelve items are written days
earlier by `python -m core.items.generate --checkpoint`, human-run and attended
(operator ruling 1, 2026-08-27: *the app never generates while a learner waits,
and never while nobody is watching*). This module reads a bank.

**THE SITTING IS A `sessions` ROW, AND ITS SINGULARITY IS MIGRATION 018.**
`task_type = 'checkpoint'`, one per learner per LOCAL date, enforced by
`sessions_one_checkpoint_per_user_per_date`. That index is what makes the
attempt key sound: without it a refetch creates two sittings, both claiming
cleanly, and `checkpoint_attempts` is bumped twice while `retake_due_on` moves
twice.

**NO PUNISHMENT COPY, AND NO SCORE ON A FAILURE.** PRD §3: *never a blocked
path, never a punishment screen*, and v2's carried rule, *drops are silent,
raises are announced*. `last_checkpoint_score` is STORED because 014 requires a
`passed` row to name the score that passed -- storing it is not licence to show
it, and `outcome.score_pct` is served only on a pass.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg.rows import tuple_row

from core.db import connection
from core.services import items as items_service
from core.services import syllabus as syllabus_service
from core.syllabus import CHECKPOINT_ITEM_COUNT
from core.syllabus.checkpoint import pass_mark, quota_map

logger = logging.getLogger(__name__)

#: `sessions.task_type` for a sitting. The value needs no CHECK widened --
#: `sessions.task_type` is a bare TEXT (001:107) -- but it DOES need migration
#: 018's partial unique index, which is a different question and the one an
#: earlier draft of this slice failed to ask.
CHECKPOINT_TASK_TYPE = "checkpoint"


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """One sitting, as the learner receives it."""

    session_id: int
    unit_number: int
    can_do: str
    item_count: int
    #: `ready` when twelve items were selected; `not_ready` when the bank could
    #: not fill this sitting's quota map; `done` when it has been scored.
    state: str
    items: tuple[Any, ...] = ()
    #: Set only once the sitting is scored.
    passed: bool | None = None
    #: **Served only on a PASS.** See the module docstring.
    score_pct: int | None = None
    retake_due_on: Any = None


def _unit_row(conn, user_id: int):
    unit_number = syllabus_service.current_unit(conn, user_id)
    return unit_number, syllabus_service.unit_for_session(conn, unit_number)


def _get_or_create_sitting(
    conn, user_id: int, unit_number: int, local_date, *, now: datetime
) -> tuple[int, bool, dict]:
    """``(session_id, completed, payload)``. Idempotent by migration 018.

    `INSERT ... ON CONFLICT DO NOTHING` plus a re-read, the same shape and the
    same reasoning as `core.services.sessions._get_or_create_daily`: the
    DATABASE decides, not a read-then-write, so two tabs or a phone that
    backgrounds and resumes cannot produce two sittings.

    **`ON CONFLICT` needs something to conflict ON**, and for a checkpoint row
    that is migration 018's `sessions_one_checkpoint_per_user_per_date`. 016's
    index is partial on `task_type = 'daily'` and does not reach here -- which is
    exactly why this slice needed a migration after two drafts said it did not.

    `delivered_at` is PASSED IN and never `NOW()`, per 013's rule for
    `card_reviews.reviewed_at`: a column default would make the instant that
    opened the sitting and the instant everything downstream reasons about two
    different clock reads.
    """
    payload = {"unit_number": unit_number}
    conn.execute(
        """
        INSERT INTO sessions (user_id, date, task_type, delivered_at, completed, payload)
        VALUES (%s, %s, %s, %s, FALSE, %s)
        ON CONFLICT (user_id, date) WHERE task_type = 'checkpoint' DO NOTHING
        """,
        (user_id, local_date, CHECKPOINT_TASK_TYPE, now, json.dumps(payload)),
    )
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT id, completed, payload
              FROM sessions
             WHERE user_id = %s AND date = %s AND task_type = %s
            """,
            (user_id, local_date, CHECKPOINT_TASK_TYPE),
        )
        row = cur.fetchone()
    assert row is not None
    return int(row[0]), bool(row[1]), dict(row[2] or {})


def today(user_id: int, *, now: datetime) -> Checkpoint | None:
    """This learner's checkpoint for today. ``None`` if the user is unknown.

    Creates the sitting if it does not exist -- idempotently, through 018's
    partial unique index -- then selects the twelve.

    **The quota map is `quota_map`'s, and this function does not compute it.**
    `core.items.generate.checkpoint_slot_plan` called the same producer to BUILD
    the cohort, so the two cannot disagree about what a sitting is made of.
    First sitting -> `missed_targets` is empty -> the blueprint's `per_target`.
    Retake -> the re-weighted map. **Twelve and 80% on both paths** (CLAUDE.md
    §3 rule 7); what differs is which targets the twelve are spread across.

    A bank that cannot fill the map yields `not_ready` and **never a short
    checkpoint**.
    """
    from core.services.sessions import local_today

    with connection() as conn:
        with conn.cursor(row_factory=tuple_row) as cur:
            cur.execute(
                "SELECT timezone FROM users WHERE id = %s", (user_id,)
            )
            row = cur.fetchone()
        if row is None:
            return None
        local_date = local_today(str(row[0]), now)

        unit_number, unit = _unit_row(conn, user_id)
        if unit is None:
            return None

        session_id, completed, payload = _get_or_create_sitting(
            conn, user_id, unit_number, local_date, now=now
        )

    if completed:
        did_pass = bool(payload.get("passed"))
        return Checkpoint(
            session_id=session_id,
            unit_number=unit_number,
            can_do=unit.can_do,
            item_count=CHECKPOINT_ITEM_COUNT,
            state="done",
            passed=did_pass,
            score_pct=payload.get("score_pct") if did_pass else None,
        )

    missed = syllabus_service.missed_targets(user_id, unit_number)
    quotas = quota_map(dict(unit.checkpoint["per_target"]), missed)
    stock = items_service.checkpoint_items(
        user_id, unit_number=unit_number, quotas=quotas
    )
    if not stock:
        return Checkpoint(
            session_id=session_id,
            unit_number=unit_number,
            can_do=unit.can_do,
            item_count=CHECKPOINT_ITEM_COUNT,
            state="not_ready",
        )
    return Checkpoint(
        session_id=session_id,
        unit_number=unit_number,
        can_do=unit.can_do,
        item_count=CHECKPOINT_ITEM_COUNT,
        state="ready",
        items=tuple(stock),
    )


def complete(user_id: int, session_id: int, *, now: datetime) -> Checkpoint | None:
    """Score one sitting. ``None`` if it is not this learner's.

    **THE CLAIM IS THE ATTEMPT KEY, and it is one statement.**

        UPDATE sessions SET completed = TRUE ... WHERE ... AND completed = FALSE
        RETURNING id

    No row returned means this sitting was already scored, and
    `record_checkpoint` is NOT called -- the already-recorded result is returned
    instead. `UNIQUE (user_id, unit_number)` on `user_unit_state` is a ROW key
    and could not do this job: a second call would `ON CONFLICT DO UPDATE`, bump
    `checkpoint_attempts` again and **move `retake_due_on` with it**, so a double
    tap would shorten or lengthen the retake.

    **A genuine retake is a different `sessions` row** -- four days later is a
    different local date -- so the key separates the two cases without needing to
    know which is which.

    The score is counted from `item_attempts`, the log, rather than from a number
    the client sends: #108's standing lesson is that the one value W6 took from
    the browser is the one that is meaningless.
    """
    with connection() as conn:
        with conn.cursor(row_factory=tuple_row) as cur:
            cur.execute(
                """
                SELECT id, completed, payload
                  FROM sessions
                 WHERE id = %s AND user_id = %s AND task_type = %s
                """,
                (session_id, user_id, CHECKPOINT_TASK_TYPE),
            )
            row = cur.fetchone()
        if row is None:
            return None
        payload = dict(row[2] or {})
        unit_number = int(payload.get("unit_number") or 0)

        with conn.cursor(row_factory=tuple_row) as cur:
            cur.execute(
                """
                SELECT count(*)::int,
                       count(*) FILTER (WHERE a.correct)::int
                  FROM item_attempts a
                 WHERE a.session_id = %s AND a.user_id = %s
                """,
                (session_id, user_id),
            )
            counted = cur.fetchone()
        answered, correct = (int(counted[0]), int(counted[1])) if counted else (0, 0)

        # THE CLAIM.
        with conn.cursor(row_factory=tuple_row) as cur:
            cur.execute(
                """
                UPDATE sessions
                   SET completed = TRUE, completed_at = %s
                 WHERE id = %s AND user_id = %s AND task_type = %s
                   AND completed = FALSE
                RETURNING id
                """,
                (now, session_id, user_id, CHECKPOINT_TASK_TYPE),
            )
            claimed = cur.fetchone() is not None

        if not claimed:
            # Already scored. Return what was recorded; write nothing.
            logger.info(
                "checkpoint already scored user_id=%s session_id=%s",
                user_id, session_id,
            )
            did_pass = bool(payload.get("passed"))
            return Checkpoint(
                session_id=session_id,
                unit_number=unit_number,
                can_do="",
                item_count=CHECKPOINT_ITEM_COUNT,
                state="done",
                passed=did_pass,
                score_pct=payload.get("score_pct") if did_pass else None,
            )

        item_count = max(answered, CHECKPOINT_ITEM_COUNT)
        state = syllabus_service.record_checkpoint(
            conn,
            user_id,
            unit_number,
            correct=correct,
            item_count=item_count,
            now=now,
        )
        did_pass = state == "passed"

        from core.syllabus.checkpoint import score_pct as _score_pct

        payload.update(
            {
                "passed": did_pass,
                "correct": correct,
                "item_count": item_count,
                "pass_mark": pass_mark(item_count),
                "score_pct": _score_pct(correct, item_count),
            }
        )
        conn.execute(
            "UPDATE sessions SET payload = %s WHERE id = %s",
            (json.dumps(payload), session_id),
        )

        with conn.cursor(row_factory=tuple_row) as cur:
            cur.execute(
                """
                SELECT retake_due_on FROM user_unit_state
                 WHERE user_id = %s AND unit_number = %s
                """,
                (user_id, unit_number),
            )
            due = cur.fetchone()

    return Checkpoint(
        session_id=session_id,
        unit_number=unit_number,
        can_do="",
        item_count=item_count,
        state="done",
        passed=did_pass,
        # **Only on a pass.** Drops are silent.
        score_pct=payload["score_pct"] if did_pass else None,
        retake_due_on=(due[0] if due and not did_pass else None),
    )


__all__ = ["CHECKPOINT_TASK_TYPE", "Checkpoint", "complete", "today"]
