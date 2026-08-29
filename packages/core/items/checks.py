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

from core.copy_rules import content_offenders
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

# ---------------------------------------------------------------------------
# Per-type numeric bounds
# ---------------------------------------------------------------------------
#
# **Promoted from inline literals 2026-08-27, so the GENERATOR PROMPT can be
# derived from them rather than restating them.** W10c's first real accept rate
# was 6 of 24, and its branch rule -- *the prompt is wrong, not the gate* --
# fired correctly: the contract carried field NAMES and no SHAPE, so the model
# was told `bank: array of strings` and left to guess that a word bank must hold
# 4-10 tokens, be a permutation of the answer, and not already be in order.
#
# A hand-written list of bounds in the prompt would be a second copy of these
# numbers, and this record is a history of a copy and its source drifting.
# `core.items.schema.constraint_block` reads THESE NAMES.

#: `mcq` shows exactly four; `collocation_pick` three or four.
MCQ_OPTIONS: tuple[int, ...] = (4,)
COLLOCATION_OPTIONS: tuple[int, ...] = (3, 4)

#: A word bank small enough to tap on a phone and large enough to be a task.
BANK_SIZE: tuple[int, int] = (4, 10)

#: `error_spot` tiles. Fewer than four is not a sentence; more than eight does
#: not fit a phone row.
TILE_COUNT: tuple[int, int] = (4, 8)

#: A bijection worth doing, small enough to hold in view.
PAIR_COUNT: tuple[int, int] = (3, 6)

#: `l1_to_l2_production` is the type with the widest legitimate variation, so one
#: accepted form is a trap: the learner produces a correct translation and is
#: marked wrong.
MIN_ACCEPTED_VARIANTS = 2

#: A dictation short enough to hold in memory and long enough to be worth typing.
DICTATION_WORDS: tuple[int, int] = (5, 15)

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


def probe_canonical(item: BaseItem) -> str | None:
    """What the BLIND SOLVER's answer is compared against. Not always `answer`.

    **`error_spot` is the one type where the two differ, and #210 is why.**
    Its `answer` is the WRONG word — the token the learner taps — and asking a
    probe to name it is asking a question that can have two defensible answers:
    in *"I have went there twice"* the wrong tile is arguably `went` (should be
    `been`) or `have` (should be dropped), and **both describe one error.** The
    probe naming the other token yielded `not_recoverable`, and because
    `ANSWER_FAMILY['error_spot']` is `fixed_option` there is no widening and no
    cue repair — one probe, then discarded. Three of W10c's first real run died
    that way on `went`, `ever` and `study`.

    **The CORRECTION is a question with one answer.** *What should this say?*
    does not depend on which of two tokens you consider defective, so the probe
    recovers a fact instead of guessing an authoring choice.

    Same shape as `sentence_of` / `judged_sentence`: a gate that needs a
    different field asks here rather than assuming.
    """
    from core.items.schema import ErrorSpotItem

    if isinstance(item, ErrorSpotItem):
        return item.correction
    return item.answer


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


def _learner_facing_text(item: BaseItem) -> list[tuple[str, str | None]]:
    """Every string on this item that a learner can end up reading, named.

    Enumerated from the model rather than hand-listed for the per-type extras,
    so a field added to a type is scanned from the moment it exists -- the same
    property `schema.payload_of` has and for the same reason. `_UNREAD_FIELDS`
    is the exclusion list, and it is short and explained.

    `explanation` is here and it is new: `core/prompts/item_generate.txt` never
    asked for one until W10c (#103), so the panel that renders it has had
    nothing to render and this scan would have had nothing to scan.
    """
    named: list[tuple[str, str | None]] = [
        ("prompt_text", item.prompt_text),
        ("answer", item.answer),
        ("cue_text", item.cue_text),
        ("explanation", item.explanation),
        ("definition", item.definition),
        ("l1_gloss", item.l1_gloss),
    ]
    seen = {name for name, _ in named}
    for name in type(item).model_fields:
        if name in seen or name in _UNREAD_FIELDS:
            continue
        value = getattr(item, name, None)
        if isinstance(value, str):
            named.append((name, value))
        elif isinstance(value, tuple):
            for index, entry in enumerate(value):
                if isinstance(entry, str):
                    named.append((f"{name}[{index}]", entry))
                elif isinstance(entry, tuple):
                    for side, half in enumerate(entry):
                        if isinstance(half, str):
                            named.append((f"{name}[{index}][{side}]", half))
    return named


