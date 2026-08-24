"""S12 M13 anti-fossilization sweep."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.db import close_pool, connection
from apps.bot.handlers import quiz as quiz_handler
from core.services.errors import (
    get_error_for_user,
    mark_result,
    pick_fossil_retest_ids,
    resolved_types,
    run_monthly_fossil_sweep,
)
from core.services.sessions import (
    create_fossil_sweep_session,
    get_session_by_id,
    mark_fossil_retest_done,
    open_fossil_sweep_for_user,
)
from core.services.identity import save_onboarding
FAKE_TELEGRAM_ID_BASE = 9_521_000_000

# 1 Aug 2026 00:30 Vilnius
_FIRST_OF_MONTH = datetime(2026, 7, 31, 21, 30, tzinfo=timezone.utc)
_MONTH_START = date(2026, 8, 1)
_DAY = date(2026, 8, 5)
_NOW = datetime(2026, 8, 5, 5, 0, tzinfo=timezone.utc)


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
            "name": "Fossil Test",
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


def _insert_resolved(
    tid: int,
    *,
    error_type: str = "quantifier_modifier",
    resolved_at: date,
    you_said: str = "so much good",
) -> int:
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO errors (
                user_id, source, you_said, correct_form, error_type,
                explanation, next_review, resolved, resolved_at,
                streak_right, times_right
            ) VALUES (
                %s, 'text', %s, 'very good', %s,
                'Use very.', CURRENT_DATE, TRUE, %s,
                5, 5
            )
            RETURNING id
            """,
            (tid, you_said, error_type, resolved_at),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _error_row(eid: int) -> dict:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT resolved, resolved_at, unresolved_count, next_review,
                   you_said, correct_form, error_type
              FROM errors WHERE id = %s
            """,
            (eid,),
        ).fetchone()
    assert row is not None
    return dict(row)


def test_pick_aged_resolved_limit_two(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    old = _MONTH_START - timedelta(days=40)
    ids = [
        _insert_resolved(user_id, resolved_at=old, you_said=f"bad {i}")
        for i in range(4)
    ]
    # Too recent — excluded
    _insert_resolved(
        user_id,
        resolved_at=_MONTH_START - timedelta(days=5),
        you_said="recent",
        error_type="article_missing",
    )
    picked = pick_fossil_retest_ids(user_id, as_of=_MONTH_START, limit=2)
    assert len(picked) == 2
    assert set(picked).issubset(set(ids))


def test_monthly_sweep_queues_and_skips_paused(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    eid = _insert_resolved(user_id, resolved_at=_MONTH_START - timedelta(days=40))
    n = run_monthly_fossil_sweep(now=_FIRST_OF_MONTH)
    assert n >= 1
    fossil = open_fossil_sweep_for_user(user_id)
    assert fossil is not None
    assert eid in (fossil.payload or {}).get("pending", [])

    # Idempotent
    n2 = run_monthly_fossil_sweep(now=_FIRST_OF_MONTH)
    assert n2 == 0

    # Paused user — no queue
    tid2 = FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)
    try:
        tid2_id = _onboard(tid2)
        _insert_resolved(tid2_id, resolved_at=_MONTH_START - timedelta(days=40))
        with connection() as conn:
            conn.execute(
                """
                UPDATE users SET paused_until = %s
                 WHERE id = %s
                """,
                (_MONTH_START + timedelta(days=10), tid2_id),
            )
        assert open_fossil_sweep_for_user(tid2_id) is None
        run_monthly_fossil_sweep(now=_FIRST_OF_MONTH)
        assert open_fossil_sweep_for_user(tid2_id) is None
    finally:
        _delete_user(tid2)


def test_wrong_retest_unresolves(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    resolved_at = _MONTH_START - timedelta(days=45)
    eid = _insert_resolved(user_id, resolved_at=resolved_at)
    sid = create_fossil_sweep_session(user_id, _MONTH_START, pending=[eid])

    mark_result(eid, False)
    mark_fossil_retest_done(sid, eid)

    row = _error_row(eid)
    assert row["resolved"] is False
    assert int(row["unresolved_count"]) == 1
    with connection() as conn:
        nr = conn.execute(
            """
            SELECT next_review = CURRENT_DATE + 1 AS ok
              FROM errors WHERE id = %s
            """,
            (eid,),
        ).fetchone()
    assert nr is not None and nr["ok"]

    fossil = get_session_by_id(user_id, sid)
    assert fossil is not None
    assert eid in (fossil.payload or {}).get("done", [])
    assert eid not in (fossil.payload or {}).get("pending", [])
    assert resolved_types(user_id) == []


def test_correct_retest_keeps_resolved_at(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    resolved_at = date(2026, 5, 1)
    eid = _insert_resolved(user_id, resolved_at=resolved_at)
    sid = create_fossil_sweep_session(user_id, _MONTH_START, pending=[eid])

    # Simulate quiz path: correct retest does not call mark_result
    before = _error_row(eid)
    mark_fossil_retest_done(sid, eid)
    after = _error_row(eid)
    assert after["resolved"] is True
    assert after["resolved_at"] == resolved_at == before["resolved_at"]

    fossil = get_session_by_id(user_id, sid)
    assert fossil is not None and fossil.completed
    assert open_fossil_sweep_for_user(user_id) is None


def test_unresolve_drops_from_resolved_types(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    eid = _insert_resolved(
        user_id,
        resolved_at=_MONTH_START - timedelta(days=40),
        error_type="article_wrong",
    )
    labels = resolved_types(user_id)
    assert any("article" in x.lower() or "Article" in x for x in labels) or labels
    mark_result(eid, False)
    assert resolved_types(user_id) == []


def test_rescue_skips_injection(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    eid = _insert_resolved(user_id, resolved_at=_MONTH_START - timedelta(days=40))
    create_fossil_sweep_session(user_id, _MONTH_START, pending=[eid])
    with connection() as conn:
        conn.execute(
            """
            UPDATE streaks SET rescue_mode_until = %s WHERE user_id = %s
            """,
            (_DAY + timedelta(days=3), user_id),
        )
        for i in range(5):
            conn.execute(
                """
                INSERT INTO errors (
                    user_id, source, you_said, correct_form, error_type,
                    explanation, next_review
                ) VALUES (
                    %s, 'text', %s, %s, 'verb_tense_past',
                    'Past.', CURRENT_DATE
                )
                """,
                (user_id, f"bad {i}", f"good {i}"),
            )

    captured: dict = {}

    def fake_build(user_id: int, errors: list, **kwargs: object):
        captured["error_ids"] = [e.id for e in errors]
        questions = [
            {
                "error_id": e.id,
                "error_type": e.error_type,
                "error_type_label": "Past tense",
                "format": "choice",
                "prompt": f"Q{e.id}?",
                "options": ["a", "b", "c", "d"],
                "accept": ["a"],
                "answer": "a",
            }
            for e in errors
        ]
        return questions, "office"

    app = MagicMock()
    app.bot = MagicMock()
    app.bot.send_message = AsyncMock(
        return_value=MagicMock(message_id=99)
    )

    with patch.object(quiz_handler, "_build_quiz_questions", side_effect=fake_build):
        action = asyncio.run(
            quiz_handler.deliver_morning(app, user_id, now=_NOW)
        )
    assert action == "quiz"
    assert eid not in captured["error_ids"]
    fossil = open_fossil_sweep_for_user(user_id)
    assert fossil is not None
    assert eid in (fossil.payload or {}).get("pending", [])


def test_injection_marks_retest_without_leak(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    eid = _insert_resolved(user_id, resolved_at=_MONTH_START - timedelta(days=40))
    create_fossil_sweep_session(user_id, _MONTH_START, pending=[eid])
    with connection() as conn:
        for i in range(4):
            conn.execute(
                """
                INSERT INTO errors (
                    user_id, source, you_said, correct_form, error_type,
                    explanation, next_review
                ) VALUES (
                    %s, 'text', %s, %s, 'verb_tense_past',
                    'Past.', CURRENT_DATE
                )
                """,
                (user_id, f"bad {i}", f"good {i}"),
            )

    def fake_build(user_id: int, errors: list, **kwargs: object):
        questions = []
        for e in errors:
            questions.append(
                {
                    "error_id": e.id,
                    "error_type": e.error_type,
                    "error_type_label": "Label",
                    "format": "choice",
                    "prompt": f"Practice: {e.you_said}",
                    "options": ["a", "b", "c", "d"],
                    "accept": ["a"],
                    "answer": "a",
                }
            )
        return questions, "cafe"

    app = MagicMock()
    app.bot = MagicMock()
    app.bot.send_message = AsyncMock(
        return_value=MagicMock(message_id=77)
    )

    with patch.object(quiz_handler, "_build_quiz_questions", side_effect=fake_build):
        action = asyncio.run(
            quiz_handler.deliver_morning(app, user_id, now=_NOW)
        )
    assert action == "quiz"
    # Inspect delivered session payload
    with connection() as conn:
        row = conn.execute(
            """
            SELECT payload FROM sessions
             WHERE user_id = %s AND task_type = 'quiz'
             ORDER BY id DESC LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    payload = dict(row["payload"])
    retest_qs = [q for q in payload["questions"] if q.get("retest")]
    assert len(retest_qs) == 1
    assert retest_qs[0]["error_id"] == eid

    kwargs = app.bot.send_message.await_args.kwargs
    body = str(kwargs.get("text", ""))
    low = body.lower()
    assert "retest" not in low
    assert "fossil" not in low
    assert "sweep" not in low
    assert "resolved" not in low


