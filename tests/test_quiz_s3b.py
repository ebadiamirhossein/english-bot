"""S3b — quiz question layout (body reads, buttons tap)."""

from __future__ import annotations

import re

from app import texts
from app.handlers.quiz import (
    _feedback_for,
    _question_text,
    compose_body,
)


def test_spot_body_contains_full_sentence() -> None:
    payload = {
        "index": 0,
        "questions": [
            {
                "format": "spot",
                "prompt": "One word is wrong. Which one?",
                "tiles": [
                    "Last",
                    "night",
                    "Sara",
                    "go",
                    "to",
                    "the",
                    "pharmacy",
                ],
                "answer": "go",
                "correction": "went",
            }
        ],
    }
    body = _question_text(payload)
    assert "One word is wrong. Which one?" in body
    assert '"Last night Sara go to the pharmacy"' in body
    assert "Last night Sara go" in body


def test_feedback_and_question_separated_by_blank_line() -> None:
    feedback = _feedback_for(
        {"format": "gap", "answer": "isn't", "explanation": "Use isn't."},
        correct=True,
    )
    question = _question_text(
        {
            "index": 0,
            "questions": [
                {
                    "format": "gap",
                    "prompt": "Her English ___ very good.",
                }
            ],
        }
    )
    body = compose_body(feedback=feedback, question_body=question)
    assert "──────────" not in body
    assert not hasattr(texts, "QUIZ_DIVIDER") or not getattr(
        texts, "QUIZ_DIVIDER", None
    )
    assert "\n\n" in body
    feedback_part, question_part = body.split("\n\n", 1)
    assert "Correct" in feedback_part
    assert "isn't" in feedback_part
    assert "Her English" in question_part
    assert "Correct" not in question_part


def test_no_guilt_in_feedback_copy() -> None:
    samples = [
        _feedback_for(
            {"format": "gap", "answer": "isn't", "explanation": "Use isn't."},
            correct=True,
        ),
        _feedback_for(
            {"format": "gap", "answer": "isn't", "explanation": "Use isn't."},
            correct=False,
        ),
        _feedback_for(
            {
                "format": "spot",
                "answer": "go",
                "correction": "went",
            },
            correct=False,
        ),
        texts.QUIZ_CORRECT,
        texts.QUIZ_WRONG,
        texts.QUIZ_WRONG_SHORT,
        texts.QUIZ_SPOT_WRONG,
        texts.QUIZ_IMPROVED,
        texts.QUIZ_CAME_BACK,
    ]
    disappointed = re.compile(
        r"wrong!|😞|😢|😔|☹️|🙁|😟|😤|😠",
        re.IGNORECASE,
    )
    for s in samples:
        assert disappointed.search(s) is None, s
