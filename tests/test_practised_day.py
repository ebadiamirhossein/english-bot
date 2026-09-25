"""W19 / #259: *did this learner practise today?* — one signal, three consumers.

`core.services.activity.practised_dates` reads five logs; the streak rollover,
`count_active_days` and the nudge ladder read it. Before W19 all three asked
`sessions.completed = TRUE`, which no `daily` row has ever carried, so a
learner on the web session every day read as inactive to every one of them.

Against the real dev database (the logs are joined across five tables and a
timezone; a fake would test the fake). The clock is never read: every date is
fixed (CLAUDE.md §3 rule 6).

**RED DEMONSTRATIONS (2026-09-25):** the three consumer tests —
`test_a_web_only_day_moves_the_streak`,
`test_count_active_days_counts_a_web_only_day` and
`test_a_learner_who_practised_is_not_nudged_that_day` — were run with
`packages/core/services/{streaks,sessions,motivation}.py` restored from HEAD
(`git stash push` of those three files) and failed: outcome `neutral` not
`active`, a count of 0 not 1, and the open quiz returned as due. The
`practised_dates` tests went red one arm at a time by commenting that arm out
of `_PRACTISED_DATES_SQL` (the writing arm's `is_english` filter by deleting
the line: the Farsi entry then counted).
"""

from __future__ import annotations

from datetime import date, time, timedelta, timezone

import psycopg
import pytest

from core.config import load_settings
from core.db import connection
from core.services import streaks as streaks_svc
from core.services.activity import practised_dates, practised_on
from core.services.motivation import MotivationUser, sessions_due_for_nudge
from core.services.sessions import count_active_days
from tests.support import progress_seed as seed

DAY = date(2026, 3, 10)  # a Tuesday


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def learner(db):
    made = seed.make_learner(db, "W19 practised", with_session=False)
    videos: list[int] = []
    yield type("L", (), {"user_id": made.user_id, "videos": videos})()
    seed.drop_learner(db, made.user_id)
    seed.drop_videos(db, videos)


def _dates(user_id: int, start: date = DAY - timedelta(days=3), end: date = DAY + timedelta(days=3)):
    with connection() as conn:
        return practised_dates(conn, user_id, start=start, end=end)


# ── the signal, one log at a time ────────────────────────────────────────────


def test_nothing_done_is_no_practice(learner) -> None:
    assert _dates(learner.user_id) == set()


def test_an_answered_item_is_practice(db, learner) -> None:
    seed.attempt(db, learner.user_id, "mcq", seed.at(DAY, 9))
    assert _dates(learner.user_id) == {DAY}


def test_a_graded_card_is_practice(db, learner) -> None:
    seed.review(db, learner.user_id, seed.at(DAY, 9))
    assert _dates(learner.user_id) == {DAY}


def test_a_turn_sent_is_practice(db, learner) -> None:
    seed.turns(db, learner.user_id, DAY, typed=1)
    assert _dates(learner.user_id) == {DAY}


def test_an_english_entry_is_practice_and_a_farsi_one_is_not(db, learner) -> None:
    """W16a's S2: a non-English entry spent a call and is not the learner's English."""
    seed.written(db, learner.user_id, DAY - timedelta(days=1), is_english=False)
    seed.written(db, learner.user_id, DAY, is_english=True)
    assert _dates(learner.user_id) == {DAY}


def test_a_video_watched_to_the_end_is_practice_and_one_assigned_is_not(db, learner) -> None:
    learner.videos.append(seed.watched(db, learner.user_id, DAY - timedelta(days=1), None))
    learner.videos.append(seed.watched(db, learner.user_id, DAY, seed.at(DAY, 20)))
    assert _dates(learner.user_id) == {DAY}


def test_opening_the_app_is_not_practice(db, learner) -> None:
    """#259's warning: a `daily` row is created by a GET, so counting it would
    make hydration count as practice."""
    db.execute(
        "INSERT INTO sessions (user_id, date, task_type, completed) VALUES (%s, %s, 'daily', FALSE)",
        (learner.user_id, DAY),
    )
    db.commit()
    assert _dates(learner.user_id) == set()


