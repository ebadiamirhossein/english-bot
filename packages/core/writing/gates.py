"""W16a — what a generated correction must survive before a learner sees it.

**WHAT THESE GATES CAN AND CANNOT ESTABLISH, STATED FIRST SO NO GREEN RUN IS
READ AS A VERDICT (#271).** Each gate refuses a shape it can recognise: a banned
word, a number, a stock phrase, a second sentence, an original the learner never
wrote, a change whose learner-side token is not an English word. **None of them
can show that the opening line is TRUE of what was written, that a correction's
rule is RIGHT, or that a journal row is a GENUINE error rather than a model
misreading.** Those are human checks, and they are in Next action as such.

**EVERY REFUSAL REMOVES; NOTHING IS REPAIRED OR REPLACED.** A refused opening
line becomes *absent* — never a fallback string, because the fallback is the
platitude Ruling 2 forbids (`correction.apply_result`'s `"Nice."`, which survives
on the bot path only). A refused correction is dropped before it is written.
Removal is the recoverable direction: CLAUDE.md §5, *a wrong entry is permanent
damage, a missing one is recoverable.*
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from core.copy_rules import BANNED, content_offenders
from core.lexicon.normalize import lemmatize

# ---------------------------------------------------------------------------
# Normalisation shared by G1 and G2
# ---------------------------------------------------------------------------

_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})
_SPACE = re.compile(r"\s+")
_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")


def _normal(text: str) -> str:
    """Casefolded, quotes straightened, whitespace collapsed.

    **Casefolded, and that is a decision rather than a convenience:** the model
    routinely re-capitalises the start of a clause it quotes back. Case is never
    the difference between a sentence the learner wrote and one they did not.
    """
    text = unicodedata.normalize("NFC", text or "").translate(_QUOTES)
    return _SPACE.sub(" ", text).strip().casefold()


# ---------------------------------------------------------------------------
# G1 — self-produced
# ---------------------------------------------------------------------------


def is_self_produced(you_said: str, submitted: str) -> bool:
    """**G1.** The original must be a substring of what the learner submitted.

    A correction whose `you_said` is not in the text is a correction of a
    sentence the learner did not write — paraphrased, merged, or invented — and
    CLAUDE.md §5 allows only genuine self-produced errors into `errors`.

    **What it cannot show:** that the correction is right. It only shows the
    original is theirs.
    """
    needle = _normal(you_said)
    return bool(needle) and needle in _normal(submitted)


# ---------------------------------------------------------------------------
# G2 — typo
# ---------------------------------------------------------------------------


def changed_learner_tokens(you_said: str, correct_form: str) -> list[str]:
    """The learner's words that the correction removed or replaced.

    Tokens carrying an apostrophe are left out: `lemmatize` resolves lemmas, not
    contractions, and a contraction failing to resolve is not evidence of a
    misspelling. A pure insertion (a missing article) changes no learner token.
    """
    kept = {_normal(t) for t in _WORD.findall(correct_form or "")}
    out: list[str] = []
    for token in _WORD.findall(you_said or ""):
        low = _normal(token)
        if "'" in low or low in kept:
            continue
        out.append(low)
    return out


def is_typo(you_said: str, correct_form: str) -> bool:
    """**G2.** A correction whose changed learner token is not an English word.

    `togehter → together` is a misspelling, and CLAUDE.md §5 says typos never
    reach the journal. The test is the one `/talk`'s `capturable` uses:
    `lemmatize(word, frozenset())` against the reference lexicon, so the
    learner's own grown lexemes cannot vouch for a token.

    **TWO STATED LIMITS, BOTH PINNED BY TESTS RATHER THAN HOPED AWAY.**

    1. **A typo that lands on a real word PASSES** (`weed` for `we'd`). That is
       the direction #402 already accepted.
    2. **A genuine error whose changed learner token is a real English word
       OUTSIDE the reference lexicon is DROPPED.** Found while building, by
       checking the gate against real tokens rather than trusting it:
       `data/lexemes.tsv` holds 15,000 lemmas and `spreadsheet` is not one of
       them, so *"two spreadsheets"* corrected to *"two spreadsheet"*-anything
       would be refused as a misspelling. **This errs toward a MISSING journal
       row, which is the recoverable direction (CLAUDE.md §5)**, and it is
       recorded in the decisions log rather than widened away — accepting
       unresolved tokens would let every misspelling through.
    """
    return any(lemmatize(token, frozenset()) is None for token in changed_learner_tokens(you_said, correct_form))


# ---------------------------------------------------------------------------
# Explanation gate
# ---------------------------------------------------------------------------


def explanation_is_clean(explanation: str) -> bool:
    """An explanation is MATERIAL a learner reads, so it takes the content rule.

    `BANNED_IN_CONTENT` and not `BANNED`: *"the boiler broke"* is ordinary
    English an explanation may quote. The second-person verdicts and the faces
    are refused wherever they appear.
    """
    return not content_offenders(explanation)


# ---------------------------------------------------------------------------
# The opening line — Ruling 2
# ---------------------------------------------------------------------------

#: Stock praise. A line that could be said about ANY entry says nothing about
#: this one, and Ruling 2's silent branch is *an empty line, not a platitude*.
PLATITUDES: frozenset[str] = frozenset(
    {
        "nice",
        "nice work",
        "nice job",
        "good",
        "good job",
        "good work",
        "great",
        "great job",
        "great work",
        "well done",
        "excellent",
        "perfect",
        "awesome",
        "keep it up",
        "keep up the good work",
        "good effort",
        "great effort",
    }
)

#: A number, or the vocabulary of a mark. The opening line is the first thing a
#: learner reads about their own writing; a figure there is a score (§4).
#:
#: **`point`/`points` was in this list and was REMOVED on its first contact
#: with a real sentence:** *"You kept the sentence short and to the point."* is
#: specific, true-shaped praise and the gate refused it. A refusal only makes
#: the line absent — the recoverable direction — but a gate that throws away
#: good lines is one someone switches off. `test_writing_rules.py` pins it.
_SCORE = re.compile(
    r"\d|%|/\s*10\b|\b(?:score|scores|scored|mark|marks|rating|rated|grade|graded)\b",
    re.IGNORECASE,
)

#: **F1 (operator, on the first §3 rule 2 call).** The opening line DESCRIBES
#: THE ENTRY and never RATES THE LEARNER. The clean fixture returned *"…shows
#: you can handle more complex time relationships between past events."* — true,
#: specific, and a verdict on the person: CLAUDE.md §4 bans a score, and this is
#: a score in prose. The prompt now says so; this refuses the shape when the
#: model does it anyway.
#:
#: The shapes are the operator's list: `you can/could`, `shows (that) you`,
#: `able to`, `your ability`. **Bare `can`/`could` without `you` are not
#: matched.** **STATED LIMIT, PINNED:** `you can` also refuses a line that only
#: describes — *"You can see the whole day in it"* — because the pattern cannot
#: tell a description from a verdict. That is an over-refusal, and an absent
#: line is the recoverable direction. Nor can the gate tell a warm description
#: from a judgement phrased some other way (#271), which is why the reading
#: stays a human check.
_EVALUATIVE = re.compile(
    r"\b(?:you\s+(?:can|could)|show(?:s|ing|ed)?\s+(?:that\s+)?you|able\s+to|your\s+abilit(?:y|ies))\b",
    re.IGNORECASE,
)

#: A second sentence: terminal punctuation followed by more text.
_SECOND_SENTENCE = re.compile(r"[.!?]+[\"')\]]*\s+\S")


def opening_line(raw: object) -> str | None:
    """The opening line if it survives, else ``None``. **Never a fallback.**

    Refused when blank, when it carries a `BANNED` term (it is the app
    addressing the learner, so it takes the COPY rule, not the content one),
    when it is a stock phrase, when it carries a number or a mark word, or when
    it is more than one sentence.
    """
    if not isinstance(raw, str):
        return None
    line = _SPACE.sub(" ", raw).strip()
    if not line:
        return None
    if BANNED.search(line):
        return None
    if _SCORE.search(line):
        return None
    if _EVALUATIVE.search(line):
        return None
    if _SECOND_SENTENCE.search(line):
        return None
    bare = re.sub(r"[^a-z ]", "", line.casefold()).strip()
    if _SPACE.sub(" ", bare) in PLATITUDES:
        return None
    return line


# ---------------------------------------------------------------------------
# Structure feedback — W16b
# ---------------------------------------------------------------------------

#: The shapes of a rubric that `_SCORE` does not already refuse: a mark "out of"
#: something, and the named dimensions the design's Q3 rejected — *a rubric grows
#: a rating, and a rating is a score.*
_RUBRIC = re.compile(r"\bout\s+of\b|\b(?:opening|order|linking)\s*:", re.IGNORECASE)

MAX_STRUCTURE_PARAGRAPHS = 2


def _word_run(text: str) -> list[str]:
    """Whole words, casefolded, quotes straightened — punctuation and spacing gone."""
    return _WORD.findall(_normal(text))


def _contains_run(outer: list[str], inner: list[str]) -> bool:
    n = len(inner)
    return n > 0 and any(outer[i : i + n] == inner for i in range(len(outer) - n + 1))


def overlaps_a_correction(quote: str, you_said: str) -> bool:
    """**Either stretch contains the other, on whole words** (live defect, 2026-09-14).

    Whole words and not characters, so `an` does not match `any`; punctuation and
    spacing are ignored, so `more.` matches `more`. **Stated limit, pinned:** a
    correction that shares only PART of the quote — neither containing the other —
    does not match.
    """
    q, s = _word_run(quote), _word_run(you_said)
    return _contains_run(q, s) or _contains_run(s, q)


def structure_of(
    raw: object,
    submitted: str,
    *,
    corrected: Iterable[str] = (),
    overlapped: list[int] | None = None,
) -> tuple[dict, ...] | None:
    """The structure prose if it survives, else ``None``. **All or nothing.**

    **LIVE DEFECT, 2026-09-14, the first real paragraph call:** the prose quoted
    *"we can't depend of the old plan any more"* as the paragraph's strongest
    moment, and a correction below fixed that exact stretch — the learner's error
    praised in the app's voice, then corrected. **So a paragraph with a `quote: true`
    segment that overlaps any `corrected` stretch is DROPPED, and the other paragraphs
    are kept** (`overlaps_a_correction`). Zero paragraphs left → absent. Each dropped
    paragraph's 1-based number is appended to ``overlapped`` (an out-parameter, as
    `core.llm.chat`'s `usage_out`), so `shape` can name it in `dropped`.

    **OPERATOR REVERSAL, 2026-09-14: PER-PARAGRAPH, NOT BLOCK-LEVEL.** This read
    *"a `quote: true` segment that overlaps any `corrected` stretch refuses the whole
    block"*, on the operator's ruling *"Absent beats wrong — the whole structure block
    drops, per the existing rule."* Reversed because the check fired on the first real
    response, 1 for 1, and so will fire often: all-or-nothing would leave Thursday with
    no structure feedback at all, and paragraph 1 of that response was good teaching.
    *Absent beats wrong; absent does not beat right.*

    **EVERY OTHER RULE IS STILL BLOCK-LEVEL, AND IT RUNS FIRST, OVER EVERY PARAGRAPH
    THE MODEL SENT:** the paragraph count (so dropping one of three cannot rescue an
    over-long block), a banned term, a digit or mark word, a rubric shape, an invented
    quote, a malformed segment. Those say the model broke the contract, so nothing in
    the block is trusted. The overlap says one paragraph praised one error. The prompt is told as well
    (`writing_paragraph.txt`); this is what holds when being told is not enough.

    **W16b. EXTENDS W16a's GATES RATHER THAN DUPLICATING THEM:** `BANNED` (the
    app addressing the learner), `_SCORE` (a digit or a mark word) and `_normal`
    (G1's whitespace- and case-tolerant match) are the same objects the opening
    line and G1 use; only `_RUBRIC` is new.

    Refused, and the WHOLE block becomes absent, when: it is not one or two
    paragraphs; any paragraph has no segments; any segment is not a non-blank
    string with a boolean `quote`; any segment carries a banned term, a digit, a
    mark word or a rubric shape; or **a `quote: true` segment is not the
    learner's own words** — an invented quote is the gate's most important catch,
    because the design's Q3 rests on quoting being what keeps the prose specific.

    **WHAT IT CANNOT ESTABLISH (#271): that the prose describes THIS paragraph
    correctly, or that it teaches.** It refuses what it catches. The reading is a
    human check (HP2).
    """
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_STRUCTURE_PARAGRAPHS:
        return None
    paragraphs: list[dict] = []
    for paragraph in raw:
        segments = paragraph.get("segments") if isinstance(paragraph, Mapping) else None
        if not isinstance(segments, list) or not segments:
            return None
        clean: list[dict] = []
        for segment in segments:
            if not isinstance(segment, Mapping):
                return None
            text, quote = segment.get("text"), segment.get("quote", False)
            if not isinstance(text, str) or not text.strip() or not isinstance(quote, bool):
                return None
            if BANNED.search(text) or _SCORE.search(text) or _RUBRIC.search(text):
                return None
            if quote and _normal(text) not in _normal(submitted):
                return None
            clean.append({"text": text, "quote": quote})
        paragraphs.append({"segments": clean})

    # Per-paragraph, and only now: every block-level rule above has passed for every
    # paragraph the model sent.
    stretches = tuple(corrected)
    kept: list[dict] = []
    for number, paragraph in enumerate(paragraphs, start=1):
        praises_an_error = any(
            segment["quote"] and any(overlaps_a_correction(segment["text"], s) for s in stretches)
            for segment in paragraph["segments"]
        )
        if praises_an_error:
            if overlapped is not None:
                overlapped.append(number)
            continue
        kept.append(paragraph)
    return tuple(kept) or None


# ---------------------------------------------------------------------------
# Every gate, in order — the one function the service and the probe both call
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Shaped:
    """What survives of one model response.

    ``dropped`` counts refusals by reason code and is for the probe's printout
    and for logs — **codes only, never the text** (CLAUDE.md §5).
    """

    is_english: bool
    did_well: str | None
    corrections: tuple[dict, ...] = ()
    dropped: dict[str, int] = field(default_factory=dict)
    #: W16b. The paragraph's structure prose, gated; ``None`` on the journal.
    structure: tuple[dict, ...] | None = None


def shape(
    raw: Mapping,
    submitted: str,
    *,
    limit: int,
    labels: Mapping[str, str | None],
    kind: str = "journal",
) -> Shaped:
    """Apply every gate to one parsed response. **The only place they run.**

    ``labels`` is ``error_types.code → learner_label`` and doubles as the set of
    valid codes, so a code the taxonomy does not hold is refused here as well as
    by `record_errors` — the learner is never shown a correction the journal
    would drop.

    **The cap is applied AFTER the gates**, so a refused correction does not
    consume one of the two places. Corrections past the cap are counted as
    ``over_cap`` and neither shown nor written.

    A response the model marked not English carries no opening line and no
    corrections: the entry is not the learner's English to comment on.

    **W16b, ``kind="paragraph"``:** no opening line (design `1n` draws none — a
    field nothing renders is a defect), `structure` through `structure_of`, and
    each kept correction carries the model's nominated `keep` phrase for
    `core.writing.offers` to judge. The `keep` value is never put on the wire.
    """
    if raw.get("is_english", True) is False:
        return Shaped(is_english=False, did_well=None)

    dropped: Counter[str] = Counter()
    kept: list[dict] = []
    for item in raw.get("corrections") or []:
        if not isinstance(item, Mapping):
            dropped["malformed"] += 1
            continue
        code = item.get("error_type")
        you_said = str(item.get("you_said") or "").strip()
        correct_form = str(item.get("correct_form") or "").strip()
        explanation = str(item.get("explanation") or "").strip()
        if code not in labels:
            dropped["unknown_type"] += 1
            continue
        if not you_said or not correct_form or not explanation:
            dropped["malformed"] += 1
            continue
        if _normal(you_said) == _normal(correct_form):
            dropped["no_change"] += 1
            continue
        if not is_self_produced(you_said, submitted):
            dropped["not_self_produced"] += 1
            continue
        if is_typo(you_said, correct_form):
            dropped["typo"] += 1
            continue
        if not explanation_is_clean(explanation):
            dropped["explanation"] += 1
            continue
        if len(kept) >= limit:
            dropped["over_cap"] += 1
            continue
        kept.append(
            {
                "you_said": you_said,
                "correct_form": correct_form,
                "error_type": code,
                "explanation": explanation,
                "label": labels[code],
                "keep": item.get("keep") if kind == "paragraph" else None,
            }
        )

    if kind == "paragraph":
        # EVERY stretch the model called an error, kept or not: a quote is not
        # praiseworthy because its correction failed a gate (over-refusal is the
        # recoverable direction).
        corrected = [
            str(item.get("you_said") or "")
            for item in raw.get("corrections") or []
            if isinstance(item, Mapping)
        ]
        raw_structure = raw.get("structure")
        overlapped: list[int] = []
        structure = structure_of(raw_structure, submitted, corrected=corrected, overlapped=overlapped)
        # Counted so the probe's `dropped by gate` and the service log can SHOW each
        # refusal — codes and paragraph numbers, never text (CLAUDE.md §5).
        for number in overlapped:
            dropped[f"structure_paragraph_{number}"] += 1
        if structure is None and not overlapped and isinstance(raw_structure, list) and raw_structure:
            dropped["structure"] += 1  # a block-level rule refused the whole block
        return Shaped(
            is_english=True,
            did_well=None,
            corrections=tuple(kept),
            dropped=dict(dropped),
            structure=structure,
        )
    return Shaped(
        is_english=True,
        did_well=opening_line(raw.get("did_well")),
        corrections=tuple(kept),
        dropped=dict(dropped),
    )