def test_advance_correct_retest_preserves_resolved_at(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    resolved_at = date(2026, 4, 15)
    eid = _insert_resolved(user_id, resolved_at=resolved_at)
    fossil_sid = create_fossil_sweep_session(user_id, _MONTH_START, pending=[eid])
    from core.services.sessions import insert_session, update_session_payload

    payload = {
        "index": 0,
        "correct_count": 0,
        "answered": 0,
        "chat_id": tid,
        "message_id": 1,
        "fossil_sweep_session_id": fossil_sid,
        "questions": [
            {
                "error_id": eid,
                "retest": True,
                "format": "choice",
                "prompt": "___",
                "options": ["a", "b", "c", "d"],
                "accept": ["a"],
                "answer": "a",
                "error_type_label": "Quantifiers",
            }
        ],
    }
    quiz_sid = insert_session(user_id, "quiz", _DAY, payload=payload, completed=False)
    payload["session_id"] = quiz_sid
    update_session_payload(quiz_sid, payload)

    context = MagicMock()
    context.bot = MagicMock()
    context.bot.edit_message_text = AsyncMock()

    asyncio.run(
        quiz_handler._advance_after_answer(
            context,
            user_id,
            quiz_sid,
            payload,
            correct=True,
            question=payload["questions"][0],
            user_answer="a",
        )
    )
    after = _error_row(eid)
    assert after["resolved"] is True
    assert after["resolved_at"] == resolved_at
    err = get_error_for_user(user_id, eid)
    assert err is not None and err.resolved
