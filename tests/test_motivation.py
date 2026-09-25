"""S10 motivation engine — nudge ladder, Sunday report, resolved_types."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.db import close_pool, connection
from core.services.errors import mark_result, resolved_types, top_error_types
from core.services.motivation import (
    MotivationUser,
    assemble_sunday_report,
    format_active_days_line,
    list_motivation_users,
    s10_button_labels,
    s10_user_facing_strings,
    task_still_open,
)
from core.services.sessions import (
    has_anki_session_on,
    insert_session,
    local_today,
    set_session_delivered_at,
)
from core.services.identity import save_onboarding
FAKE_TELEGRAM_ID_BASE = 9_510_000_000
_TG_ADDRESS_BASE = 9_000_000_000

# Monday 2026-08-03 08:00 Vilnius (UTC+3)
_MON_MORNING = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)
# Sunday 2026-08-09 21:05 Vilnius
_SUNDAY_EVENING = datetime(2026, 8, 9, 18, 5, tzinfo=timezone.utc)


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


def _onboard(
    tid: int,
    *,
    tz: str = "Europe/Vilnius",
    evening: str = "21:00",
    why: str = "Speak without freezing up",
) -> int:
    user_id = save_onboarding(
        tid,
        {
            "name": "Motivation Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": why,
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": "08:00",
            "evening_time": evening,
        },
    )
    with connection() as conn:
        conn.execute(
            "UPDATE users SET timezone = %s WHERE telegram_user_id = %s",
            (tz, tid),
        )
    return user_id


def _mot_user(tid: int, *, tz: str = "Europe/Vilnius") -> MotivationUser:
    users = [u for u in list_motivation_users() if u.id == tid]
    assert len(users) == 1
    u = users[0]
    assert u.timezone == tz
    return u


def _quiz_payload(**extra: object) -> dict:
    base = {
        "index": 0,
        "correct_count": 0,
        "answered": 0,
        "chat_id": 1,
        "message_id": 42,
        "questions": [
            {
                "error_id": 1,
                "format": "gap",
                "prompt": f"Q{i} ___",
                "accept": ["a"],
            }
            for i in range(5)
        ],
    }
    base.update(extra)
    return base


def _open_quiz(
    tid: int,
    day: date,
    *,
    delivered_at: datetime,
    payload: dict | None = None,
) -> int:
    sid = insert_session(
        tid, "quiz", day, payload=payload or _quiz_payload(), completed=False
    )
    set_session_delivered_at(tid, sid, delivered_at)
    return sid


def _mock_app() -> MagicMock:
    app = MagicMock()
    app.bot = MagicMock()
    app.bot.send_message = AsyncMock()
    return app


# --- resolved_types -----------------------------------------------------------


def _insert_error(
    tid: int,
    *,
    error_type: str = "preposition",
    created_at: date | None = None,
    streak_right: int = 0,
    resolved: bool = False,
    resolved_at: date | None = None,
) -> int:
    created = created_at or date.today()
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO errors (
                user_id, source, you_said, correct_form, error_type,
                explanation, murphy_units, streak_right, times_right,
                times_wrong, next_review, resolved, resolved_at, created_at
            ) VALUES (
                %s, 'quiz', 'in Monday', 'on Monday', %s,
                'on for days', '121-136', %s, 0, 1,
                CURRENT_DATE, %s, %s, %s::timestamp
            )
            RETURNING id
            """,
            (
                tid,
                error_type,
                streak_right,
                resolved,
                resolved_at,
                created.isoformat(),
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def test_resolved_types_five_correct_spanning_three_weeks(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    eid = _insert_error(
        user_id,
        created_at=date.today() - timedelta(days=25),
        streak_right=4,
    )
    mark_result(eid, True)
    labels = resolved_types(user_id)
    assert any("Preposition" in lab for lab in labels)


def test_resolved_types_five_inside_two_weeks_does_not(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    eid = _insert_error(
        user_id,
        created_at=date.today() - timedelta(days=10),
        streak_right=4,
    )
    mark_result(eid, True)
    assert resolved_types(user_id) == []


def test_resolved_types_wrong_resets(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    eid = _insert_error(
        user_id,
        created_at=date.today() - timedelta(days=30),
        streak_right=5,
        resolved=True,
        resolved_at=date.today(),
    )
    assert resolved_types(user_id)
    mark_result(eid, False)
    assert resolved_types(user_id) == []


def test_resolved_types_ten_row_mixed_absent(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _insert_error(
        user_id,
        created_at=date.today() - timedelta(days=40),
        streak_right=5,
        resolved=True,
        resolved_at=date.today() - timedelta(days=1),
    )
    for _ in range(9):
        _insert_error(user_id, resolved=False, streak_right=0)
    assert resolved_types(user_id) == []


def test_top_error_types_orders_unresolved(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    for _ in range(3):
        _insert_error(user_id, error_type="preposition")
    _insert_error(user_id, error_type="quantifier_modifier")
    top = top_error_types(user_id, n=2)
    assert top[0] == "Prepositions"


# --- active days copy ---------------------------------------------------------


def test_active_days_copy_bands() -> None:
    line4 = format_active_days_line(4)
    line5 = format_active_days_line(5)
    line7 = format_active_days_line(7)
    assert "4 of 5" in line4
    assert "/7" not in line4
    assert "5 active days" in line5
    assert "/5" not in line5
    assert "7 active days" in line7
    assert "7/5" not in line7
    assert "/7" not in line7


def test_sunday_report_leads_with_resolved_types(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _insert_error(
        user_id,
        created_at=date.today() - timedelta(days=40),
        streak_right=5,
        resolved=True,
        resolved_at=date.today(),
    )
    body = assemble_sunday_report(
        user_id, local_day=date.today(), why_statement=None
    )
    assert body.startswith("Quiet this week:")
    assert "Preposition" in body


# --- nudge ladder -------------------------------------------------------------


def test_task_still_open_until_0300_next_night() -> None:
    session_date = date(2026, 8, 3)
    tue_0259 = datetime(2026, 8, 3, 23, 59, tzinfo=timezone.utc)
    assert task_still_open(session_date, "Europe/Vilnius", tue_0259)
    tue_0300 = datetime(2026, 8, 4, 0, 0, tzinfo=timezone.utc)
    assert not task_still_open(session_date, "Europe/Vilnius", tue_0300)


# --- smaller version / early complete -----------------------------------------


# --- no-guilt / labels --------------------------------------------------------


def test_no_guilt_in_nudge_and_report_copy() -> None:
    banned = re.compile(
        r"\bmissed\b|\bfailed\b|\bbroke\b|wrong!|should have|"
        r"😞|😢|😔|☹️|🙁|😟|😤|😠",
        re.IGNORECASE,
    )
    for s in s10_user_facing_strings():
        assert banned.search(s) is None, s


def test_s10_button_labels_max_20() -> None:
    for label in s10_button_labels():
        assert len(label) <= 20, label
