"""W4: tokenising, lemmatising and coverage. No database touched by this file.

`core.lexicon` is pure by design, so every expectation here is checked against
a hand-counted number or a text built to make the answer true by construction —
never against whatever the code happens to return (CLAUDE.md §3 rule 5).
"""

from __future__ import annotations

import pytest

from core.lexicon import coverage as coverage_module
from core.lexicon import normalize
from core.lexicon.coverage import compute_coverage
from core.lexicon.normalize import (
    cefr_tagged_lemmas,
    inflections,
    lemmatize,
    lexeme_rows,
    seeded_lemmas,
    tokenize,
)
from core.services import lexicon as lexicon_service
from core.services.reading import normalize_for_match

# ── the hand-counted fixture ────────────────────────────────────────────────
#
# Seventeen tokens. Their lemmas, worked out by hand and written down here so
# the test does not ask the lemmatiser what it thinks the answer is:
#
#   The cat sat on  the mat It be  a very old cat and two dog  watch it
#   the cat sit on  the mat it be  a very old cat and two dog  watch it
#
# 17 tokens, 14 distinct lemmas (`the`, `cat` and `it` each appear twice).
FIXTURE = "The cat sat on the mat. It was a very old cat, and two dogs watched it."
FIXTURE_TOKENS = 17
FIXTURE_LEMMAS = (
    "the", "cat", "sit", "on", "the", "mat", "it", "be",
    "a", "very", "old", "cat", "and", "two", "dog", "watch", "it",
)


def test_the_fixture_lemmatises_as_hand_counted() -> None:
    tokens = tokenize(FIXTURE)
    assert len(tokens) == FIXTURE_TOKENS
    assert tuple(lemmatize(t.surface) for t in tokens) == FIXTURE_LEMMAS


def test_a_fixture_transcript_scores_its_hand_counted_coverage() -> None:
    """Eleven of seventeen tokens are covered: the×2 cat×2 sit on mat it×2 be a."""
    known = frozenset({"the", "cat", "sit", "on", "mat", "it", "be", "a"})
    report = compute_coverage(FIXTURE, known)
    assert report.counted_tokens == 17
    assert report.coverage == pytest.approx(11 / 17)
    assert report.percent == pytest.approx(64.71, abs=0.01)


def test_coverage_is_computed_on_tokens_not_types() -> None:
    """The two answers must differ measurably, or the fixture proves nothing.

    `the`, `cat` and `it` are three of fourteen types (21.43%) but six of
    seventeen tokens (35.29%). Comprehensible input is defined on running
    words: a learner who knows `the` genuinely follows every occurrence of it.
    """
    known = frozenset({"the", "cat", "it"})
    report = compute_coverage(FIXTURE, known)
    assert report.coverage == pytest.approx(6 / 17)
    types = len(set(FIXTURE_LEMMAS))
    assert types == 14
    assert report.coverage != pytest.approx(3 / types)


# ── knowing more words moves the number ─────────────────────────────────────


def _lemmas_ranked(low: int, high: int) -> tuple[str, ...]:
    return tuple(row[0] for row in lexeme_rows() if low <= row[2] < high)


def test_marking_two_hundred_words_known_moves_the_number_by_that_much() -> None:
    """Built so the answer is true by construction, not by asking the code.

    Eighty tokens drawn from a base set and twenty from a 200-lemma extra set.
    Coverage must read exactly 80% before the extra set is known and exactly
    100% after — a twenty-point rise, which is the twenty tokens.
    """
    base = _lemmas_ranked(1, 400)[:80]
    extra = _lemmas_ranked(3000, 3400)[:200]
    assert len(base) == 80 and len(extra) == 200
    assert not set(base) & set(extra)

    text = " ".join(base + extra[:20])
    before = compute_coverage(text, frozenset(base))
    after = compute_coverage(text, frozenset(base) | frozenset(extra))

    assert before.counted_tokens == 100
    assert before.coverage == pytest.approx(0.80)
    assert after.coverage == pytest.approx(1.00)
    assert after.coverage - before.coverage == pytest.approx(0.20)


# ── what is excluded, and the casing gate in front of it ────────────────────


def test_numerals_and_fillers_leave_the_denominator() -> None:
    report = compute_coverage("um I have 3 cats uh", frozenset({"i", "have", "cat"}))
    assert report.counted_tokens == 3          # I, have, cats
    assert report.excluded_tokens == 3         # um, 3, uh
    assert report.coverage == pytest.approx(1.0)


