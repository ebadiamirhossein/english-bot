"""S10 motivation engine — nudge ladder, Sunday report, resolved_types."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import texts
from app.db import close_pool, connection
from app.handlers.nudge import on_nudge_callback
from app.handlers.quiz import quiz_effective_total
from app.scheduler import (
    ANKI_FIRST_SECONDS,
    NUDGE_FIRST_SECONDS,
    SUNDAY_REPORT_FIRST_SECONDS,
)
from app.services.errors import mark_result, resolved_types, top_error_types
from app.services.motivation import (
    EARLY_LIMIT,
    MotivationUser,
    assemble_sunday_report,
    deliver_nudges_for_user,
    deliver_sunday_report,
    format_active_days_line,
    format_nudge_message,
    is_user_due_for_sunday_report,
    list_motivation_users,
    s10_button_labels,
    s10_user_facing_strings,
    sessions_due_for_nudge,
    task_still_open,
)
from app.services.sessions import (
    bot_initiated_count,
    complete_session,
    daily_nudges_sent,
    get_session_by_id,
    has_anki_session_on,
    has_sunday_report_session_on,
    increment_bot_messages,
    insert_session,
    local_today,
    set_session_delivered_at,
)
from app.services.users import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_510_000_000

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
) -> None:
    save_onboarding(
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


def _mot_user(tid: int, *, tz: str = "Europe/Vilnius") -> MotivationUser:
    users = [u for u in list_motivation_users() if u.telegram_user_id == tid]
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
    _onboard(tid)
    eid = _insert_error(
        tid,
        created_at=date.today() - timedelta(days=25),
        streak_right=4,
    )
    mark_result(eid, True)
    labels = resolved_types(tid)
    assert any("Preposition" in lab for lab in labels)


def test_resolved_types_five_inside_two_weeks_does_not(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    eid = _insert_error(
        tid,
        created_at=date.today() - timedelta(days=10),
        streak_right=4,
    )
    mark_result(eid, True)
    assert resolved_types(tid) == []


def test_resolved_types_wrong_resets(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    eid = _insert_error(
        tid,
        created_at=date.today() - timedelta(days=30),
        streak_right=5,
        resolved=True,
        resolved_at=date.today(),
    )
    assert resolved_types(tid)
    mark_result(eid, False)
    assert resolved_types(tid) == []


def test_resolved_types_ten_row_mixed_absent(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_error(
        tid,
        created_at=date.today() - timedelta(days=40),
        streak_right=5,
        resolved=True,
        resolved_at=date.today() - timedelta(days=1),
    )
    for _ in range(9):
        _insert_error(tid, resolved=False, streak_right=0)
    assert resolved_types(tid) == []


def test_top_error_types_orders_unresolved(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    for _ in range(3):
        _insert_error(tid, error_type="preposition")
    _insert_error(tid, error_type="quantifier_modifier")
    top = top_error_types(tid, n=2)
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


def test_sunday_report_leads_with_progress_not_shortfall(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 8, 9)
    body = assemble_sunday_report(tid, local_day=day, why_statement=None)
    assert body.startswith(texts.SUNDAY_LEAD_KEEPING) or "Quiet" in body
    assert not body.startswith(texts.SUNDAY_SHORTFALL)


def test_sunday_report_leads_with_resolved_types(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_error(
        tid,
        created_at=date.today() - timedelta(days=40),
        streak_right=5,
        resolved=True,
        resolved_at=date.today(),
    )
    body = assemble_sunday_report(
        tid, local_day=date.today(), why_statement=None
    )
    assert body.startswith("Quiet this week:")
    assert "Preposition" in body


# --- nudge ladder -------------------------------------------------------------


def test_nudge_ladder_3h_6h_never_third(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    user = _mot_user(tid)
    day = local_today("Europe/Vilnius", _MON_MORNING)
    delivered = _MON_MORNING
    sid = _open_quiz(tid, day, delivered_at=delivered)
    app = _mock_app()

    at_plus_2h = delivered + timedelta(hours=2)
    assert sessions_due_for_nudge(user, at_plus_2h) == []

    at_plus_3h = delivered + timedelta(hours=3)
    actions = asyncio.run(deliver_nudges_for_user(app, user, now=at_plus_3h))
    assert actions == ["sent_first"]
    assert daily_nudges_sent(tid, day) == 1

    actions2 = asyncio.run(deliver_nudges_for_user(app, user, now=at_plus_3h))
    assert actions2 == []
    assert daily_nudges_sent(tid, day) == 1

    at_plus_6h = delivered + timedelta(hours=6)
    actions3 = asyncio.run(deliver_nudges_for_user(app, user, now=at_plus_6h))
    assert actions3 == ["sent_second"]
    assert daily_nudges_sent(tid, day) == 2

    at_plus_9h = delivered + timedelta(hours=9)
    actions4 = asyncio.run(deliver_nudges_for_user(app, user, now=at_plus_9h))
    assert actions4 == []
    with connection() as conn:
        row = conn.execute(
            "SELECT nudges_sent FROM sessions WHERE id = %s", (sid,)
        ).fetchone()
    assert int(row["nudges_sent"]) == 2


def test_second_nudge_copy_differs_and_offers_smaller(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = local_today("Europe/Vilnius", _MON_MORNING)
    sid = _open_quiz(tid, day, delivered_at=_MON_MORNING)
    from app.services.sessions import list_open_nudgeable_sessions

    sessions = list_open_nudgeable_sessions(tid)
    assert sessions
    s0 = sessions[0]
    first_body, first_kb = format_nudge_message(s0)
    with connection() as conn:
        conn.execute(
            "UPDATE sessions SET nudges_sent = 1 WHERE id = %s", (sid,)
        )
    s1 = list_open_nudgeable_sessions(tid)[0]
    second_body, second_kb = format_nudge_message(s1)
    assert first_body != second_body
    assert first_kb is None
    assert second_kb is not None
    assert "2" in second_body or "two" in second_body.lower()
    button = second_kb.inline_keyboard[0][0]
    assert button.text == texts.BTN_NUDGE_JUST_2
    assert f"nudge:short:{sid}" == button.callback_data


def test_completed_before_3h_no_nudge(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    user = _mot_user(tid)
    day = local_today("Europe/Vilnius", _MON_MORNING)
    sid = _open_quiz(tid, day, delivered_at=_MON_MORNING)
    complete_session(sid, 1.0)
    app = _mock_app()
    actions = asyncio.run(
        deliver_nudges_for_user(
            app, user, now=_MON_MORNING + timedelta(hours=4)
        )
    )
    assert actions == []
    assert app.bot.send_message.await_count == 0


def test_ceiling_suppresses_nudge_no_increment(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    user = _mot_user(tid)
    day = local_today("Europe/Vilnius", _MON_MORNING)
    sid = _open_quiz(tid, day, delivered_at=_MON_MORNING)
    for _ in range(3):
        increment_bot_messages(tid, day)
    assert bot_initiated_count(tid, day) == 3
    app = _mock_app()
    with caplog.at_level(logging.WARNING):
        actions = asyncio.run(
            deliver_nudges_for_user(
                app, user, now=_MON_MORNING + timedelta(hours=3)
            )
        )
    assert actions == ["skipped_ceiling"]
    with connection() as conn:
        row = conn.execute(
            "SELECT nudges_sent FROM sessions WHERE id = %s", (sid,)
        ).fetchone()
    assert int(row["nudges_sent"]) == 0
    assert any("message_ceiling" in r.message for r in caplog.records)


def test_nudge_dual_timezone(cleanup_user: int, fake_telegram_id: int) -> None:
    """Tokyo and Vilnius each get nudges on their own local clock."""
    tid_v = cleanup_user
    tid_t = fake_telegram_id + 1
    try:
        _onboard(tid_v, tz="Europe/Vilnius")
        _onboard(tid_t, tz="Asia/Tokyo")
        delivered = datetime(2026, 8, 3, 2, 0, tzinfo=timezone.utc)
        day_v = local_today("Europe/Vilnius", delivered)
        day_t = local_today("Asia/Tokyo", delivered)
        _open_quiz(tid_v, day_v, delivered_at=delivered)
        _open_quiz(tid_t, day_t, delivered_at=delivered)
        user_v = _mot_user(tid_v, tz="Europe/Vilnius")
        user_t = _mot_user(tid_t, tz="Asia/Tokyo")
        app = _mock_app()
        now = delivered + timedelta(hours=3)
        asyncio.run(deliver_nudges_for_user(app, user_v, now=now))
        asyncio.run(deliver_nudges_for_user(app, user_t, now=now))
        assert daily_nudges_sent(tid_v, day_v) == 1
        assert daily_nudges_sent(tid_t, day_t) == 1
    finally:
        _delete_user(tid_t)


def test_paused_user_no_nudge_no_report(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = local_today("Europe/Vilnius", _MON_MORNING)
    with connection() as conn:
        conn.execute(
            "UPDATE users SET paused_until = %s WHERE telegram_user_id = %s",
            (day + timedelta(days=30), tid),
        )
    user = _mot_user(tid)
    _open_quiz(tid, day, delivered_at=_MON_MORNING)
    app = _mock_app()
    actions = asyncio.run(
        deliver_nudges_for_user(
            app, user, now=_MON_MORNING + timedelta(hours=4)
        )
    )
    assert actions == []
    assert is_user_due_for_sunday_report(user, _SUNDAY_EVENING) is False
    assert (
        asyncio.run(deliver_sunday_report(app, user, now=_SUNDAY_EVENING))
        == "skipped"
    )


def test_sunday_report_idempotent(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    user = _mot_user(tid)
    app = _mock_app()
    action = asyncio.run(deliver_sunday_report(app, user, now=_SUNDAY_EVENING))
    assert action == "sent"
    day = local_today("Europe/Vilnius", _SUNDAY_EVENING)
    assert has_sunday_report_session_on(tid, day)
    action2 = asyncio.run(
        deliver_sunday_report(app, user, now=_SUNDAY_EVENING)
    )
    assert action2 == "skipped"
    assert app.bot.send_message.await_count == 1


def test_anki_not_due_on_sunday_evening(cleanup_user: int) -> None:
    """S11: Anki moved to Saturday — Sunday evening must not write anki_export."""
    tid = cleanup_user
    _onboard(tid)
    from app.scheduler import EligibleUser, is_user_due_for_anki

    anki_user = EligibleUser(
        telegram_user_id=tid,
        timezone="Europe/Vilnius",
        morning_time=time(8, 0),
        paused_until=None,
        evening_time=time(21, 0),
    )
    assert is_user_due_for_anki(anki_user, _SUNDAY_EVENING) is False
    day = local_today("Europe/Vilnius", _SUNDAY_EVENING)
    assert not has_anki_session_on(tid, day)


def test_scheduler_report_before_anki_offsets() -> None:
    assert SUNDAY_REPORT_FIRST_SECONDS < ANKI_FIRST_SECONDS
    assert ANKI_FIRST_SECONDS < NUDGE_FIRST_SECONDS


def test_task_still_open_until_0300_next_night() -> None:
    session_date = date(2026, 8, 3)
    tue_0259 = datetime(2026, 8, 3, 23, 59, tzinfo=timezone.utc)
    assert task_still_open(session_date, "Europe/Vilnius", tue_0259)
    tue_0300 = datetime(2026, 8, 4, 0, 0, tzinfo=timezone.utc)
    assert not task_still_open(session_date, "Europe/Vilnius", tue_0300)


# --- smaller version / early complete -----------------------------------------


def test_just_do_2_completes_quiz_with_score(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = local_today("Europe/Vilnius", _MON_MORNING)
    payload = _quiz_payload(answered=2, correct_count=1, index=2)
    payload["early_limit"] = EARLY_LIMIT
    sid = _open_quiz(tid, day, delivered_at=_MON_MORNING, payload=payload)

    msg = MagicMock()
    msg.reply_text = AsyncMock()
    cq = MagicMock()
    cq.data = f"nudge:short:{sid}"
    cq.answer = AsyncMock()
    cq.message = msg
    update = MagicMock()
    update.callback_query = cq
    update.effective_user = MagicMock(id=tid)
    context = MagicMock()
    context.bot = MagicMock()
    context.bot.edit_message_text = AsyncMock()

    asyncio.run(on_nudge_callback(update, context))
    sess = get_session_by_id(tid, sid)
    assert sess is not None
    assert sess.completed is True
    assert sess.score == pytest.approx(0.5)  # 1/2


def test_quiz_effective_total_honours_early_limit() -> None:
    payload = _quiz_payload(early_limit=2)
    assert quiz_effective_total(payload) == 2
    assert quiz_effective_total(_quiz_payload()) == 5


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
