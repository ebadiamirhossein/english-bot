"""Nudge ladder and Sunday progress report (S10 / M7).

No LLM — copy is assembled from database facts and texts.py templates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app import texts
from app.db import connection
from app.services.errors import resolved_types
from app.services.sessions import (
    MAX_NUDGES_PER_DAY,
    MAX_NUDGES_PER_SESSION,
    NudgeableSession,
    claim_sunday_report_session,
    count_active_days,
    daily_nudges_sent,
    has_sunday_report_session_on,
    increment_bot_messages,
    increment_nudges_sent,
    list_open_nudgeable_sessions,
    local_time_hhmm,
    local_today,
    under_message_ceiling,
)

if TYPE_CHECKING:
    from telegram.ext import Application

logger = logging.getLogger(__name__)

NUDGE_FIRST_HOURS = 3
NUDGE_SECOND_HOURS = 6
EARLY_LIMIT = 2
SUNDAY_WEEKDAY = 6
WEEKLY_SUCCESS_DAYS = 5
ACTIVE_LOOKBACK_DAYS = 7


@dataclass(frozen=True)
class MotivationUser:
    telegram_user_id: int
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
            SELECT telegram_user_id, timezone, evening_time, paused_until,
                   why_statement
              FROM users
             WHERE onboarded = TRUE
            """
        ).fetchall()
    return [
        MotivationUser(
            telegram_user_id=int(r["telegram_user_id"]),
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
    for session in list_open_nudgeable_sessions(user.telegram_user_id):
        if not task_still_open(session.date, user.timezone, now):
            continue
        # Daily budget keys off the session's delivery local date (PRD: max 2
        # nudges per day) so Monday's quiz nudges count on Monday even before
        # Tuesday 03:00 close.
        if daily_nudges_sent(user.telegram_user_id, session.date) >= MAX_NUDGES_PER_DAY:
            continue
        due_at = next_nudge_due_at(session)
        if due_at is None:
            continue
        if now < due_at:
            continue
        due.append(session)
    return due


def nudge_keyboard(session_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    texts.BTN_NUDGE_JUST_2,
                    callback_data=f"nudge:short:{session_id}",
                )
            ]
        ]
    )


def format_nudge_message(session: NudgeableSession) -> tuple[str, InlineKeyboardMarkup | None]:
    """Return (body, optional keyboard). Second quiz/reading nudge offers Just do 2.

    Diary nudges are text-only — no early_limit button (S13).
    """
    if session.nudges_sent == 0:
        if session.task_type == "reading":
            return texts.NUDGE_FIRST_READING, None
        if session.task_type == "diary":
            return texts.NUDGE_FIRST_DIARY, None
        return texts.NUDGE_FIRST_QUIZ, None
    # Second (and only second) nudge.
    if session.task_type == "diary":
        return texts.NUDGE_SECOND_DIARY, None
    if session.task_type == "reading":
        body = texts.NUDGE_SECOND_READING
    else:
        body = texts.NUDGE_SECOND_QUIZ
    return body, nudge_keyboard(session.id)


async def send_nudge(
    app: Application,
    user: MotivationUser,
    session: NudgeableSession,
    *,
    now: datetime,
) -> str:
    """Send one nudge if ceiling allows. Returns action string."""
    day = local_today(user.timezone, now)
    if not under_message_ceiling(user.telegram_user_id, day):
        logger.warning(
            "Nudge suppressed user_id=%s session_id=%s reason=message_ceiling",
            user.telegram_user_id,
            session.id,
        )
        return "skipped_ceiling"

    # Re-check ladder + daily budget under the same now (idempotent poll).
    if session.nudges_sent >= MAX_NUDGES_PER_SESSION:
        return "skipped_ladder"
    if daily_nudges_sent(user.telegram_user_id, session.date) >= MAX_NUDGES_PER_DAY:
        return "skipped_daily_cap"
    due_at = next_nudge_due_at(session)
    if due_at is None or now < due_at:
        return "skipped_not_due"
    if not task_still_open(session.date, user.timezone, now):
        return "skipped_closed"

    body, keyboard = format_nudge_message(session)
    await app.bot.send_message(
        chat_id=user.telegram_user_id,
        text=body,
        reply_markup=keyboard,
    )
    increment_bot_messages(user.telegram_user_id, day)
    increment_nudges_sent(user.telegram_user_id, session.id)
    which = "first" if session.nudges_sent == 0 else "second"
    logger.info(
        "Nudge sent user_id=%s session_id=%s which=%s",
        user.telegram_user_id,
        session.id,
        which,
    )
    return f"sent_{which}"


async def deliver_nudges_for_user(
    app: Application,
    user: MotivationUser,
    *,
    now: datetime,
) -> list[str]:
    """Send at most the remaining daily budget for one user."""
    actions: list[str] = []
    # Refresh sessions after each send so nudges_sent / daily sum stay current.
    while True:
        due = sessions_due_for_nudge(user, now)
        if not due:
            break
        # One send per loop; oldest first (list already ordered).
        action = await send_nudge(app, user, due[0], now=now)
        actions.append(action)
        if not action.startswith("sent_"):
            break
        # Stop after one successful send per poll tick per user — next tick
        # can send the second if +6h already elapsed. Avoids double-send in
        # one tick when both +3h and +6h windows somehow overlap incorrectly.
        # Actually: if first was delayed and now both +3 and +6 are past with
        # nudges_sent=0, one tick should only send the first; the second waits
        # until nudges_sent=1 and +6h (already true) on the *next* tick — or
        # we allow two in one tick if daily budget remains?
        # Plan: max 2/day; if somehow both due, oldest session first nudge,
        # then if same session needs second and +6h met, could send both in
        # one day across ticks. Within one tick: send one to stay simple and
        # keep poll-twice idempotent tests clear.
        break
    return actions


