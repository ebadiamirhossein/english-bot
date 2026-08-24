"""User reads and writes, all scoped by the internal ``users.id``.

Since W4b, ``user_id`` here means ``users.id`` and never a Telegram id. The
translation happens once, at the bot edge, through ``core.services.identity`` --
this module does not do it and its SQL may not name ``telegram_user_id``
(``tests/test_identity_boundary.py`` enforces that by parsing the tree).

``save_onboarding`` moved to ``identity`` for the same reason: it is the one
write that creates identity *from* a Telegram id.

Handlers must not talk to the database directly — call these helpers instead.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, time

from psycopg.types.json import Jsonb


from core.db import connection

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class User:
    id: int
    # Nullable since W4b: a web-only learner has no Telegram account. Read it as
    # a delivery address, never as an identity.
    telegram_user_id: int | None
    name: str
    native_language: str
    cefr_level: str
    explanation_language_fallback: bool
    efset_baseline: int | None
    work_domain: str | None
    why_statement: str | None
    track_weights: dict[str, int]
    morning_time: time
    evening_time: time
    onboarded: bool


def efset_to_cefr(score: int) -> str:
    """Map an EF SET score (1–100) to a CEFR band using EF's official table."""
    if score < 1 or score > 100:
        raise ValueError(f"EF SET score must be 1–100 (got {score})")
    if score <= 30:
        return "A1"
    if score <= 40:
        return "A2"
    if score <= 50:
        return "B1"
    if score <= 60:
        return "B2"
    if score <= 70:
        return "C1"
    return "C2"


def get_user(user_id: int) -> User | None:
    """Return the user row, or None if this user id is unknown."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, telegram_user_id, name, native_language, cefr_level,
                   explanation_language_fallback,
                   efset_baseline, work_domain, why_statement, track_weights,
                   morning_time, evening_time, onboarded
              FROM users
             WHERE id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    weights = row["track_weights"]
    if not isinstance(weights, dict):
        weights = dict(weights)
    tg = row["telegram_user_id"]
    return User(
        id=int(row["id"]),
        telegram_user_id=None if tg is None else int(tg),
        name=row["name"],
        native_language=row["native_language"],
        cefr_level=row["cefr_level"],
        explanation_language_fallback=bool(row["explanation_language_fallback"]),
        efset_baseline=row["efset_baseline"],
        work_domain=row["work_domain"],
        why_statement=row["why_statement"],
        track_weights={k: int(v) for k, v in weights.items()},
        morning_time=row["morning_time"],
        evening_time=row["evening_time"],
        onboarded=bool(row["onboarded"]),
    )


def is_registered(user_id: int) -> bool:
    """True when a users row exists and access is currently approved.

    Revoked users keep their ``users`` row (and learning history) but are
    treated as unregistered for every handler that calls this helper.
    """
    with connection() as conn:
        row = conn.execute(
            """
            SELECT 1
              FROM users u
              INNER JOIN access_requests ar
                      ON ar.user_id = u.id
             WHERE u.id = %s
               AND ar.status = 'approved'
            """,
            (user_id,),
        ).fetchone()
    return row is not None


def update_cefr_level(user_id: int, new_level: str) -> None:
    """Set users.cefr_level for this user only."""
    with connection() as conn:
        conn.execute(
            """
            UPDATE users
               SET cefr_level = %s
             WHERE id = %s
            """,
            (new_level, user_id),
        )
    logger.info(
        "Updated cefr_level user_id=%s level=%s",
        user_id,
        new_level,
    )


def update_track_weights(
    user_id: int, weights: dict[str, int]
) -> None:
    """Set users.track_weights for this user only."""
    with connection() as conn:
        conn.execute(
            """
            UPDATE users
               SET track_weights = %s
             WHERE id = %s
            """,
            (Jsonb(weights), user_id),
        )
    logger.info(
        "Updated track_weights user_id=%s weights=%s",
        user_id,
        weights,
    )


def update_morning_time(user_id: int, morning: time | str) -> None:
    """Set users.morning_time for this user only."""
    value = _as_time(morning)
    with connection() as conn:
        conn.execute(
            """
            UPDATE users
               SET morning_time = %s
             WHERE id = %s
            """,
            (value, user_id),
        )
    logger.info(
        "Updated morning_time user_id=%s time=%s",
        user_id,
        value.strftime("%H:%M"),
    )


def update_evening_time(user_id: int, evening: time | str) -> None:
    """Set users.evening_time for this user only."""
    value = _as_time(evening)
    with connection() as conn:
        conn.execute(
            """
            UPDATE users
               SET evening_time = %s
             WHERE id = %s
            """,
            (value, user_id),
        )
    logger.info(
        "Updated evening_time user_id=%s time=%s",
        user_id,
        value.strftime("%H:%M"),
    )


def update_explanation_language_fallback(
    user_id: int, enabled: bool
) -> None:
    """Set users.explanation_language_fallback for this user only."""
    with connection() as conn:
        conn.execute(
            """
            UPDATE users
               SET explanation_language_fallback = %s
             WHERE id = %s
            """,
            (enabled, user_id),
        )
    logger.info(
        "Updated explanation_language_fallback user_id=%s enabled=%s",
        user_id,
        enabled,
    )


def _as_time(value: time | str) -> time:
    if isinstance(value, time):
        return value
    parts = value.strip().split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"invalid time: {value!r}")
    hour, minute = int(parts[0]), int(parts[1])
    return time(hour, minute)


def get_paused_until(user_id: int) -> date | None:
    """Return users.paused_until for this telegram id, or None."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT paused_until
              FROM users
             WHERE id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return row["paused_until"]


def set_paused_until(
    user_id: int, paused_until: date | None
) -> None:
    """Set or clear users.paused_until for this user only."""
    with connection() as conn:
        conn.execute(
            """
            UPDATE users
               SET paused_until = %s
             WHERE id = %s
            """,
            (paused_until, user_id),
        )
    logger.info(
        "Updated paused_until user_id=%s until=%s",
        user_id,
        paused_until,
    )


