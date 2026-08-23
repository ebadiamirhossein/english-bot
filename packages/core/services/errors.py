"""Error journal writes and spacing ladder.

S2: record_errors. S3: due_errors / mark_result / spacing.
S10: resolved_types / top_error_types (type-level aggregation).
S11: weekly-test selection + Murphy unit lookup.
S12: M13 fossil-sweep candidate selection (monthly retest queue).
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.db import connection
from app.services.sessions import (
    create_fossil_sweep_session,
    get_fossil_sweep_session,
    local_today,
)

logger = logging.getLogger(__name__)

FOSSIL_SWEEP_LIMIT = 2
FOSSIL_MIN_AGE_DAYS = 30

# streak_right is the ladder index after a correct answer (and at insert = 0).
SPACING_DAYS: dict[int, int] = {
    0: 1,
    1: 3,
    2: 7,
    3: 21,
    4: 60,
}


@dataclass(frozen=True)
class SpacingStep:
    """Pure ladder outcome — shared by errors and chunks (S7a)."""

    streak_right: int
    next_review: date
    times_right_delta: int
    times_wrong_delta: int


def spacing_step(
    *,
    correct: bool,
    streak_right: int,
    today: date,
) -> SpacingStep:
    """Advance or reset the 1→3→7→21→60 ladder. No resolve logic."""
    if correct:
        new_streak = int(streak_right) + 1
        interval = SPACING_DAYS[min(new_streak, 4)]
        return SpacingStep(
            streak_right=new_streak,
            next_review=today + timedelta(days=interval),
            times_right_delta=1,
            times_wrong_delta=0,
        )
    return SpacingStep(
        streak_right=0,
        next_review=today + timedelta(days=1),
        times_right_delta=0,
        times_wrong_delta=1,
    )


@dataclass(frozen=True)
class Error:
    id: int
    user_id: int
    you_said: str
    correct_form: str
    error_type: str
    explanation: str | None
    streak_right: int
    times_right: int
    times_wrong: int
    next_review: date
    resolved: bool
    resolved_at: date | None
    unresolved_count: int
    created_at: datetime


def record_errors(user_id: int, source: str, corrections: list[dict]) -> int:
    """Insert one errors row per correction. Returns the number of rows written.

    All corrections from one message share a single transaction. Unknown
    error_type values are dropped with a warning — they do not fail the batch.
    """
    if not corrections:
        return 0

    written = 0
    with connection() as conn:
        with conn.transaction():
            type_rows = conn.execute(
                "SELECT code, murphy_units FROM error_types"
            ).fetchall()
            murphy_by_code = {
                row["code"]: row["murphy_units"] for row in type_rows
            }
            valid_codes = frozenset(murphy_by_code)

            for item in corrections:
                error_type = item.get("error_type")
                if error_type not in valid_codes:
                    logger.warning(
                        "Dropping correction with unknown error_type=%r "
                        "user_id=%s",
                        error_type,
                        user_id,
                    )
                    continue
                conn.execute(
                    """
                    INSERT INTO errors (
                        user_id,
                        source,
                        you_said,
                        correct_form,
                        error_type,
                        explanation,
                        murphy_units,
                        next_review
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        CURRENT_DATE + 1
                    )
                    """,
                    (
                        user_id,
                        source,
                        item["you_said"],
                        item["correct_form"],
                        error_type,
                        item.get("explanation"),
                        murphy_by_code[error_type],
                    ),
                )
                written += 1
    return written


def due_errors(user_id: int, limit: int = 5) -> list[Error]:
    """Unresolved errors due for review, oldest next_review first."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, you_said, correct_form, error_type, explanation,
                   streak_right, times_right, times_wrong, next_review,
                   resolved, resolved_at, unresolved_count, created_at
              FROM errors
             WHERE user_id = %s
               AND resolved = FALSE
               AND next_review <= CURRENT_DATE
             ORDER BY next_review ASC, id ASC
             LIMIT %s
            """,
            (user_id, limit),
        ).fetchall()
    return [_row_to_error(row) for row in rows]


def select_weekly_test_errors(user_id: int, limit: int = 15) -> list[Error]:
    """Spread unresolved errors across distinct types for the Sunday test.

    Not limited to the due queue — coverage is the point. Within each type,
    due items come first, then oldest ``next_review``. Round-robin across
    types before repeating one.
    """
    if limit < 1:
        return []
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, you_said, correct_form, error_type, explanation,
                   streak_right, times_right, times_wrong, next_review,
                   resolved, resolved_at, unresolved_count, created_at
              FROM errors
             WHERE user_id = %s
               AND resolved = FALSE
             ORDER BY (next_review <= CURRENT_DATE) DESC,
                      next_review ASC,
                      id ASC
            """,
            (user_id,),
        ).fetchall()
    groups: OrderedDict[str, list[Error]] = OrderedDict()
    for row in rows:
        err = _row_to_error(row)
        groups.setdefault(err.error_type, []).append(err)
    selected: list[Error] = []
    round_idx = 0
    while len(selected) < limit:
        added = False
        for items in groups.values():
            if round_idx < len(items):
                selected.append(items[round_idx])
                added = True
                if len(selected) >= limit:
                    break
        if not added:
            break
        round_idx += 1
    return selected


