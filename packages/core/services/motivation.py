"""Nudge ladder and Sunday progress report (S10 / M7).

Channel-neutral. Delivery — the sends, the passes over all users — lives in
``apps/bot/motivation_delivery.py`` until the worker takes it at W20.

No LLM — copy is assembled from database facts and copy.py templates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from zoneinfo import ZoneInfo

from core import copy
from core.db import connection
from core.services.activity import practised_on
from core.services.errors import resolved_types
from core.services.sessions import (
    MAX_NUDGES_PER_DAY,
    MAX_NUDGES_PER_SESSION,
    NudgeableSession,
    count_active_days,
    daily_nudges_sent,
    has_sunday_report_session_on,
    list_open_nudgeable_sessions,
    local_time_hhmm,
    local_today,
    under_message_ceiling,
)

logger = logging.getLogger(__name__)

NUDGE_FIRST_HOURS = 3
NUDGE_SECOND_HOURS = 6
EARLY_LIMIT = 2
SUNDAY_WEEKDAY = 6
WEEKLY_SUCCESS_DAYS = 5
ACTIVE_LOOKBACK_DAYS = 7


@dataclass(frozen=True)
class MotivationUser:
    id: int
    telegram_address: int | None
    timezone: str
    evening_time: time
    paused_until: date | None
    why_statement: str | None


def _time_reached(local_hhmm: tuple[int, int], slot: time) -> bool:
    hour, minute = local_hhmm
    return (hour, minute) >= (slot.hour, slot.minute)


def task_still_open(session_date: date, timezone_name: str, now: datetime) -> bool:
    """True until 03:00 local on the calendar day after session_date."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    tz = ZoneInfo(timezone_name)
    close_at = datetime(
        session_date.year,
        session_date.month,
        session_date.day,
        3,
        0,
        tzinfo=tz,
    ) + timedelta(days=1)
    return now.astimezone(tz) < close_at


def next_nudge_due_at(session: NudgeableSession) -> datetime | None:
    """Instant when the next nudge may fire, or None if ladder exhausted."""
    if session.nudges_sent >= MAX_NUDGES_PER_SESSION:
        return None
    hours = NUDGE_FIRST_HOURS if session.nudges_sent == 0 else NUDGE_SECOND_HOURS
    return session.delivered_at + timedelta(hours=hours)


def list_motivation_users() -> list[MotivationUser]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, telegram_user_id, timezone, evening_time, paused_until,
                   why_statement
              FROM approved_onboarded_users
            """
        ).fetchall()
    return [
        MotivationUser(
            id=int(r["id"]),
            telegram_address=(
                None if r["telegram_user_id"] is None else int(r["telegram_user_id"])
            ),
            timezone=str(r["timezone"] or "Europe/Vilnius"),
            evening_time=r["evening_time"] or time(21, 0),
            paused_until=r["paused_until"],
            why_statement=r["why_statement"],
        )
        for r in rows
    ]


def is_user_paused(user: MotivationUser, now: datetime) -> bool:
    day = local_today(user.timezone, now)
    return user.paused_until is not None and user.paused_until >= day


def sessions_due_for_nudge(
    user: MotivationUser,
    now: datetime,
) -> list[NudgeableSession]:
    """Open nudgeable sessions ready for the next ladder step at ``now``."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if is_user_paused(user, now):
        return []

    due: list[NudgeableSession] = []
    for session in list_open_nudgeable_sessions(user.id):
        if not task_still_open(session.date, user.timezone, now):
            continue
        # **#259 (W19): a learner who practised on the session's day is never
        # nudged to practise that day** — an open v2 quiz beside a finished web
        # session was enough to nudge before. The signal is the logs'
        # (`core.services.activity`), the same one the streak reads.
        with connection() as conn:
            if practised_on(conn, user.id, session.date):
                continue
        # Daily budget keys off the session's delivery local date (PRD: max 2
        # nudges per day) so Monday's quiz nudges count on Monday even before
        # Tuesday 03:00 close.
        if daily_nudges_sent(user.id, session.date) >= MAX_NUDGES_PER_DAY:
            continue
        due_at = next_nudge_due_at(session)
        if due_at is None:
            continue
        if now < due_at:
            continue
        due.append(session)
    return due


def nudge_action(session_id: int) -> dict[str, object]:
    """The one action a nudge may offer, as channel-neutral data.

    ``apps/bot`` renders this as an inline keyboard; the web client renders it
    as a button. The core service names the action, never the widget.
    """
    return {"action": "short_session", "session_id": session_id}


