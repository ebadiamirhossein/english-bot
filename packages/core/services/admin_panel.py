"""Operator admin panel assembly (S18d).

Activity and state only — never error text, diary corrections, chunks,
or reading topics. PRD §10: the journal is private data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from core import copy
from core.db import connection
from core.services.access_control import AccessRequest, count_pending_requests, list_pending_requests
from core.services.motivation import ACTIVE_LOOKBACK_DAYS, WEEKLY_SUCCESS_DAYS
from core.services.sessions import count_active_days, local_today
from core.services.streaks import get_streak
from core.services.users import get_paused_until


@dataclass(frozen=True)
class AdminUserRow:
    id: int
    # The Telegram account behind this learner, or None for a web-only one.
    # Shown, never used as a key -- see W4b.
    telegram_user_id: int | None
    name: str
    cefr_level: str
    current_streak: int
    active_days: int
    last_active: date | None
    paused: bool
    revoked: bool


def list_admin_users(*, now_day: date | None = None) -> list[AdminUserRow]:
    """All onboarded users (including revoked), activity fields only."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.telegram_user_id, u.name, u.cefr_level, u.timezone,
                   u.paused_until,
                   COALESCE(ar.status, 'approved') AS access_status
              FROM users u
              LEFT JOIN access_requests ar
                     ON ar.user_id = u.id
             WHERE u.onboarded = TRUE
             ORDER BY u.name ASC, u.id ASC
            """
        ).fetchall()

    out: list[AdminUserRow] = []
    for row in rows:
        uid = int(row["id"])
        telegram = row["telegram_user_id"]
        tz = str(row["timezone"] or "Europe/Vilnius")
        # now_day is a local calendar date already chosen by the caller when
        # injected; otherwise derive "today" in the user's timezone via a
        # UTC wall — tests inject now_day to avoid the wall clock.
        if now_day is not None:
            day = now_day
        else:
            from datetime import datetime, timezone

            day = local_today(tz, datetime.now(timezone.utc))
        paused_until = row["paused_until"]
        paused = paused_until is not None and paused_until >= day
        try:
            streak = get_streak(uid)
            current_streak = int(streak.current_streak)
            last_active = streak.last_active_date
        except LookupError:
            current_streak = 0
            last_active = None
        week_start = day.fromordinal(day.toordinal() - (ACTIVE_LOOKBACK_DAYS - 1))
        active = count_active_days(uid, start=week_start, end=day)
        out.append(
            AdminUserRow(
                id=uid,
                telegram_user_id=None if telegram is None else int(telegram),
                name=str(row["name"]),
                cefr_level=str(row["cefr_level"]),
                current_streak=current_streak,
                active_days=active,
                last_active=last_active,
                paused=paused,
                revoked=str(row["access_status"]) == "revoked",
            )
        )
    return out


def format_admin_home(
    users: list[AdminUserRow],
    *,
    pending_count: int | None = None,
) -> str:
    n = count_pending_requests() if pending_count is None else pending_count
    lines = [
        copy.ADMIN_TITLE,
        copy.ADMIN_PENDING_LINE.format(n=n),
        "",
    ]
    if not users:
        lines.append(copy.ADMIN_EMPTY)
        return "\n".join(lines)

    for u in users:
        last = (
            u.last_active.isoformat()
            if u.last_active is not None
            else copy.ADMIN_LAST_NEVER
        )
        paused = copy.ADMIN_PAUSED_YES if u.paused else copy.ADMIN_PAUSED_NO
        name = u.name
        if u.revoked:
            name = f"{name} ({copy.ADMIN_REVOKED_TAG})"
        lines.append(
            copy.ADMIN_USER_LINE.format(
                name=name,
                level=u.cefr_level,
                streak=u.current_streak,
                active=u.active_days,
                week=WEEKLY_SUCCESS_DAYS,
                last=last,
                paused=paused,
            )
        )
    return "\n".join(lines)


def format_pending_list(pending: list[AccessRequest] | None = None) -> str:
    items = list_pending_requests() if pending is None else pending
    lines = [copy.ADMIN_TITLE, copy.ADMIN_PENDING_LINE.format(n=len(items)), ""]
    if not items:
        lines.append(copy.ADMIN_PENDING_NONE)
        return "\n".join(lines)
    for req in items:
        display = req.display_name or (
            f"@{req.username}" if req.username else str(req.telegram_user_id)
        )
        lines.append(
            copy.ADMIN_PENDING_ITEM.format(
                display=display,
                telegram_id=req.telegram_user_id,
            )
        )
    return "\n".join(lines)


def admin_user_label(user_id: int) -> str:
    """Short label for notices — name or id, never content."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT name FROM users WHERE id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return str(user_id)
    return str(row["name"])


def user_is_paused(user_id: int, day: date) -> bool:
    paused_until = get_paused_until(user_id)
    return paused_until is not None and paused_until >= day
