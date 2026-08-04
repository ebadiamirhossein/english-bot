"""Streak / freeze / rescue tests — ARCHITECTURE §8 mandatory suite (S4)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.db import close_pool, connection
from app.handlers.quiz import format_completion_message
from app.services.sessions import (
    complete_open_free_practice,
    complete_session,
    insert_session,
)
from app.services.streaks import (
    evaluate_pending,
    get_streak,
    is_in_rescue,
    reset_monthly_freezes,
    roll_over_day,
)
from app.services.users import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_340_000_000


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


def _onboard(tid: int, *, tz: str = "Europe/Vilnius") -> None:
    save_onboarding(
        tid,
        {
            "name": "Streak Test",
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
    with connection() as conn:
        conn.execute(
            "UPDATE users SET timezone = %s WHERE telegram_user_id = %s",
            (tz, tid),
        )


def _set_streak(
    tid: int,
    *,
    current: int = 0,
    longest: int = 0,
    tokens: int = 2,
    last_active: date | None = None,
    last_eval: date | None = None,
    rescue_until: date | None = None,
    total_active: int = 0,
    freeze_reset_on: date | None = None,
) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE streaks
               SET current_streak = %s,
                   longest_streak = %s,
                   freeze_tokens = %s,
                   last_active_date = %s,
                   last_evaluated_date = %s,
                   rescue_mode_until = %s,
                   total_active_days = %s,
                   freeze_reset_on = %s,
                   pending_freeze_notice = FALSE
             WHERE user_id = %s
            """,
            (
                current,
                longest,
                tokens,
                last_active,
                last_eval,
                rescue_until,
                total_active,
                freeze_reset_on,
                tid,
            ),
        )


def _quiz(tid: int, day: date, *, completed: bool) -> int:
    sid = insert_session(tid, "quiz", day, completed=False)
    if completed:
        complete_session(sid, 1.0)
    return sid


def _free_practice(tid: int, day: date) -> int:
    return insert_session(tid, "free_practice", day, completed=False)


def test_completed_day_increments_streak(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 7, 10)
    _set_streak(tid, current=5, longest=5, total_active=5, last_active=date(2026, 7, 9), last_eval=date(2026, 7, 9))
    _quiz(tid, day, completed=True)

    result = roll_over_day(tid, day)
    streak = get_streak(tid)

    assert result.outcome == "active"
    assert streak.current_streak == 6
    assert streak.total_active_days == 6
    assert streak.last_active_date == day
    assert streak.last_evaluated_date == day


def test_longest_streak_updates_only_when_exceeded(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 7, 10)
    _set_streak(tid, current=3, longest=10, total_active=3, last_eval=date(2026, 7, 9))
    _quiz(tid, day, completed=True)

    roll_over_day(tid, day)
    assert get_streak(tid).current_streak == 4
    assert get_streak(tid).longest_streak == 10

    day2 = date(2026, 7, 11)
    _quiz(tid, day2, completed=True)
    # Push current past longest
    _set_streak(
        tid,
        current=10,
        longest=10,
        total_active=10,
        last_eval=day,
        last_active=day,
        tokens=2,
    )
    roll_over_day(tid, day2)
    assert get_streak(tid).current_streak == 11
    assert get_streak(tid).longest_streak == 11


def test_missed_with_tokens_consumes_freeze(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 7, 10)
    _set_streak(
        tid,
        current=6,
        longest=6,
        tokens=2,
        last_active=date(2026, 7, 9),
        last_eval=date(2026, 7, 9),
    )
    _quiz(tid, day, completed=False)

    result = roll_over_day(tid, day)
    streak = get_streak(tid)

    assert result.outcome == "missed"
    assert result.freeze_consumed is True
    assert streak.current_streak == 6
    assert streak.freeze_tokens == 1
    assert streak.last_active_date == date(2026, 7, 9)
    assert streak.pending_freeze_notice is True


