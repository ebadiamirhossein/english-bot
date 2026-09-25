"""Pronounceable non-words for the yes/no section. **Pure and deterministic.**

PRD §6: *"Yes/No lexical decision test … + 20 pseudowords. Score corrected for
false alarms."* The pseudo-words are the standard control against saying yes to
everything; a learner who says yes to *blorent* is guessing, and the estimate
subtracts it.

**Built from English-shaped syllables, not by a model.** A generated non-word
needs no billed call and cannot be a real word a model half-remembered; it is
then CHECKED ABSENT from `lexemes` and from every inflected form in
`inflections.tsv` (the caller passes both in). **What that check cannot see:**
an English word outside the 15,000-lemma list — a rare word, a brand, a word in
the learner's own language. **So every pseudo-word the bank holds is read by the
operator before the first sitting** (the launch pass's reading check), and a
real one is deleted by id before anyone is served it.

Deterministic for a seed, so the dry run prints exactly the list `--apply`
writes.
"""

from __future__ import annotations

import random
from collections.abc import Container

ONSETS = (
    "b", "bl", "br", "d", "dr", "f", "fl", "fr", "g", "gl", "gr", "h", "k", "l",
    "m", "n", "p", "pl", "pr", "r", "s", "sl", "sm", "sn", "sp", "st", "t", "tr",
    "v", "w",
)
VOWELS = ("a", "e", "i", "o", "u", "ai", "ea", "oa", "ee", "ou")
MEDIALS = ("b", "d", "f", "g", "l", "m", "n", "p", "r", "s", "t", "v", "nd", "nt", "st", "mp")
CODAS = ("b", "d", "g", "k", "l", "m", "n", "p", "t", "sk", "nt", "nd", "st", "ck", "sh")

#: Endings that would make a non-word read as an inflected real word, so a
#: learner could say yes to a stem they recognise. Refused.
_INFLECTED_ENDINGS = ("s", "ed", "ing", "er", "ly")


def candidate(rng: random.Random) -> str:
    """One two-syllable non-word: onset-vowel-medial-vowel-coda."""
    return (
        rng.choice(ONSETS) + rng.choice(VOWELS) + rng.choice(MEDIALS)
        + rng.choice(("a", "e", "i", "o", "u")) + rng.choice(CODAS)
    )


def pronounceable(word: str) -> bool:
    """Shape rules a pseudo-word must pass: 5–9 letters, no letter three times
    running, no inflectional ending."""
    if not 5 <= len(word) <= 9 or not word.isalpha() or not word.islower():
        return False
    if any(word[i] == word[i + 1] == word[i + 2] for i in range(len(word) - 2)):
        return False
    return not word.endswith(_INFLECTED_ENDINGS)


def pseudowords(
    n: int, *, seed: int, real: Container[str], avoid: Container[str] = frozenset()
) -> list[str]:
    """``n`` distinct pronounceable non-words, none in ``real`` or ``avoid``.

    Raises if ``n`` cannot be reached in a generous number of tries — a
    shape-rule change that starved the generator is a bug to see, not a
    shorter list to ship.
    """
    rng = random.Random(seed)
    out: list[str] = []
    seen: set[str] = set()
    for _ in range(n * 500):
        word = candidate(rng)
        if word in seen:
            continue
        seen.add(word)
        if not pronounceable(word) or word in real or word in avoid:
            continue
        out.append(word)
        if len(out) == n:
            return out
    raise ValueError(f"only {len(out)} of {n} pseudo-words could be made")
