"""W16a: the writing surface's pure rules and gates.

Every expected value below is HARDCODED — the day kind, the caps, the bounds,
which strings a gate refuses — never read back from the function under test
(CLAUDE.md §3 rule 5). Dates are fixed literals; nothing reads the clock (§3
rule 6).

**RED DEMONSTRATIONS, recorded in the decisions log:** each group below was run
against a deliberate mutation of `core.writing` before being accepted —
`JOURNAL_MAX_CORRECTIONS = 3`; `day_kind` returning `paragraph` on a Thursday;
`is_self_produced` returning True; `is_typo` returning False; `BANNED` removed
from `opening_line`; the cap applied before the gates in `shape`.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.writing import gates, rules

# ── the day kind ─────────────────────────────────────────────────────────────


def test_thursday_is_the_paragraph_and_every_other_day_the_journal() -> None:
    """**W16b INVERTED W16a's pin, quoted rather than deleted (#82's shape):**
    *test_the_day_kind_is_journal_on_every_day_of_a_week* asserted `journal` for
    all eight days. PRD §4.2 gives Thursday the paragraph; A1 left that row
    intact, so W16b makes the spec true and owes no amendment.
    **Red demonstration:** `PARAGRAPH_WEEKDAY = 2` turned this red."""
    monday = date(2026, 9, 14)
    assert monday.weekday() == 0
    expected = ["journal", "journal", "journal", "paragraph", "journal", "journal", "journal", "journal"]
    assert [rules.day_kind(monday + timedelta(days=i)) for i in range(8)] == expected


def test_both_kinds_are_written_from_w16b() -> None:
    """**Inverts W16a's `test_w16a_writes_no_paragraph`**, which pinned
    `WRITTEN_DAY_KINDS == ("journal",)`. The table has admitted `paragraph` since
    027 was written, so W16b needs no DDL."""
    assert rules.DAY_KINDS == ("journal", "paragraph")
    assert rules.WRITTEN_DAY_KINDS == ("journal", "paragraph")


# ── the numbers ──────────────────────────────────────────────────────────────


def test_the_journal_shows_and_writes_at_most_two() -> None:
    """The TASKS Accept cell's number, hardcoded here."""
    assert rules.max_corrections("journal") == 2


def test_the_paragraph_shows_and_writes_at_most_eight() -> None:
    """**Q-D.** Inverts W16a's `test_no_paragraph_ceiling_is_built_yet`.
    **Red demonstration:** `PARAGRAPH_MAX_CORRECTIONS = 9` turned this red."""
    assert rules.max_corrections("paragraph") == 8
    with pytest.raises(ValueError):
        rules.max_corrections("essay")  # type: ignore[arg-type]


def test_the_bounds() -> None:
    """The floor is W3's ten, unchanged; the ceiling is Q-B's two thousand."""
    assert rules.MIN_CHARS == 10
    assert rules.MAX_CHARS == 2000
    assert rules.WRITING_MAX_TOKENS == 2000


# ── G1: self-produced ───────────────────────────────────────────────────────

ENTRY = "Today I go to the dentist in the morning. My colleague Rasa explain everything twice."


@pytest.mark.parametrize(
    "you_said",
    [
        "Today I go to the dentist",
        "today i go to the dentist",  # the model re-capitalises; case never decides
        "Rasa  explain   everything",  # whitespace collapsed
    ],
)
def test_an_original_the_learner_wrote_is_self_produced(you_said) -> None:
    assert gates.is_self_produced(you_said, ENTRY) is True


@pytest.mark.parametrize(
    "you_said",
    [
        "Yesterday I go to the dentist",  # paraphrased
        "I goes to the dentist",  # invented
        "",
    ],
)
def test_an_original_the_learner_did_not_write_is_refused(you_said) -> None:
    assert gates.is_self_produced(you_said, ENTRY) is False


def test_stated_limit_g1_cannot_see_intent() -> None:
    """**Pinned, not hoped away.** A span across two sentences IS in the text,
    so G1 accepts it. G1 proves the words are the learner's; it cannot prove the
    model quoted a sensible unit of them."""
    assert gates.is_self_produced("the dentist in the morning. My colleague", ENTRY) is True


# ── G2: typo ─────────────────────────────────────────────────────────────────


def test_a_misspelling_is_a_typo_and_is_refused() -> None:
    assert gates.is_typo("togehter", "together") is True
    assert gates.is_typo("becuase nobody", "because nobody") is True


@pytest.mark.parametrize(
    ("you_said", "correct_form"),
    [
        ("Today I go to the dentist", "Today I went to the dentist"),
        ("she only clean my teeth", "she only cleaned my teeth"),
        ("two episodes from a series", "two episodes of a series"),
        ("I have lived here since", "I've lived here since"),  # only an apostrophe token changes
        ("went to dentist", "went to the dentist"),  # a pure insertion changes no learner token
    ],
)
def test_a_grammar_error_on_real_words_is_not_a_typo(you_said, correct_form) -> None:
    assert gates.is_typo(you_said, correct_form) is False


