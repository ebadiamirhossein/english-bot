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

from datetime import date, datetime, timedelta

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


def test_the_paragraph_has_its_own_output_budget() -> None:
    """**Finding (d).** One 2,000-token budget served both kinds, and the paragraph
    asks for up to four times the corrections plus the structure prose. Adaptive
    thinking counts against `max_tokens` (`llm.py:_describe_truncation`), and the
    item generator reserves `THINKING_HEADROOM_TOKENS = 2000` for thinking ALONE —
    so a 2,000 paragraph budget left no room for the answer, and a long paragraph
    would 503 as truncated. **Red demonstration:** before `max_tokens(kind)` existed
    this failed on the attribute; with the paragraph mapped to 2,000 it failed on
    the number."""
    assert rules.max_tokens("journal") == 2000
    assert rules.max_tokens("paragraph") == 4000
    with pytest.raises(ValueError):
        rules.max_tokens("essay")  # type: ignore[arg-type]


# ── which kind the server accepts (finding (c)) ─────────────────────────────


@pytest.mark.parametrize(
    ("local", "kind", "accepted"),
    [
        (datetime(2026, 9, 17, 0, 0), "paragraph", True),  # Thursday, first minute
        (datetime(2026, 9, 17, 23, 59), "paragraph", True),  # Thursday, last minute
        (datetime(2026, 9, 18, 2, 59), "paragraph", True),  # Friday, inside the grace
        (datetime(2026, 9, 18, 3, 0), "paragraph", False),  # Friday, grace over
        (datetime(2026, 9, 16, 23, 59), "paragraph", False),  # Wednesday night
        (datetime(2026, 9, 14, 12, 0), "paragraph", False),  # Monday
        (datetime(2026, 9, 17, 12, 0), "journal", True),  # the lighter kind, on Thursday
        (datetime(2026, 9, 14, 12, 0), "journal", True),
    ],
)
def test_the_server_accepts_the_paragraph_only_on_its_day(local, kind, accepted) -> None:
    """**Red demonstration:** `accepts_day_kind` returning True for every kind turned
    the four `False` rows red; the grace removed turned the Friday 02:59 row red."""
    assert rules.accepts_day_kind(kind, local) is accepted


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


# ── The live defect: structure praised a stretch a correction then fixed ─────
#
# **FOUND BY THE OPERATOR ON THE FIRST LIVE PARAGRAPH CALL (2026-09-14).** The
# structure prose quoted *"we can't depend of the old plan any more"* as the
# paragraph's strongest moment, and correction 3 fixed *"depend of the old plan"*
# inside it — the learner's own error, quoted approvingly in the app's voice, then
# corrected below. **THE QUOTE CONTAINS THE CORRECTION: that is the direction that
# shipped.**
#
# **THE FIXTURE IS THE REAL RESPONSE, AS THE OPERATOR TRANSCRIBED IT FROM THE
# `--live` PRINT:** the text sent (`probe.FIXTURE_PARAGRAPH`); all four corrections'
# `you_said`, `correct_form`, `error_type` and `keep`; and every `quote: true`
# segment. **Not transcribed, and so written here:** the four explanations and the
# prose around the quotes. **The overlap gate reads none of those.** *(This block
# first held a RECONSTRUCTION that guessed correction 3 as a longer stretch and
# invented corrections 1–2; replaced on the operator's transcription, #82's shape.)*
#
# **Red demonstrations (decisions log), against THIS fixture:** the overlap check
# removed from `structure_of` (M12); only the correction-contains-quote direction
# kept (M13, the shipped case goes red); only the quote-contains-correction
# direction kept (M14, the other direction goes red).

LIVE_QUOTE = "we can't depend of the old plan any more"

#: The first structure paragraph of the live response. **PINNED AS THE SURVIVOR:**
#: it quotes `First`, `After lunch` and `Finally`, and no correction touches them.
SURVIVOR = {"segments": [
    {"text": "You walk through the day in the order it happened, and ", "quote": False},
    {"text": "First", "quote": True},
    {"text": ", ", "quote": False},
    {"text": "After lunch", "quote": True},
    {"text": " and ", "quote": False},
    {"text": "Finally", "quote": True},
    {"text": " keep it easy to follow.", "quote": False},
]}

#: The second paragraph: the one that praised the corrected stretch.
REFUSED = {"segments": [
    {"text": "The strongest moment is ", "quote": False},
    {"text": LIVE_QUOTE, "quote": True},
    {"text": ", where the day turns.", "quote": False},
]}


def _correction(you_said: str, correct_form: str, code: str, keep: str | None, explanation: str) -> dict:
    return {"you_said": you_said, "correct_form": correct_form, "error_type": code,
            "explanation": explanation, "keep": keep}


