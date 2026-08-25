"""What makes an instance of each type invalid, decided without a model.

Pure: no database, no network, no `core.llm`. Every function here is a function
of its arguments, which is what lets the whole set be tested with no Postgres
and no recorded fixtures.

**Deterministic first, always.** A check that can be made here costs nothing and
runs every time; a check that needs a model costs a call per item and can only
run after this file has already said yes. S24b's lesson is the precedent: exact
word-form validation with one capped retry beat every softer approach, and the
softer approaches were the ones that asked a model to judge what a string
comparison could decide.

Failure codes are stable strings. They are stored in `items.validation` and read
by tests, so renaming one is a data migration, not a refactor.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from core.items import TYPES_WITHOUT_ANSWER
from core.items.grading import fold, fold_answer
from core.items.schema import (
    BaseItem,
    ClozeCuedItem,
    CollocationPickItem,
    DictationItem,
    ErrorSpotItem,
    GAP,
    L1ToL2ProductionItem,
    ListeningGapItem,
    MatchPairsItem,
    MCQItem,
    SpeakAnswerItem,
    SpeakRepeatItem,
    WordBankOrderItem,
)
from core.lexicon.coverage import compute_coverage
from core.lexicon.normalize import CONTRACTIONS, lemmatize, tokenize

# v2's own constant, from `apps/bot/handlers/quiz.py:920`, kept rather than
# re-chosen: a stem longer than this does not fit a phone without scrolling,
# and W6's acceptance is that every type renders on a phone.
MAX_PROMPT_CHARS = 140

# PRD §4.6 wants spoken English. Twelve words is the ceiling v2's `quiz.txt`
# already used, and the sentences people say to friends are shorter than that.
MAX_SENTENCE_WORDS = 12

# PRD §2.1's comprehensible-input band. Below this the learner is decoding
# rather than practising the target, and the item tests vocabulary it did not
# mean to test. Applied only when the caller supplies a ledger.
COVERAGE_FLOOR = 0.90

# Reduced at conversational speed to the point where no learner can recover them
# from audio alone. Gapping one of these in a listening item tests hearing
# acuity, not English.
UNGAPPABLE_IN_AUDIO = frozenset({"a", "an", "of", "to", "the", "and", "or", "'s"})

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_LATIN = re.compile(r"[A-Za-z]")
_ARABIC_SCRIPT = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿]")
_LITHUANIAN = re.compile(r"[ąčęėįšųūžĄČĘĖĮŠŲŪŽ]")

# A spoken-answer stem that is not a question. PRD gives no list; these are the
# imperative openers that make an open production task well-formed.
_SPEAK_OPENERS = ("tell me", "describe", "say", "explain", "talk about")


@dataclass(frozen=True, slots=True)
class Failure:
    """One reason an item is invalid. `code` is stable; `detail` is for humans."""

    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


def words(text: str) -> list[str]:
    return _WORD.findall(text or "")


def sentence_of(item: BaseItem) -> str:
    """The English sentence this item is built on, whichever field holds it.

    Not always `prompt_text`: for `dictation` the stem is an instruction and the
    sentence is the answer, for `listening_gap` it is the transcript, and for
    `l1_to_l2_production` the stem is not English at all. A gate that must read
    the English asks here rather than assuming.

    **This is the STEM, gap and all.** It is what the mechanical rules and the
    deterministic checks want; it is not what the LLM naturalness judge wants.
    See `judged_sentence` below and W5b's finding (#115).
    """
    if isinstance(item, DictationItem):
        return item.answer or ""
    if isinstance(item, ListeningGapItem):
        return item.transcript
    if isinstance(item, WordBankOrderItem):
        return item.answer or ""
    if isinstance(item, L1ToL2ProductionItem):
        return item.answer or ""
    if isinstance(item, MatchPairsItem):
        return ""  # a mapping has no sentence; nothing to judge for naturalness
    if isinstance(item, ErrorSpotItem):
        return " ".join(item.tiles)
    return item.prompt_text


def judged_sentence(item: BaseItem) -> str:
    """`sentence_of` as PROSE — the gap closed, the wrong tile corrected.

    **The string the LLM naturalness judge is given, and the only caller that
    wants this one.** `item_naturalness.txt` asks whether a real person would
    say this to a friend; it never mentions gaps, exercises or learners, and it
    instructs rejection of anything "nobody actually phrases that way". Handing
    it `"I ___ to the shops yesterday."` or `"I goed to the shops"` is asking
    the right question about the wrong string, and a model that answers no is
    obeying its prompt. W5b measured it: 0/5 natural as shipped, 5/5 filled,
    across all four defective types, forty observations in the predicted
    direction (#115).

    **Deterministic, no model call**, by design. W5b's arm B was built this way
    for a reason: a second source of ambiguity inside the thing that decides is
    how a gate becomes unfalsifiable.

    Byte-identical to `sentence_of` for the seven types whose sentence is
    already prose, which `tests/test_items_judged_sentence.py` asserts in both
    directions so the change stays provably narrow.
    """
    if isinstance(item, ErrorSpotItem):
        tiles = list(item.tiles)
        tiles[item.wrong_index] = item.correction
        return " ".join(tiles)
    sentence = sentence_of(item)
    # The guard makes the function total, not because it is expected to fire:
    # the judge runs only after `deterministic_failures` has returned empty.
    if GAP in sentence and item.answer:
        return sentence.replace(GAP, item.answer)
    return sentence


def looks_proper_noun(word: str, sentence: str) -> bool:
    """Capitalised away from a sentence start, and not a known lemma.

    Deliberately the *same* rule `core.lexicon.coverage` uses to exclude proper
    nouns from the coverage denominator, rather than a second one written here.
    PRD §4.3 gate 2 says "never gap a proper noun"; if this rule and coverage's
    rule drifted, an item could be gapped on a token coverage does not count,
    and both halves would keep looking correct on their own terms.
    """
    target = fold(word)
    if not target:
        return False

    # A contraction is never a name, and `I'll` would otherwise trip every
    # heuristic below: it is capitalised, it carries an apostrophe, and the
    # lemma table cannot account for it as written. Getting this wrong does not
    # change *whether* the PRD's own broken item is rejected -- it changes the
    # REASON recorded in `items.validation`, and a wrong reason there is what
    # sends the next person to tune the wrong half of the generator prompt.
    # That item is ambiguous, not proper-nouned, and only the blind solver can
    # say so. PRD §4.3 makes the same point: "this is not a prompt-tuning
    # problem; it is a missing validation layer."
    if target in CONTRACTIONS or "'" in target:
        return False
    if target == "i":
        return False

    for token in tokenize(sentence):
        if token.lower != target:
            continue
        if token.is_capitalised and not token.sentence_initial:
            return True
    # A capitalised word the lemma table cannot account for is a name.
    return word[:1].isupper() and lemmatize(word) is None


# ---------------------------------------------------------------------------
# Shared — every type
# ---------------------------------------------------------------------------


def _shared(item: BaseItem, known_lemmas: frozenset[str] | None) -> list[Failure]:
    out: list[Failure] = []
    stem = item.prompt_text or ""

    if not stem.strip():
        out.append(Failure("empty_prompt", "prompt_text is blank"))
    if len(stem) > MAX_PROMPT_CHARS:
        out.append(
            Failure(
                "prompt_too_long",
                f"{len(stem)} chars, limit {MAX_PROMPT_CHARS}",
            )
        )

    sentence = sentence_of(item)
    n_words = len(words(sentence))
    if n_words > MAX_SENTENCE_WORDS:
        out.append(
            Failure(
                "sentence_too_long",
                f"{n_words} words, limit {MAX_SENTENCE_WORDS}",
            )
        )

    # Migration 012 encodes the same rule as a CHECK. It is repeated here so a
    # draft is rejected before it reaches SQL, with a message that names the
    # type rather than a constraint name.
    has_answer = item.answer is not None
    should_have = item.item_type not in TYPES_WITHOUT_ANSWER
    if has_answer != should_have:
        out.append(
            Failure(
                "answer_presence",
                f"{item.item_type} must {'have' if should_have else 'not have'} "
                f"an answer",
            )
        )

    if item.answer is not None:
        folded = fold_answer(item.answer)
        if folded and folded not in {fold_answer(v) for v in item.accepted_variants}:
            out.append(
                Failure(
                    "answer_not_accepted",
                    "accepted_variants does not contain the canonical answer",
                )
            )

    if item.lexeme is None and item.error_type is None and item.unit_number is None:
        out.append(
            Failure(
                "no_target",
                "gate 3 is unverifiable: no lexeme, error_type or unit_number",
            )
        )

    if known_lemmas is not None and sentence.strip():
        report = compute_coverage(sentence, known_lemmas)
        if report.coverage < COVERAGE_FLOOR:
            out.append(
                Failure(
                    "below_coverage_floor",
                    f"{report.percent}% known, floor {COVERAGE_FLOOR * 100}%",
                )
            )
    return out


# ---------------------------------------------------------------------------
# Per type
# ---------------------------------------------------------------------------


def _options_failures(options: tuple[str, ...], answer: str | None,
                      expected: tuple[int, ...]) -> list[Failure]:
    """Shared between `mcq` and `collocation_pick`; they differ only in count."""
    out: list[Failure] = []
    if len(options) not in expected:
        out.append(
            Failure("option_count", f"{len(options)} options, expected {expected}")
        )
    folded = [fold_answer(o) for o in options]
    if len(set(folded)) != len(folded):
        out.append(Failure("duplicate_options", "two options fold to one string"))
    for i, a in enumerate(folded):
        for j, b in enumerate(folded):
            if i != j and a and b and a != b and (a in b or b in a):
                out.append(
                    Failure(
                        "substring_option",
                        f"{options[i]!r} is contained in {options[j]!r}",
                    )
                )
    lengths = [len(o) for o in options if o]
    if lengths and max(lengths) > 2 * min(lengths):
        out.append(
            Failure(
                "option_length_tell",
                f"lengths {sorted(lengths)} — the odd one out is guessable "
                f"without reading the stem",
            )
        )
    if answer is not None and fold_answer(answer) not in folded:
        out.append(Failure("answer_not_an_option", "the answer is not offered"))
    return out


def _mcq(item: MCQItem) -> list[Failure]:
    out = _options_failures(item.options, item.answer, (4,))
    # More than one option accepted means two right answers, which is the
    # coin-flip bug in its most direct form.
    accepted = {fold_answer(v) for v in item.accepted_variants}
    hits = [o for o in item.options if fold_answer(o) in accepted]
    if len(hits) > 1:
        out.append(
            Failure("multiple_correct_options", f"{hits} are all accepted")
        )
    return out


def _cloze(item: ClozeCuedItem | ListeningGapItem) -> list[Failure]:
    out: list[Failure] = []
    stem = item.prompt_text
    gaps = stem.count(GAP)
    if gaps != 1:
        out.append(Failure("gap_count", f"{gaps} gaps, expected exactly 1"))

    answer = item.answer or ""
    if not answer.strip():
        return out

    if any(ch.isdigit() for ch in answer):
        out.append(
            Failure("numeric_gap", f"{answer!r} — a number is not recoverable")
        )
    if looks_proper_noun(answer, sentence_of(item)):
        out.append(
            Failure("proper_noun_gap", f"{answer!r} is a name (gate 2)")
        )

    # The answer already visible elsewhere in the stem gives itself away.
    visible = stem.replace(GAP, " ")
    if fold_answer(answer) and fold_answer(answer) in {
        fold_answer(w) for w in words(visible)
    }:
        out.append(
            Failure("answer_visible_in_stem", f"{answer!r} appears in the stem")
        )

    # Gate 3, deterministically: when a target lexeme is declared, the gapped
    # word must actually be that lexeme. S24b — exact word-form, not a lemma
    # match, when the target is grammar; the lemma check is the weaker of the
    # two and is what is available here.
    if item.lexeme is not None:
        lemma = lemmatize(answer)
        if lemma is not None and fold(lemma) != fold(item.lexeme):
            out.append(
                Failure(
                    "gap_misses_target",
                    f"gapped {answer!r} (lemma {lemma!r}) but the target is "
                    f"{item.lexeme!r}",
                )
            )

    # A first-letter cue that disagrees with the answer is worse than no cue.
    if item.cue_type == "first_letter_length" and item.cue_text:
        first = next((c for c in item.cue_text if c.isalpha()), None)
        if first and answer[:1].lower() != first.lower():
            out.append(
                Failure(
                    "cue_contradicts_answer",
                    f"cue {item.cue_text!r} vs answer {answer!r}",
                )
            )
    return out


def _listening_gap(item: ListeningGapItem) -> list[Failure]:
    out = _cloze(item)
    answer = item.answer or ""
    if fold(answer) in UNGAPPABLE_IN_AUDIO or len(answer.strip()) < 3:
        out.append(
            Failure(
                "unhearable_gap",
                f"{answer!r} is reduced at speed and cannot be recovered by ear",
            )
        )
    if fold_answer(answer) not in {fold_answer(w) for w in words(item.transcript)}:
        out.append(
            Failure(
                "answer_not_in_transcript",
                f"{answer!r} is not spoken in the transcript",
            )
        )
    # The stem must be the transcript with the gap punched in it, or the learner
    # is reading one sentence and hearing another.
    reconstructed = fold(item.prompt_text.replace(GAP, answer))
    if reconstructed != fold(item.transcript):
        out.append(
            Failure(
                "stem_transcript_mismatch",
                "prompt_text with the gap filled does not equal the transcript",
            )
        )
    return out


def _word_bank(item: WordBankOrderItem) -> list[Failure]:
    out: list[Failure] = []
    answer_tokens = words(item.answer or "")
    if not 4 <= len(item.bank) <= 10:
        out.append(Failure("bank_size", f"{len(item.bank)} tokens, expected 4-10"))
    # Permutation completeness — the check that catches a missing or extra
    # token, which makes the item unsolvable rather than merely hard.
    if Counter(fold(t) for t in item.bank) != Counter(fold(t) for t in answer_tokens):
        out.append(
            Failure(
                "bank_not_a_permutation",
                f"bank {list(item.bank)} does not rearrange to {item.answer!r}",
            )
        )
    if [fold(t) for t in item.bank] == [fold(t) for t in answer_tokens]:
        out.append(
            Failure("bank_already_ordered", "the bank is already the answer")
        )
    return out


def _error_spot(item: ErrorSpotItem) -> list[Failure]:
    out: list[Failure] = []
    if not 4 <= len(item.tiles) <= 8:
        out.append(Failure("tile_count", f"{len(item.tiles)} tiles, expected 4-8"))
    if not 0 <= item.wrong_index < len(item.tiles):
        out.append(
            Failure(
                "wrong_index_out_of_range",
                f"{item.wrong_index} against {len(item.tiles)} tiles",
            )
        )
        return out
    wrong = item.tiles[item.wrong_index]
    if fold_answer(wrong) == fold_answer(item.correction):
        out.append(
            Failure(
                "correction_is_a_no_op",
                f"{wrong!r} and the correction are the same word",
            )
        )
    if looks_proper_noun(wrong, " ".join(item.tiles)):
        out.append(Failure("proper_noun_target", f"{wrong!r} is a name"))
    return out


def _l1_production(item: L1ToL2ProductionItem) -> list[Failure]:
    out: list[Failure] = []
    stem = item.prompt_text
    if item.l1 == "fa":
        if not _ARABIC_SCRIPT.search(stem):
            out.append(
                Failure(
                    "l1_wrong_script",
                    "a Farsi prompt written in Latin letters is unreadable to "
                    "someone who reads the script (prompt_rules #45)",
                )
            )
    elif item.l1 == "lt" and not _LITHUANIAN.search(stem) and not stem.strip():
        out.append(Failure("l1_wrong_script", "prompt is not Lithuanian"))

    if not _LATIN.search(item.answer or ""):
        out.append(Failure("answer_not_english", "the answer is not in English"))

    # The type with the widest legitimate variation. One accepted form is a
    # trap: the learner produces a correct translation and is marked wrong.
    if len(item.accepted_variants) < 2:
        out.append(
            Failure(
                "too_few_variants",
                f"{len(item.accepted_variants)} accepted; a translation needs "
                f"at least 2",
            )
        )
    return out


def _dictation(item: DictationItem) -> list[Failure]:
    out: list[Failure] = []
    transcript = item.answer or ""
    n = len(words(transcript))
    if not 5 <= n <= 15:
        out.append(Failure("dictation_length", f"{n} words, expected 5-15"))
    if any(ch.isdigit() for ch in transcript):
        out.append(
            Failure(
                "digits_in_dictation",
                "'2020' or 'twenty twenty' are both right and it cannot be marked",
            )
        )
    for word in words(transcript):
        if looks_proper_noun(word, transcript):
            out.append(
                Failure(
                    "unspellable_name",
                    f"{word!r} is a name the learner has no way to spell",
                )
            )
            break
    return out


def _speak_repeat(item: SpeakRepeatItem) -> list[Failure]:
    out: list[Failure] = []
    # A repeat item with a gap is a category error, and it is one line to catch.
    if GAP in item.prompt_text:
        out.append(
            Failure("gap_in_repeat", "a repeat-after-me item cannot have a gap")
        )
    if fold(item.answer) != fold(item.prompt_text):
        out.append(
            Failure(
                "repeat_answer_differs",
                "the answer must be the sentence shown",
            )
        )
    if any(ch.isdigit() for ch in item.prompt_text):
        out.append(Failure("digits_in_speech", "TTS mispronounces bare digits"))
    return out


def _speak_answer(item: SpeakAnswerItem) -> list[Failure]:
    out: list[Failure] = []
    folded = fold(item.prompt_text)
    if not folded.endswith("?") and not folded.startswith(_SPEAK_OPENERS):
        out.append(
            Failure(
                "not_answerable",
                "an open-production stem must be a question or an imperative",
            )
        )
    if not item.rubric.strip():
        out.append(
            Failure("empty_rubric", "gate 3 is unverifiable without a rubric")
        )
    else:
        target = item.lexeme or item.error_type or ""
        if target and fold(target) not in fold(item.rubric):
            out.append(
                Failure(
                    "rubric_misses_target",
                    f"the rubric does not name {target!r}",
                )
            )
    return out


def _match_pairs(item: MatchPairsItem) -> list[Failure]:
    out: list[Failure] = []
    if not 3 <= len(item.pairs) <= 6:
        out.append(Failure("pair_count", f"{len(item.pairs)} pairs, expected 3-6"))
    lefts = [fold(left) for left, _ in item.pairs]
    rights = [fold(right) for _, right in item.pairs]
    if len(set(lefts)) != len(lefts):
        out.append(Failure("duplicate_left", "a left-hand key appears twice"))
    if len(set(rights)) != len(rights):
        out.append(Failure("duplicate_right", "a right-hand value appears twice"))
    overlap = set(lefts) & set(rights)
    if overlap:
        out.append(
            Failure(
                "columns_overlap",
                f"{sorted(overlap)} appear on both sides — the pairing gives "
                f"itself away",
            )
        )
    return out


def _collocation(item: CollocationPickItem) -> list[Failure]:
    out = _options_failures(item.options, item.answer, (3, 4))
    # The frame already containing the answer makes the choice free.
    if item.answer and fold_answer(item.answer) in {
        fold_answer(w) for w in words(item.prompt_text.replace(GAP, " "))
    }:
        out.append(
            Failure("answer_visible_in_stem", "the frame already uses the answer")
        )
    return out


_DISPATCH = {
    MCQItem: _mcq,
    ClozeCuedItem: _cloze,
    ListeningGapItem: _listening_gap,
    WordBankOrderItem: _word_bank,
    ErrorSpotItem: _error_spot,
    L1ToL2ProductionItem: _l1_production,
    DictationItem: _dictation,
    SpeakRepeatItem: _speak_repeat,
    SpeakAnswerItem: _speak_answer,
    MatchPairsItem: _match_pairs,
    CollocationPickItem: _collocation,
}


def deterministic_failures(
    item: BaseItem, *, known_lemmas: frozenset[str] | None = None
) -> tuple[Failure, ...]:
    """Every deterministic reason this item is invalid. Empty means "so far".

    ``known_lemmas`` is a frozenset and never a connection — the same shape
    `core.lexicon.coverage.compute_coverage` takes, and for the same reason.
    Omit it and the coverage floor is skipped, which is what lets the whole
    suite run without Postgres.
    """
    out = _shared(item, known_lemmas)
    handler = _DISPATCH.get(type(item))
    if handler is not None:
        out.extend(handler(item))
    return tuple(out)
