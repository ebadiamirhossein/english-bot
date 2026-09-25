"""W20 — Web Push: subscriptions, and the worker's daily reminder ladder.

**The ladder, v2's ported to the web session:**

    reminder   at `users.morning_time`, local        opens /session
    nudge_1    reminder + 3h  (motivation.NUDGE_FIRST_HOURS)
    nudge_2    reminder + 6h  (motivation.NUDGE_SECOND_HOURS)

Each step goes only if the one before it was `sent`; a nudge that falls due
after 21:00 local is dropped, never sent late. Every step is decided once per
learner per local day and the decision is a `push_deliveries` row (031).

**THE RULES, IN THE ORDER THEY ARE CHECKED — every one of them makes the app
send LESS:**

1. **A learner who practised today is never reminded or nudged today** — #259's
   one signal (`core.services.activity.practised_on`), the same the streak and
   the bot's ladder read.
2. **One nudge ladder per learner per day.** If the Telegram bot delivered a v2
   task (quiz, reading, diary) today, its own ladder nudges about it and the push
   ladder sends no nudge. Two ladders would double the nagging, and they would
   run on the same clock — which is also the one systematic race with the bot's
   non-atomic ceiling check (`sessions.reserve_message_slot`'s docstring). The
   reminder is not a nudge and still goes.
3. **PRD §10's combined ceiling: 3 messages a day, bot and push together.** A
   slot is reserved atomically before the send, in the same row the bot counts
   in. **The 4th is never sent; it is dropped, not queued** — a missed reminder
   shrinks the day, it never piles up (CLAUDE.md §4).
4. **Reachability.** No subscription → nothing sent. **#95's loud case** — no
   browser AND no Telegram, so the app cannot reach this learner at all — is
   logged at ERROR once per day. The worker has no operator channel (#65), so
   the journal is where it lands.

**What a push says is `core/copy.py`'s and carries no number.** The message is
not stored; the decision row holds a kind and an outcome.

**WHAT THIS DOES NOT DO: define a *missed* day (#431).** A reminder sent and not
acted on is NOT made a missed day here. It would make the streak breakable only
for learners who turned reminders on — the product would punish opting in. That
is an operator ruling, recorded, and #431 is retargeted to it.

SQL lives here (CLAUDE.md §2). No HTTP: the send is `core.push_api`'s, passed
in as ``sender`` so tests replace it at the provider door.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from psycopg.rows import tuple_row

from core import copy, push_api
from core.config import Settings
from core.db import connection
from core.push import PushConfigError, Subscription, Vapid, build_request, endpoint_host
from core.services.activity import practised_on
from core.services.motivation import NUDGE_FIRST_HOURS, NUDGE_SECOND_HOURS
from core.services.sessions import (
    NUDGEABLE_TASK_TYPES,
    local_today,
    reserve_message_slot,
)

logger = logging.getLogger(__name__)

REMINDER = "reminder"
NUDGE_1 = "nudge_1"
NUDGE_2 = "nudge_2"
KINDS = (REMINDER, NUDGE_1, NUDGE_2)

#: Hours after the reminder's decision each nudge falls due. v2's numbers.
NUDGE_AFTER = {
    NUDGE_1: timedelta(hours=NUDGE_FIRST_HOURS),
    NUDGE_2: timedelta(hours=NUDGE_SECOND_HOURS),
}
#: A nudge due at or after this local time is dropped (`late`). v2's ladder ran
#: until 03:00 the next morning; a phone lighting up at 02:00 about practice is
#: not something a friend who teaches English would do.
LAST_NUDGE_LOCAL = time(21, 0)
#: Where a tap on the notification lands. The session itself, not home: the
#: TASKS row's acceptance is *opens the session directly*.
SESSION_URL = "/session"

BODIES = {
    REMINDER: copy.PUSH_REMINDER,
    NUDGE_1: copy.PUSH_NUDGE_FIRST,
    NUDGE_2: copy.PUSH_NUDGE_SECOND,
}


# ── configuration ────────────────────────────────────────────────────────────


def vapid_from(settings: Settings) -> Vapid | None:
    """The configured VAPID identity, or None when push is not set up."""
    if not settings.vapid_private_key:
        return None
    return Vapid(
        private_key=settings.vapid_private_key,
        public_key=settings.vapid_public_key,
        subject=settings.vapid_subject,
    )


def public_key(settings: Settings) -> str | None:
    """What `GET /push/key` hands the browser: the public half, or None.

    None when unset, AND when the pair does not match — a browser subscribed
    against a public key the server cannot sign for would never receive a push,
    and nobody would find out.
    """
    vapid = vapid_from(settings)
    if vapid is None:
        return None
    try:
        vapid.check()
    except PushConfigError:
        logger.error("push: VAPID configuration is inconsistent; reminders are off")
        return None
    return vapid.public_key


# ── subscriptions ────────────────────────────────────────────────────────────


def save_subscription(user_id: int, subscription: Subscription) -> None:
    """Store this browser for this learner. Idempotent.

    **The endpoint MOVES to this learner if another one held it** — one device,
    one learner, the last one who turned reminders on there. Otherwise a shared
    phone would carry the other learner's reminders indefinitely.
    """
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (endpoint) DO UPDATE
               SET user_id = EXCLUDED.user_id,
                   p256dh = EXCLUDED.p256dh,
                   auth = EXCLUDED.auth
            """,
            (user_id, subscription.endpoint, subscription.p256dh, subscription.auth),
        )


