"""Why-statement sentence builder (S1c motivation clauses)."""

from __future__ import annotations

from app.handlers.onboarding import build_why_sentence


def test_why_one_selection() -> None:
    assert (
        build_why_sentence(["freeze"]) == "I want to speak without freezing up."
    )


def test_why_two_selections() -> None:
    assert (
        build_why_sentence(["freeze", "travel"])
        == "I want to speak without freezing up and travel more easily."
    )


def test_why_three_selections() -> None:
    assert (
        build_why_sentence(["freeze", "meetings", "friends"])
        == (
            "I want to speak without freezing up, do better in meetings, "
            "and make friends here."
        )
    )


def test_why_six_selections_ordered() -> None:
    # Input order must not matter — clauses follow WHY_OPTIONS order.
    assert (
        build_why_sentence(
            ["study", "travel", "embarrassed", "friends", "meetings", "freeze"]
        )
        == (
            "I want to speak without freezing up, do better in meetings, "
            "make friends here, stop feeling embarrassed about my English, "
            "travel more easily, and study or pass an exam."
        )
    )