_MURPHY_RANGE_RE = re.compile(
    r"^\s*(\d+)\s*(?:-\s*(\d+))?\s*$"
)


def expand_murphy_units(spec: str | None) -> set[str]:
    """Expand ``'69-81'`` / ``'5-6,11-14'`` into unit-number strings."""
    if not spec or not str(spec).strip():
        return set()
    out: set[str] = set()
    for part in str(spec).split(","):
        m = _MURPHY_RANGE_RE.match(part)
        if m is None:
            token = part.strip()
            if token:
                out.add(token)
            continue
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) is not None else start
        if end < start:
            start, end = end, start
        for n in range(start, end + 1):
            out.add(str(n))
    return out


def murphy_units_for_labels(labels: list[str]) -> list[tuple[str, str]]:
    """Map labels → non-NULL murphy_units specs, preserving label order."""
    if not labels:
        return []
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT label, murphy_units
              FROM error_types
             WHERE label = ANY(%s)
               AND murphy_units IS NOT NULL
            """,
            (list(labels),),
        ).fetchall()
    by_label = {
        str(r["label"]): str(r["murphy_units"])
        for r in rows
        if r["murphy_units"]
    }
    return [(lab, by_label[lab]) for lab in labels if lab in by_label]


def get_error_for_user(user_id: int, error_id: int) -> Error | None:
    """Load one error row scoped by user_id."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, you_said, correct_form, error_type, explanation,
                   streak_right, times_right, times_wrong, next_review,
                   resolved, resolved_at, unresolved_count, created_at
              FROM errors
             WHERE id = %s AND user_id = %s
            """,
            (error_id, user_id),
        ).fetchone()
    if row is None:
        return None
    return _row_to_error(row)


def pick_fossil_retest_ids(
    user_id: int,
    *,
    as_of: date,
    limit: int = FOSSIL_SWEEP_LIMIT,
    exclude_ids: frozenset[int] | None = None,
) -> list[int]:
    """Choose aged resolved rows for the monthly silent retest.

    Prefer types that are currently all-clear (every row resolved), then
    oldest ``resolved_at``, then id. Does not mutate ``resolved_at``.
    """
    if limit < 1:
        return []
    exclude = exclude_ids or frozenset()
    cutoff = as_of - timedelta(days=FOSSIL_MIN_AGE_DAYS)
    with connection() as conn:
        rows = conn.execute(
            """
            WITH type_clear AS (
                SELECT error_type
                  FROM errors
                 WHERE user_id = %s
                 GROUP BY error_type
                HAVING BOOL_AND(resolved) AND COUNT(*) >= 1
            )
            SELECT e.id
              FROM errors e
              LEFT JOIN type_clear tc ON tc.error_type = e.error_type
             WHERE e.user_id = %s
               AND e.resolved = TRUE
               AND e.resolved_at IS NOT NULL
               AND e.resolved_at <= %s
             ORDER BY (tc.error_type IS NOT NULL) DESC,
                      e.resolved_at ASC,
                      e.id ASC
            """,
            (user_id, user_id, cutoff),
        ).fetchall()
    picked: list[int] = []
    for row in rows:
        eid = int(row["id"])
        if eid in exclude:
            continue
        picked.append(eid)
        if len(picked) >= limit:
            break
    return picked


def list_fossil_sweep_user_ids() -> list[int]:
    """Approved onboarded user ids (drift-test + fossil sweep source)."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT telegram_user_id
              FROM approved_onboarded_users
             ORDER BY telegram_user_id
            """
        ).fetchall()
    return [int(r["telegram_user_id"]) for r in rows]


def run_monthly_fossil_sweep(*, now: datetime) -> int:
    """Queue up to FOSSIL_SWEEP_LIMIT retests per user on their local 1st.

    Idempotent via an existing fossil_sweep session for that month-start.
    Skips paused users. Returns how many queues were created.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    with connection() as conn:
        rows = conn.execute(
            """
            SELECT telegram_user_id, timezone, paused_until
              FROM approved_onboarded_users
            """
        ).fetchall()

    created = 0
    for row in rows:
        user_id = int(row["telegram_user_id"])
        tz = str(row["timezone"] or "Europe/Vilnius")
        local_day = local_today(tz, now)
        if local_day.day != 1:
            continue
        paused_until = row["paused_until"]
        if paused_until is not None and paused_until >= local_day:
            continue
        month_start = local_day.replace(day=1)
        if get_fossil_sweep_session(user_id, month_start) is not None:
            continue
        pending = pick_fossil_retest_ids(user_id, as_of=local_day)
        create_fossil_sweep_session(user_id, month_start, pending=pending)
        created += 1
        logger.info(
            "fossil_sweep queued user_id=%s month=%s pending=%s",
            user_id,
            month_start,
            pending,
        )
    return created