def delete_subscription(user_id: int, endpoint: str) -> bool:
    """Turn reminders off on this browser. Only this learner's own row."""
    with connection() as conn:
        result = conn.execute(
            "DELETE FROM push_subscriptions WHERE user_id = %s AND endpoint = %s",
            (user_id, endpoint),
        )
        return result.rowcount > 0


def has_subscription(user_id: int, endpoint: str) -> bool:
    """Whether THIS browser is subscribed for this learner (the toggle's state)."""
    with connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM push_subscriptions WHERE user_id = %s AND endpoint = %s",
            (user_id, endpoint),
        ).fetchone()
    return row is not None


def _subscriptions(conn, user_id: int) -> list[Subscription]:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT endpoint, p256dh, auth FROM push_subscriptions "
            "WHERE user_id = %s ORDER BY id",
            (user_id,),
        )
        return [Subscription(*row) for row in cur.fetchall()]


# ── the ladder ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PushLearner:
    id: int
    has_telegram: bool
    timezone: str
    morning_time: time
    paused_until: date | None


@dataclass
class PassReport:
    """One tick's decisions, `(user_id, kind, outcome)`. Logged as counts."""

    decisions: list[tuple[int, str, str]] = field(default_factory=list)


def list_push_learners() -> list[PushLearner]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, telegram_user_id, timezone, morning_time, paused_until
              FROM approved_onboarded_users
             ORDER BY id
            """
        ).fetchall()
    return [
        PushLearner(
            id=int(r["id"]),
            has_telegram=r["telegram_user_id"] is not None,
            timezone=str(r["timezone"] or "Europe/Vilnius"),
            morning_time=r["morning_time"] or time(8, 0),
            paused_until=r["paused_until"],
        )
        for r in rows
    ]


def _decisions(conn, user_id: int, day: date) -> dict[str, tuple[str, datetime]]:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT kind, outcome, decided_at FROM push_deliveries "
            "WHERE user_id = %s AND local_date = %s",
            (user_id, day),
        )
        return {row[0]: (row[1], row[2]) for row in cur.fetchall()}


def _bot_delivered_today(conn, user_id: int, day: date) -> bool:
    """Did the Telegram bot deliver a v2 task (and so start its ladder) today?"""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT 1 FROM sessions
             WHERE user_id = %s AND date = %s AND task_type = ANY(%s)
               AND delivered_at IS NOT NULL
             LIMIT 1
            """,
            (user_id, day, sorted(NUDGEABLE_TASK_TYPES)),
        )
        return cur.fetchone() is not None


def due_kind(
    learner: PushLearner,
    decisions: dict[str, tuple[str, datetime]],
    now: datetime,
) -> str | None:
    """The one step of today's ladder that is due at ``now``, or None. Pure."""
    local = now.astimezone(ZoneInfo(learner.timezone))
    if REMINDER not in decisions:
        return REMINDER if local.time() >= learner.morning_time else None
    reminder_outcome, reminder_at = decisions[REMINDER]
    if reminder_outcome != "sent":
        return None
    for kind, before in ((NUDGE_1, REMINDER), (NUDGE_2, NUDGE_1)):
        if kind in decisions:
            continue
        if decisions.get(before, ("",))[0] != "sent":
            return None
        return kind if now >= reminder_at + NUDGE_AFTER[kind] else None
    return None