def test_real_interjections_stay_in_the_denominator() -> None:
    """`wow` and `yeah` are words a learner knows or does not; `uh` is not."""
    report = compute_coverage("wow yeah okay", frozenset())
    assert report.counted_tokens == 3


def test_caption_annotations_are_stripped() -> None:
    report = compute_coverage("[Music] the cat (laughs) sat", frozenset({"the"}))
    assert report.counted_tokens == 3


def test_a_transcript_full_of_names_does_not_read_as_hard() -> None:
    """The proper-noun rule, and the reason it exists."""
    known = frozenset({"and", "go", "to", "the", "shop", "with", "then", "leave"})
    with_names = (
        "Sarah and Michael went to the shop with Jonathan and Persephone. "
        "Then Bartholomew and Anastasia left with Sarah and Michael too."
    )
    report = compute_coverage(with_names, known)
    assert report.proper_nouns_detected
    # EIGHT. Seven capitalised tokens sit mid-sentence — Michael, Jonathan,
    # Persephone, Bartholomew, Anastasia, and Sarah and Michael again — and
    # since W12a the opening `Sarah` is excluded too, because `Sarah` is
    # attested mid-sentence later in the same text (#89).
    #
    # This assertion read `== 7` until W12a, above the comment *"The opening
    # `Sarah` is sentence-initial and is NOT excluded"* — the defect written
    # down as expected behaviour, which is why #89 sat open from W4.
    assert report.excluded_tokens == 8
    assert report.coverage > 0.85


# ── #177 and #89, both fixed in W12a ────────────────────────────────────────


def test_a_derivational_er_is_not_stripped_onto_a_stem() -> None:
    """#177. `-er` is a derivational suffix far more often than a comparative one.

    Every expected value below is HAND-WRITTEN (CLAUDE.md §3 rule 5). Asking
    `lemmatize` what it thinks `router` is would pass against the defect.

    `tier` was the reported case and it is the mildest: the stem `ti` is an
    OpenSubtitles artefact, so the accept-only-a-known-lemma guard passed on a
    non-word. `router → route` and `blogger → blog` are worse, because they are
    real lemmas and the resolution still credits a learner who knows `route`
    with knowing `router`. Coverage then reads HIGH, which is the direction this
    module refuses everywhere else.
    """
    assert lemmatize("tier") is None
    assert lemmatize("router") is None
    assert lemmatize("blogger") is None
    assert lemmatize("renter") is None
    assert lemmatize("influencer") is None
    assert lemmatize("toner") is None


def test_deleting_the_er_rules_did_not_cost_a_single_comparative() -> None:
    """The other half of #177, and the half that can actually fail.

    A test that only states what a fix repairs cannot go red when the fix
    breaks something else. These five were always answered by the inflection
    table at step 1, so the deleted branches never saw them.
    """
    assert lemmatize("bigger") == "big"
    assert lemmatize("biggest") == "big"
    assert lemmatize("happier") == "happy"
    assert lemmatize("easiest") == "easy"
    assert lemmatize("nicer") == "nice"


def test_the_eight_comparatives_the_deletion_would_have_cost_are_in_the_table() -> None:
    """#282. The eight resolutions that hung off the deleted branches.

    `data/inflections.tsv` held `freeer` and `blueest` — `lemminflect` spells
    an `-e`-final comparative by appending — so the real spellings were absent
    and only the suffix rules answered them. **A defect in the data was masked
    by a defect in the code.** Deleting the branches without repairing the rows
    would have lost these eight; repairing the rows without deleting the
    branches would have left `tier → ti`. Neither fix alone is correct, which
    is the finding.

    `truer`, `weer` and `weest` are here as well and were never in the eight:
    they resolved to `tru` and `we` — the `ti` artefact class again — so the
    repair CORRECTED them rather than preserving them.
    """
    assert lemmatize("freer") == "free"
    assert lemmatize("freest") == "free"
    assert lemmatize("bluer") == "blue"
    assert lemmatize("bluest") == "blue"
    assert lemmatize("eerier") == "eerie"
    assert lemmatize("eeriest") == "eerie"
    assert lemmatize("vaguer") == "vague"
    assert lemmatize("vaguest") == "vague"
    # Repaired, not preserved. These read `tru`, `we`, `we` before W12a.
    assert lemmatize("truer") == "true"
    assert lemmatize("weer") == "wee"
    assert lemmatize("weest") == "wee"


