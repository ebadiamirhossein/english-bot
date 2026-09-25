"""Interests profile (S9) — save, replace, preserve, min-2, free-text, layout."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from core.db import close_pool, connection
from core.services.interests import list_interests, replace_interests
from core.services.identity import save_onboarding
FAKE_TELEGRAM_ID_BASE = 9_450_000_000


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
            "name": "Interests Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": "07:00",
            "evening_time": "21:00",
        },
    )
    return user_id


def _full_seed() -> list[tuple[str, str]]:
    return [
        ("campaigns", "work"),
        ("negotiation", "work"),
        ("apartments", "life"),
        ("travel", "life"),
        ("space", "curiosity"),
        ("history", "curiosity"),
    ]


def test_save_writes_one_row_per_topic_lowercased(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    replace_interests(
        user_id,
        [
            ("  Campaigns ", "work"),
            ("Client Email", "work"),
            ("Apartments", "life"),
            ("Travel", "life"),
            ("Space", "curiosity"),
            ("History", "curiosity"),
        ],
    )
    rows = list_interests(user_id)
    assert len(rows) == 6
    by_topic = {r.topic: r for r in rows}
    assert set(by_topic) == {
        "campaigns",
        "client email",
        "apartments",
        "travel",
        "space",
        "history",
    }
    assert by_topic["campaigns"].track == "work"
    assert by_topic["client email"].track == "work"
    assert by_topic["apartments"].track == "life"
    assert by_topic["space"].track == "curiosity"
    for row in rows:
        assert row.weight == 1.0
        assert row.last_used is None


def test_rerun_replaces_rather_than_duplicates(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    replace_interests(user_id, _full_seed())
    replace_interests(
        user_id,
        [
            ("pricing", "work"),
            ("interviews", "work"),
            ("cooking", "life"),
            ("humour", "life"),
            ("sport", "curiosity"),
            ("nature", "curiosity"),
        ],
    )
    rows = list_interests(user_id)
    assert len(rows) == 6
    assert {r.topic for r in rows} == {
        "pricing",
        "interviews",
        "cooking",
        "humour",
        "sport",
        "nature",
    }


def test_kept_topic_retains_weight_and_last_used(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    replace_interests(user_id, _full_seed())
    used = date(2026, 7, 1)
    with connection() as conn:
        conn.execute(
            """
            UPDATE interests
               SET weight = 0.4, last_used = %s
             WHERE user_id = %s AND topic = %s AND track = %s
            """,
            (used, user_id, "campaigns", "work"),
        )

    replace_interests(
        user_id,
        [
            ("campaigns", "work"),
            ("pricing", "work"),
            ("apartments", "life"),
            ("travel", "life"),
            ("space", "curiosity"),
            ("history", "curiosity"),
        ],
    )
    rows = {r.topic: r for r in list_interests(user_id)}
    assert rows["campaigns"].weight == pytest.approx(0.4)
    assert rows["campaigns"].last_used == used
    assert rows["pricing"].weight == 1.0
    assert rows["pricing"].last_used is None


def test_free_text_topic_trimmed_and_lowercased(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    replace_interests(
        user_id,
        [
            ("  AI: The Future  ", "work"),
            ("negotiation", "work"),
            ("apartments", "life"),
            ("travel", "life"),
            ("space", "curiosity"),
            ("history", "curiosity"),
        ],
    )
    topics = {r.topic for r in list_interests(user_id)}
    assert "ai: the future" in topics
    assert "  AI: The Future  " not in topics