def test_missed_without_tokens_resets_streak(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 7, 10)
    _set_streak(
        tid,
        current=6,
        longest=6,
        tokens=0,
        last_active=date(2026, 7, 9),
        last_eval=date(2026, 7, 9),
    )
    _quiz(tid, day, completed=False)

    result = roll_over_day(tid, day)
    streak = get_streak(tid)

    assert result.outcome == "missed"
    assert result.freeze_consumed is False
    assert streak.current_streak == 0
    assert streak.freeze_tokens == 0
    assert streak.last_active_date == date(2026, 7, 9)


def test_no_session_is_neutral(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 7, 10)
    _set_streak(
        tid,
        current=4,
        longest=4,
        tokens=2,
        last_active=date(2026, 7, 8),
        last_eval=date(2026, 7, 9),
        total_active=4,
    )

    result = roll_over_day(tid, day)
    streak = get_streak(tid)

    assert result.outcome == "neutral"
    assert streak.current_streak == 4
    assert streak.freeze_tokens == 2
    assert streak.total_active_days == 4
    assert streak.last_active_date == date(2026, 7, 8)
    assert streak.last_evaluated_date == day


def test_roll_over_day_idempotent(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 7, 10)
    _set_streak(tid, current=2, longest=2, tokens=2, last_eval=date(2026, 7, 9))
    _quiz(tid, day, completed=True)

    first = roll_over_day(tid, day)
    second = roll_over_day(tid, day)
    streak = get_streak(tid)

    assert first.outcome == "active"
    assert second.outcome == "skipped"
    assert streak.current_streak == 3
    assert streak.total_active_days == 1
    assert streak.freeze_tokens == 2


