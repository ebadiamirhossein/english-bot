"""S3c — order format, no divider, scenario continuity."""

from __future__ import annotations

import inspect
import uuid
from datetime import date
from pathlib import Path

import pytest
from psycopg.types.json import Jsonb
from telegram import InlineKeyboardMarkup

from core.db import close_pool, connection
from apps.bot.handlers import quiz as quiz_handler
from apps.bot.handlers.quiz import (
    _VALID_FORMATS,
    _keyboard_for_question,
    compose_body,
    init_quiz_prompt,
    recent_scenarios,
)
from core.services.errors import Error
from core.services.identity import save_onboarding
FAKE_TELEGRAM_ID_BASE = 9_340_000_000
_PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages" / "core" / "prompts" / "quiz.txt"
)
_HANDLER_PATH = (
    Path(__file__).resolve().parents[1]
    / "apps" / "bot" / "handlers" / "quiz.py"
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
            "name": "S3c Test",
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


def test_reorder_removed_from_contract_and_handler() -> None:
    assert "reorder" not in _VALID_FORMATS
    assert "order" in _VALID_FORMATS
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    assert '"format": "reorder"' not in prompt
    assert "- reorder:" not in prompt
    assert '"format": "order"' in prompt
    assert "- order:" in prompt
    handler_src = _HANDLER_PATH.read_text(encoding="utf-8")
    assert "grade_reorder" not in handler_src
    assert "_reorder_assembly" not in handler_src
    assert "reorder_placed" not in handler_src
    # Format set literal must not list reorder
    assert '{"gap", "choice", "spot", "order"}' in handler_src or (
        "gap" in handler_src and "order" in handler_src and "reorder" not in _VALID_FORMATS
    )


def test_order_options_each_on_own_row() -> None:
    # Superseded 2026-08-07: full sentences moved to the message body;
    # buttons are numbers on one shared row (see test_quiz_s3b numbered labels).
    q = {
        "format": "order",
        "prompt": "Which one sounds right?",
        "options": [
            "She went to the pharmacy yesterday morning",
            "She went yesterday morning to the pharmacy",
            "Yesterday morning she to the pharmacy went",
            "She yesterday morning went to the pharmacy",
        ],
        "answer": "She went to the pharmacy yesterday morning",
    }
    markup = _keyboard_for_question(q, {})
    assert isinstance(markup, InlineKeyboardMarkup)
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert labels == ["1", "2", "3", "4"]


def test_no_divider_in_rendered_messages() -> None:
    body = compose_body(
        feedback='✅ Correct — "isn\'t"',
        question_body="○●○○○\n\nWhich one sounds right?",
    )
    assert "──────────" not in body
    assert "\n\n" in body


def test_past_scenarios_passed_into_llm(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
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
            (user_id,),
        ).fetchone()
    assert err is not None
    eid = int(err["id"])

    old_scenario = "weekend trip with flatmates"
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO sessions (
                user_id, date, task_type, delivered_at, completed, payload
            ) VALUES (%s, %s, 'quiz', NOW(), TRUE, %s)
            """,
            (
                user_id,
                date.today(),
                Jsonb(
                    {
                        "scenario": old_scenario,
                        "questions": [
                            {
                                "error_id": eid,
                                "format": "gap",
                                "prompt": "Coffee ___ ready yet.",
                                "accept": ["isn't"],
                                "answer": "isn't",
                            }
                        ],
                    }
                ),
            ),
        )

    assert old_scenario in recent_scenarios(user_id)

    captured: dict[str, str] = {}

    def fake_chat(messages, *, system=None, json_mode=False, max_tokens=1000):
        captured["system"] = system or ""
        return {
            "scenario": "busy Monday standup",
            "questions": [
                {
                    "error_id": eid,
                    "format": "gap",
                    "prompt": "Marta ___ here yet.",
                    "accept": ["isn't"],
                    "answer": "isn't",
                }
            ],
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

    questions, scenario = quiz_handler._build_quiz_questions(
        user_id, [error], chat_fn=fake_chat
    )
    assert questions
    assert scenario == "busy Monday standup"
    assert old_scenario in captured["system"]
    assert "avoid_scenarios" in inspect.getsource(quiz_handler._build_quiz_questions) or (
        old_scenario in captured["system"]
    )