def test_no_malformed_e_final_comparative_remains_in_the_table() -> None:
    """#282, asserted against the data rather than against the eleven names.

    Named rows would pass while a twelfth sat beside them. This states the
    RULE — a lemma ending in `e` always drops it before `-er`/`-est` — and
    checks every row, so a regenerated file that reintroduces the bug goes red
    here even for a lemma nobody has met.
    """
    offenders = [
        (form, lemma)
        for form, lemma in inflections().items()
        if lemma.endswith("e") and form in (lemma + "er", lemma + "est")
    ]
    assert offenders == [], f"`-e`-final lemma + er/est without dropping the e: {offenders}"


def test_a_sentence_initial_name_is_excluded_when_the_text_attests_it() -> None:
    """#89, and the assertion NAMES the lemma rather than counting exclusions.

    A count could not see the wrong twelve in W11 and it could not see the
    wrong name here. `Sarah` opens the first sentence and sits mid-sentence in
    the second; one mid-sentence capital is the evidence, and it now vouches
    for both occurrences.
    """
    known = frozenset({"go", "to", "the", "shop", "i", "see", "yesterday"})
    text = "Sarah went to the shop. I saw Sarah yesterday."
    report = compute_coverage(text, known)

    assert report.proper_nouns_detected
    assert "sarah" not in report.unknown_lemmas
    # Both occurrences, not merely the mid-sentence one.
    assert report.excluded_tokens == 2
    assert report.counted_tokens == 7


def test_a_name_that_only_ever_opens_a_sentence_is_still_counted() -> None:
    """#89's RESIDUE, pinned rather than described. See #284.

    Nothing in `Sarah went to the shop.` distinguishes `Sarah` from an ordinary
    word opening a sentence, so it stays in the denominator and reads unknown.
    Coverage is understated, which is the safe direction — the alternative,
    excluding every sentence-initial capital, would drop the first word of
    every sentence in the language.

    This is asserted because a residue named in a docstring and not in a test
    is a residue that gets rediscovered as a bug.
    """
    known = frozenset({"go", "to", "the", "shop"})
    report = compute_coverage("Sarah went to the shop.", known)

    assert report.excluded_tokens == 0
    assert "sarah" in report.unknown_lemmas
    assert report.counted_tokens == 5


def test_a_lowercase_occurrence_of_a_name_form_is_still_counted() -> None:
    """The bound on #89's fix, in the direction that would do damage.

    #89's wording is *mark it as a name everywhere in the text*. Read as *every
    occurrence whatever its case*, `Jack` the person would drag `jack` the tool
    out of the denominator with it, and coverage would read HIGH — which is
    what puts a learner in front of material they cannot follow. So the capital
    is still required AT the occurrence; what W12a dropped is only the demand
    that the capital be mid-sentence.

    `jack` is the fixture because it is untagged. A tagged homograph never
    reaches this rule at all — `mark`, `bill`, `rose` and `will` all carry CEFR
    tags, which is what
    `test_a_capitalised_word_the_syllabus_levels_is_not_treated_as_a_name`
    covers.
    """
    assert "jack" not in cefr_tagged_lemmas()
    known = frozenset({"i", "see", "at", "the", "shop", "use", "a", "to", "lift", "car", "he"})
    text = "I saw Jack at the shop. He used a jack to lift the car."
    report = compute_coverage(text, known)

    assert report.excluded_tokens == 1       # the capitalised person, excluded
    assert "jack" in report.unknown_lemmas   # the lowercase tool, still counted


def test_a_capitalised_word_the_syllabus_levels_is_not_treated_as_a_name() -> None:
    """`internet` carries a CEFR tag; `sarah` does not. That is the whole rule."""
    assert "internet" in cefr_tagged_lemmas()
    assert "sarah" not in cefr_tagged_lemmas()
    report = compute_coverage(
        "I read about the Internet and about Sarah in that book yesterday.",
        frozenset({"i", "read", "about", "the", "internet", "and", "in",
                   "that", "book", "yesterday"}),
    )
    assert report.coverage == pytest.approx(1.0)
    assert report.excluded_tokens == 1  # Sarah, not Internet


# ── the casing gate ─────────────────────────────────────────────────────────

