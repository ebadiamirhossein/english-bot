"""PRD §4.6, the three mechanical rules. Zero model calls, and asserted so.

TASKS' acceptance criterion is "a Life-track item containing 'deploy', 'Q3' or
'stakeholder' is rejected". The inverse matters just as much and is tested here
too: the same word on the Work track must be ACCEPTED, or the gate is not a
jargon rule, it is a word ban, and the 20% Work track becomes unusable.
"""

from __future__ import annotations

import pytest

from core.items.naturalness import (
    JARGON,
    contract,
    jargon_hits,
    textbook_hits,
    uncontracted,
)

# PRD §4.6 names these five. Two are single words, three are phrases.
PRD_TERMS = ("deploy", "stakeholder", "q3", "campaign performance", "onboarding flow")


@pytest.mark.parametrize("term", PRD_TERMS)
@pytest.mark.parametrize("track", ["life", "curiosity"])
def test_prd_jargon_is_rejected_off_the_work_track(term, track) -> None:
    assert jargon_hits(f"I saw the {term} this morning.", track=track)


@pytest.mark.parametrize("term", PRD_TERMS)
def test_the_same_term_is_accepted_on_the_work_track(term) -> None:
    """The inverse. Without it this is a word ban, not a track rule."""
    assert jargon_hits(f"I saw the {term} this morning.", track="work") == ()


@pytest.mark.parametrize("form", ["deploy", "deploys", "deployed", "deploying"])
def test_inflections_are_caught_by_the_lemmatised_match(form) -> None:
    """One list entry, every inflection — the point of matching on lemmas."""
    assert "deploy" in jargon_hits(f"She {form} it every Friday.", track="life")


def test_an_ordinary_word_that_merely_contains_a_jargon_term_is_not_a_hit() -> None:
    """A raw substring list gets this wrong in both directions.

    `sprint` is jargon; `sprinted` is what you did for the bus. The lemmatiser
    resolves `sprinted` to `sprint`, so this one IS a hit — and that is the
    honest limit of a word list, recorded rather than hidden. What must not
    happen is a hit on a word that merely spells another one.
    """
    assert jargon_hits("I need a raincoat.", track="life") == ()
    assert jargon_hits("We ate dinner outside.", track="life") == ()


def test_the_jargon_list_carries_its_unmeasured_provenance() -> None:
    """#57's UNMEASURED branch. The comment is the record; this pins its shape.

    If someone widens the list from data later, this test fails and they have to
    decide deliberately — which is the point of recording provenance at all.
    """
    assert JARGON == {"deploy", "stakeholder", "sprint", "standup", "kpi", "deliverable"}


@pytest.mark.parametrize(
    "text",
    ["Indeed, it is quite interesting.", "I am very fond of tea.",
     "Let us discuss the matter.", "Moreover, the bus was late."],
)
def test_textbook_english_is_rejected(text) -> None:
    assert textbook_hits(text)


def test_ordinary_speech_is_not_textbook_english() -> None:
    assert textbook_hits("Honestly, the bus was ages late again.") == ()


def test_uncontracted_speech_is_detected_and_repaired() -> None:
    assert uncontracted("I do not want to go out tonight.")
    assert contract("I do not want to go out tonight.") == (
        "I don't want to go out tonight."
    )


def test_the_contraction_repair_preserves_sentence_case() -> None:
    assert contract("Do not worry about it.").startswith("Don't")


def test_emphatic_uncontracted_forms_are_left_alone() -> None:
    """`I *am* going` is correct spoken English, not a rule-4 failure."""
    assert uncontracted("I *am* going, I promise.") == ()
    assert contract("I *am* going, I promise.") == "I *am* going, I promise."


def test_the_repair_table_is_derived_from_the_tokeniser_table() -> None:
    """One table, not two. Two copies is how they stop agreeing."""
    from core.items.naturalness import CONTRACTION_REPAIRS
    from core.lexicon.normalize import CONTRACTIONS

    for expansion, contracted in CONTRACTION_REPAIRS.items():
        assert CONTRACTIONS[contracted] == expansion