LIVE_CORRECTIONS = (
    _correction("I wake up late", "I woke up late", "verb_tense_past", None,
                "It happened yesterday, so the verb is in the past: woke."),
    _correction("I go to the office", "I went to the office", "verb_tense_past", None,
                "Same day, same past: went."),
    _correction("depend of the old plan", "depend on the old plan", "preposition", "to depend on",
                "Depend always takes on in English."),
    _correction("I was waiting my friend", "I was waiting for my friend", "preposition", "to wait for someone",
                "You wait for someone, so it needs for."),
)


def _live(corrections=LIVE_CORRECTIONS, structure=(SURVIVOR, REFUSED)) -> dict:
    return {"is_english": True, "structure": [dict(p) for p in structure],
            "corrections": [dict(c) for c in corrections]}


def _with_correction_three(**changes) -> tuple[dict, ...]:
    return tuple({**c, **changes} if i == 2 else c for i, c in enumerate(LIVE_CORRECTIONS))


LIVE_LABELS = {"verb_tense_past": "Past tense", "preposition": "Prepositions"}


def _shape_live(raw: dict) -> gates.Shaped:
    from core.writing.probe import FIXTURE_PARAGRAPH

    return gates.shape(raw, FIXTURE_PARAGRAPH, limit=8, labels=LIVE_LABELS, kind="paragraph")


def test_the_shipped_response_keeps_paragraph_one_and_drops_paragraph_two() -> None:
    """**The case that shipped, under the operator's REVERSAL (per-paragraph overlap).**
    Paragraph 1 (*First* / *After lunch* / *Finally*) is kept and shown; paragraph 2,
    which praised the corrected stretch, is dropped and named in `dropped`. All four
    corrections survive, and Q-E still offers exactly what the live run printed.
    *(Until the reversal this test asserted `structure is None` and
    `dropped == {"structure": 1}` — quoted, #82.)* **Red demonstration:** overlap made
    block-level again (M15) turned this red."""
    from core.writing import offers

    shaped = _shape_live(_live())
    assert shaped.structure == (SURVIVOR,), "the good paragraph stays; the one praising an error goes"
    assert [c["you_said"] for c in shaped.corrections] == [
        "I wake up late", "I go to the office", "depend of the old plan", "I was waiting my friend",
    ]
    assert shaped.dropped == {"structure_paragraph_2": 1}
    assert [o.phrase for o in offers.select(shaped.corrections)] == ["to depend on", "to wait for someone"]


def test_both_paragraphs_overlapping_leaves_structure_absent() -> None:
    """Per-paragraph dropping that leaves zero paragraphs is an absent block, never an
    empty one. Both drops are named."""
    finally_fixed = _correction("Finally I went to bed at midnight", "Finally, I went to bed at midnight",
                                "verb_tense_past", None, "A short pause after Finally reads more naturally.")
    shaped = _shape_live(_live(corrections=LIVE_CORRECTIONS + (finally_fixed,)))
    assert shaped.structure is None
    assert shaped.dropped == {"structure_paragraph_1": 1, "structure_paragraph_2": 1}


INVENTED = {"segments": [
    {"text": "The strongest moment is ", "quote": False},
    {"text": "we can't depend on the new plan", "quote": True},  # not in the text
    {"text": ", where the day turns.", "quote": False},
]}
DIGIT = {"segments": [{"text": "The 2 turns in the middle carry it.", "quote": False}]}


@pytest.mark.parametrize(("second", "why"), [(INVENTED, "an invented quote"), (DIGIT, "a digit")])
def test_a_block_level_fault_in_paragraph_two_still_drops_the_whole_block(second, why) -> None:
    """**THE DISTINCTION THAT WILL GET BLURRED LATER, PINNED.** Only the OVERLAP rule is
    per-paragraph. An invented quote, a banned term, a digit, a rubric word, or the wrong
    number of paragraphs says the MODEL did not follow the contract, so nothing it wrote
    in that block is trusted — the clean paragraph 1 goes with it. **Red
    demonstration:** the invented-quote rule made per-paragraph (M17) turned the
    invented-quote case red."""
    shaped = _shape_live(_live(structure=(SURVIVOR, second)))
    assert shaped.structure is None, why
    assert shaped.dropped == {"structure": 1}, why


def test_the_paragraph_count_is_judged_on_what_the_model_sent() -> None:
    """Three paragraphs is over the limit of two even if overlap would drop one of them:
    dropping cannot rescue an over-long block. **Red demonstration:** the count checked
    after overlap dropping (M16) turned this red."""
    shaped = _shape_live(_live(structure=(SURVIVOR, REFUSED, SURVIVOR)))
    assert shaped.structure is None
    assert shaped.dropped == {"structure": 1}