_SENTENCE = (
    "Sarah went to the shop and bought some bread for Michael before the rain. "
)
CONVENTIONAL = _SENTENCE * 3
LOWERCASE = CONVENTIONAL.lower()
UPPERCASE = CONVENTIONAL.upper()


def test_conventional_casing_applies_the_proper_noun_rule() -> None:
    report = compute_coverage(CONVENTIONAL, frozenset())
    assert report.casing == "conventional"
    assert report.proper_nouns_detected
    # Only `Michael` is excluded, three times. Each `Sarah` opens a sentence.
    assert report.excluded_tokens == 3


def test_lowercase_captions_switch_the_rule_off_and_say_so() -> None:
    """Auto-generated captions are often entirely lowercase.

    Nothing looks capitalised, so no name can be detected. The number is then
    biased low — a good video is rejected as too hard — and the report must
    admit it rather than present a degraded number as a clean one.
    """
    report = compute_coverage(LOWERCASE, frozenset())
    assert report.casing == "lowercase"
    assert not report.proper_nouns_detected
    assert report.excluded_tokens == 0


def test_uppercase_captions_switch_the_rule_off_before_it_does_damage() -> None:
    """The dangerous direction, and why disabling is the fix.

    With everything capitalised the rule would fire on every token the
    syllabus does not level — including genuinely unknown words, which would be
    *excluded* rather than counted, biasing coverage high. That is the drowning
    direction. Switched off, names merely count as unknown and the number is
    biased low instead.
    """
    report = compute_coverage(UPPERCASE, frozenset())
    assert report.casing == "uppercase"
    assert not report.proper_nouns_detected
    assert report.excluded_tokens == 0
    assert report.counted_tokens == compute_coverage(LOWERCASE, frozenset()).counted_tokens


def test_a_short_text_is_not_judged_on_its_casing() -> None:
    """Below the token floor the ratios mean nothing; the rule applies normally."""
    report = compute_coverage("i saw Sarah today", frozenset({"i", "see", "today"}))
    assert report.casing == "conventional"
    assert report.proper_nouns_detected


# ── resolving never invents ─────────────────────────────────────────────────


def test_lemmatize_returns_none_rather_than_guessing() -> None:
    for nonsense in ("zzzzq", "blorping", "frimbled", "quxes"):
        assert lemmatize(nonsense) is None


def test_an_unresolvable_token_is_counted_unknown_not_dropped() -> None:
    report = compute_coverage("the zzzzq sat", frozenset({"the", "sit"}))
    assert report.counted_tokens == 3
    assert report.coverage == pytest.approx(2 / 3)
    assert "zzzzq" in report.unknown_lemmas


def test_a_suffix_guess_is_only_accepted_when_it_is_already_a_lemma() -> None:
    """`stopped` resolves because `stop` exists; `blorped` does not."""
    assert lemmatize("stopped") == "stop"
    assert "blorp" not in seeded_lemmas()
    assert lemmatize("blorped") is None


def test_vocabulary_widens_what_is_accepted_so_a_grown_lexeme_is_recognised() -> None:
    """A lexeme grown from a tap is absent from `data/`, and must still resolve."""
    assert lemmatize("kubernetes") is None
    assert lemmatize("kubernetes", frozenset({"kubernetes"})) == "kubernetes"


# ── the homograph ordering ──────────────────────────────────────────────────


def test_saw_resolves_to_see_and_not_to_the_carpentry_tool() -> None:
    """The inflection table is consulted before the identity check.

    `saw` earns a lexeme row of its own off `sawing`/`sawed`, far down the
    list, while `see` sits near the top. Identity-first would leave "I saw a
    film" unresolvable for a learner who plainly knows `see`.
    """
    assert "saw" in seeded_lemmas()
    assert inflections()["saw"] == "see"
    assert lemmatize("saw") == "see"


def test_irregular_forms_resolve() -> None:
    assert lemmatize("went") == "go"
    assert lemmatize("children") == "child"
    assert lemmatize("women") == "woman"
    assert lemmatize("better") == "well"


# ── contractions ────────────────────────────────────────────────────────────


def test_contractions_expand_rather_than_becoming_their_own_lexemes() -> None:
    """A `gonna` row would fragment a ledger that already holds `go` and `to`."""
    assert [t.lower for t in tokenize("I don't think we're gonna")] == [
        "i", "do", "not", "think", "we", "are", "going", "to",
    ]
    assert "gonna" not in seeded_lemmas() or lemmatize("gonna") is not None