def test_the_day_is_the_learners_local_day(db, learner) -> None:
    """00:30 on the 11th in Vilnius is 22:30 UTC on the 10th, and it is the
    11th's practice — the learner's calendar, not the server's."""
    seed.attempt(db, learner.user_id, "mcq", seed.at(DAY + timedelta(days=1), 0, 30))
    assert _dates(learner.user_id) == {DAY + timedelta(days=1)}


# ── the three consumers ──────────────────────────────────────────────────────


def test_a_web_only_day_moves_the_streak(db, learner) -> None:
    """User action: a learner does the web session and nothing on Telegram."""
    seed.attempt(db, learner.user_id, "cloze_cued", seed.at(DAY, 9))
    result = streaks_svc.roll_over_day(learner.user_id, DAY)
    assert result.outcome == "active"
    assert result.current_streak == 1
    assert result.total_active_days == 1


def test_a_day_with_nothing_done_is_still_neutral(learner) -> None:
    """v2's rule is unchanged: a day with no session and no practice breaks nothing."""
    result = streaks_svc.roll_over_day(learner.user_id, DAY)
    assert result.outcome == "neutral"


def test_practice_beats_an_unfinished_v2_quiz(db, learner) -> None:
    """Active > Missed: an untouched Telegram quiz on a day the learner did the
    web session must not spend a freeze."""
    db.execute(
        "INSERT INTO sessions (user_id, date, task_type, completed, delivered_at) "
        "VALUES (%s, %s, 'quiz', FALSE, %s)",
        (learner.user_id, DAY, seed.at(DAY, 8)),
    )
    db.commit()
    seed.review(db, learner.user_id, seed.at(DAY, 21))
    result = streaks_svc.roll_over_day(learner.user_id, DAY)
    assert result.outcome == "active"
    assert result.freeze_consumed is False
    assert result.freeze_tokens == 2


def test_count_active_days_counts_a_web_only_day(db, learner) -> None:
    seed.turns(db, learner.user_id, DAY, voice=1)
    assert count_active_days(learner.user_id, start=DAY - timedelta(days=6), end=DAY) == 1


def test_count_active_days_does_not_count_one_day_twice(db, learner) -> None:
    """A v2 completed row and web practice on the same date are one day."""
    db.execute(
        "INSERT INTO sessions (user_id, date, task_type, completed) VALUES (%s, %s, 'quiz', TRUE)",
        (learner.user_id, DAY),
    )
    db.commit()
    seed.attempt(db, learner.user_id, "mcq", seed.at(DAY, 9))
    assert count_active_days(learner.user_id, start=DAY - timedelta(days=6), end=DAY) == 1


def test_a_learner_who_practised_is_not_nudged_that_day(db, learner) -> None:
    """#259's symptom: an open v2 quiz beside a finished web session was
    enough to nudge someone who had practised. CLAUDE.md §4."""
    db.execute(
        "INSERT INTO sessions (user_id, date, task_type, completed, delivered_at) "
        "VALUES (%s, %s, 'quiz', FALSE, %s)",
        (learner.user_id, DAY, seed.at(DAY, 8)),
    )
    db.commit()
    user = MotivationUser(
        id=learner.user_id,
        telegram_address=None,
        timezone="Europe/Vilnius",
        evening_time=time(21, 0),
        paused_until=None,
        why_statement=None,
    )
    late = seed.at(DAY, 22).astimezone(timezone.utc)

    # Positive control: nothing practised, so the open quiz IS due a nudge.
    assert [s.date for s in sessions_due_for_nudge(user, late)] == [DAY]

    seed.attempt(db, learner.user_id, "mcq", seed.at(DAY, 12))
    assert sessions_due_for_nudge(user, late) == []


def test_practised_on_is_the_same_signal(db, learner) -> None:
    seed.written(db, learner.user_id, DAY)
    with connection() as conn:
        assert practised_on(conn, learner.user_id, DAY) is True
        assert practised_on(conn, learner.user_id, DAY + timedelta(days=1)) is False


def test_an_unknown_user_practised_nothing() -> None:
    with connection() as conn:
        assert practised_dates(conn, -1, start=DAY, end=DAY) == set()