def _claim(conn, user_id: int, day: date, kind: str, outcome: str, now: datetime) -> bool:
    """Write the decision; False if this step was already decided (idempotent)."""
    row = conn.execute(
        """
        INSERT INTO push_deliveries (user_id, local_date, kind, outcome, decided_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        RETURNING 1
        """,
        (user_id, day, kind, outcome, now),
    ).fetchone()
    return row is not None


def _set_outcome(conn, user_id: int, day: date, kind: str, outcome: str) -> None:
    conn.execute(
        "UPDATE push_deliveries SET outcome = %s "
        "WHERE user_id = %s AND local_date = %s AND kind = %s",
        (outcome, user_id, day, kind),
    )


def decide_and_send(
    learner: PushLearner,
    now: datetime,
    vapid: Vapid,
    *,
    sender: Callable[..., push_api.PushResult] = push_api.send,
) -> tuple[str, str] | None:
    """Advance this learner's ladder by at most one step. Returns (kind, outcome)."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    day = local_today(learner.timezone, now)
    if learner.paused_until is not None and learner.paused_until >= day:
        return None

    with connection() as conn:
        kind = due_kind(learner, _decisions(conn, learner.id, day), now)
        if kind is None:
            return None

        # Every early exit below writes its reason and ends today's ladder.
        skip: str | None = None
        subs = _subscriptions(conn, learner.id)
        if practised_on(conn, learner.id, day):
            skip = "practised"
        elif kind != REMINDER and now.astimezone(ZoneInfo(learner.timezone)).time() >= LAST_NUDGE_LOCAL:
            skip = "late"
        elif kind != REMINDER and _bot_delivered_today(conn, learner.id, day):
            skip = "bot_ladder"
        elif not subs:
            skip = "no_subscription" if learner.has_telegram else "no_channel"

        if skip is not None:
            claimed = _claim(conn, learner.id, day, kind, skip, now)
            conn.commit()
            if claimed and skip == "no_channel":
                # #95: loud, not silent. A user id and nothing else.
                logger.error("push: no reachable channel user_id=%s", learner.id)
            return (kind, skip) if claimed else None

        # Claim the step and reserve the day's slot in ONE transaction, and
        # COMMIT it before the send: the row exists before the push does, so a
        # crash loses a push but never repeats one. (**An explicit commit, not
        # `conn.transaction()`**: the reads above opened the pool connection's
        # implicit transaction, and a nested `transaction()` is only a savepoint
        # — it would not commit until after the send.)
        if not _claim(conn, learner.id, day, kind, "sending", now):
            conn.rollback()
            return None
        if not reserve_message_slot(conn, learner.id, day):
            _set_outcome(conn, learner.id, day, kind, "ceiling")
            conn.commit()
            return (kind, "ceiling")
        conn.commit()

        message = {"title": copy.PUSH_TITLE, "body": BODIES[kind], "url": SESSION_URL}
        results: list[tuple[Subscription, push_api.PushResult]] = []
        for sub in subs:
            try:
                request = build_request(sub, message, vapid, now=now)
            except PushConfigError:
                results.append((sub, push_api.PushResult("gone", None)))
                continue
            results.append((sub, sender(request)))

        outcome = "sent" if any(r.outcome == "sent" for _, r in results) else "failed"
        _set_outcome(conn, learner.id, day, kind, outcome)
        for sub, result in results:
            if result.outcome == "gone":
                conn.execute(
                    "DELETE FROM push_subscriptions WHERE endpoint = %s",
                    (sub.endpoint,),
                )
        conn.commit()
        for sub, result in results:
            logger.info(
                "push: user_id=%s kind=%s host=%s result=%s status=%s",
                learner.id, kind, endpoint_host(sub.endpoint), result.outcome, result.status,
            )
        return (kind, outcome)


def run_push_pass(
    settings: Settings,
    now: datetime,
    *,
    sender: Callable[..., push_api.PushResult] = push_api.send,
) -> PassReport:
    """The worker's tick: every learner, one ladder step each at most."""
    report = PassReport()
    vapid = vapid_from(settings)
    if vapid is None:
        logger.error("push: VAPID keys are not set; no reminder is sent")
        return report
    try:
        vapid.check()
    except PushConfigError as exc:
        logger.error("push: VAPID configuration refused (%s); no reminder is sent", exc)
        return report
    for learner in list_push_learners():
        try:
            decided = decide_and_send(learner, now, vapid, sender=sender)
        except Exception:
            logger.exception("push: failed user_id=%s", learner.id)
            continue
        if decided is not None:
            report.decisions.append((learner.id, *decided))
    return report
