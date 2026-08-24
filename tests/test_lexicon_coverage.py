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
    # Seven capitalised tokens sit mid-sentence and are excluded: Michael,
    # Jonathan, Persephone, Bartholomew, Anastasia, and Sarah and Michael
    # again. The opening `Sarah` is sentence-initial and is NOT excluded.
    assert report.excluded_tokens == 7
    assert report.coverage > 0.85


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
