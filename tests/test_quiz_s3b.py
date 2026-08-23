"""S3b — quiz question layout (body reads, buttons tap)."""

from __future__ import annotations

import re

from telegram import InlineKeyboardMarkup

from apps.bot import texts
from apps.bot.handlers.quiz import (
    _MAX_BUTTON_LABEL_CHARS,
    _keyboard_for_question,
    _question_text,
    compose_body,
    format_feedback,
    grade_answer,
)

_ORDER_OPTIONS = [
    "She went to the pharmacy yesterday morning",
    "She went yesterday morning to the pharmacy",
    "Yesterday morning she to the pharmacy went",
    "She yesterday morning went to the pharmacy",
]
_CHOICE_OPTIONS = [
    "I agree with Marta",
    "I am agree with Marta",
    "I am agreeing with Marta",
    "I agreed with Marta",
]


def _labels(markup: InlineKeyboardMarkup | None) -> list[str]:
    assert isinstance(markup, InlineKeyboardMarkup)
    return [btn.text for row in markup.inline_keyboard for btn in row]


def _callbacks(markup: InlineKeyboardMarkup | None) -> list[str]:
    assert isinstance(markup, InlineKeyboardMarkup)
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


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


def test_order_body_lists_full_options_buttons_are_numbers() -> None:
    q = {
        "format": "order",
        "prompt": "Which one sounds right?",
        "options": list(_ORDER_OPTIONS),
        "answer": _ORDER_OPTIONS[0],
        "accept": [_ORDER_OPTIONS[0].lower()],
    }
    body = _question_text({"index": 0, "questions": [q]})
    for opt in _ORDER_OPTIONS:
        assert opt in body
    assert "1. She went to the pharmacy yesterday morning" in body
    assert "4. She yesterday morning went to the pharmacy" in body
    labels = _labels(_keyboard_for_question(q, {}))
    assert labels == ["1", "2", "3", "4"]
    assert all(len(label) <= 3 for label in labels)


def test_choice_body_lists_full_options_buttons_are_numbers() -> None:
    q = {
        "format": "choice",
        "prompt": "Which one sounds right?",
        "options": list(_CHOICE_OPTIONS),
        "answer": _CHOICE_OPTIONS[0],
        "accept": [_CHOICE_OPTIONS[0].lower()],
    }
    body = _question_text({"index": 0, "questions": [q]})
    for opt in _CHOICE_OPTIONS:
        assert opt in body
    labels = _labels(_keyboard_for_question(q, {}))
    assert labels == ["1", "2", "3", "4"]
    assert all(len(label) <= 3 for label in labels)


def test_no_quiz_button_label_exceeds_max_chars() -> None:
    """Regression: every current format keeps button labels ≤20 chars."""
    samples = {
        "order": {
            "format": "order",
            "prompt": "Which one sounds right?",
            "options": list(_ORDER_OPTIONS),
            "answer": _ORDER_OPTIONS[0],
        },
        "choice": {
            "format": "choice",
            "prompt": "Which one sounds right?",
            "options": list(_CHOICE_OPTIONS),
            "answer": _CHOICE_OPTIONS[0],
        },
        "spot": {
            "format": "spot",
            "prompt": "One word is wrong. Which one?",
            "tiles": ["She", "buyed", "coffee", "before", "we", "left"],
            "answer": "buyed",
        },
        "gap": {
            "format": "gap",
            "prompt": "Her English ___ very good.",
            "answer": "isn't",
        },
    }
    for fmt, q in samples.items():
        markup = _keyboard_for_question(q, {})
        if markup is None:
            assert fmt == "gap"
            continue
        for label in _labels(markup):
            assert len(label) <= _MAX_BUTTON_LABEL_CHARS, (
                f"{fmt} button label too long: {label!r} ({len(label)} chars)"
            )


def test_numbered_button_still_grades_correct_option() -> None:
    """callback_data index still selects the full option text for grading."""
    q = {
        "format": "order",
        "options": list(_ORDER_OPTIONS),
        "answer": _ORDER_OPTIONS[0],
        "accept": [_ORDER_OPTIONS[0].lower()],
    }
    markup = _keyboard_for_question(q, {})
    callbacks = _callbacks(markup)
    assert callbacks == ["quiz:opt:0", "quiz:opt:1", "quiz:opt:2", "quiz:opt:3"]
    # Tap button "1" → index 0 → correct sentence
    chosen = q["options"][int(callbacks[0].rsplit(":", 1)[-1])]
    assert chosen == _ORDER_OPTIONS[0]
    assert grade_answer(chosen, q["accept"]) is True
    # Tap button "2" → wrong
    wrong = q["options"][int(callbacks[1].rsplit(":", 1)[-1])]
    assert grade_answer(wrong, q["accept"]) is False
