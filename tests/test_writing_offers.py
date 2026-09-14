"""W16b: Q-E — which phrases from a paragraph's corrections are offered to the deck.

Every expected value is hardcoded (CLAUDE.md §3 rule 5). Pure: no database.

**RED DEMONSTRATIONS** (decisions log): the resolve check removed from
`matched_words` → *a word that does not resolve, even when the app wrote it* (the plainer `to experinence` case stays refused without the check, because the word is not in `correct_form` either — found while demonstrating); the change condition removed →
*a phrase the correction did not change*; comparing lemmas instead of surface words
in the change condition → the design's *to miss someone* refused; `MAX_OFFERS = 3`
→ *at most two*; the citation marker allowed anywhere → *to only leads*.
"""

from __future__ import annotations

import pytest

from core.writing import offers


# The design's own two drawn examples (`1o`), which Q-E must offer.
@pytest.mark.parametrize(
    ("phrase", "correct_form", "you_said"),
    [
        ("to depend on", "it depends on the person", "it depends of the person"),
        ("to miss someone", "he misses his family very much", "he miss his family very much"),
        ("to wait for someone", "I was waiting for my friend", "I was waiting my friend"),
    ],
)
def test_the_designs_examples_are_offered(phrase, correct_form, you_said) -> None:
    assert offers.is_offerable(phrase, correct_form, you_said) is True


def test_d16_the_ledger_is_not_consulted_for_phrases() -> None:
    """**D16, a recorded refusal, pinned.** `depend` and `miss` are known at B1;
    a lemma-level ledger filter would refuse both design examples. The rule takes
    no ledger at all — this asserts its signature, so a later change that adds one
    has to change this test and say why."""
    import inspect

    params = set(inspect.signature(offers.is_offerable).parameters)
    assert params == {"phrase", "correct_form", "you_said"}
    assert "ledger" not in inspect.getsource(offers).split('"""', 2)[2]


@pytest.mark.parametrize(
    ("phrase", "correct_form", "you_said", "why"),
    [
        ("depends of", "it depends on the person", "it depends of the person", "the learner's wording, not the app's"),
        ("to experinence", "I had experience", "I had experinence", "a word that does not resolve"),
        # The resolve check's own case: every word IS in the app's text, and one of
        # them does not resolve. Without the check, this phrase would be offered.
        ("spreadsheets were", "the spreadsheets were broken", "the spreadsheets was broken", "a word that does not resolve, even when the app wrote it"),
        ("the person", "it depends on the person", "it depends of the person", "a phrase the correction did not change"),
        ("to depend upon", "it depends on the person", "it depends of the person", "a word not in correct_form"),
        ("someone", "he misses his family", "he miss his family", "placeholders only"),
        ("to go home early today now please", "go home", "goes home", "more than six words"),
        ("to depend on!", "it depends on the person", "it depends of the person", "punctuation"),
        ("go to", "I go home", "I goes home", "to only leads"),
    ],
)
def test_a_phrase_outside_the_rule_is_refused(phrase, correct_form, you_said, why) -> None:
    assert offers.is_offerable(phrase, correct_form, you_said) is False, why


def test_keep_without_the_original_still_applies_every_other_condition() -> None:
    """`POST /write/keep` has no `you_said` — the original is never stored."""
    assert offers.is_offerable("to depend on", "it depends on the person") is True
    assert offers.is_offerable("to experinence", "I had experience") is False
    assert offers.is_offerable("to depend upon", "it depends on the person") is False


def test_at_most_two_one_per_correction_no_repeats_in_order() -> None:
    corrections = [
        {"you_said": "it depends of the person", "correct_form": "it depends on the person", "keep": "to depend on"},
        {"you_said": "he earn more", "correct_form": "he earns more", "keep": None},
        {"you_said": "it depends of the day", "correct_form": "it depends on the day", "keep": "To  Depend  On"},
        {"you_said": "he miss his family", "correct_form": "he misses his family", "keep": "to miss someone"},
        {"you_said": "I was waiting my friend", "correct_form": "I was waiting for my friend", "keep": "to wait for someone"},
    ]
    chosen = offers.select(corrections)
    assert [(o.phrase, o.sentence) for o in chosen] == [
        ("to depend on", "it depends on the person"),
        ("to miss someone", "he misses his family"),
    ]
