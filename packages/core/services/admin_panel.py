"""Operator admin panel assembly (S18d; ported to the web by W23).

Activity and state only — never error text, diary corrections, chunks,
or reading topics. PRD §10: the journal is private data.

**W23 — `operator_activity` is the web's door to the same rows.** It returns
exactly what the bot's panel prints (``AdminUserRow`` and the pending count),
and nothing is added for the web: the rows were already chosen as activity and
never content, and ``tests/test_access_approval.py`` has held that since S18d.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

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


def list_admin_users(
    *, now_day: date | None = None, now: datetime | None = None
) -> list[AdminUserRow]:
    """All onboarded users (including revoked), activity fields only.

    ``now`` (W23) is an instant, turned into each learner's OWN local date — the
    web route reads the clock once and passes it. ``now_day`` is the bot's
    older form: one calendar date for everybody. Neither: the wall clock.
    """
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
        elif now is not None:
            day = local_today(tz, now)
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


@dataclass(frozen=True)
class OperatorActivity:
    """W23: the web panel's whole payload — the bot panel's home screen."""

    pending_requests: int
    weekly_goal_days: int
    lookback_days: int
    users: list[AdminUserRow]


def is_operator(user_id: int, admin_user_ids: tuple[int, ...]) -> bool:
    """Is this ``users.id`` on ``ADMIN_USER_IDS``? **Empty means nobody.**

    A ``users.id`` allowlist, not the operator's Telegram id: the web path
    identifies people by ``users.id`` alone (W4b), and the first build of this
    function — which compared ``OPERATOR_TELEGRAM_ID`` with
    ``users.telegram_user_id`` — was refused by ``tests/test_identity_boundary.py``.
    """
    return user_id in admin_user_ids


def operator_activity(
    user_id: int, *, admin_user_ids: tuple[int, ...], now: datetime
) -> OperatorActivity | None:
    """The panel, or ``None`` when the caller is not the operator.

    One call for the route (CLAUDE.md §2): the authorisation question and the
    read are one service function, so no route can read the rows unasked.
    """
    if not is_operator(user_id, admin_user_ids):
        return None
    return OperatorActivity(
        pending_requests=count_pending_requests(),
        weekly_goal_days=WEEKLY_SUCCESS_DAYS,
        lookback_days=ACTIVE_LOOKBACK_DAYS,
        users=list_admin_users(now=now),
    )