def test_stated_limit_one_a_typo_on_a_real_word_passes() -> None:
    """**Pinned, not hoped away.** `weed` is a word, so G2 cannot see the slip."""
    assert gates.is_typo("weed like to come", "we'd like to come") is False


def test_stated_limit_two_a_real_word_outside_the_lexicon_is_refused() -> None:
    """**Pinned, not hoped away.** Found while building: `spreadsheets` does not
    resolve against the 15,000-lemma reference list, so a genuine agreement
    error on it is dropped. The recoverable direction (CLAUDE.md §5)."""
    assert gates.is_typo("the spreadsheets was broken", "the spreadsheet was broken") is True


# ── the explanation gate ─────────────────────────────────────────────────────


def test_an_explanation_may_quote_ordinary_english() -> None:
    """Content rule, not copy rule: "broke" in material is fine."""
    assert gates.explanation_is_clean("When something stopped working, English says it broke.")


@pytest.mark.parametrize(
    "explanation",
    ["You got it wrong again.", "You failed to use the past.", "Try harder with tenses."],
)
def test_an_explanation_that_addresses_the_learner_is_refused(explanation) -> None:
    assert not gates.explanation_is_clean(explanation)


# ── the opening line (Ruling 2) ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "line",
    [
        "You got the whole day down, start to finish.",
        # **Refused by the first draft of the gate**, whose mark vocabulary
        # included `point`. Red demonstration: re-adding `points?` to `_SCORE`
        # turns this case red.
        "You kept the sentence short and to the point.",
    ],
)
def test_a_specific_true_seeming_line_survives(line) -> None:
    assert gates.opening_line(line) == line


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "Nice.",
        "Good job!",
        "well done",
        "Keep it up!",
        "Nothing wrong here.",  # BANNED
        "You missed a few things but it reads well.",  # BANNED
        "A solid 8/10 entry.",  # a number
        "Your score is high.",  # a mark word
        "Three sentences in the past.",  # no digit, but see the next case
        "A full day. It holds together.",  # two sentences
        42,
    ],
)
def test_a_refused_line_is_absent_never_a_fallback(raw) -> None:
    if raw == "Three sentences in the past.":
        # A number word is not a digit and is not refused by this gate. Recorded
        # as a limit rather than widened into a list of every number word.
        assert gates.opening_line(raw) == raw
        return
    assert gates.opening_line(raw) is None


# ── shape: every gate in order ───────────────────────────────────────────────

LABELS = {
    "verb_tense_past": "Past tense",
    "preposition": "Prepositions",
    "word_order": "Word order",
    "filler_overuse": None,
}

SUBMITTED = (
    "Today I go to the dentist in the morning. She only clean my teeth. "
    "We watched two episodes from a series. It was togehter fine."
)


def _c(you_said, correct_form, code="verb_tense_past", explanation="Because it happened."):
    return {
        "you_said": you_said,
        "correct_form": correct_form,
        "error_type": code,
        "explanation": explanation,
    }


def test_the_cap_is_applied_after_the_gates() -> None:
    """Two refused corrections come first; they must not use up the two places."""
    raw = {
        "is_english": True,
        "corrections": [
            _c("Yesterday I go", "Yesterday I went"),  # not self-produced
            _c("togehter", "together", code="word_order"),  # typo
            _c("Today I go to the dentist", "Today I went to the dentist"),
            _c("She only clean my teeth", "She only cleaned my teeth"),
            _c("two episodes from a series", "two episodes of a series", code="preposition"),
        ],
        "did_well": "You explain why the day went the way it did.",
    }
    shaped = gates.shape(raw, SUBMITTED, limit=2, labels=LABELS)
    assert [c["you_said"] for c in shaped.corrections] == [
        "Today I go to the dentist",
        "She only clean my teeth",
    ]
    assert shaped.dropped == {"not_self_produced": 1, "typo": 1, "over_cap": 1}
    assert shaped.corrections[0]["label"] == "Past tense"


def test_an_unknown_code_is_refused_and_a_null_label_is_kept() -> None:
    raw = {
        "is_english": True,
        "corrections": [
            _c("Today I go", "Today I went", code="not_a_code"),
            _c("Today I go", "Today I went", code="filler_overuse"),
        ],
    }
    shaped = gates.shape(raw, SUBMITTED, limit=2, labels=LABELS)
    assert shaped.dropped == {"unknown_type": 1}
    assert len(shaped.corrections) == 1
    assert shaped.corrections[0]["label"] is None
    assert shaped.did_well is None


def test_no_change_and_malformed_are_refused() -> None:
    raw = {
        "is_english": True,
        "corrections": [
            _c("Today I go", "today i go"),
            {"you_said": "Today I go", "error_type": "verb_tense_past"},
            "not a dict",
        ],
    }
    shaped = gates.shape(raw, SUBMITTED, limit=2, labels=LABELS)
    assert shaped.corrections == ()
    assert shaped.dropped == {"no_change": 1, "malformed": 2}