def format_nudge_message(
    session: NudgeableSession,
) -> tuple[str, dict[str, object] | None]:
    """Return (body, optional action). Second quiz/reading nudge offers Just do 2.

    Diary nudges are text-only — no early_limit action (S13).
    """
    if session.nudges_sent == 0:
        if session.task_type == "reading":
            return copy.NUDGE_FIRST_READING, None
        if session.task_type == "diary":
            return copy.NUDGE_FIRST_DIARY, None
        return copy.NUDGE_FIRST_QUIZ, None
    # Second (and only second) nudge.
    if session.task_type == "diary":
        return copy.NUDGE_SECOND_DIARY, None
    if session.task_type == "reading":
        body = copy.NUDGE_SECOND_READING
    else:
        body = copy.NUDGE_SECOND_QUIZ
    return body, nudge_action(session.id)


def format_active_days_line(active_days: int) -> str:
    """Weekly success copy. Never use denominator 7; never N/5 for N>5."""
    if active_days >= WEEKLY_SUCCESS_DAYS:
        return copy.SUNDAY_ACTIVE_FULL.format(n=active_days)
    return copy.SUNDAY_ACTIVE_SHORT.format(
        n=active_days, target=WEEKLY_SUCCESS_DAYS
    )


def assemble_sunday_report(
    user_id: int,
    *,
    local_day: date,
    why_statement: str | None,
) -> str:
    """Deterministic Sunday report body (no LLM)."""
    newly = resolved_types(user_id, since_days=ACTIVE_LOOKBACK_DAYS)
    if newly:
        lead = copy.SUNDAY_LEAD_QUIET.format(labels=_join_labels(newly))
    else:
        all_quiet = resolved_types(user_id, since_days=None)
        if all_quiet:
            lead = copy.SUNDAY_LEAD_QUIET.format(labels=_join_labels(all_quiet))
        else:
            lead = copy.SUNDAY_LEAD_KEEPING

    start = local_day - timedelta(days=ACTIVE_LOOKBACK_DAYS - 1)
    active = count_active_days(user_id, start=start, end=local_day)
    active_line = format_active_days_line(active)

    parts = [lead, active_line]
    if active < WEEKLY_SUCCESS_DAYS:
        parts.append(copy.SUNDAY_SHORTFALL)

    body = "\n".join(parts)
    if why_statement:
        why_line = copy.SUNDAY_WHY.format(why=why_statement.strip())
        candidate = f"{body}\n{why_line}"
        if len(candidate) <= 400:
            body = candidate
    return body


def _join_labels(labels: list[str]) -> str:
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def is_user_due_for_sunday_report(user: MotivationUser, now: datetime) -> bool:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    day = local_today(user.timezone, now)
    local_dt = now.astimezone(ZoneInfo(user.timezone))
    if local_dt.weekday() != SUNDAY_WEEKDAY:
        return False
    if is_user_paused(user, now):
        return False
    if not _time_reached(local_time_hhmm(user.timezone, now), user.evening_time):
        return False
    if has_sunday_report_session_on(user.id, day):
        return False
    if not under_message_ceiling(user.id, day):
        return False
    return True


def s10_button_labels() -> list[str]:
    """All S10 button labels for the ≤20-char audit."""
    return [copy.BTN_NUDGE_JUST_2]


def s10_user_facing_strings() -> list[str]:
    """Every nudge/report template for no-guilt checks."""
    samples = [
        copy.NUDGE_FIRST_QUIZ,
        copy.NUDGE_FIRST_READING,
        copy.NUDGE_FIRST_DIARY,
        copy.NUDGE_SECOND_QUIZ,
        copy.NUDGE_SECOND_READING,
        copy.NUDGE_SECOND_DIARY,
        copy.NUDGE_SHORT_ACK,
        copy.NUDGE_SHORT_DONE,
        copy.SUNDAY_LEAD_QUIET.format(labels="Prepositions"),
        copy.SUNDAY_LEAD_KEEPING,
        copy.SUNDAY_ACTIVE_FULL.format(n=5),
        copy.SUNDAY_ACTIVE_FULL.format(n=7),
        copy.SUNDAY_ACTIVE_SHORT.format(n=4, target=5),
        copy.SUNDAY_SHORTFALL,
        copy.SUNDAY_WHY.format(why="Speak in meetings"),
        copy.BTN_NUDGE_JUST_2,
    ]
    return samples
