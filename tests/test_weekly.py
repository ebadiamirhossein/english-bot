"""S11 — weekly test + Murphy routing + Saturday Anki."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.db import close_pool, connection
from apps.bot.handlers import quiz as quiz_handler
from apps.bot.handlers.quiz import (
    _MAX_BUTTON_LABEL_CHARS,
    format_murphy_recommendation,
    quiz_effective_total,
)
from apps.bot.scheduler import ANKI_WEEKDAY, EligibleUser, is_user_due_for_anki
from core.services.books import MergedUnit, upsert_unit
from core.services.errors import (
    expand_murphy_units,
    mark_result,
    select_weekly_test_errors,
    top_error_types,
)
from apps.bot.motivation_delivery import deliver_sunday_report
from core.services.motivation import (
    MotivationUser,
    is_user_due_for_sunday_report,
)
from core.services.sessions import (
    bot_initiated_count,
    get_session_by_id,
    has_anki_session_on,
    insert_session,
    local_today,
    update_session_payload,
)
from core.services.identity import save_onboarding
FAKE_TELEGRAM_ID_BASE = 9_490_000_000
_TG_ADDRESS_BASE = 9_000_000_000

# Sunday 2026-08-09 08:05 Vilnius (UTC+3)
_SUNDAY_MORNING = datetime(2026, 8, 9, 5, 5, tzinfo=timezone.utc)
# Monday 2026-08-10 08:05 Vilnius
_MONDAY_MORNING = datetime(2026, 8, 10, 5, 5, tzinfo=timezone.utc)
# Sunday evening for report
_SUNDAY_EVENING = datetime(2026, 8, 9, 18, 5, tzinfo=timezone.utc)
# Saturday evening for Anki
_SATURDAY_EVENING = datetime(2026, 8, 8, 18, 5, tzinfo=timezone.utc)

_GUILT = re.compile(
    r"\b(fail(ed|ure)?|broke|disappoint|guilt|lazy|should have)\b",
    re.I,
)


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
            "name": "Weekly Test",
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
    error_type: str,
    you_said: str,
    next_review: date | None = None,
) -> int:
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO errors (
                user_id, source, you_said, correct_form, error_type,
                explanation, next_review
            ) VALUES (
                %s, 'text', %s, %s, %s, 'x', COALESCE(%s, CURRENT_DATE)
            )
            RETURNING id
            """,
            (tid, you_said, f"ok {you_said}", error_type, next_review),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _set_rescue(tid: int, until: date) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE streaks SET rescue_mode_until = %s WHERE user_id = %s
            """,
            (until, tid),
        )


def _fake_questions(n: int, *, error_ids: list[int] | None = None) -> list[dict]:
    ids = error_ids or list(range(1, n + 1))
    out = []
    for i in range(n):
        eid = ids[i] if i < len(ids) else i + 1
        out.append(
            {
                "error_id": eid,
                "error_type": "quantifier_modifier",
                "error_type_label": "Quantifiers and modifiers",
                "format": "choice",
                "prompt": f"Q{i}?",
                "options": ["a", "b", "c", "d"],
                "accept": ["a"],
                "answer": "a",
                "explanation": "because",
            }
        )
    return out


def _deliver(
    tid: int,
    now: datetime,
    *,
    n_questions: int,
    day: date | None = None,
) -> tuple[str, Any]:
    app = MagicMock()
    app.bot = AsyncMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    local_day = day or local_today("Europe/Vilnius", now)
    fake = _fake_questions(n_questions)

    def build(user_id: int, errors: list, **kwargs: Any) -> tuple[list, str]:
        qs = _fake_questions(len(errors), error_ids=[e.id for e in errors])
        books = kwargs.get("book_items") or []
        for j, b in enumerate(books):
            qs.append(
                {
                    "source": "book",
                    "book": b.get("book"),
                    "unit_number": b.get("unit_number"),
                    "target_item": b.get("item"),
                    "error_type": "article_missing",
                    "error_type_label": "Missing article",
                    "format": "choice",
                    "prompt": f"Book {j}?",
                    "options": ["a", "b", "c", "d"],
                    "accept": ["a"],
                    "answer": "a",
                    "explanation": "book",
                }
            )
        return qs[:n_questions] if qs else fake[:n_questions], "cafe"

    with (
        patch.object(quiz_handler, "_build_quiz_questions", side_effect=build) as build_mock,
        patch.object(quiz_handler, "_user_timezone", return_value="Europe/Vilnius"),
        patch.object(quiz_handler, "local_today", return_value=local_day),
    ):
        action = asyncio.run(quiz_handler.deliver_morning(app, tid, now=now))
    return action, build_mock


def test_sunday_delivers_fifteen(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    for i in range(15):
        _insert_error(
            user_id,
            error_type="quantifier_modifier" if i % 2 == 0 else "preposition",
            you_said=f"bad{i}",
        )
    action, build = _deliver(user_id, _SUNDAY_MORNING, n_questions=15)
    assert action == "quiz"
    errors_arg = build.call_args[0][1]
    assert len(errors_arg) == 15
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
    assert payload.get("weekly_test") is True
    assert len(payload["questions"]) == 15


def test_monday_delivers_five(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    for i in range(8):
        _insert_error(user_id, error_type="preposition", you_said=f"m{i}")
    action, build = _deliver(user_id, _MONDAY_MORNING, n_questions=5)
    assert action == "quiz"
    assert len(build.call_args[0][1]) == 5
    with connection() as conn:
        row = conn.execute(
            """
            SELECT payload FROM sessions
             WHERE user_id = %s AND task_type = 'quiz'
             ORDER BY id DESC LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    assert dict(row["payload"]).get("weekly_test") is not True


