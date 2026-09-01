"""S12 M14 difficulty calibration."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.bot import texts
from core.db import close_pool, connection
from core.services.calibration import (
    CEFR_LADDER,
    MIN_SAMPLE,
    compute_accuracy_window,
    deliver_raise_notice,
    maybe_calibrate,
    s12_user_facing_strings,
)
from core.services.sessions import (
    bot_initiated_count,
    complete_session,
    increment_bot_messages,
    insert_session,
)
from core.services.identity import save_onboarding
from core.services.users import get_user
FAKE_TELEGRAM_ID_BASE = 9_520_000_000

# Monday 2026-08-10 12:00 Vilnius (UTC+3)
_NOW = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)
_TODAY = date(2026, 8, 10)


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


def _onboard(tid: int, *, level: str = "B1") -> int:
    user_id = save_onboarding(
        tid,
        {
            "name": "Calib Test",
            "native_language": "fa",
            "cefr_level": level,
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": "08:00",
            "evening_time": "21:00",
        },
    )
    return user_id


def _insert_scored_quiz(
    tid: int,
    day: date,
    *,
    correct: int,
    answered: int,
    completed_at: datetime,
) -> None:
    payload = {
        "correct_count": correct,
        "answered": answered,
        "questions": [{"format": "gap"} for _ in range(answered)],
    }
    score = correct / answered if answered else 0.0
    sid = insert_session(tid, "quiz", day, payload=payload, completed=False)
    complete_session(sid, score)
    with connection() as conn:
        conn.execute(
            """
            UPDATE sessions
               SET completed_at = %s, date = %s
             WHERE id = %s
            """,
            (completed_at, day, sid),
        )


def _insert_book_test(
    tid: int,
    day: date,
    *,
    correct: int,
    answered: int,
    completed_at: datetime,
) -> None:
    payload = {
        "correct_count": correct,
        "answered": answered,
        "questions": [{"format": "choice"} for _ in range(answered)],
    }
    score = correct / answered if answered else 0.0
    sid = insert_session(tid, "book_test", day, payload=payload, completed=False)
    complete_session(sid, score)
    with connection() as conn:
        conn.execute(
            """
            UPDATE sessions
               SET completed_at = %s, date = %s
             WHERE id = %s
            """,
            (completed_at, day, sid),
        )


def _seed_high_accuracy_sessions(tid: int) -> None:
    """Enough quiz questions at 90% for MIN_SAMPLE (3 × 10 at 9/10)."""
    for i in range(3):
        day = _TODAY - timedelta(days=i)
        _insert_scored_quiz(
            tid,
            day,
            correct=9,
            answered=10,
            completed_at=_NOW - timedelta(hours=i + 1),
        )


def _insert_log(
    tid: int,
    day: date,
    *,
    accuracy: float,
    old_level: str = "B1",
    new_level: str = "B1",
) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO calibration_log (
                user_id, date, accuracy_30, old_level, new_level
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (tid, day, accuracy, old_level, new_level),
        )


def _logs(tid: int) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT date, accuracy_30, old_level, new_level
              FROM calibration_log
             WHERE user_id = %s
             ORDER BY date ASC, id ASC
            """,
            (tid,),
        ).fetchall()
    return [dict(r) for r in rows]


def test_raise_with_10_of_14_days_above_85(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, level="B1")
    _seed_high_accuracy_sessions(user_id)
    # 9 prior days in the window (today will be the 10th via maybe_calibrate)
    for i in range(1, 10):
        _insert_log(user_id, _TODAY - timedelta(days=i), accuracy=0.90)

    outcome = maybe_calibrate(user_id, now=_NOW)
    assert outcome.changed
    assert outcome.old_level == "B1"
    assert outcome.new_level == "B2"
    assert outcome.raise_notice is not None
    assert "B2" in outcome.raise_notice
    user = get_user(user_id)
    assert user is not None and user.cefr_level == "B2"
    logs = _logs(user_id)
    today_rows = [r for r in logs if r["date"] == _TODAY]
    assert len(today_rows) == 1
    assert today_rows[0]["old_level"] == "B1"
    assert today_rows[0]["new_level"] == "B2"


def test_fewer_than_8_logged_days_no_raise(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, level="B1")
    _seed_high_accuracy_sessions(user_id)
    for i in range(1, 7):  # 6 prior + today = 7 < 8
        _insert_log(user_id, _TODAY - timedelta(days=i), accuracy=0.90)

    outcome = maybe_calibrate(user_id, now=_NOW)
    assert not outcome.changed
    assert get_user(user_id).cefr_level == "B1"  # type: ignore[union-attr]