def test_three_misses_set_rescue(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    d1, d2, d3 = date(2026, 7, 8), date(2026, 7, 9), date(2026, 7, 10)
    _set_streak(tid, current=5, tokens=2, last_eval=date(2026, 7, 7))
    for d in (d1, d2, d3):
        _quiz(tid, d, completed=False)

    roll_over_day(tid, d1)
    assert get_streak(tid).rescue_mode_until is None
    roll_over_day(tid, d2)
    assert get_streak(tid).rescue_mode_until is None
    result = roll_over_day(tid, d3)
    assert result.rescue_started is True
    assert get_streak(tid).rescue_mode_until == d3 + timedelta(days=7)
    assert is_in_rescue(tid, d3 + timedelta(days=3))
    assert not is_in_rescue(tid, d3 + timedelta(days=8))


def test_freeze_covered_miss_counts_toward_rescue(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    d1, d2, d3 = date(2026, 7, 8), date(2026, 7, 9), date(2026, 7, 10)
    _set_streak(tid, current=5, tokens=2, last_eval=date(2026, 7, 7))
    for d in (d1, d2, d3):
        _quiz(tid, d, completed=False)

    roll_over_day(tid, d1)  # freeze
    roll_over_day(tid, d2)  # freeze
    assert get_streak(tid).current_streak == 5
    assert get_streak(tid).freeze_tokens == 0
    roll_over_day(tid, d3)  # no tokens → streak 0, but rescue from 3 misses
    streak = get_streak(tid)
    assert streak.current_streak == 0
    assert streak.rescue_mode_until == d3 + timedelta(days=7)


def test_completing_during_rescue_does_not_clear(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    until = date(2026, 7, 17)
    day = date(2026, 7, 12)
    _set_streak(
        tid,
        current=0,
        tokens=2,
        last_eval=date(2026, 7, 11),
        rescue_until=until,
    )
    _quiz(tid, day, completed=True)

    roll_over_day(tid, day)
    assert get_streak(tid).rescue_mode_until == until
    assert get_streak(tid).current_streak == 1
    assert is_in_rescue(tid, day)


def test_offline_seven_days_evaluated_in_order(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    # Start: streak 3, 2 freezes, last evaluated Sun Jul 5
    start = date(2026, 7, 5)
    _set_streak(
        tid,
        current=3,
        longest=3,
        tokens=2,
        last_active=start,
        last_eval=start,
        total_active=3,
    )
    # Mon–Sun Jul 6–12: incomplete quizzes
    days = [start + timedelta(days=i) for i in range(1, 8)]
    for d in days:
        _quiz(tid, d, completed=False)

    # Local Mon Jul 13 04:00 Vilnius — window closed through Jul 12
    now = datetime(2026, 7, 13, 1, 0, tzinfo=timezone.utc)  # 04:00 Vilnius (UTC+3)
    results = evaluate_pending(tid, timezone="Europe/Vilnius", now=now)

    assert [r.day for r in results] == days
    streak = get_streak(tid)
    # 2 freezes consumed on first two misses; then streak resets; rescue on day 3
    assert streak.freeze_tokens == 0
    assert streak.current_streak == 0
    assert streak.rescue_mode_until == days[2] + timedelta(days=7)
    assert streak.last_evaluated_date == days[-1]
    assert streak.total_active_days == 3


def test_monthly_reset_sets_tokens_idempotent(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _set_streak(tid, tokens=0, freeze_reset_on=None)
    # 1 Aug 2026 00:30 Vilnius
    now = datetime(2026, 7, 31, 21, 30, tzinfo=timezone.utc)
    assert local_date(now, "Europe/Vilnius") == date(2026, 8, 1)

    reset_monthly_freezes(now=now)
    assert get_streak(tid).freeze_tokens == 2
    assert get_streak(tid).freeze_reset_on == date(2026, 8, 1)

    reset_monthly_freezes(now=now)
    assert get_streak(tid).freeze_tokens == 2
    assert get_streak(tid).freeze_reset_on == date(2026, 8, 1)


def test_unused_tokens_do_not_carry_over(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _set_streak(tid, tokens=2, freeze_reset_on=date(2026, 7, 1))
    now = datetime(2026, 7, 31, 21, 30, tzinfo=timezone.utc)
    reset_monthly_freezes(now=now)
    assert get_streak(tid).freeze_tokens == 2
    assert get_streak(tid).freeze_reset_on == date(2026, 8, 1)


def test_monthly_reset_per_user_timezone() -> None:
    tokyo_id = FAKE_TELEGRAM_ID_BASE + 1
    vilnius_id = FAKE_TELEGRAM_ID_BASE + 2
    _delete_user(tokyo_id)
    _delete_user(vilnius_id)
    try:
        _onboard(tokyo_id, tz="Asia/Tokyo")
        _onboard(vilnius_id, tz="Europe/Vilnius")
        _set_streak(tokyo_id, tokens=0, freeze_reset_on=None)
        _set_streak(vilnius_id, tokens=0, freeze_reset_on=None)

        # 1 Aug 2026 00:30 Tokyo = 31 Jul 15:30 UTC — Vilnius still 31 Jul
        now_tokyo_first = datetime(2026, 7, 31, 15, 30, tzinfo=timezone.utc)
        assert local_date(now_tokyo_first, "Asia/Tokyo") == date(2026, 8, 1)
        assert local_date(now_tokyo_first, "Europe/Vilnius") == date(2026, 7, 31)

        reset_monthly_freezes(now=now_tokyo_first)
        assert get_streak(tokyo_id).freeze_tokens == 2
        assert get_streak(tokyo_id).freeze_reset_on == date(2026, 8, 1)
        assert get_streak(vilnius_id).freeze_tokens == 0
        assert get_streak(vilnius_id).freeze_reset_on is None

        # Same tick again — Tokyo not reset twice
        reset_monthly_freezes(now=now_tokyo_first)
        assert get_streak(tokyo_id).freeze_reset_on == date(2026, 8, 1)
        assert get_streak(tokyo_id).freeze_tokens == 2

        # Later: Vilnius 1 Aug 00:30
        now_vilnius_first = datetime(2026, 7, 31, 21, 30, tzinfo=timezone.utc)
        assert local_date(now_vilnius_first, "Europe/Vilnius") == date(2026, 8, 1)
        reset_monthly_freezes(now=now_vilnius_first)
        assert get_streak(vilnius_id).freeze_tokens == 2
        assert get_streak(vilnius_id).freeze_reset_on == date(2026, 8, 1)
        # Tokyo still once
        assert get_streak(tokyo_id).freeze_reset_on == date(2026, 8, 1)
        reset_monthly_freezes(now=now_vilnius_first)
        assert get_streak(vilnius_id).freeze_reset_on == date(2026, 8, 1)
    finally:
        _delete_user(tokyo_id)
        _delete_user(vilnius_id)


def test_free_practice_with_correction_is_active(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 7, 10)
    _set_streak(tid, current=4, longest=4, tokens=2, last_eval=date(2026, 7, 9), total_active=4)
    _free_practice(tid, day)
    assert complete_open_free_practice(tid, day) is True

    result = roll_over_day(tid, day)
    streak = get_streak(tid)
    assert result.outcome == "active"
    assert streak.current_streak == 5
    assert streak.freeze_tokens == 2
    assert streak.total_active_days == 5


def test_free_practice_without_messages_is_neutral(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 7, 10)
    _set_streak(tid, current=4, longest=4, tokens=2, last_eval=date(2026, 7, 9), total_active=4)
    _free_practice(tid, day)

    result = roll_over_day(tid, day)
    streak = get_streak(tid)
    assert result.outcome == "neutral"
    assert streak.current_streak == 4
    assert streak.freeze_tokens == 2
    assert streak.total_active_days == 4


def test_free_practice_never_consumes_freeze(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 7, 10)
    _set_streak(tid, current=4, tokens=1, last_eval=date(2026, 7, 9))
    _free_practice(tid, day)

    roll_over_day(tid, day)
    assert get_streak(tid).freeze_tokens == 1
    assert get_streak(tid).pending_freeze_notice is False


def test_incomplete_quiz_plus_completed_voice_is_active(cleanup_user: int) -> None:
    """S5: Active wins over Missed when both exist on the same local day.

    Voice-then-ignored-quiz (or ignore-quiz-then-voice) must not burn a freeze.
    """
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 7, 10)
    _set_streak(
        tid,
        current=5,
        longest=5,
        tokens=2,
        total_active=5,
        last_active=date(2026, 7, 9),
        last_eval=date(2026, 7, 9),
    )
    # Voice first (completed), then incomplete quiz with higher id — the
    # dangerous insert order after morning delivery is no longer blocked by voice.
    insert_session(
        tid,
        "voice",
        day,
        payload={"messages": [], "turn_count": 1},
        completed=True,
    )
    _quiz(tid, day, completed=False)

    result = roll_over_day(tid, day)
    streak = get_streak(tid)

    assert result.outcome == "active"
    assert result.freeze_consumed is False
    assert streak.freeze_tokens == 2
    assert streak.pending_freeze_notice is False
    assert streak.last_active_date == day
    assert streak.current_streak == 6
    assert streak.total_active_days == 6


def test_completing_quiz_does_not_change_last_evaluated(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 7, 10)
    _set_streak(tid, current=5, last_eval=date(2026, 7, 9), last_active=date(2026, 7, 9))
    sid = _quiz(tid, day, completed=False)
    before = get_streak(tid).last_evaluated_date

    complete_session(sid, 0.8)
    # Optimistic display only — no roll_over_day on completion.
    msg = format_completion_message(
        correct_count=4, total=5, streak_days=get_streak(tid).current_streak + 1
    )
    assert "🔥 6-day streak" in msg
    assert get_streak(tid).last_evaluated_date == before
    assert get_streak(tid).current_streak == 5


def local_date(now: datetime, tz: str) -> date:
    return now.astimezone(ZoneInfo(tz)).date()
