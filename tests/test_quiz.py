"""Quiz grading, mark_result once, abandon, free_practice idempotency (S3)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from core.db import close_pool, connection
from core.services.errors import mark_result
from core.services.identity import save_onboarding
FAKE_TELEGRAM_ID_BASE = 9_310_000_000


@pytest.fixture
def fake_telegram_id() -> int:
    return FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)


@pytest.fixture(autouse=True)
def _close_pool_after_test() -> None:
    yield
    close_pool()


def _delete_user(telegram_user_id: int) -> None:
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM users WHERE telegram_user_id = %s",
                (telegram_user_id,),
            )


@pytest.fixture
def cleanup_user(fake_telegram_id: int):
    yield fake_telegram_id
    _delete_user(fake_telegram_id)


def _onboard(tid: int, *, morning: str = "07:00", tz: str = "Europe/Vilnius") -> int:
    user_id = save_onboarding(
        tid,
        {
            "name": "Quiz Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": morning,
            "evening_time": "21:00",
        },
    )
    with connection() as conn:
        conn.execute(
            "UPDATE users SET timezone = %s WHERE telegram_user_id = %s",
            (tz, tid),
        )
    return user_id


def _insert_error(tid: int, *, next_review: date | None = None) -> int:
    review = next_review if next_review is not None else date.today()
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO errors (
                user_id, source, you_said, correct_form, error_type,
                explanation, next_review
            ) VALUES (
                %s, 'text', 'so much good', 'very good',
                'quantifier_modifier', 'Use very.', %s
            )
            RETURNING id
            """,
            (tid, review),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _sessions(tid: int) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT task_type, completed, date
              FROM sessions WHERE user_id = %s ORDER BY id
            """,
            (tid,),
        ).fetchall()
    return [dict(r) for r in rows]


def _next_review(error_id: int) -> date:
    with connection() as conn:
        row = conn.execute(
            "SELECT next_review FROM errors WHERE id = %s",
            (error_id,),
        ).fetchone()
    assert row is not None
    return row["next_review"]


def test_abandon_leaves_remaining_untouched(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    today = date.today()
    ids = [_insert_error(user_id, next_review=today) for _ in range(5)]
    reviews_before = {eid: _next_review(eid) for eid in ids}

    # Answer only first two via mark_result (simulate); leave 3–5 alone.
    mark_result(ids[0], True)
    mark_result(ids[1], False)

    for eid in ids[2:]:
        assert _next_review(eid) == reviews_before[eid]