#: Fields that are not English a learner reads: enumerations, tags and the
#: target bindings. `track`, `register` and `item_type` are closed vocabularies;
#: `lexeme`, `error_type` and `grammar_target` are operator-side bindings that
#: `projection.NEVER_VISIBLE` already keeps off every wire.
_UNREAD_FIELDS: frozenset[str] = frozenset(
    {
        "item_type",
        "track",
        "register_tag",
        "cue_type",
        "lexeme",
        "error_type",
        "unit_number",
        "grammar_target",
        "accepted_variants",
        "l1",
        "wrong_index",
    }
)


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

    # CLAUDE.md §4's no-guilt rule, reaching item content for the first time
    # (#110). Until W10c the banned-phrase scan could only be applied by a test,
    # so it covered components and never the strings inside them -- and from
    # W10c those strings are model-generated and are the highest-volume
    # user-facing copy in the app.
    #
    # **`BANNED_IN_CONTENT`, not `BANNED`**, and the narrower rule is the point:
    # a sentence a learner practises may contain the word "wrong", and a thing
    # the app says about the learner may not. The looser pattern fires on
    # `error_spot`'s own shipped instruction -- "Tap the word that is wrong." --
    # which is correct content, and a check that rejects correct content is a
    # check the next person switches off. See `core.copy_rules`.
    #
    # Scanned per field so the failure names WHERE it was found: the generator
    # prompt is what has to change, and "somewhere in this item" does not tell
    # anyone which instruction to rewrite.
    for field_name, value in _learner_facing_text(item):
        hits = content_offenders(value)
        if hits:
            out.append(
                Failure("guilt_phrase", f"{field_name}: {list(hits)}")
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
    out = _options_failures(item.options, item.answer, MCQ_OPTIONS)
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
    if not BANK_SIZE[0] <= len(item.bank) <= BANK_SIZE[1]:
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
    if not TILE_COUNT[0] <= len(item.tiles) <= TILE_COUNT[1]:
        out.append(Failure("tile_count", f"{len(item.tiles)} tiles, expected 4-8"))
    if not 0 <= item.wrong_index < len(item.tiles):
        out.append(
            Failure(
                "wrong_index_out_of_range",
                f"{item.wrong_index} against {len(item.tiles)} tiles",
            )
        )
        return out
    # **`prompt_text` IS THE INSTRUCTION AND THE SENTENCE LIVES IN `tiles` (#271).**
    #
    # `ErrorSpot` renders `prompt_text` as the stem with the tiles beneath it, and
    # `projections.fixture.json` has always carried `prompt_text: "Tap the word
    # that is wrong."` with the sentence in `tiles`. **That convention was real,
    # was what the renderer implements, and was written down nowhere the
    # generator could read** -- `schema.py`'s `error_spot` block specified tiles,
    # `wrong_index`, `answer` and `correction` and said nothing about
    # `prompt_text`.
    #
    # So the generator took the other reasonable reading and wrote the SENTENCE
    # there. On H4 (2026-08-29) question 10 showed *"I was walk home when it
    # started raining."* as the stem, the same words as tappable tiles below it,
    # and **nothing telling the learner what to do** -- indistinguishable from a
    # word bank, and the sentence rendered twice.
    #
    # **Every render test passed throughout, because the fixture obeyed the
    # convention: a suite agreeing with itself.** This is the check that makes the
    # convention enforceable rather than merely true of one committed file.
    #
    # SUBSTRING and not equality: a wrapper -- *"Find the mistake: I was walk
    # home yesterday."* -- is the same defect wearing a prefix, and folding both
    # sides means a trailing full stop cannot smuggle it past.
    joined = fold_answer(" ".join(item.tiles))
    if joined and joined in fold_answer(item.prompt_text):
        out.append(
            Failure(
                "prompt_is_the_sentence",
                f"prompt_text contains the tiles' own sentence; it must be the "
                f"INSTRUCTION (the fixture's is 'Tap the word that is wrong.') "
                f"and the sentence belongs in `tiles`",
            )
        )

    wrong = item.tiles[item.wrong_index]
    # **`answer` MUST be the tile `wrong_index` points at, and nothing checked
    # it until 2026-08-27.** `response.chosen_option` returns
    # `item.tiles[tapped]`, and `grade_text` compares that against
    # `accepted_variants`, which is derived from `answer` -- so an `answer` that
    # is not the wrong tile means **a learner taps the correct tile and is
    # marked wrong.** That is the failure the whole v3 rebuild exists to end.
    #
    # Found because W10c's first real run returned the FULL CORRECTED SENTENCE
    # in `answer` while `tiles[wrong_index]` was `went`; it parsed, passed every
    # deterministic check, and would have graded every correct tap as wrong.
    # `item_generate.txt` has stated this rule since the constraint block was
    # derived -- it was stated and unenforced, which is #199's shape.
    if fold_answer(item.answer) != fold_answer(wrong):
        out.append(
            Failure(
                "answer_not_the_wrong_tile",
                f"answer is {item.answer!r} but tiles[{item.wrong_index}] is "
                f"{wrong!r} — a correct tap would be graded wrong",
            )
        )
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
    if len(item.accepted_variants) < MIN_ACCEPTED_VARIANTS:
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
    if not DICTATION_WORDS[0] <= n <= DICTATION_WORDS[1]:
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
    if not PAIR_COUNT[0] <= len(item.pairs) <= PAIR_COUNT[1]:
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
    out = _options_failures(item.options, item.answer, COLLOCATION_OPTIONS)
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