def test_one_day_at_or_below_85_blocks_raise(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, level="B1")
    _seed_high_accuracy_sessions(user_id)
    for i in range(1, 10):
        acc = 0.80 if i == 3 else 0.90
        _insert_log(user_id, _TODAY - timedelta(days=i), accuracy=acc)

    outcome = maybe_calibrate(user_id, now=_NOW)
    assert not outcome.changed


def test_below_70_lowers_silently(cleanup_user: int, caplog: pytest.LogCaptureFixture) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, level="B1")
    for i in range(3):
        _insert_scored_quiz(
            user_id,
            _TODAY - timedelta(days=i),
            correct=6,
            answered=10,
            completed_at=_NOW - timedelta(hours=i + 1),
        )
    bot = MagicMock()
    bot.send_message = AsyncMock()

    with caplog.at_level(logging.INFO):
        outcome = maybe_calibrate(user_id, now=_NOW)

    assert outcome.changed
    assert outcome.new_level == "A2"
    assert outcome.raise_notice is None
    assert get_user(user_id).cefr_level == "A2"  # type: ignore[union-attr]
    # No raise path — caller must not send; we assert notice is None.
    assert bot.send_message.await_count == 0
    logs = _logs(user_id)
    assert logs[-1]["old_level"] == "B1"
    assert logs[-1]["new_level"] == "A2"


def test_raise_notice_sent_and_ceiling_skip(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, level="B1")
    _seed_high_accuracy_sessions(user_id)
    for i in range(1, 10):
        _insert_log(user_id, _TODAY - timedelta(days=i), accuracy=0.90)

    outcome = maybe_calibrate(user_id, now=_NOW)
    assert outcome.raise_notice

    bot = MagicMock()
    bot.send_message = AsyncMock()
    sent = asyncio.run(
        deliver_raise_notice(bot, user_id, day=_TODAY, notice=outcome.raise_notice)
    )
    assert sent
    bot.send_message.assert_awaited_once()
    assert bot_initiated_count(user_id, _TODAY) == 1

    # Ceiling full — level already changed; second notice skipped.
    increment_bot_messages(user_id, _TODAY)
    increment_bot_messages(user_id, _TODAY)
    assert bot_initiated_count(user_id, _TODAY) == 3
    bot2 = MagicMock()
    bot2.send_message = AsyncMock()
    with caplog.at_level(logging.WARNING):
        skipped = asyncio.run(
            deliver_raise_notice(
                bot2, user_id, day=_TODAY, notice=outcome.raise_notice
            )
        )
    assert not skipped
    bot2.send_message.assert_not_awaited()
    assert "ceiling" in caplog.text.lower()
    assert get_user(user_id).cefr_level == "B2"  # type: ignore[union-attr]


def test_cooldown_blocks_second_change(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, level="B1")
    _seed_high_accuracy_sessions(user_id)
    for i in range(1, 10):
        _insert_log(user_id, _TODAY - timedelta(days=i), accuracy=0.90)
    maybe_calibrate(user_id, now=_NOW)
    assert get_user(user_id).cefr_level == "B2"  # type: ignore[union-attr]

    # Next day still high accuracy — cooldown prevents another raise.
    next_now = _NOW + timedelta(days=1)
    next_day = _TODAY + timedelta(days=1)
    _insert_scored_quiz(
        user_id,
        next_day,
        correct=10,
        answered=10,
        completed_at=next_now,
    )
    for i in range(1, 10):
        _insert_log(user_id, next_day - timedelta(days=i), accuracy=0.90)
    outcome = maybe_calibrate(user_id, now=next_now)
    assert not outcome.changed
    assert get_user(user_id).cefr_level == "B2"  # type: ignore[union-attr]


def test_below_minimum_sample_no_calibration(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, level="B1")
    _insert_scored_quiz(
        user_id, _TODAY, correct=4, answered=5, completed_at=_NOW
    )
    outcome = maybe_calibrate(user_id, now=_NOW)
    assert outcome.sample < MIN_SAMPLE
    assert not outcome.changed
    assert _logs(user_id) == []


