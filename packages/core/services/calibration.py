"""Difficulty auto-calibration (M14 / S12).

Rolling accuracy is approximated from completed quiz + reading session
aggregates (not a true per-question event stream). ``book_test`` and
Sunday weekly tests (``payload.weekly_test``) are excluded — coverage /
self-selected material must not vote on level. Chunk gap answers are
excluded via ``payload.calib_*`` counters (S7a) — phrase recall is not
difficulty fit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from core import copy
from core.db import connection
from core.services.sessions import (
    increment_bot_messages,
    local_today,
    under_message_ceiling,
)
from core.services.users import update_cefr_level

logger = logging.getLogger(__name__)

MIN_SAMPLE = 30
RAISE_THRESHOLD = 0.85
LOWER_THRESHOLD = 0.70
RAISE_WINDOW_DAYS = 14
RAISE_MIN_LOG_DAYS = 8  # ~5/7 over a fortnight (exact pace ≈10)
COOLDOWN_DAYS = 14
CEFR_LADDER = ("A2", "B1", "B2", "C1")
# Comprehension accuracy only. Shadow (S16) stores ASR-intelligibility on
# sessions.score — never add 'shadow' (or other pronunciation proxies) here.
CALIBRATION_TASK_TYPES = ("quiz", "reading")


@dataclass(frozen=True)
class AccuracyWindow:
    correct: int
    answered: int

    @property
    def sample(self) -> int:
        return self.answered

    @property
    def accuracy(self) -> float | None:
        if self.answered <= 0:
            return None
        return self.correct / self.answered


@dataclass(frozen=True)
class CalibrationOutcome:
    sample: int
    accuracy_30: float | None
    old_level: str | None
    new_level: str | None
    changed: bool
    raise_notice: str | None


def _session_counts(payload: dict[str, Any] | None, score: float | None) -> tuple[int, int]:
    """Return (correct, answered) for one completed session.

    Prefer ``calib_correct`` / ``calib_answered`` when present (S7a — chunk
    phrase-recall excluded from difficulty calibration). Legacy sessions
    without those keys fall back to ``correct_count`` / ``answered`` / score.
    """
    data = payload if isinstance(payload, dict) else {}
    if "calib_answered" in data:
        try:
            n = max(0, int(data.get("calib_answered") or 0))
        except (TypeError, ValueError):
            n = 0
        if n <= 0:
            return 0, 0
        try:
            c = max(0, int(data.get("calib_correct") or 0))
        except (TypeError, ValueError):
            c = 0
        return min(c, n), n

    answered = data.get("answered")
    if answered is None:
        early = data.get("early_limit")
        questions = data.get("questions") or []
        if early is not None:
            try:
                answered = int(early)
            except (TypeError, ValueError):
                answered = len(questions)
        else:
            answered = len(questions)
    try:
        n = max(0, int(answered))
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return 0, 0

    correct = data.get("correct_count")
    if correct is not None:
        try:
            c = max(0, int(correct))
        except (TypeError, ValueError):
            c = 0
        return min(c, n), n

    if score is None:
        return 0, n
    c = int(round(float(score) * n))
    return max(0, min(c, n)), n


def compute_accuracy_window(user_id: int) -> AccuracyWindow:
    """Approximate last ~30 questions from quiz/reading session aggregates."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT score, payload, completed_at, id
              FROM sessions
             WHERE user_id = %s
               AND task_type = ANY(%s)
               AND completed = TRUE
               AND score IS NOT NULL
             ORDER BY completed_at DESC NULLS LAST, id DESC
            """,
            (user_id, list(CALIBRATION_TASK_TYPES)),
        ).fetchall()

    total_c = 0
    total_n = 0
    for row in rows:
        payload = row["payload"]
        if payload is not None and not isinstance(payload, dict):
            payload = dict(payload)
        # S11: weekly test is coverage, not difficulty fit — skip entirely.
        if isinstance(payload, dict) and payload.get("weekly_test"):
            continue
        c, n = _session_counts(payload, row["score"])
        if n <= 0:
            continue
        total_c += c
        total_n += n
        if total_n >= MIN_SAMPLE:
            break
    return AccuracyWindow(correct=total_c, answered=total_n)


def _user_context(
    user_id: int,
) -> tuple[str, str, date | None] | None:
    """Return (cefr_level, timezone, paused_until) or None if unknown/revoked."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT cefr_level, timezone, paused_until
              FROM approved_onboarded_users
             WHERE telegram_user_id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return (
        str(row["cefr_level"]),
        str(row["timezone"] or "Europe/Vilnius"),
        row["paused_until"],
    )


def list_calibration_user_ids() -> list[int]:
    """Approved onboarded ids (same view as _user_context; drift-test contract)."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT telegram_user_id
              FROM approved_onboarded_users
             ORDER BY telegram_user_id
            """
        ).fetchall()
    return [int(r["telegram_user_id"]) for r in rows]


def _is_paused(paused_until: date | None, day: date) -> bool:
    return paused_until is not None and paused_until >= day


def _ladder_index(level: str) -> int | None:
    try:
        return CEFR_LADDER.index(level)
    except ValueError:
        return None


def _raise_level(level: str) -> str | None:
    idx = _ladder_index(level)
    if idx is None or idx >= len(CEFR_LADDER) - 1:
        return None
    return CEFR_LADDER[idx + 1]


def _lower_level(level: str) -> str | None:
    idx = _ladder_index(level)
    if idx is None or idx <= 0:
        return None
    return CEFR_LADDER[idx - 1]


def _last_level_change_date(user_id: int) -> date | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT date
              FROM calibration_log
             WHERE user_id = %s
               AND old_level IS DISTINCT FROM new_level
             ORDER BY date DESC, id DESC
             LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return row["date"]


