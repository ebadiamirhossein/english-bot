"""Spacing ladder tests — ARCHITECTURE §8 mandatory suite (S3)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from core.db import close_pool, connection
from core.services.errors import due_errors, mark_result, record_errors
from core.services.identity import save_onboarding
FAKE_TELEGRAM_ID_BASE = 9_300_000_000


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


def _onboard(tid: int) -> int:
    user_id = save_onboarding(
        tid,
        {
            "name": "Spacing Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": "08:00",
            "evening_time": "21:00",
        },
    )
    return user_id


def _insert_error(
    tid: int,
    *,
    created_at: date | None = None,
    next_review: date | None = None,
    streak_right: int = 0,
    resolved: bool = False,
    resolved_at: date | None = None,
    unresolved_count: int = 0,
    error_type: str = "quantifier_modifier",
) -> int:
    created = created_at or date.today()
    review = next_review if next_review is not None else date.today()
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO errors (
                user_id, source, you_said, correct_form, error_type,
                explanation, murphy_units, streak_right, times_right,
                times_wrong, next_review, resolved, resolved_at,
                unresolved_count, created_at
            ) VALUES (
                %s, 'text', 'so much good', 'very good', %s,
                'Use very before adjectives.', '101-102', %s, 0,
                1, %s, %s, %s, %s,
                %s::timestamp
            )
            RETURNING id
            """,
            (
                tid,
                error_type,
                streak_right,
                review,
                resolved,
                resolved_at,
                unresolved_count,
                created.isoformat(),
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _fetch(error_id: int) -> dict:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT streak_right, times_right, times_wrong, next_review,
                   resolved, resolved_at, unresolved_count, created_at
              FROM errors WHERE id = %s
            """,
            (error_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


def test_correct_ladder_four_steps(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    eid = _insert_error(user_id, next_review=date.today(), streak_right=0)
    today = date.today()

    mark_result(eid, True)
    row = _fetch(eid)
    assert row["streak_right"] == 1
    assert row["times_right"] == 1
    assert row["next_review"] == today + timedelta(days=3)

    mark_result(eid, True)
    row = _fetch(eid)
    assert row["streak_right"] == 2
    assert row["next_review"] == today + timedelta(days=7)

    mark_result(eid, True)
    row = _fetch(eid)
    assert row["streak_right"] == 3
    assert row["next_review"] == today + timedelta(days=21)

    mark_result(eid, True)
    row = _fetch(eid)
    assert row["streak_right"] == 4
    assert row["next_review"] == today + timedelta(days=60)
    assert row["resolved"] is False


def test_wrong_resets_ladder(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    eid = _insert_error(user_id, streak_right=3, next_review=date.today())
    with connection() as conn:
        conn.execute(
            "UPDATE errors SET times_wrong = 1 WHERE id = %s",
            (eid,),
        )

    mark_result(eid, False)
    row = _fetch(eid)
    assert row["streak_right"] == 0
    assert row["times_wrong"] == 2
    assert row["next_review"] == date.today() + timedelta(days=1)


def test_streak_five_young_does_not_resolve(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    eid = _insert_error(
        user_id,
        created_at=date.today() - timedelta(days=10),
        streak_right=4,
        next_review=date.today(),
    )
    mark_result(eid, True)
    row = _fetch(eid)
    assert row["streak_right"] == 5
    assert row["resolved"] is False
    assert row["resolved_at"] is None
    assert row["next_review"] == date.today() + timedelta(days=60)


def test_streak_five_old_resolves(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    eid = _insert_error(
        user_id,
        created_at=date.today() - timedelta(days=21),
        streak_right=4,
        next_review=date.today(),
    )
    mark_result(eid, True)
    row = _fetch(eid)
    assert row["streak_right"] == 5
    assert row["resolved"] is True
    assert row["resolved_at"] == date.today()


def test_wrong_on_resolved_unresolves(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    eid = _insert_error(
        user_id,
        created_at=date.today() - timedelta(days=30),
        streak_right=5,
        resolved=True,
        resolved_at=date.today() - timedelta(days=5),
        unresolved_count=0,
        next_review=date.today(),
    )
    mark_result(eid, False)
    row = _fetch(eid)
    assert row["resolved"] is False
    assert row["resolved_at"] is None
    assert row["unresolved_count"] == 1
    assert row["streak_right"] == 0
    assert row["next_review"] == date.today() + timedelta(days=1)


def test_due_errors_filter_order_limit(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    today = date.today()
    # Future — excluded
    _insert_error(user_id, next_review=today + timedelta(days=5))
    # Resolved — excluded
    _insert_error(
        user_id,
        next_review=today,
        resolved=True,
        resolved_at=today,
        streak_right=5,
    )
    old = _insert_error(user_id, next_review=today - timedelta(days=2))
    mid = _insert_error(user_id, next_review=today - timedelta(days=1))
    new = _insert_error(user_id, next_review=today)
    extra = _insert_error(user_id, next_review=today)

    due = due_errors(user_id, limit=3)
    assert [e.id for e in due] == [old, mid, new]
    assert extra not in [e.id for e in due]
    assert all(not e.resolved for e in due)


def test_due_errors_never_other_user(
    cleanup_user: int, fake_telegram_id: int
) -> None:
    tid_a = cleanup_user
    tid_b = FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)
    try:
        user_id = _onboard(tid_a)
        tid_b_id = _onboard(tid_b)
        a_id = _insert_error(user_id, next_review=date.today())
        _insert_error(tid_b_id, next_review=date.today())
        due = due_errors(user_id, limit=5)
        assert [e.id for e in due] == [a_id]
        assert all(e.user_id == user_id for e in due)
    finally:
        _delete_user(tid_b)