def test_bounds_floor_and_ceiling(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, level="A2")
    for i in range(3):
        _insert_scored_quiz(
            user_id,
            _TODAY - timedelta(days=i),
            correct=5,
            answered=10,
            completed_at=_NOW - timedelta(hours=i + 1),
        )
    outcome = maybe_calibrate(user_id, now=_NOW)
    assert not outcome.changed
    assert get_user(user_id).cefr_level == "A2"  # type: ignore[union-attr]

    with connection() as conn:
        conn.execute(
            "UPDATE users SET cefr_level = %s WHERE id = %s",
            ("C1", user_id),
        )
        conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        conn.execute("DELETE FROM calibration_log WHERE user_id = %s", (user_id,))
    _seed_high_accuracy_sessions(user_id)
    for i in range(1, 10):
        _insert_log(user_id, _TODAY - timedelta(days=i), accuracy=0.90)
    outcome = maybe_calibrate(user_id, now=_NOW)
    assert not outcome.changed
    assert get_user(user_id).cefr_level == "C1"  # type: ignore[union-attr]
    assert "C1" == CEFR_LADDER[-1]


def test_book_test_excluded_from_window(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, level="B1")
    # Only book_test sessions — high scores must not create a window.
    for i in range(3):
        _insert_book_test(
            user_id,
            _TODAY - timedelta(days=i),
            correct=10,
            answered=10,
            completed_at=_NOW - timedelta(hours=i + 1),
        )
    window = compute_accuracy_window(user_id)
    assert window.sample == 0
    outcome = maybe_calibrate(user_id, now=_NOW)
    assert not outcome.changed
    assert _logs(user_id) == []


def test_weekly_test_excluded_from_window(cleanup_user: int) -> None:
    """S11: a perfect 15Q weekly alone must not raise or write calibration_log."""
    tid = cleanup_user
    user_id = _onboard(tid, level="B1")
    payload = {
        "correct_count": 15,
        "answered": 15,
        "weekly_test": True,
        "questions": [{"format": "choice"} for _ in range(15)],
    }
    sid = insert_session(user_id, "quiz", _TODAY, payload=payload, completed=False)
    complete_session(sid, 1.0)
    with connection() as conn:
        conn.execute(
            """
            UPDATE sessions
               SET completed_at = %s, date = %s
             WHERE id = %s
            """,
            (_NOW, _TODAY, sid),
        )
    window = compute_accuracy_window(user_id)
    assert window.sample == 0
    outcome = maybe_calibrate(user_id, now=_NOW)
    assert not outcome.changed
    # **NOT `… or window.sample < 30`, and the disjunction was worse than
    # permissive: `window.sample == 0` is asserted three lines above and
    # `window` is not recomputed, so the right branch was a TAUTOLOGY and the
    # assertion said nothing at all about `accuracy_30`.** It passed whether the
    # calibrator returned None or returned a number. Found by W13-i's sweep for
    # the shape #345 describes. The left branch is the real claim: with a
    # zero-sample window there is no accuracy to report.
    assert outcome.accuracy_30 is None
    assert _logs(user_id) == []
    assert get_user(user_id).cefr_level == "B1"  # type: ignore[union-attr]


def test_same_day_upsert_refreshes_accuracy(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, level="B1")
    _insert_scored_quiz(
        user_id, _TODAY, correct=20, answered=30, completed_at=_NOW - timedelta(hours=2)
    )
    maybe_calibrate(user_id, now=_NOW)
    first = _logs(user_id)[0]["accuracy_30"]
    assert first is not None
    assert abs(float(first) - (20 / 30)) < 1e-6

    _insert_scored_quiz(
        user_id, _TODAY, correct=30, answered=30, completed_at=_NOW - timedelta(hours=1)
    )
    # Newest sessions first: 30/30 then part of older → accuracy rises.
    maybe_calibrate(user_id, now=_NOW)
    logs = _logs(user_id)
    assert len(logs) == 1
    assert float(logs[0]["accuracy_30"]) > float(first)


def test_paused_user_no_calibration(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, level="B1")
    _seed_high_accuracy_sessions(user_id)
    for i in range(1, 10):
        _insert_log(user_id, _TODAY - timedelta(days=i), accuracy=0.90)
    with connection() as conn:
        conn.execute(
            """
            UPDATE users SET paused_until = %s WHERE id = %s
            """,
            (_TODAY + timedelta(days=7), user_id),
        )
    outcome = maybe_calibrate(user_id, now=_NOW)
    assert not outcome.changed
    assert _logs(user_id)  # prior seeds remain
    assert all(r["date"] != _TODAY for r in _logs(user_id))
    assert get_user(user_id).cefr_level == "B1"  # type: ignore[union-attr]


def test_no_guilt_in_s12_copy() -> None:
    banned = re.compile(
        r"missed|failed|broke|wrong!|should have|😞|😢|😭|👎",
        re.IGNORECASE,
    )
    for s in s12_user_facing_strings():
        assert banned.search(s) is None, s
    assert banned.search(texts.LEVEL_RAISE.format(level="B2")) is None