def _in_cooldown(user_id: int, day: date) -> bool:
    changed_on = _last_level_change_date(user_id)
    if changed_on is None:
        return False
    return day < changed_on + timedelta(days=COOLDOWN_DAYS)


def _logs_in_window(user_id: int, day: date) -> list[dict[str, Any]]:
    start = day - timedelta(days=RAISE_WINDOW_DAYS - 1)
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT date, accuracy_30, old_level, new_level
              FROM calibration_log
             WHERE user_id = %s
               AND date BETWEEN %s AND %s
             ORDER BY date ASC
            """,
            (user_id, start, day),
        ).fetchall()
    return [dict(r) for r in rows]


def _should_raise(
    user_id: int,
    day: date,
    accuracy: float,
) -> bool:
    """Raise when every reading in the 14-day window is >85% and ≥8 exist.

    Today's recomputed accuracy is merged in-memory so we do not need to
    overwrite the log row before deciding (preserves same-day change rows).
    """
    if accuracy <= RAISE_THRESHOLD:
        return False
    logs = _logs_in_window(user_id, day)
    by_date: dict[date, float] = {}
    for r in logs:
        if r["accuracy_30"] is None:
            continue
        by_date[r["date"]] = float(r["accuracy_30"])
    by_date[day] = accuracy
    if len(by_date) < RAISE_MIN_LOG_DAYS:
        return False
    return all(a > RAISE_THRESHOLD for a in by_date.values())


def _upsert_calibration_log(
    user_id: int,
    day: date,
    *,
    accuracy_30: float,
    old_level: str,
    new_level: str,
) -> None:
    with connection() as conn:
        with conn.transaction():
            existing = conn.execute(
                """
                SELECT id, old_level, new_level FROM calibration_log
                 WHERE user_id = %s AND date = %s
                 ORDER BY id DESC
                 LIMIT 1
                 FOR UPDATE
                """,
                (user_id, day),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO calibration_log (
                        user_id, date, accuracy_30, old_level, new_level
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (user_id, day, accuracy_30, old_level, new_level),
                )
                return

            # Keep a level-change already recorded today; only refresh accuracy
            # (a later same-day completion must not erase the audit row).
            write_old = old_level
            write_new = new_level
            prev_old = existing["old_level"]
            prev_new = existing["new_level"]
            if prev_old is not None and prev_new is not None and prev_old != prev_new:
                write_old = str(prev_old)
                write_new = str(prev_new)
            conn.execute(
                """
                UPDATE calibration_log
                   SET accuracy_30 = %s,
                       old_level = %s,
                       new_level = %s
                 WHERE id = %s
                """,
                (accuracy_30, write_old, write_new, int(existing["id"])),
            )


def maybe_calibrate(user_id: int, *, now: datetime) -> CalibrationOutcome:
    """Recompute accuracy, upsert today's log when sample is enough, maybe change level.

    Never announces a drop. On raise, ``raise_notice`` is set for the caller
    to deliver (subject to the bot-message ceiling).
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    ctx = _user_context(user_id)
    if ctx is None:
        return CalibrationOutcome(0, None, None, None, False, None)
    level, tz, paused_until = ctx
    day = local_today(tz, now)
    if _is_paused(paused_until, day):
        return CalibrationOutcome(0, None, level, level, False, None)

    window = compute_accuracy_window(user_id)
    if window.sample < MIN_SAMPLE or window.accuracy is None:
        return CalibrationOutcome(
            window.sample, window.accuracy, level, level, False, None
        )

    accuracy = window.accuracy
    new_level = level
    raise_notice: str | None = None
    if not _in_cooldown(user_id, day):
        if _should_raise(user_id, day, accuracy):
            raised = _raise_level(level)
            if raised is not None:
                new_level = raised
                raise_notice = copy.LEVEL_RAISE.format(level=new_level)
        elif accuracy < LOWER_THRESHOLD:
            lowered = _lower_level(level)
            if lowered is not None:
                new_level = lowered

    changed = new_level != level
    if changed:
        update_cefr_level(user_id, new_level)
        if raise_notice is None:
            # Drop: silent by design (PRD §7 rule 4).
            logger.info(
                "cefr_level lowered user_id=%s %s -> %s accuracy=%.3f",
                user_id,
                level,
                new_level,
                accuracy,
            )
        else:
            logger.info(
                "cefr_level raised user_id=%s %s -> %s accuracy=%.3f",
                user_id,
                level,
                new_level,
                accuracy,
            )

    # Single upsert: refreshes accuracy; records change when it fired.
    _upsert_calibration_log(
        user_id,
        day,
        accuracy_30=accuracy,
        old_level=level,
        new_level=new_level,
    )

    return CalibrationOutcome(
        sample=window.sample,
        accuracy_30=accuracy,
        old_level=level,
        new_level=new_level,
        changed=changed,
        raise_notice=raise_notice if changed else None,
    )


async def deliver_raise_notice(
    bot: Any,
    user_id: int,
    *,
    day: date,
    notice: str,
) -> bool:
    """Send a level-raise message if under the daily ceiling. Returns True if sent."""
    if not under_message_ceiling(user_id, day):
        logger.warning(
            "level raise notice skipped (ceiling) user_id=%s day=%s",
            user_id,
            day,
        )
        return False
    await bot.send_message(chat_id=user_id, text=notice)
    increment_bot_messages(user_id, day)
    return True


def s12_user_facing_strings() -> list[str]:
    """Every S12 user-facing string for no-guilt assertions."""
    return [
        copy.LEVEL_RAISE.format(level="B2"),
    ]