def test_rescue_sunday_delivers_three_not_fifteen(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = local_today("Europe/Vilnius", _SUNDAY_MORNING)
    _set_rescue(user_id, day + timedelta(days=3))
    for i in range(12):
        _insert_error(user_id, error_type="modal_verb", you_said=f"r{i}")
    action, build = _deliver(user_id, _SUNDAY_MORNING, n_questions=3, day=day)
    assert action == "quiz"
    assert len(build.call_args[0][1]) == 3
    with connection() as conn:
        row = conn.execute(
            """
            SELECT payload FROM sessions
             WHERE user_id = %s AND task_type = 'quiz'
             ORDER BY id DESC LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    assert dict(row["payload"]).get("weekly_test") is not True


def test_selection_spreads_across_types(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    types = [
        "article_missing",
        "preposition",
        "modal_verb",
        "word_order",
        "present_perfect",
    ]
    for t in types:
        for i in range(4):
            _insert_error(user_id, error_type=t, you_said=f"{t}-{i}")
    selected = select_weekly_test_errors(user_id, limit=15)
    assert len(selected) == 15
    first_five = [e.error_type for e in selected[:5]]
    assert len(set(first_five)) == 5  # one of each before repeats


def test_fewer_than_fifteen_tops_up_from_book(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    for i in range(3):
        _insert_error(user_id, error_type="preposition", you_said=f"few{i}")
    upsert_unit(
        user_id,
        "murphy",
        MergedUnit(
            unit_number="1",
            unit_title="Present continuous",
            target_items=["am/is/are + -ing", "spelling of -ing"],
        ),
        studied_at=date(2026, 8, 1),
    )
    action, build = _deliver(user_id, _SUNDAY_MORNING, n_questions=15)
    assert action == "quiz"
    errors_arg = build.call_args[0][1]
    books = build.call_args.kwargs.get("book_items") or []
    assert len(errors_arg) == 3
    assert len(books) >= 1


def test_nothing_available_free_practice(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    action, _ = _deliver(user_id, _SUNDAY_MORNING, n_questions=15)
    assert action == "free_practice"


def test_mark_result_on_weekly_error_answers(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    eid = _insert_error(
        user_id,
        error_type="article_missing",
        you_said="a apple",
        next_review=date(2030, 1, 1),  # not yet due
    )
    with connection() as conn:
        before = conn.execute(
            "SELECT streak_right, next_review FROM errors WHERE id = %s",
            (eid,),
        ).fetchone()
    mark_result(eid, True)
    with connection() as conn:
        after = conn.execute(
            "SELECT streak_right, next_review FROM errors WHERE id = %s",
            (eid,),
        ).fetchone()
    # Not-yet-due correct answers still advance the ladder (S11 decision).
    assert int(after["streak_right"]) == int(before["streak_right"]) + 1
    assert after["next_review"] != before["next_review"]


def test_early_limit_two_on_fifteen(cleanup_user: int) -> None:
    questions = _fake_questions(15)
    payload = {
        "questions": questions,
        "early_limit": 2,
        "correct_count": 2,
        "answered": 2,
    }
    assert quiz_effective_total(payload) == 2
    score = float(payload["correct_count"]) / float(quiz_effective_total(payload))
    assert score == 1.0
    # score formula used at completion
    assert float(2) / 2.0 == 1.0


def test_anki_saturday_not_sunday(cleanup_user: int) -> None:
    assert ANKI_WEEKDAY == 5
    tid = cleanup_user
    user_id = _onboard(tid)
    user = EligibleUser(
        id=user_id,
        # Deliberately not equal to `id`.
        telegram_address=_TG_ADDRESS_BASE + user_id,
        timezone="Europe/Vilnius",
        morning_time=time(8, 0),
        paused_until=None,
        evening_time=time(21, 0),
    )
    assert is_user_due_for_anki(user, _SATURDAY_EVENING) is True
    assert is_user_due_for_anki(user, _SUNDAY_EVENING) is False
    sun = local_today("Europe/Vilnius", _SUNDAY_EVENING)
    assert has_anki_session_on(user_id, sun) is False


def test_sunday_message_count_two_with_headroom(cleanup_user: int) -> None:
    """Weekly test (morning) + report (evening) = 2; ceiling headroom left."""
    tid = cleanup_user
    user_id = _onboard(tid)
    for i in range(15):
        _insert_error(user_id, error_type="preposition", you_said=f"c{i}")
    day = local_today("Europe/Vilnius", _SUNDAY_MORNING)
    action, _ = _deliver(user_id, _SUNDAY_MORNING, n_questions=15, day=day)
    assert action == "quiz"
    assert bot_initiated_count(user_id, day) == 1

    mot = MotivationUser(
        id=user_id,
        # Deliberately not equal to `id`.
        telegram_address=_TG_ADDRESS_BASE + user_id,
        timezone="Europe/Vilnius",
        evening_time=time(21, 0),
        paused_until=None,
        why_statement="Speak without freezing up",
    )
    assert is_user_due_for_sunday_report(mot, _SUNDAY_EVENING)
    app = MagicMock()
    app.bot = AsyncMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=99))
    assert (
        asyncio.run(deliver_sunday_report(app, mot, now=_SUNDAY_EVENING))
        == "sent"
    )
    assert bot_initiated_count(user_id, day) == 2
    assert bot_initiated_count(user_id, day) < 3


def test_murphy_routing_skips_null_and_marks_studied(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    # collocation has NULL murphy_units; article_missing → 69-81
    for i in range(5):
        _insert_error(user_id, error_type="collocation", you_said=f"col{i}")
    for i in range(3):
        _insert_error(user_id, error_type="article_missing", you_said=f"art{i}")
    upsert_unit(
        user_id,
        "murphy",
        MergedUnit(
            unit_number="70",
            unit_title="A/an",
            target_items=["a/an before nouns"],
        ),
        studied_at=date(2026, 8, 1),
    )
    top = top_error_types(user_id, n=5)
    assert "Collocation" in top
    rec = format_murphy_recommendation(user_id)
    assert rec is not None
    assert "Collocation" not in rec  # NULL skipped
    assert "Missing article" in rec
    assert "69-81" in rec
    assert "already" in rec.lower() or "stored" in rec.lower()
    assert "collocation" not in rec.lower()
    assert len(rec) <= 400
    assert _GUILT.search(rec) is None


def test_murphy_new_when_not_studied(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    for i in range(3):
        _insert_error(user_id, error_type="word_order", you_said=f"wo{i}")
    rec = format_murphy_recommendation(user_id)
    assert rec is not None
    assert "Word order" in rec
    assert "New" in rec or "new" in rec
    assert "already" not in rec.lower()


def test_expand_murphy_ranges() -> None:
    assert expand_murphy_units("69-81") == {str(n) for n in range(69, 82)}
    assert expand_murphy_units("5-6,11-14") == {
        "5",
        "6",
        "11",
        "12",
        "13",
        "14",
    }
    assert expand_murphy_units(None) == set()


def test_s11_button_labels_short() -> None:
    assert _MAX_BUTTON_LABEL_CHARS <= 20
    for label in ("1", "2", "3", "4"):
        assert len(label) <= 20


def test_early_limit_completes_fifteen_set(cleanup_user: int) -> None:
    """Just do 2 against a 15Q weekly payload → score / 2.0."""
    tid = cleanup_user
    user_id = _onboard(tid)
    ids = [
        _insert_error(user_id, error_type="preposition", you_said=f"el{i}")
        for i in range(15)
    ]
    questions = _fake_questions(15, error_ids=ids)
    day = local_today("Europe/Vilnius", _SUNDAY_MORNING)
    payload: dict[str, Any] = {
        "index": 0,
        "correct_count": 0,
        "answered": 0,
        "questions": questions,
        "scenario": "x",
        "chat_id": tid,
        "message_id": 7,
        "weekly_test": True,
        "early_limit": 2,
    }
    sid = insert_session(user_id, "quiz", day, payload=payload, completed=False)
    payload["session_id"] = sid
    update_session_payload(sid, payload)

    context = MagicMock()
    context.bot = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    for i in range(2):
        session = get_session_by_id(user_id, sid)
        assert session is not None
        payload = dict(session.payload or {})
        asyncio.run(
            quiz_handler._advance_after_answer(
                context,
                user_id,
                sid,
                payload,
                correct=True,
                question=questions[i],
                user_answer="a",
            )
        )
    session = get_session_by_id(user_id, sid)
    assert session is not None
    assert session.completed is True
    assert session.score == pytest.approx(2 / 2.0)
