"""One notion of "same answer", shared by the blind-solver gate and the grader.

If these two ever diverge, an item passes the uniqueness gate and is then
ungradable: the solver's answer counted as a match, the learner's identical
answer does not. Nothing fails, nothing logs, and the learner sees a coin flip —
which is the exact bug W5 exists to end, one level up. So there is one function,
and both callers use it.

**The fold does not import `core.services.reading.normalize_for_match`, and that
is deliberate rather than an oversight.** `core/lexicon/normalize.py` records the
decision in a comment: that module lives in a file full of SQL, `core.lexicon` is
pure, and the two folds are pinned by assertion instead of by an import that
would breach the boundary. `normalize_for_match` has ~25 call sites, so moving it
is a slice of its own. This package folds with `fold_apostrophes().casefold()`
plus whitespace collapse — the same expression
`tests/test_lexicon_coverage.py` already asserts equal to `normalize_for_match` —
and that test gains one assertion covering this fold too. One fold, three
modules, no boundary breach.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from core.lexicon.normalize import fold_apostrophes

_WHITESPACE = re.compile(r"\s+")

# Stripped from the ends of a token before comparison. W6's acceptance says
# typed items never require punctuation or capitalisation to match, so the
# grader must not fail an answer over a trailing full stop the learner typed out
# of habit. Interior punctuation is kept: `don't` and `dont` are different
# spellings of the same word and the fold below already handles the apostrophe.
_EDGE_PUNCTUATION = " \t\n\r.,;:!?\"'()[]{}…-–—"


def fold(text: str | None) -> str:
    """Casefold, normalise apostrophes and quotes, collapse whitespace.

    ``None`` folds to the empty string. Two of the eleven types carry
    ``answer IS NULL`` by schema rule, and `content_hash` needs a defined
    contribution for them rather than a crash.
    """
    if not text:
        return ""
    return _WHITESPACE.sub(" ", fold_apostrophes(text).casefold()).strip()


def fold_answer(text: str | None) -> str:
    """``fold`` plus edge punctuation, for comparing a learner's typed answer."""
    return fold(text).strip(_EDGE_PUNCTUATION).strip()


def normalise_variants(
    answer: str | None, extra: Iterable[str] = ()
) -> tuple[str, ...]:
    """The stored ``accepted_variants``: folded, deduplicated, order preserved.

    The canonical answer is always first when there is one, so a reader of the
    column can see which form the item was authored around. Migration 012 stores
    the result already normalised precisely so grading is `= ANY()` and not a
    loop of folds at grade time.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in (answer, *extra):
        folded = fold_answer(raw)
        if folded and folded not in seen:
            seen.add(folded)
            out.append(folded)
    return tuple(out)


def matches(response: str | None, accepted: Sequence[str]) -> bool:
    """True when a response equals any accepted variant, both folded.

    ``accepted`` is expected to be stored-normalised already; it is folded again
    here so an in-memory draft that has not been through ``normalise_variants``
    grades the same way a stored row does. Folding an already-folded string is
    a no-op, which is what makes that safe.
    """
    candidate = fold_answer(response)
    if not candidate:
        return False
    return any(candidate == fold_answer(variant) for variant in accepted)


def grade_text(response: str | None, item: object) -> bool:
    """Grade a typed or tapped response against an item.

    Duck-typed on ``accepted_variants`` rather than importing ``schema`` — that
    import would be circular, and this function is deliberately the lowest layer
    in the package.
    """
    accepted = getattr(item, "accepted_variants", ()) or ()
    return matches(response, accepted)