async def run_nudge_pass(
    app: Application,
    *,
    now: datetime,
) -> list[tuple[int, list[str]]]:
    results: list[tuple[int, list[str]]] = []
    for user in list_motivation_users():
        try:
            actions = await deliver_nudges_for_user(app, user, now=now)
            if actions:
                results.append((user.telegram_user_id, actions))
        except Exception:
            logger.exception(
                "Nudge pass failed user_id=%s", user.telegram_user_id
            )
            results.append((user.telegram_user_id, ["error"]))
    return results


def format_active_days_line(active_days: int) -> str:
    """Weekly success copy. Never use denominator 7; never N/5 for N>5."""
    if active_days >= WEEKLY_SUCCESS_DAYS:
        return texts.SUNDAY_ACTIVE_FULL.format(n=active_days)
    return texts.SUNDAY_ACTIVE_SHORT.format(
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
        lead = texts.SUNDAY_LEAD_QUIET.format(labels=_join_labels(newly))
    else:
        all_quiet = resolved_types(user_id, since_days=None)
        if all_quiet:
            lead = texts.SUNDAY_LEAD_QUIET.format(labels=_join_labels(all_quiet))
        else:
            lead = texts.SUNDAY_LEAD_KEEPING

    start = local_day - timedelta(days=ACTIVE_LOOKBACK_DAYS - 1)
    active = count_active_days(user_id, start=start, end=local_day)
    active_line = format_active_days_line(active)

    parts = [lead, active_line]
    if active < WEEKLY_SUCCESS_DAYS:
        parts.append(texts.SUNDAY_SHORTFALL)

    body = "\n".join(parts)
    if why_statement:
        why_line = texts.SUNDAY_WHY.format(why=why_statement.strip())
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
    if has_sunday_report_session_on(user.telegram_user_id, day):
        return False
    if not under_message_ceiling(user.telegram_user_id, day):
        return False
    return True


async def deliver_sunday_report(
    app: Application,
    user: MotivationUser,
    *,
    now: datetime,
) -> str:
    """Send one Sunday report if due. Returns action string."""
    if not is_user_due_for_sunday_report(user, now):
        day = local_today(user.timezone, now)
        if not under_message_ceiling(user.telegram_user_id, day):
            logger.warning(
                "Sunday report suppressed user_id=%s reason=message_ceiling",
                user.telegram_user_id,
            )
            return "skipped_ceiling"
        return "skipped"

    day = local_today(user.timezone, now)
    # Re-check marker + ceiling immediately before send.
    if has_sunday_report_session_on(user.telegram_user_id, day):
        return "skipped_idempotent"
    if not under_message_ceiling(user.telegram_user_id, day):
        logger.warning(
            "Sunday report suppressed user_id=%s reason=message_ceiling",
            user.telegram_user_id,
        )
        return "skipped_ceiling"

    body = assemble_sunday_report(
        user.telegram_user_id,
        local_day=day,
        why_statement=user.why_statement,
    )
    await app.bot.send_message(chat_id=user.telegram_user_id, text=body)
    increment_bot_messages(user.telegram_user_id, day)
    claim_sunday_report_session(
        user.telegram_user_id,
        day,
        payload={"chars": len(body)},
    )
    logger.info("Sunday report sent user_id=%s", user.telegram_user_id)
    return "sent"


async def run_sunday_report_pass(
    app: Application,
    *,
    now: datetime,
) -> list[tuple[int, str]]:
    results: list[tuple[int, str]] = []
    for user in list_motivation_users():
        try:
            if not is_user_due_for_sunday_report(user, now):
                continue
            action = await deliver_sunday_report(app, user, now=now)
            results.append((user.telegram_user_id, action))
        except Exception:
            logger.exception(
                "Sunday report failed user_id=%s", user.telegram_user_id
            )
            results.append((user.telegram_user_id, "error"))
    return results


def s10_button_labels() -> list[str]:
    """All S10 button labels for the ≤20-char audit."""
    return [texts.BTN_NUDGE_JUST_2]


def s10_user_facing_strings() -> list[str]:
    """Every nudge/report template for no-guilt checks."""
    samples = [
        texts.NUDGE_FIRST_QUIZ,
        texts.NUDGE_FIRST_READING,
        texts.NUDGE_FIRST_DIARY,
        texts.NUDGE_SECOND_QUIZ,
        texts.NUDGE_SECOND_READING,
        texts.NUDGE_SECOND_DIARY,
        texts.NUDGE_SHORT_ACK,
        texts.NUDGE_SHORT_DONE,
        texts.SUNDAY_LEAD_QUIET.format(labels="Prepositions"),
        texts.SUNDAY_LEAD_KEEPING,
        texts.SUNDAY_ACTIVE_FULL.format(n=5),
        texts.SUNDAY_ACTIVE_FULL.format(n=7),
        texts.SUNDAY_ACTIVE_SHORT.format(n=4, target=5),
        texts.SUNDAY_SHORTFALL,
        texts.SUNDAY_WHY.format(why="Speak in meetings"),
        texts.BTN_NUDGE_JUST_2,
    ]
    return samples
