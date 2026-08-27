"""CLAUDE.md §4's banned-phrase rule, in one place, for **two** audiences.

Until W10c this pattern lived in `tests/support/no_guilt.py` and could only ever
be applied by a test. **#110 is that nothing could apply it to item content**:
`prompt_text`, `cue_text`, options, tiles and the canonical answer live in
`items`, and from this slice they are model-generated. They are the
highest-volume user-facing copy in the app and no check touched them.

A gate in `packages/core` cannot import from `tests/`, so the pattern moves here
and `tests/support/no_guilt.py` re-exports it. **That is one fewer copy, not one
more** — known issue #46 (five hand-copied regexes over eight hand-maintained
string lists) keeps its scope and its W19 target and is narrowed by exactly one.

────────────────────────────────────────────────────────────────────────────────
TWO PATTERNS, AND THE SPLIT IS THE WHOLE DESIGN

**A sentence a learner practises may contain the word "wrong". A thing the app
says about the learner may not.**

`BANNED` is unchanged and is for **copy the app says** — button labels, feedback,
nudges, empty states. Every existing caller keeps this one.

`BANNED_IN_CONTENT` is for **English a learner reads as material**: an item's
stem, its sentence, its explanation, its cue. It drops the bare words
`wrong / incorrect / missed / failed / broke`, because those are ordinary English
that ordinary sentences contain -- *"I missed the bus"*, *"we took the wrong
turning"*, *"the boiler broke again"* are exactly the everyday register §4 asks
the generator for. It keeps the second-person verdicts and the disappointed
faces, which are the app addressing the learner whatever field they arrive in.

**Without the split the check fires on shipped, correct content.**
`error_spot`'s own instruction is *"Tap the word that is wrong."* -- which #110's
own text calls fine, because it describes the sentence and not the learner. A
check that rejects correct content is a check the next person switches off, and
then nothing is covered at all.

`CONTENT_NARROWS` is the subset relation written down rather than asserted in
prose: every content term names the copy term it narrows, and the module refuses
to import if one of them is not a copy term. So `BANNED_IN_CONTENT` can never
come to forbid something `BANNED` permits -- the drift that would make the
looser rule the stricter one.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# The copy pattern -- unchanged from `tests/support/no_guilt.py`
# ---------------------------------------------------------------------------

#: Terms the three original Python copies already ban
#: (`test_hardening.py`, `test_motivation.py`, `test_shadow.py`).
_CARRIED: tuple[str, ...] = (
    r"\bmissed\b",
    r"\bfailed\b",
    r"\bbroke\b",
    r"wrong!",
    r"should have",
)

#: Added by W6, for the answer-feedback surface. Eleven components' worth of
#: wrong-answer feedback is the highest-risk copy in the app, and the phrasings
#: that come naturally -- "Wrong", "Incorrect", "You missed it" -- are exactly
#: the ones to refuse. The verdict belongs to the attempt, never to the person.
_ITEM_RENDERERS: tuple[str, ...] = (
    r"\bwrong\b",
    r"\bincorrect\b",
    r"try harder",
    r"you lost",
)

#: Disappointed faces, plus the two failure marks a renderer reaches for.
_SAD: tuple[str, ...] = (
    "😞", "😢", "😔", "☹️", "🙁", "😟", "😤", "😠", "❌", "✗",
)

COPY_TERMS: tuple[str, ...] = _CARRIED + _ITEM_RENDERERS + _SAD

BANNED = re.compile("|".join(COPY_TERMS), re.IGNORECASE)


# ---------------------------------------------------------------------------
# The content pattern -- W10c, #110
# ---------------------------------------------------------------------------

#: ``{term applied to content: the copy term it narrows}``.
#:
#: Read the left column as *the app addressing the learner*, which is banned
#: wherever it appears; read the right column as the reason it is still a subset
#: of the copy rule. The module-level assertion at the bottom is what keeps the
#: two from drifting apart in the wrong direction.
CONTENT_NARROWS: dict[str, str] = {
    # Second-person verdicts. Each contains its copy term, so anything caught
    # here is caught by `BANNED` too.
    r"you\s+failed": r"\bfailed\b",
    r"you\s+missed": r"\bmissed\b",
    # One term, not two, and it must CONTAIN "wrong" to be a narrowing of it.
    # The first draft had a bare `you\s+(?:always|keep|still)\s+get` here,
    # declared as narrowing `\bwrong\b` -- and "you always get" contains no
    # "wrong" at all, so the content rule would have forbidden a string the copy
    # rule permits and the two would have swapped roles. The declaration said
    # otherwise; `test_every_content_term_is_caught_by_both_patterns` drove a
    # real string through both patterns and caught it. That test is why the
    # relation is checked behaviourally and not only declared.
    r"you\s+(?:got|get|keep\s+getting|always\s+get|still\s+get)"
    r"\s+(?:it|that|this|them|these)?\s*wrong": r"\bwrong\b",
    r"wrong!": r"wrong!",
    r"try harder": r"try harder",
    r"you lost": r"you lost",
    r"should have": r"should have",
    # The faces carry no ordinary-English defence at all: a sentence a learner
    # practises has no reason to contain one, so they transfer unchanged.
    **{face: face for face in _SAD},
}

CONTENT_TERMS: tuple[str, ...] = tuple(CONTENT_NARROWS)

BANNED_IN_CONTENT = re.compile("|".join(CONTENT_TERMS), re.IGNORECASE)


def offenders(sources: dict[str, str], pattern: re.Pattern[str] = BANNED) -> list[str]:
    """``{path: text}`` -> one entry per banned term found, sorted by path.

    Takes a mapping rather than reading files so a meta-test can feed it
    deliberate violations without writing any, and takes the pattern so the same
    reporting shape serves both audiences.
    """
    found: list[str] = []
    for path, text in sorted(sources.items()):
        for match in pattern.finditer(text or ""):
            found.append(f"{path}: {match.group(0)!r}")
    return found


def content_offenders(text: str | None) -> tuple[str, ...]:
    """The banned terms present in one piece of learner-facing English.

    Returns what it found rather than a boolean, for the reason
    `naturalness.jargon_hits` returns its hits: a gate that says only "no"
    cannot be debugged, and the generator prompt is what has to change.
    """
    if not text:
        return ()
    seen: set[str] = set()
    out: list[str] = []
    for match in BANNED_IN_CONTENT.finditer(text):
        hit = match.group(0)
        folded = hit.casefold()
        if folded not in seen:
            seen.add(folded)
            out.append(hit)
    return tuple(out)


# Declared so the relation is checked rather than believed, the same way
# `core.items.schema` asserts its union against `ITEM_TYPES`. If a content term
# is ever added that does not narrow a copy term, the looser rule would be
# forbidding something the stricter one permits -- and this import fails.
assert set(CONTENT_NARROWS.values()) <= set(COPY_TERMS), (
    "BANNED_IN_CONTENT must stay a narrowing of BANNED: "
    f"{sorted(set(CONTENT_NARROWS.values()) - set(COPY_TERMS))} is not a copy term"
)

__all__ = [
    "BANNED",
    "BANNED_IN_CONTENT",
    "CONTENT_NARROWS",
    "CONTENT_TERMS",
    "COPY_TERMS",
    "content_offenders",
    "offenders",
]
