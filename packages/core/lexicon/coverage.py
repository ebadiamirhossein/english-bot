"""Known-word coverage: text plus a ledger → one number.

Pure. ``compute_coverage`` takes a set of lemmas, never a connection, which is
what lets it be tested without a database and keeps
``test_no_sql_outside_services`` unexempted. ``core.services.lexicon`` reads the
ledger and hands the set in.

W12 selects video by this number and W13 highlights what it reports unknown, so
every choice below is fixed here rather than left for those slices to
rediscover differently.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from core.lexicon.normalize import (
    Token,
    casing_profile,
    cefr_tagged_lemmas,
    lemmatize,
    tokenize,
)
from core.lexicon.states import COVERED_STATES

UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Everything a caller could want, so nobody re-derives the tokenisation."""

    coverage: float
    total_tokens: int
    counted_tokens: int
    excluded_tokens: int
    by_state: dict[str, int] = field(default_factory=dict)
    unknown_lemmas: tuple[str, ...] = ()
    #: False when the casing gate switched proper-noun exclusion off, so a
    #: caller can see the number was computed on a degraded basis.
    proper_nouns_detected: bool = True
    casing: str = "conventional"

    @property
    def percent(self) -> float:
        return round(self.coverage * 100, 2)


def compute_coverage(
    text: str,
    known_lemmas: frozenset[str],
    *,
    ledger: Mapping[str, str] | None = None,
    vocabulary: frozenset[str] | None = None,
) -> CoverageReport:
    """% of **counted tokens** whose lemma is in ``known``/``mastered``.

    Tokens, not types. Comprehensible input is defined on running words: if
    `the` is 6% of a transcript, a learner who knows `the` genuinely follows 6%
    of it. Types would weight `defenestrate` equally with `the` and so measure
    the *text's* vocabulary breadth rather than the *learner's* comprehension —
    and because the top hundred types are roughly half of all tokens, a
    type-based number would make every transcript look far harder than it is
    and put W12's band permanently out of reach.

    Excluded from numerator **and** denominator: numerals, ASR disfluency
    fillers, and proper nouns — a transcript full of names must not read as
    hard. Real interjections (`wow`, `oh`, `yeah`) stay in: they are words a
    learner either knows or does not.

    ``known_lemmas`` is the covered set. ``ledger`` optionally maps lemma →
    state so the report can break the count down; ``vocabulary`` is every lemma
    this learner has a row for, and it widens what ``lemmatize`` will accept so
    that a lexeme grown from a tap is still recognised in running text.
    """
    if vocabulary is None:
        vocabulary = frozenset(ledger) | known_lemmas if ledger else known_lemmas

    tokens = tokenize(text)
    casing = casing_profile(tokens)
    # Auto-generated captions are often entirely lower- or uppercase, and the
    # proper-noun rule reads capitalisation. Applied to uppercase text it fires
    # on everything absent from the syllabus — including genuinely unknown
    # words, which would then be *excluded* rather than counted, biasing
    # coverage high. That is the drowning direction. Switching the rule off
    # makes names count as unknown instead, biasing low, which W12 survives.
    detect_proper_nouns = casing == "conventional"

    tagged = cefr_tagged_lemmas()
    counted = 0
    excluded = 0
    by_state: dict[str, int] = {}
    unknown: dict[str, None] = {}

    for token in tokens:
        if _is_excluded(token, detect_proper_nouns, tagged):
            excluded += 1
            continue
        counted += 1
        lemma = lemmatize(token.surface, vocabulary)
        if lemma is None:
            # Never guessed at. An unresolved token counts unknown, so the
            # number reads low rather than falsely high.
            by_state[UNKNOWN] = by_state.get(UNKNOWN, 0) + 1
            unknown.setdefault(token.lower, None)
            continue
        state = ledger.get(lemma, UNKNOWN) if ledger else None
        if state is None:
            state = "known" if lemma in known_lemmas else UNKNOWN
        by_state[state] = by_state.get(state, 0) + 1
        if lemma not in known_lemmas:
            unknown.setdefault(lemma, None)

    covered = sum(count for state, count in by_state.items() if state in COVERED_STATES)
    if ledger is None:
        covered = by_state.get("known", 0)

    return CoverageReport(
        coverage=(covered / counted) if counted else 0.0,
        total_tokens=len(tokens),
        counted_tokens=counted,
        excluded_tokens=excluded,
        by_state=by_state,
        unknown_lemmas=tuple(unknown),
        proper_nouns_detected=detect_proper_nouns,
        casing=casing,
    )


def _is_excluded(token: Token, detect_proper_nouns: bool, tagged: frozenset[str]) -> bool:
    if token.is_numeric or token.is_filler:
        return True
    if not detect_proper_nouns:
        return False
    # A capitalised token that is not starting a sentence, and that no
    # vocabulary syllabus levels, is a name. The CEFR tag is the discriminator
    # because the frequency list is lowercased: `sarah` sits at rank 1221 with
    # no tag, `internet` at 2113 with A1.
    return (
        token.is_capitalised
        and not token.sentence_initial
        and token.lower not in tagged
    )
