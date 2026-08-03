"""S3a — track distribution, reorder/spot grading, labels, past prompts."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from psycopg.types.json import Jsonb

from app import texts
from app.db import close_pool, connection
from app.handlers import quiz as quiz_handler
from app.handlers.quiz import (
    distribute_tracks,
    error_type_label,
    format_completion_message,
    grade_reorder,
    grade_spot,
    init_quiz_prompt,
    recent_prompts_for_errors,
)
from app.services.errors import Error
from app.services.users import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_330_000_000


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


def _onboard(tid: int) -> None:
    save_onboarding(
        tid,
        {
            "name": "S3a Test",
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


def test_distribute_tracks_5_at_40_40_20() -> None:
    tracks = distribute_tracks(5, {"work": 40, "life": 40, "curiosity": 20})
    assert len(tracks) == 5
    assert tracks.count("work") == 2
    assert tracks.count("life") == 2
    assert tracks.count("curiosity") == 1
    # Interleaved, not grouped WWW…
    assert tracks != ["work", "work", "life", "life", "curiosity"]


def test_distribute_tracks_small_counts() -> None:
    three = distribute_tracks(3, {"work": 40, "life": 40, "curiosity": 20})
    assert len(three) == 3
    assert set(three) <= {"work", "life", "curiosity"}

    one = distribute_tracks(1, {"work": 40, "life": 40, "curiosity": 20})
    assert len(one) == 1
    assert one[0] in {"work", "life", "curiosity"}

    assert distribute_tracks(0, {"work": 40, "life": 40, "curiosity": 20}) == []


def test_reorder_grading() -> None:
    answer = "I usually check my email at eight"
    assert grade_reorder("I usually check my email at eight", answer)
    assert grade_reorder("  I Usually Check My Email At Eight. ", answer)
    assert not grade_reorder("I check usually my email at eight", answer)


def test_spot_grading() -> None:
    assert grade_spot("buyed", "buyed")
    assert grade_spot("Buyed", "buyed")
    assert not grade_spot("bought", "buyed")
    assert not grade_spot("coffee", "buyed")


def test_completion_uses_label_not_code() -> None:
    init_quiz_prompt()
    label = error_type_label("quantifier_modifier")
    assert label == "Quantifiers and modifiers"
    msg = format_completion_message(
        correct_count=4,
        total=5,
        improved_labels=[label],
    )
    assert "quantifier_modifier" not in msg
    assert "Quantifiers and modifiers" in msg
    assert "quantifier_modifier" not in texts.QUIZ_IMPROVED


def test_past_prompts_passed_into_llm_call(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    init_quiz_prompt()

    with connection() as conn:
        err = conn.execute(
            """
            INSERT INTO errors (
                user_id, source, you_said, correct_form, error_type,
                explanation, next_review
            ) VALUES (
                %s, 'text', 'so much good', 'very good',
                'quantifier_modifier', 'Use very.', CURRENT_DATE
            )
            RETURNING id
            """,
            (tid,),
        ).fetchone()
    assert err is not None
    eid = int(err["id"])

    old_prompt = "The coffee ___ hot enough this morning."
    prior_payload = {
        "questions": [
            {
                "error_id": eid,
                "format": "gap",
                "prompt": old_prompt,
                "accept": ["isn't"],
                "answer": "isn't",
            }
        ]
    }
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO sessions (
                user_id, date, task_type, delivered_at, completed, payload
            ) VALUES (%s, %s, 'quiz', NOW(), TRUE, %s)
            """,
            (tid, date.today(), Jsonb(prior_payload)),
        )

    recent = recent_prompts_for_errors(tid, [eid])
    assert recent[eid] == [old_prompt]

    captured: dict[str, str] = {}

    def fake_chat(messages, *, system=None, json_mode=False, max_tokens=1000):
        captured["system"] = system or ""
        return {
            "questions": [
                {
                    "error_id": eid,
                    "format": "gap",
                    "prompt": "Marta ___ ready for the standup yet.",
                    "accept": ["isn't", "is not"],
                    "answer": "isn't",
                }
            ]
        }

    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, you_said, correct_form, error_type, explanation,
                   streak_right, times_right, times_wrong, next_review,
                   resolved, resolved_at, unresolved_count, created_at
              FROM errors WHERE id = %s
            """,
            (eid,),
        ).fetchone()
    assert row is not None
    error = Error(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        you_said=row["you_said"],
        correct_form=row["correct_form"],
        error_type=row["error_type"],
        explanation=row["explanation"],
        streak_right=int(row["streak_right"]),
        times_right=int(row["times_right"]),
        times_wrong=int(row["times_wrong"]),
        next_review=row["next_review"],
        resolved=bool(row["resolved"]),
        resolved_at=row["resolved_at"],
        unresolved_count=int(row["unresolved_count"]),
        created_at=row["created_at"],
    )

    questions = quiz_handler._build_quiz_questions(
        tid, [error], chat_fn=fake_chat
    )
    assert questions
    assert old_prompt in captured["system"]
    assert "avoid_prompts" in captured["system"]
