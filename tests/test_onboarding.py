"""Persistence checks for S1 onboarding (run against local Postgres :5433)."""

from __future__ import annotations

import uuid

import pytest

from core.db import close_pool, connection
from core.services.users import efset_to_cefr, get_user, save_onboarding


FAKE_TELEGRAM_ID_BASE = 9_000_000_000


@pytest.fixture
def fake_telegram_id() -> int:
    """Unique id per test run so parallel leftovers cannot collide."""
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


def test_efset_to_cefr_band_boundaries() -> None:
    expected = {
        1: "A1",
        30: "A1",
        31: "A2",
        40: "A2",
        41: "B1",
        50: "B1",
        51: "B2",
        60: "B2",
        61: "C1",
        70: "C1",
        71: "C2",
        100: "C2",
    }
    for score, level in expected.items():
        assert efset_to_cefr(score) == level, score


def test_save_onboarding_creates_user_and_streak(cleanup_user: int) -> None:
    tid = cleanup_user
    data = {
        "name": "Test User",
        "native_language": "fa",
        "cefr_level": "B1",
        "efset_baseline": 45,
        "work_domain": "marketing",
        "why_statement": "Talk to clients without freezing",
        "track_weights": {"work": 40, "life": 40, "curiosity": 20},
        "morning_time": "08:00",
        "evening_time": "21:00",
    }
    save_onboarding(tid, data)

    user = get_user(tid)
    assert user is not None
    assert user.name == "Test User"
    assert user.native_language == "fa"
    assert user.cefr_level == "B1"
    assert user.efset_baseline == 45
    assert user.work_domain == "marketing"
    assert user.why_statement == "Talk to clients without freezing"
    assert user.track_weights == {"work": 40, "life": 40, "curiosity": 20}
    assert user.morning_time.strftime("%H:%M") == "08:00"
    assert user.evening_time.strftime("%H:%M") == "21:00"
    assert user.onboarded is True

    with connection() as conn:
        streak = conn.execute(
            "SELECT freeze_tokens, current_streak FROM streaks WHERE user_id = %s",
            (tid,),
        ).fetchone()
        user_count = conn.execute(
            "SELECT count(*) AS n FROM users WHERE telegram_user_id = %s",
            (tid,),
        ).fetchone()
        streak_count = conn.execute(
            "SELECT count(*) AS n FROM streaks WHERE user_id = %s",
            (tid,),
        ).fetchone()

    assert streak is not None
    assert streak["freeze_tokens"] == 2
    assert user_count["n"] == 1
    assert streak_count["n"] == 1


def test_save_onboarding_twice_no_duplicates(cleanup_user: int) -> None:
    tid = cleanup_user
    data = {
        "name": "First",
        "native_language": "lt",
        "cefr_level": "B2",
        "efset_baseline": 55,
        "work_domain": "ops",
        "why_statement": "Meetings",
        "track_weights": {"work": 60, "life": 25, "curiosity": 15},
        "morning_time": "07:00",
        "evening_time": "19:00",
    }
    save_onboarding(tid, data)
    data["name"] = "Second"
    data["efset_baseline"] = None
    data["cefr_level"] = "B1"
    save_onboarding(tid, data)

    with connection() as conn:
        user_count = conn.execute(
            "SELECT count(*) AS n FROM users WHERE telegram_user_id = %s",
            (tid,),
        ).fetchone()
        streak_count = conn.execute(
            "SELECT count(*) AS n FROM streaks WHERE user_id = %s",
            (tid,),
        ).fetchone()

    assert user_count["n"] == 1
    assert streak_count["n"] == 1
    user = get_user(tid)
    assert user is not None
    assert user.name == "Second"
    assert user.efset_baseline is None
    assert user.cefr_level == "B1"


def test_redo_does_not_reset_streak(cleanup_user: int) -> None:
    tid = cleanup_user
    data = {
        "name": "Streaky",
        "native_language": "es",
        "cefr_level": "B1",
        "efset_baseline": None,
        "work_domain": "design",
        "why_statement": "Travel",
        "track_weights": {"work": 25, "life": 60, "curiosity": 15},
        "morning_time": "09:00",
        "evening_time": "20:00",
    }
    save_onboarding(tid, data)

    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE streaks SET current_streak = 5 WHERE user_id = %s",
                (tid,),
            )

    data["name"] = "Streaky Redo"
    save_onboarding(tid, data)

    with connection() as conn:
        streak = conn.execute(
            "SELECT current_streak FROM streaks WHERE user_id = %s",
            (tid,),
        ).fetchone()

    assert streak is not None
    assert streak["current_streak"] == 5