def mark_result(error_id: int, correct: bool) -> None:
    """Apply one review result and advance or reset the spacing ladder."""
    with connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """
                SELECT id, streak_right, resolved, created_at
                  FROM errors
                 WHERE id = %s
                 FOR UPDATE
                """,
                (error_id,),
            ).fetchone()
            if row is None:
                logger.warning("mark_result: unknown error_id=%s", error_id)
                return

            today = conn.execute("SELECT CURRENT_DATE AS d").fetchone()["d"]
            step = spacing_step(
                correct=correct,
                streak_right=int(row["streak_right"]),
                today=today,
            )

            if correct:
                age_days = conn.execute(
                    """
                    SELECT (CURRENT_DATE - created_at::date) AS age
                      FROM errors
                     WHERE id = %s
                    """,
                    (error_id,),
                ).fetchone()["age"]
                if step.streak_right >= 5 and int(age_days) >= 21:
                    conn.execute(
                        """
                        UPDATE errors
                           SET streak_right = %s,
                               times_right = times_right + 1,
                               resolved = TRUE,
                               resolved_at = CURRENT_DATE
                         WHERE id = %s
                        """,
                        (step.streak_right, error_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE errors
                           SET streak_right = %s,
                               times_right = times_right + 1,
                               next_review = %s
                         WHERE id = %s
                        """,
                        (step.streak_right, step.next_review, error_id),
                    )
            else:
                if row["resolved"]:
                    conn.execute(
                        """
                        UPDATE errors
                           SET streak_right = %s,
                               times_wrong = times_wrong + 1,
                               next_review = %s,
                               resolved = FALSE,
                               resolved_at = NULL,
                               unresolved_count = unresolved_count + 1
                         WHERE id = %s
                        """,
                        (step.streak_right, step.next_review, error_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE errors
                           SET streak_right = %s,
                               times_wrong = times_wrong + 1,
                               next_review = %s
                         WHERE id = %s
                        """,
                        (step.streak_right, step.next_review, error_id),
                    )


def resolved_types(user_id: int, since_days: int | None = None) -> list[str]:
    """Labels of error types that are fully quiet for this user.

    A type counts as resolved only when every row of that type is resolved
    (at least one row, zero unresolved). Optional ``since_days`` keeps types
    whose latest ``resolved_at`` falls within that many local calendar days
    ending on CURRENT_DATE.
    """
    with connection() as conn:
        if since_days is None:
            rows = conn.execute(
                """
                SELECT et.label
                  FROM errors e
                  JOIN error_types et ON et.code = e.error_type
                 WHERE e.user_id = %s
                 GROUP BY e.error_type, et.label
                HAVING BOOL_AND(e.resolved)
                   AND COUNT(*) >= 1
                 ORDER BY et.label
                """,
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT et.label
                  FROM errors e
                  JOIN error_types et ON et.code = e.error_type
                 WHERE e.user_id = %s
                 GROUP BY e.error_type, et.label
                HAVING BOOL_AND(e.resolved)
                   AND COUNT(*) >= 1
                   AND MAX(e.resolved_at) >= CURRENT_DATE - %s::integer
                 ORDER BY MAX(e.resolved_at) DESC NULLS LAST, et.label
                """,
                (user_id, since_days),
            ).fetchall()
    return [str(r["label"]) for r in rows]


def top_error_types(user_id: int, n: int = 5) -> list[str]:
    """Labels of the user's noisiest unresolved error types."""
    if n < 1:
        return []
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT et.label
              FROM errors e
              JOIN error_types et ON et.code = e.error_type
             WHERE e.user_id = %s
               AND e.resolved = FALSE
             GROUP BY e.error_type, et.label
             ORDER BY COUNT(*) DESC, SUM(e.times_wrong) DESC, et.label
             LIMIT %s
            """,
            (user_id, n),
        ).fetchall()
    return [str(r["label"]) for r in rows]


def _row_to_error(row: dict) -> Error:
    return Error(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        you_said=row["you_said"],
        correct_form=row["correct_form"],
        error_type=row["error_type"],
        explanation=row["explanation"],
        streak_right=int(row["streak_right"]),
        times_right=int(row["times_right"]),
        times_wrong=int(row["times_wrong"]),
        next_review=row["next_review"],
        resolved=bool(row["resolved"]),
        resolved_at=row["resolved_at"],
        unresolved_count=int(row["unresolved_count"]),
        created_at=row["created_at"],
    )
