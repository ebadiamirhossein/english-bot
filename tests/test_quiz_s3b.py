"""S3b — quiz question layout (body reads, buttons tap)."""

from __future__ import annotations

import re

from app import texts
from app.handlers.quiz import (
    _question_text,
    compose_body,
    format_feedback,
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
    assert "Last night Sara go to the pharmacy" in body
    # Dots last, not first
    assert body.strip().endswith("●") or "●" in body.split("\n")[-1]


def test_feedback_and_question_separated_by_blank_line() -> None:
    feedback = format_feedback(
        {
            "format": "gap",
            "prompt": "Her English ___ very good.",
            "answer": "isn't",
            "explanation": "Use isn't.",
        },
        correct=True,
        user_answer="isn't",
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
    assert "\n\n" in body
    assert "Her English" in feedback
    assert "isn't" in feedback


def test_no_guilt_in_feedback_copy() -> None:
    samples = [
        format_feedback(
            {
                "format": "gap",
                "prompt": "Her English ___ very good.",
                "answer": "isn't",
                "explanation": "Use isn't.",
            },
            correct=True,
            user_answer="isn't",
        ),
        format_feedback(
            {
                "format": "gap",
                "prompt": "Her English ___ very good.",
                "answer": "isn't",
                "explanation": "Use isn't.",
            },
            correct=False,
            user_answer="is not so much",
        ),
        format_feedback(
            {
                "format": "spot",
                "tiles": ["She", "go", "home"],
                "answer": "go",
                "correction": "went",
            },
            correct=False,
            user_answer="She",
        ),
        texts.QUIZ_YOU_SAID,
        texts.QUIZ_CORRECT_SENTENCE,
        texts.QUIZ_IMPROVED,
        texts.QUIZ_CAME_BACK,
    ]
    disappointed = re.compile(
        r"wrong!|😞|😢|😔|☹️|🙁|😟|😤|😠",
        re.IGNORECASE,
    )
    for s in samples:
        assert disappointed.search(s) is None, s
