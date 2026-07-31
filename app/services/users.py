"""User reads/writes and onboarding persistence.

All queries are scoped by telegram_user_id. Handlers must not talk to
the database directly — call these helpers instead.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import time
from typing import Any

from psycopg.types.json import Jsonb

from app.db import connection

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class User:
    telegram_user_id: int
    name: str
    native_language: str
    cefr_level: str
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


def get_user(telegram_user_id: int) -> User | None:
    """Return the user row, or None if this telegram id is unknown."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT telegram_user_id, name, native_language, cefr_level,
                   efset_baseline, work_domain, why_statement, track_weights,
                   morning_time, evening_time, onboarded
              FROM users
             WHERE telegram_user_id = %s
            """,
            (telegram_user_id,),
        ).fetchone()
    if row is None:
        return None
    weights = row["track_weights"]
    if not isinstance(weights, dict):
        weights = dict(weights)
    return User(
        telegram_user_id=int(row["telegram_user_id"]),
        name=row["name"],
        native_language=row["native_language"],
        cefr_level=row["cefr_level"],
        efset_baseline=row["efset_baseline"],
        work_domain=row["work_domain"],
        why_statement=row["why_statement"],
        track_weights={k: int(v) for k, v in weights.items()},
        morning_time=row["morning_time"],
        evening_time=row["evening_time"],
        onboarded=bool(row["onboarded"]),
    )


def is_registered(telegram_user_id: int) -> bool:
    """True when a users row exists for this telegram id."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM users WHERE telegram_user_id = %s
            """,
            (telegram_user_id,),
        ).fetchone()
    return row is not None


def save_onboarding(telegram_user_id: int, data: dict[str, Any]) -> None:
    """Persist onboarding answers and ensure a streaks row exists.

    Writes both rows in one transaction. On conflict, updates the users
    profile but never touches an existing streak (ON CONFLICT DO NOTHING).
    Does not overwrite created_at.
    """
    weights = data["track_weights"]
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO users (
                    telegram_user_id,
                    name,
                    native_language,
                    cefr_level,
                    efset_baseline,
                    work_domain,
                    why_statement,
                    track_weights,
                    morning_time,
                    evening_time,
                    onboarded
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE
                )
                ON CONFLICT (telegram_user_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    native_language = EXCLUDED.native_language,
                    cefr_level = EXCLUDED.cefr_level,
                    efset_baseline = EXCLUDED.efset_baseline,
                    work_domain = EXCLUDED.work_domain,
                    why_statement = EXCLUDED.why_statement,
                    track_weights = EXCLUDED.track_weights,
                    morning_time = EXCLUDED.morning_time,
                    evening_time = EXCLUDED.evening_time,
                    onboarded = TRUE
                """,
                (
                    telegram_user_id,
                    data["name"],
                    data["native_language"],
                    data["cefr_level"],
                    data.get("efset_baseline"),
                    data["work_domain"],
                    data["why_statement"],
                    Jsonb(weights),
                    data["morning_time"],
                    data["evening_time"],
                ),
            )
            conn.execute(
                """
                INSERT INTO streaks (user_id)
                VALUES (%s)
                ON CONFLICT DO NOTHING
                """,
                (telegram_user_id,),
            )
    logger.info("Saved onboarding for user_id=%s", telegram_user_id)
