"""W16b — which phrases from a paragraph's corrections are offered to the deck.

**Q-E, operator-accepted 2026-09-14. A NEW RULE, NOT A REUSE OF `/talk`'s.**
`capturable` (`core.services.conversations`) keeps single tokens from the
LEARNER's typed turns that resolve against the reference lexicon and carry a
CEFR tag. This rule is the reverse on the axis that matters:

* **Candidates come only from the app's own `correct_form`, never from what the
  learner typed.** The model nominates at most one citation-form phrase per
  correction (*to depend on*), and every content word of it must lemmatise to a
  word of that correction's `correct_form`. So a misspelling in the learner's
  text can never become a card — #402's defect cannot happen here by
  construction, not by a filter that might be skipped. `/talk` draws from the
  learner's own text, which is exactly why this is stated rather than assumed.
* **Every word must resolve against the reference lexicon** (`lemmatize(word,
  frozenset())`), so an invented or garbled phrase is refused.
* **The correction must CHANGE at least one word of the phrase** — the phrase is
  the teaching, not a restatement of words the learner already had right. The
  comparison is on SURFACE words, not lemmas: *he miss his family* → *he misses
  his family* changed `miss` to `misses`, which a lemma comparison would read as
  no change at all and refuse the design's own drawn example.
* **At most two, paragraph only.**

**THE KNOWN-WORD LEDGER IS NOT CONSULTED, AND THAT IS A RECORDED REFUSAL (D16).**
`user_lexemes` is lemma-level. *depend* and *miss* are known at B1, so a ledger
filter would refuse BOTH of the design's own drawn examples. A filter that cannot
answer the question "does this learner know this phrase" is not applied as if it
could.

**WHAT THIS RULE CANNOT ESTABLISH (#271):** that the phrase is good English, a
well-formed citation form, or worth keeping. It refuses shapes it can recognise.
The operator reads the first run's offers (human check HP1).

Pure: no database, no model.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from core.lexicon.normalize import lemmatize

#: Words that stand in for an argument in a citation form (*to miss someone*).
PLACEHOLDERS: frozenset[str] = frozenset({"someone", "something", "somebody", "somewhere"})

#: A leading infinitive marker (*to depend on*). Only in first position, and only
#: before another word: a `to` elsewhere is a real word and must match.
CITATION_MARKER = "to"

MAX_OFFERS = 2
MAX_PHRASE_WORDS = 6

_PHRASE = re.compile(r"^[a-z]+(?:'[a-z]+)?(?: [a-z]+(?:'[a-z]+)?)*$")
_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")


@dataclass(frozen=True)
class Offer:
    phrase: str
    sentence: str


def normal_phrase(raw: object) -> str | None:
    """Lowercase, single-spaced, letters and apostrophes only, at most six words."""
    if not isinstance(raw, str):
        return None
    phrase = " ".join(raw.replace("’", "'").split()).casefold()
    if not phrase or not _PHRASE.match(phrase) or len(phrase.split()) > MAX_PHRASE_WORDS:
        return None
    return phrase


def _words(text: str) -> list[str]:
    return [w.casefold() for w in _WORD.findall(text or "")]


def matched_words(phrase: str, correct_form: str) -> list[str] | None:
    """The `correct_form` words each content word of the phrase matched, or None.

    None when any word fails to resolve, any content word matches nothing in
    `correct_form`, or the phrase has no content word at all.
    """
    tokens = phrase.split()
    form = _words(correct_form)
    form_lemmas = [(word, lemmatize(word, frozenset())) for word in form]
    matched: list[str] = []
    content = 0
    for i, token in enumerate(tokens):
        lemma = lemmatize(token, frozenset())
        if lemma is None:
            return None
        if token in PLACEHOLDERS:
            continue
        if token == CITATION_MARKER and i == 0 and len(tokens) > 1:
            continue
        hits = [word for word, word_lemma in form_lemmas if word == token or word_lemma == lemma]
        if not hits:
            return None
        content += 1
        matched.extend(hits)
    return matched if content else None


def is_offerable(phrase: str, correct_form: str, you_said: str | None = None) -> bool:
    """Q-E for one phrase against one correction.

    ``you_said`` is None on `POST /write/keep`, which cannot re-check the
    change condition: the learner's original is never stored (CLAUDE.md §5). The
    other conditions are re-applied in full.
    """
    normal = normal_phrase(phrase)
    if normal is None:
        return False
    matched = matched_words(normal, correct_form)
    if matched is None:
        return False
    if you_said is not None:
        original = set(_words(you_said))
        if all(word in original for word in matched):
            return False
    return True


def select(corrections: Iterable[Mapping]) -> tuple[Offer, ...]:
    """At most two offers, in correction order, one per correction, no repeats."""
    offers: list[Offer] = []
    seen: set[str] = set()
    for c in corrections:
        phrase = normal_phrase(c.get("keep"))
        if phrase is None or phrase in seen:
            continue
        if not is_offerable(phrase, str(c.get("correct_form") or ""), str(c.get("you_said") or "")):
            continue
        offers.append(Offer(phrase=phrase, sentence=str(c["correct_form"])))
        seen.add(phrase)
        if len(offers) == MAX_OFFERS:
            break
    return tuple(offers)