def test_the_first_structure_paragraph_survives_the_gate_on_its_own() -> None:
    """**PINNED AS THE SURVIVOR.** Checked alone against all four corrections, the
    paragraph quoting `First`, `After lunch` and `Finally` passes, and the paragraph
    quoting the corrected stretch does not. Since the operator's reversal the survivor is
    also SHOWN on the shipped response (the test above). *(This docstring said the
    survivor was not shown "because the block is all or nothing" — quoted, #82.)*"""
    from core.writing.probe import FIXTURE_PARAGRAPH

    corrected = [c["you_said"] for c in LIVE_CORRECTIONS]
    assert gates.structure_of([SURVIVOR], FIXTURE_PARAGRAPH, corrected=corrected) == (SURVIVOR,)
    assert gates.structure_of([REFUSED], FIXTURE_PARAGRAPH, corrected=corrected) is None


def test_without_correction_three_the_same_structure_survives() -> None:
    """The baseline: remove the correction on the quoted stretch and both paragraphs
    pass every other gate — so the refusal above is the overlap and nothing else."""
    shaped = _shape_live(_live(corrections=LIVE_CORRECTIONS[:2] + LIVE_CORRECTIONS[3:]))
    assert shaped.structure == (SURVIVOR, REFUSED)
    assert "structure" not in shaped.dropped


@pytest.mark.parametrize(
    "you_said",
    [
        "depend of the old plan",  # AS SHIPPED: the quote contains the correction
        LIVE_QUOTE,  # the same stretch
        "my manager said that we can't depend of the old plan any more",  # the correction contains the quote
        "we can't  depend of the old plan any more.",  # doubled space, full stop
    ],
)
def test_the_paragraph_quoting_a_corrected_stretch_is_dropped_in_either_direction(you_said) -> None:
    shaped = _shape_live(_live(corrections=_with_correction_three(you_said=you_said, keep=None)))
    assert shaped.structure == (SURVIVOR,)
    assert len(shaped.corrections) == 4, "the corrections are unaffected"
    assert shaped.dropped == {"structure_paragraph_2": 1}, "the dropped paragraph is named, so the probe can show it"


def test_a_correction_the_gates_dropped_still_refuses_the_quote() -> None:
    """A stretch the model itself called an error is not praised just because its
    correction failed a gate (here: an unknown code). Over-refusal is the recoverable
    direction."""
    shaped = _shape_live(_live(corrections=_with_correction_three(error_type="not_a_code")))
    assert shaped.structure == (SURVIVOR,)
    assert len(shaped.corrections) == 3


def test_overlap_ignores_the_apostrophe_a_phone_types() -> None:
    """iOS types `’`. The overlap is matched after `_normal`, so a curly `can’t` in
    the correction still matches a straight `can't` in the quote. *(Tested on the pure
    gate, not through `shape`: through `shape` the curly correction is dropped by G2
    first — #421, below.)*"""
    assert gates.overlaps_a_correction(LIVE_QUOTE, "we can’t  depend of the old plan any more.")


def test_stated_defect_421_g2_drops_a_correction_whose_apostrophe_is_curly() -> None:
    """**#421, FOUND WHILE DEMONSTRATING THIS FIX, PINNED AND NOT FIXED.**
    `changed_learner_tokens` tokenises `you_said` BEFORE straightening its quotes, so
    `can’t` splits into `can` + `t`; `t` does not resolve, and G2 calls a genuine
    error a typo whenever `you_said` carries `’` and `correct_form` carries `'`.
    **Not fixed here: the W16b prompt holds G1 and G2 exactly as W16a built them.**
    It errs toward a MISSING journal row (recoverable). **When #421 is fixed this
    test goes red — invert it; do not restore the defect.**"""
    assert gates.is_typo("we can’t depend of the old plan", "we can't depend on the old plan") is True
    assert gates.is_typo("we can't depend of the old plan", "we can't depend on the old plan") is False


def test_overlap_is_matched_on_whole_words() -> None:
    """`an` is not `any`: a character-level substring would refuse on a letter pair."""
    assert gates.structure_of([REFUSED], LIVE_QUOTE + ".", corrected=("an",)) is not None
    assert gates.structure_of([REFUSED], LIVE_QUOTE + ".", corrected=("old plan",)) is None


def test_stated_limit_a_partial_overlap_passes() -> None:
    """**STATED LIMIT, PINNED.** The rule is containment in either direction. A
    correction that shares only PART of a quoted stretch — neither contains the
    other — does not refuse it, although the shared part may be the error. Widening
    to any shared word would refuse nearly every quote. HP2 is the check for this."""
    raw = _live(corrections=_with_correction_three(you_said="the old plan any more. After", keep=None))
    assert _shape_live(raw).structure == (SURVIVOR, REFUSED)
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