def test_curly_and_straight_apostrophes_are_one_token() -> None:
    assert [t.lower for t in tokenize("don’t")] == ["do", "not"]
    assert [t.lower for t in tokenize("don't")] == ["do", "not"]


def test_the_apostrophe_fold_agrees_with_the_one_the_services_use() -> None:
    """Two folds that disagree is how `don't` and `don’t` become two words.

    `core.services.reading.normalize_for_match` cannot be imported here — it
    lives in a module full of SQL and `core.lexicon` is pure — so the two are
    pinned by assertion instead of by an import that would breach the boundary.
    """
    for character in ("\u2019", "\u2018", "\u0060", "\u00b4",
                      "\u201c", "\u201d", "\u00ab", "\u00bb"):
        raw = f"it{character}s"
        assert normalize.fold_apostrophes(raw).casefold() == normalize_for_match(raw)


def test_the_items_fold_agrees_with_both_of_them() -> None:
    """W5's third fold, pinned to the same pair rather than imported across.

    `core/items/grading.fold` cannot import `normalize_for_match` either -- it
    lives in a module full of SQL and `core.items` is pure, the same boundary
    `core.lexicon` respects. So the same assertion covers it: three modules, one
    notion of "same string".

    This matters more here than anywhere else in the tree. `grading.fold` is
    what the blind-solver gate and the grader BOTH use, and if it drifted from
    what the rest of the system considers one word, an item would pass the
    uniqueness gate and then be ungradable -- the learner types the identical
    string and is marked wrong.
    """
    from core.items.grading import fold

    for character in ("\u2019", "\u2018", "\u0060", "\u00b4",
                      "\u201c", "\u201d", "\u00ab", "\u00bb"):
        raw = f"it{character}s"
        assert fold(raw) == normalize_for_match(raw)
        assert fold(raw) == normalize.fold_apostrophes(raw).casefold()

    # Whitespace collapse, which `normalize_for_match` also does.
    assert fold("  Hello   World  ") == normalize_for_match("  Hello   World  ")


def test_the_lexicon_folds_two_apostrophes_the_services_never_meet() -> None:
    """A superset, deliberately: transcripts carry U+02BC and U+2032.

    The direction matters. Folding *less* than the services do would split
    `don’t` from `don't` and quietly halve a contraction's frequency; folding
    more only ever merges two spellings of one word.
    """
    assert normalize.fold_apostrophes("he\u02bcs") == "he's"
    assert normalize.fold_apostrophes("he\u2032s") == "he's"


# ── the data files ──────────────────────────────────────────────────────────


def test_the_seed_file_parses_completely() -> None:
    rows = lexeme_rows()
    assert len(rows) == 15_000
    assert [row[2] for row in rows] == list(range(1, 15_001))


def test_a_word_that_looks_like_a_header_is_still_a_word() -> None:
    """`surface` is an English word at rank 1946, and a header row is not data.

    A header check that matched on text rather than position dropped it
    silently: no error, one lexeme short, and a hole in coverage with nothing
    pointing at it.
    """
    assert "surface" in seeded_lemmas()
    assert "lemma" not in {"", None}


def test_every_inflection_resolves_back_to_a_seeded_lemma() -> None:
    """Seeding and coverage must agree, or the ledger silently never matches."""
    lemmas = seeded_lemmas()
    offenders = [
        (surface, lemma) for surface, lemma in inflections().items()
        if lemma not in lemmas
    ]
    assert offenders == []


def test_seeding_and_coverage_lemmatise_through_the_same_function() -> None:
    """The same object, not two that agree today (CLAUDE.md §3 rule 5)."""
    assert coverage_module.lemmatize is normalize.lemmatize
    assert lexicon_service.lemmatize is normalize.lemmatize


def test_a_sample_of_seeded_lemmas_round_trips_through_its_own_inflections() -> None:
    """Every recorded surface form of a lemma resolves back to that lemma."""
    table = inflections()
    checked = 0
    for surface, lemma in table.items():
        if lemma in ("well", "wrong"):  # genuine many-to-one comparatives
            continue
        assert lemmatize(surface) == lemma, f"{surface} should resolve to {lemma}"
        checked += 1
        if checked >= 2000:
            break
    assert checked == 2000
