"""Read-only /stats assembly (S18). All queries scoped by user_id."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from core import copy
from core.db import connection
from core.services.errors import resolved_types
from core.services.motivation import (
    ACTIVE_LOOKBACK_DAYS,
    WEEKLY_SUCCESS_DAYS,
    format_active_days_line,
)
from core.services.sessions import (
    count_active_days,
    local_today,
    open_fossil_sweep_for_user,
)
from core.services.streaks import get_streak
from core.services.users import get_user


@dataclass(frozen=True)
class UserStats:
    cefr_level: str
    current_streak: int
    freeze_tokens: int
    active_days: int
    active_line: str
    due_count: int
    resolved_labels: list[str]
    chunk_total: int
    chunk_unexported: int
    chunk_due: int
    book_units: int
    accuracy_30: float | None
    last_level_change: str | None
    sweep_pending: int | None
    sweep_done: int | None


def _user_timezone(user_id: int) -> str:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT timezone FROM users WHERE telegram_user_id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return "Europe/Vilnius"
    return str(row["timezone"] or "Europe/Vilnius")


def _due_count(user_id: int) -> int:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)::int AS n
              FROM errors
             WHERE user_id = %s
               AND resolved = FALSE
               AND next_review <= CURRENT_DATE
            """,
            (user_id,),
        ).fetchone()
    assert row is not None
    return int(row["n"])


def _chunk_counts(user_id: int, *, now: date) -> tuple[int, int, int]:
    # S25: due uses the shared presented-and-due predicate (chunks.py).
    from core.services.chunks import CHUNK_PRESENTED_AND_DUE_SQL

    with connection() as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*)::int AS total,
                   COUNT(*) FILTER (WHERE exported_to_anki = FALSE)::int
                     AS unexported,
                   COUNT(*) FILTER (
                     WHERE {CHUNK_PRESENTED_AND_DUE_SQL}
                   )::int AS due
              FROM chunks
             WHERE user_id = %s
            """,
            (now, user_id),
        ).fetchone()
    assert row is not None
    return int(row["total"]), int(row["unexported"]), int(row["due"])


def _book_unit_count(user_id: int) -> int:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)::int AS n
              FROM book_units
             WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
    assert row is not None
    return int(row["n"])


def _calibration_snapshot(
    user_id: int,
) -> tuple[float | None, str | None]:
    with connection() as conn:
        latest = conn.execute(
            """
            SELECT accuracy_30
              FROM calibration_log
             WHERE user_id = %s
             ORDER BY date DESC
             LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        change = conn.execute(
            """
            SELECT old_level, new_level, date
              FROM calibration_log
             WHERE user_id = %s
               AND old_level IS DISTINCT FROM new_level
             ORDER BY date DESC
             LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    accuracy = (
        float(latest["accuracy_30"])
        if latest is not None and latest["accuracy_30"] is not None
        else None
    )
    last_change: str | None = None
    if change is not None:
        last_change = (
            f"{change['old_level']}→{change['new_level']} "
            f"({change['date']})"
        )
    return accuracy, last_change


def _sweep_counts(user_id: int) -> tuple[int | None, int | None]:
    session = open_fossil_sweep_for_user(user_id)
    if session is None:
        return None, None
    payload = session.payload or {}
    pending = payload.get("pending") or []
    done = payload.get("done") or []
    return len(pending), len(done)


def collect_stats(
    user_id: int,
    *,
    now: datetime,
    include_sweep: bool = False,
) -> UserStats | None:
    """Assemble stats for one user. Returns None if unknown."""
    user = get_user(user_id)
    if user is None:
        return None
    tz = _user_timezone(user_id)
    day = local_today(tz, now)
    start = day - timedelta(days=ACTIVE_LOOKBACK_DAYS - 1)
    active = count_active_days(user_id, start=start, end=day)
    streak = get_streak(user_id)
    due = _due_count(user_id)
    resolved = resolved_types(user_id)
    chunk_total, chunk_unexported, chunk_due = _chunk_counts(user_id, now=day)
    books = _book_unit_count(user_id)
    accuracy, last_change = _calibration_snapshot(user_id)
    sweep_pending: int | None = None
    sweep_done: int | None = None
    if include_sweep:
        sweep_pending, sweep_done = _sweep_counts(user_id)
        if sweep_pending is None:
            sweep_pending, sweep_done = 0, 0
    return UserStats(
        cefr_level=user.cefr_level,
        current_streak=streak.current_streak,
        freeze_tokens=streak.freeze_tokens,
        active_days=active,
        active_line=format_active_days_line(active),
        due_count=due,
        resolved_labels=resolved,
        chunk_total=chunk_total,
        chunk_unexported=chunk_unexported,
        chunk_due=chunk_due,
        book_units=books,
        accuracy_30=accuracy,
        last_level_change=last_change,
        sweep_pending=sweep_pending,
        sweep_done=sweep_done,
    )


def format_stats_message(stats: UserStats, *, include_sweep: bool) -> str:
    """Learner-facing body. Sweep lines only when include_sweep is True."""
    lines = [
        copy.STATS_HEADER,
        copy.STATS_LEVEL.format(level=stats.cefr_level),
        copy.STATS_STREAK.format(
            streak=stats.current_streak, freezes=stats.freeze_tokens
        ),
        copy.STATS_ACTIVE.format(active_line=stats.active_line),
        copy.STATS_DUE.format(n=stats.due_count),
    ]
    if stats.resolved_labels:
        labels = ", ".join(stats.resolved_labels)
        lines.append(copy.STATS_RESOLVED.format(labels=labels))
    else:
        lines.append(copy.STATS_RESOLVED_NONE)
    lines.append(
        copy.STATS_CHUNKS.format(
            total=stats.chunk_total,
            due=stats.chunk_due,
            unexported=stats.chunk_unexported,
        )
    )
    lines.append(copy.STATS_BOOKS.format(n=stats.book_units))
    if stats.accuracy_30 is not None:
        pct = f"{stats.accuracy_30 * 100:.0f}%"
        change = stats.last_level_change or "none"
        lines.append(
            copy.STATS_CALIBRATION.format(accuracy=pct, change=change)
        )
    else:
        lines.append(copy.STATS_CALIBRATION_NONE)
    if include_sweep:
        pending = stats.sweep_pending if stats.sweep_pending is not None else 0
        done = stats.sweep_done if stats.sweep_done is not None else 0
        lines.append(
            copy.STATS_OPERATOR_SWEEP.format(pending=pending, done=done)
        )
    return "\n".join(lines)


# Re-export for tests that assert the weekly target.
WEEKLY_SUCCESS_DAYS_FOR_STATS = WEEKLY_SUCCESS_DAYS
