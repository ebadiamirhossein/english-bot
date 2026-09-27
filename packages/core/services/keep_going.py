"""W24e — *keep going*: what a learner may optionally do next.

**Operator decision 1 of 2026-09-27:** when today's session is finished, and on
the Sunday rest screen, the learner sees a short optional choice instead of a
dead end — *there's always a next thing* — **under this product's copy rules: no
count, no score, no backlog, no guilt; optional and never nagging.**

**This module decides only WHICH options exist**, as bare kinds. It never says
how many cards are due, how many turns are left or how many videos wait: each
cap is read here and reaches the wire as the presence or absence of one word.
An option whose surface would open onto nothing is not offered.

| kind  | offered when                                              | billed per use |
|-------|-----------------------------------------------------------|----------------|
| watch | today's extra (or, on Sunday, today's own video) is open, or the pool holds one in band and unseen | 0 |
| talk  | not Sunday, and the day's conversation turns are under `CONVERSATION_MAX_TURNS_PER_DAY` | the conversation's own (≈3 + one per turn; +1 STT per voice turn) |
| cards | not Sunday, and `due_queue` holds a card now — never a near-due one (R7) | 0 |
| write | not Sunday, and today's submissions are under `WRITING_MAX_SUBMISSIONS_PER_DAY` | 1 per entry |

**Nothing here writes to the error journal**, and keep going adds no journal
writer: talk's close and write's correction are the existing, integration-tested
paths, and only they journal (only genuine, self-produced errors — CLAUDE.md §5).

**Sunday is watch-only (R1)** — PRD §4.2's *free extensive input, tracked but
never required* — and Sunday's *watch* opens the day's own video first (R3),
which the worker assigned and which no session button reaches.

**Whether the session is finished is the CLIENT's gate, not this module's**
(R2: the choice appears only then). This answers *what could be offered*; the
session route's `finished` answers *whether to show it*. The one write here,
`watch`, is bounded by migration 034 to one extra per learner per day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.config import Settings, load_settings
from core.db import connection

#: The order the choice is shown in: input first (decision 4 — input and
#: speaking drive fluency), then speaking, then the practice surfaces. **W31d
#: adds `practice`** (the word drill, W24f un-deferred by C6), beside `cards`.
KINDS = ("watch", "talk", "cards", "practice", "write")

#: W31d: the drill is offered only when it has at least this many exercises —
#: fewer is not five minutes of anything.
PRACTICE_MIN_EXERCISES = 4

SUNDAY = 6


@dataclass(frozen=True, slots=True)
class Watch:
    """What `/watch` plays: the player's payload and the learner's L1."""

    video: dict[str, Any]
    l1_language: str


def _learner(conn: Any, user_id: int) -> tuple[str, str] | None:
    row = conn.execute(
        "SELECT COALESCE(timezone, 'Europe/Vilnius') AS tz, native_language "
        "FROM users WHERE id = %s",
        (user_id,),
    ).fetchone()
    return None if row is None else (str(row["tz"]), str(row["native_language"]))


def _open_video(conn: Any, user_id: int, local_date, *, sunday: bool):
    """The video *watch* would reopen, or None. Sunday's own video first (R3);
    then today's extra, unless it is finished (one extra a day)."""
    from core.services import video as video_service

    if sunday:
        daily = video_service.today_for(conn, user_id, on=local_date)
        if daily is not None and daily.completed_at is None:
            return daily
    extra = video_service.today_for(conn, user_id, on=local_date, kind="extra")
    if extra is not None and extra.completed_at is None:
        return extra
    return None


def _extra_used(conn: Any, user_id: int, local_date) -> bool:
    from core.services import video as video_service

    return video_service.today_for(conn, user_id, on=local_date, kind="extra") is not None


def options(
    user_id: int, *, now: datetime, settings: Settings | None = None
) -> tuple[str, ...] | None:
    """The kinds available to this learner now, in `KINDS` order. None if unknown."""
    from core.services import cards as cards_service
    from core.services.conversations import usage_today
    from core.services.sessions import local_today
    from core.services.writing import submissions_on
    from core.video import assign

    cfg = settings or load_settings()
    with connection() as conn:
        learner = _learner(conn, user_id)
        if learner is None:
            return None
        tz, _l1 = learner
        local_date = local_today(tz, now)
        sunday = local_date.weekday() == SUNDAY

        available: set[str] = set()
        if _open_video(conn, user_id, local_date, sunday=sunday) is not None:
            available.add("watch")
        elif not _extra_used(conn, user_id, local_date):
            ranked = assign.rank_for(conn, user_id)
            if ranked is not None and assign.choose(ranked[0], 1):
                available.add("watch")
        conn.rollback()  # ranking wrote nothing; say so to the pool

        if not sunday:
            if usage_today(conn, user_id, local_date).turns_learner < cfg.conversation_max_turns_per_day:
                available.add("talk")
            if submissions_on(conn, user_id, local_date) < cfg.writing_max_submissions_per_day:
                available.add("write")
    if not sunday and cards_service.due_queue(user_id, now=now, limit=1):
        available.add("cards")
    # W31d: the word drill, not on Sunday (R1). **Offered even when nothing is
    # due** — the top-up is practice only and writes nothing (Q8), so R7's
    # reason for keeping `cards` to due cards does not reach it.
    if not sunday:
        from core.services import practice as practice_service

        if len(practice_service.start(user_id, now=now)) >= PRACTICE_MIN_EXERCISES:
            available.add("practice")
    return tuple(k for k in KINDS if k in available)


def watch(user_id: int, *, now: datetime) -> Watch | None:
    """`POST /keep-going/watch`: reopen today's open video, or assign one extra.

    **Assigned, never browsed (R2):** the extra is the selection score's best
    in-band, unseen video — `core.video.assign.assign_day(kind="extra")`, the
    same choice the worker makes for block 2. None when there is nothing: no
    repeat, nothing below band, and no second extra on one day.
    """
    from core.services.sessions import local_today, video_payload
    from core.services import video as video_service
    from core.video import assign

    with connection() as conn:
        learner = _learner(conn, user_id)
        if learner is None:
            return None
        tz, l1 = learner
        local_date = local_today(tz, now)
        sunday = local_date.weekday() == SUNDAY
        target = _open_video(conn, user_id, local_date, sunday=sunday)
        if target is None:
            if _extra_used(conn, user_id, local_date):
                return None
            if assign.assign_day(conn, user_id, local_date, kind="extra") is None:
                conn.rollback()
                return None
            conn.commit()
            target = video_service.today_for(conn, user_id, on=local_date, kind="extra")
        return Watch(video=video_payload(conn, user_id, target), l1_language=l1)
