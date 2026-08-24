"""The unit of practice: the eleven item types, and what makes one valid.

This package is the pure half of W5. It turns a generated draft into a verdict
without touching a database — `core.services.items` holds every query, the same
split `core.lexicon` / `core.services.lexicon` uses, and for the same reason:
it is what lets the validator be tested without Postgres and what keeps
`tests/test_core_boundary.py::test_no_sql_outside_services` unexempted
(known issue #59 stays the only exemption).

Two modules here are impure by design and are named so nobody has to guess:
`gates.py` (the model-required gates) and `verify.py` (the human-run
verification). Everything else is a pure function of its arguments.

**PRD names the eleven types and stops.** There is no per-type description
anywhere in `docs/PRD-v3-web.md` — only a bare list at §4 and one paragraph on
`l1_to_l2_production`. So the field shapes in `schema.py` and the failure modes
in `checks.py` are *defined* by this slice rather than transcribed from it. That
is the substance of W5 and the reason a later slice cannot repair a weak type:
a bad item type produces plausible exercises that teach the wrong thing, and
nothing fails.
"""

from __future__ import annotations

from core.lexicon.states import REGISTERS

# PRD-v3-web.md §4, quoted in order. Eleven, and the CHECK in migration 012
# is asserted against this tuple rather than maintained beside it.
ITEM_TYPES: tuple[str, ...] = (
    "mcq",
    "cloze_cued",
    "word_bank_order",
    "error_spot",
    "l1_to_l2_production",
    "dictation",
    "listening_gap",
    "speak_repeat",
    "speak_answer",
    "match_pairs",
    "collocation_pick",
)

# PRD §4.3's repair-before-rejection table, exactly five.
CUE_TYPES: tuple[str, ...] = (
    "first_letter_length",
    "l1_gloss",
    "definition",
    "word_bank",
    "converted_mcq",
)

# `chunks.track` (001) uses these three spellings; a second spelling here would
# be the S24 Meaning/Translation trap again.
TRACKS: tuple[str, ...] = ("work", "life", "curiosity")

# How the learner answers. **PRD does not define this** and W5 must, because
# three later slices branch on it: W6 renders from it, W10 mixes from it, and
# W7's harvest decision reads it.
#
# The harvest question is the one that matters. `errors.source = 'item'` covers
# typed and spoken responses under a single value, so it is NOT harvested (see
# migration 012 §3). This trichotomy is what lets a later slice split the two
# honestly instead of widening the allow-list and hoping.
RESPONSE_MODE: dict[str, str] = {
    "mcq": "tap",
    "error_spot": "tap",
    "word_bank_order": "tap",
    "collocation_pick": "tap",
    "match_pairs": "tap",
    "cloze_cued": "typed",
    "l1_to_l2_production": "typed",
    "dictation": "typed",
    "listening_gap": "typed",
    "speak_repeat": "spoken",
    "speak_answer": "spoken",
}

# Bumped whenever a gate is tightened. `items.validator_version` stores it, and
# that column is the only way a later slice can tell which of the accumulated
# bank was validated under the old rules. Retrofitting it is impossible.
VALIDATOR_VERSION = 1

# The two types PRD leaves without a single canonical answer string:
# `speak_answer` is open production scored against a rubric, `match_pairs`'
# answer is a bijection. Migration 012 encodes the same fact as an equality
# CHECK so a twelfth type cannot dodge the decision.
TYPES_WITHOUT_ANSWER: frozenset[str] = frozenset({"speak_answer", "match_pairs"})

# The types whose gate is an audio round-trip rather than a blind solver.
# `speak_repeat` is in neither set for uniqueness purposes — its answer *is* its
# prompt, so there is no uniqueness question to ask at all.
TYPES_WITH_AUDIO: frozenset[str] = frozenset(
    {"dictation", "listening_gap", "speak_repeat"}
)

__all__ = [
    "CUE_TYPES",
    "ITEM_TYPES",
    "REGISTERS",
    "RESPONSE_MODE",
    "TRACKS",
    "TYPES_WITHOUT_ANSWER",
    "TYPES_WITH_AUDIO",
    "VALIDATOR_VERSION",
]
