"""Telegram delivery for nudges and the Sunday report (S10 / M7).

Lifted unchanged out of ``core.services.motivation`` at W1 so the core
service is channel-neutral. The ladder arithmetic, the eligibility
predicates and the report copy stay in core. The worker takes this file
at W20.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from apps.bot import texts
from core.services.motivation import (
    MotivationUser,
    assemble_sunday_report,
    format_nudge_message,
    is_user_due_for_sunday_report,
    list_motivation_users,
    next_nudge_due_at,
    sessions_due_for_nudge,
    task_still_open,
)
from core.services.sessions import (
    MAX_NUDGES_PER_DAY,
    MAX_NUDGES_PER_SESSION,
    NudgeableSession,
    claim_sunday_report_session,
    daily_nudges_sent,
    has_sunday_report_session_on,
    increment_bot_messages,
    increment_nudges_sent,
    local_today,
    under_message_ceiling,
)

if TYPE_CHECKING:
    from telegram.ext import Application

logger = logging.getLogger(__name__)


def nudge_keyboard(action: dict[str, object] | None) -> InlineKeyboardMarkup | None:
    """Render `core.services.motivation.nudge_action` as an inline keyboard."""
    if action is None:
        return None
    if action.get("action") != "short_session":
        logger.warning("Unknown nudge action %r — sending text only", action)
        return None
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    texts.BTN_NUDGE_JUST_2,
                    callback_data=f"nudge:short:{action['session_id']}",
                )
            ]
        ]
    )


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

    body, action = format_nudge_message(session)
    await app.bot.send_message(
        chat_id=user.telegram_user_id,
        text=body,
        reply_markup=nudge_keyboard(action),
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
