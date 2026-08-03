"""S3d — quiz feedback richness and 2/3 typed-to-tapped mix."""

from __future__ import annotations

from app.handlers.quiz import (
    _question_text,
    format_feedback,
    plan_formats,
    typed_gap_count,
)


def test_correct_gap_feedback_contains_full_sentence() -> None:
    fb = format_feedback(
        {
            "format": "gap",
            "prompt": "Her English ___ very good.",
            "answer": "isn't",
            "explanation": "Use isn't.",
        },
        correct=True,
        user_answer="isn't",
    )
    assert "Her English" in fb
    assert "very good" in fb
    assert "isn't" in fb
    # Not answer-only
    assert fb.strip() != '✅ "isn\'t"'
    assert "<b>isn't</b>" in fb or "isn't" in fb


def test_wrong_gap_feedback_contains_said_and_correct() -> None:
    fb = format_feedback(
        {
            "format": "gap",
            "prompt": "Her English ___ very good.",
            "answer": "isn't",
            "explanation": '"so much" doesn\'t go before adjectives. Use "very".',
        },
        correct=False,
        user_answer="is not so much",
    )
    assert "You said:" in fb
    assert "is not so much" in fb
    assert "Her English" in fb
    assert "isn't" in fb
    assert "so much" in fb


def test_five_question_mix_exactly_two_gap() -> None:
    assert typed_gap_count(5) == 2
    formats = plan_formats(5)
    assert len(formats) == 5
    assert formats.count("gap") == 2
    tapped = [f for f in formats if f != "gap"]
    assert len(tapped) == 3
    assert all(f in ("choice", "spot", "order") for f in tapped)
    # Never three of the same
    for i in range(len(formats) - 2):
        assert not (formats[i] == formats[i + 1] == formats[i + 2])


def test_progress_dots_appear_after_question() -> None:
    payload = {
        "index": 1,
        "questions": [
            {"format": "gap", "prompt": "First ___."},
            {"format": "gap", "prompt": "Her English ___ very good."},
        ],
    }
    body = _question_text(payload)
    lines = [ln for ln in body.splitlines() if ln.strip()]
    assert lines[-1] == "○●"
    # Hint or sentence comes before dots
    assert any("Type the missing" in ln or "Her English" in ln for ln in lines[:-1])
    assert not body.startswith("○") and not body.startswith("●")
