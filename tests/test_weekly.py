"""S11 — weekly test + Murphy routing + Saturday Anki."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone

import pytest

from core.db import close_pool, connection
from core.services.errors import expand_murphy_units, mark_result, select_weekly_test_errors
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


