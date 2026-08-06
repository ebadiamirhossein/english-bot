"""Interest profile reads/writes (S9) and topic selection (S9a).

All queries are scoped by user_id. Handlers must not talk to the database
directly — call these helpers instead.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence

from app.db import connection

logger = logging.getLogger(__name__)

# Unused topics score as if last used this many days ago (S9a).
_NULL_LAST_USED_DAYS = 30


@dataclass(frozen=True)
class Interest:
    topic: str
    track: str
    weight: float
    last_used: date | None


def list_interests(user_id: int) -> list[Interest]:
    """Return this user's interest rows, ordered by track then topic."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT topic, track, weight, last_used
              FROM interests
             WHERE user_id = %s
             ORDER BY track NULLS LAST, topic
            """,
            (user_id,),
        ).fetchall()
    return [
        Interest(
            topic=str(row["topic"]),
            track=str(row["track"]) if row["track"] is not None else "",
            weight=float(row["weight"]) if row["weight"] is not None else 1.0,
            last_used=row["last_used"],
        )
        for row in rows
    ]


def _days_since(last_used: date | None, today: date) -> int:
    if last_used is None:
        return _NULL_LAST_USED_DAYS
    return max(0, (today - last_used).days)


def topic_score(
    interest: Interest,
    track_weights: dict[str, int],
    today: date,
) -> float:
    """Selection score: weight × track_weight × (1 + days_since)."""
    tw = max(0, int(track_weights.get(interest.track, 0)))
    return interest.weight * tw * (1 + _days_since(interest.last_used, today))


def select_topic(
    user_id: int,
    track_weights: dict[str, int],
    today: date,
) -> Interest | None:
    """Pick one interest by score; ties broken by topic alphabetically.

    Returns None when the user has no interest rows.
    """
    interests = list_interests(user_id)
    if not interests:
        return None
    return _pick_best(interests, track_weights, today)


def _pick_best(
    interests: list[Interest],
    track_weights: dict[str, int],
    today: date,
) -> Interest:
    """Highest score wins; exact ties → alphabetically first topic."""
    best = interests[0]
    best_score = topic_score(best, track_weights, today)
    for item in interests[1:]:
        score = topic_score(item, track_weights, today)
        if score > best_score or (
            score == best_score and item.topic < best.topic
        ):
            best = item
            best_score = score
    return best


def mark_last_used(
    user_id: int,
    topic: str,
    track: str,
    today: date,
    *,
    conn: Any | None = None,
) -> None:
    """Set last_used on the matching interest row.

    When ``conn`` is provided, uses that connection (caller owns the txn).
    """
    sql = """
        UPDATE interests
           SET last_used = %s
         WHERE user_id = %s AND topic = %s AND track = %s
        """
    params = (today, user_id, topic, track)
    if conn is not None:
        conn.execute(sql, params)
        return
    with connection() as owned:
        with owned.transaction():
            owned.execute(sql, params)


def replace_interests(
    user_id: int,
    selections: Sequence[tuple[str, str]],
) -> None:
    """Replace all interest rows for this user.

    ``selections`` is a sequence of ``(topic, track)``. Topics are trimmed and
    lowercased; empty topics are skipped. For any ``(topic, track)`` that
    already existed, ``weight`` and ``last_used`` are preserved; new topics
    get weight 1.0 and last_used NULL.
    """
    normalized: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw_topic, raw_track in selections:
        topic = raw_topic.strip().lower()
        track = raw_track.strip().lower()
        if not topic or not track:
            continue
        key = (topic, track)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(key)

    with connection() as conn:
        with conn.transaction():
            existing_rows = conn.execute(
                """
                SELECT topic, track, weight, last_used
                  FROM interests
                 WHERE user_id = %s
                """,
                (user_id,),
            ).fetchall()
            prior: dict[tuple[str, str], tuple[float, date | None]] = {}
            for row in existing_rows:
                key = (str(row["topic"]), str(row["track"] or ""))
                weight = float(row["weight"]) if row["weight"] is not None else 1.0
                prior[key] = (weight, row["last_used"])

            conn.execute(
                "DELETE FROM interests WHERE user_id = %s",
                (user_id,),
            )
            for topic, track in normalized:
                weight, last_used = prior.get((topic, track), (1.0, None))
                conn.execute(
                    """
                    INSERT INTO interests (user_id, topic, track, weight, last_used)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (user_id, topic, track, weight, last_used),
                )
    logger.info(
        "Replaced interests for user_id=%s count=%s",
        user_id,
        len(normalized),
    )