def test_a_non_english_entry_carries_nothing() -> None:
    raw = {
        "is_english": False,
        "corrections": [_c("Today I go", "Today I went")],
        "did_well": "Lovely rhythm in this one.",
    }
    shaped = gates.shape(raw, SUBMITTED, limit=2, labels=LABELS)
    assert shaped.is_english is False
    assert shaped.did_well is None
    assert shaped.corrections == ()


# ── F1: the opening line describes the entry, never rates the learner ────────


@pytest.mark.parametrize(
    "raw",
    [
        # Verbatim from the clean fixture on the first §3 rule 2 call.
        "Your entry shows you can handle more complex time relationships between past events.",
        "You're able to keep the story in order.",
        "Your ability to link events is clear.",
        "You could tell the day in the right order.",
        "This showed that you know how to join sentences.",
    ],
)
def test_a_line_that_rates_the_learner_is_refused(raw) -> None:
    """**Red demonstration:** removing `_EVALUATIVE` from `opening_line` turns
    every case here red."""
    assert gates.opening_line(raw) is None


@pytest.mark.parametrize(
    "line",
    [
        "You explain why you were nervous, which makes the day easy to follow.",
        "The whole day is there, from the dentist to dinner.",
    ],
)
def test_a_line_that_describes_the_entry_survives(line) -> None:
    """Pinned so the gate is not widened into refusing description."""
    assert gates.opening_line(line) == line


def test_stated_limit_you_can_refuses_a_line_that_only_describes() -> None:
    """**Pinned, not hoped away.** The operator's `you can` shape cannot tell a
    description from a verdict, so this describing line is refused too. An
    absent line is the recoverable direction; the reading is a human check."""
    assert gates.opening_line("You can see the whole day in it, from the dentist to dinner.") is None


# ── F5: a language is a name ─────────────────────────────────────────────────


def test_the_two_learners_languages_are_named() -> None:
    assert rules.language_name("fa") == "Farsi"
    assert rules.language_name("lt") == "Lithuanian"


def test_an_unmapped_code_is_refused_never_sent_raw() -> None:
    with pytest.raises(ValueError):
        rules.language_name("xx")


# ── W16b: the structure gate ─────────────────────────────────────────────────

PARA = "I think is a good idea. But he told me that he miss his family very much."
QUOTED = [{"segments": [
    {"text": "The turn at ", "quote": False},
    {"text": "But he told me", "quote": True},
    {"text": " is the strongest part.", "quote": False},
]}]


def test_the_designs_structure_prose_survives() -> None:
    assert gates.structure_of(QUOTED, PARA) == tuple(QUOTED)


@pytest.mark.parametrize(
    ("raw", "why"),
    [
        ([{"segments": [{"text": "But she said", "quote": True}]}], "an invented quote"),
        ([{"segments": [{"text": "Opening: strong.", "quote": False}]}], "a named dimension"),
        ([{"segments": [{"text": "Order: fine.", "quote": False}]}], "a named dimension"),
        ([{"segments": [{"text": "Seven out of ten readers would follow it.", "quote": False}]}], "out of"),
        ([{"segments": [{"text": "It makes 3 points.", "quote": False}]}], "a digit"),
        ([{"segments": [{"text": "A good score for this.", "quote": False}]}], "a mark word"),
        ([{"segments": [{"text": "Nothing wrong with the order.", "quote": False}]}], "a banned term"),
        ([], "no paragraphs"),
        (QUOTED * 3, "three paragraphs"),
        ([{"segments": []}], "an empty paragraph"),
        ([{"segments": [{"text": "   ", "quote": False}]}], "a blank segment"),
        ([{"segments": [{"text": "Fine.", "quote": "yes"}]}], "a non-boolean quote"),
        ("You give your opinion first.", "prose that is not the shape"),
    ],
)
def test_a_refused_structure_is_absent_as_a_whole(raw, why) -> None:
    """**Red demonstrations** (decisions log): the quote check, `_RUBRIC`, and the
    paragraph-count bound each removed in turn, and the matching cases went red."""
    assert gates.structure_of(raw, PARA) is None, why


def test_the_paragraph_shape_has_no_opening_line_and_carries_keep() -> None:
    """Design `1n` draws no opening line for the paragraph, so the field is absent
    whatever the model sends; the nominated phrase travels to the offer rule."""
    raw = {
        "is_english": True,
        "did_well": "A lovely paragraph with a clear shape.",
        "structure": QUOTED,
        "corrections": [{
            "you_said": "he miss his family", "correct_form": "he misses his family",
            "error_type": "verb_tense_past", "explanation": "With he, the verb takes an s.",
            "keep": "to miss someone",
        }],
    }
    shaped = gates.shape(raw, PARA, limit=8, labels=LABELS, kind="paragraph")
    assert shaped.did_well is None
    assert shaped.structure == tuple(QUOTED)
    assert shaped.corrections[0]["keep"] == "to miss someone"
    journal = gates.shape(raw, PARA, limit=2, labels=LABELS)
    assert journal.structure is None and journal.corrections[0]["keep"] is None
