"""Prompt clauses that more than one feature must state identically.

**Known issue #45.** S26c fixed explanation language-mixing and Latin
transliteration for the conversation close-out by writing the rule inline in
`apps/bot/handlers/conversation.py`. The other four paths that ask the model for
an explanation — correction, diary, voice, capture — each carried their own
copy of the surrounding fallback rule *without* that fix, so a learner could get
a Farsi explanation written in Latin letters from `/diary` and a correct one
from `/talk`, on the same day, about the same kind of mistake.

This module is the one place that wording lives now. It is deliberately **only
the single-language / no-transliteration sentences** — not the whole
explanation-language rule. The five features do genuinely different things
(corrections quote a wrong fragment; capture glosses an opaque phrase in 25
words), and their surrounding wording differs for real reasons. Replacing all of
it with one constant would be rewriting four prompts to fix one bug.

The W0 decisions log names three predicates that drifted once they were copied.
A prompt clause drifts the same way and is worse to detect, because a prompt
does not throw — it just quietly answers differently.
"""

from __future__ import annotations

# Appended when the learner has asked for explanations in their own language.
# `{native_language}` is filled by the caller.
#
# The three sentences do three separate jobs, and all three came from real
# output: the model mixing two languages inside one explanation; writing Farsi
# in Latin letters ("zaman" for زمان), which is unreadable to someone who reads
# the script; and — the reason for the third sentence — over-correcting to the
# point of translating "present perfect continuous" into a coined phrase nobody
# uses, which S26c found while fixing the first two.
SINGLE_LANGUAGE_RULE = (
    "Each explanation must be ONE language only — never mix. "
    "If using {native_language}, write the whole sentence in that language's "
    "own script (never Latin transliteration like \"zaman\"). "
    "Standard English grammar terms (e.g. present perfect continuous) may "
    "stay in English inside an otherwise fully {native_language} sentence."
)

# Appended when explanations stay in English. Shorter because there is no
# script to get wrong — the only failure left is drifting into the learner's
# language unasked.
ENGLISH_ONLY_RULE = "Never mix in another language or transliterate."


def single_language_clause(
    *, fallback_enabled: bool, native_language: str | None = None
) -> str:
    """The clause for this learner's explanation-language setting.

    Callers append it to their own fallback wording rather than replacing it,
    which is what keeps five differently-shaped prompts correct without making
    them identical.
    """
    if not fallback_enabled:
        return ENGLISH_ONLY_RULE
    return SINGLE_LANGUAGE_RULE.format(native_language=native_language or "")


def with_single_language_rule(
    rule: str, *, fallback_enabled: bool, native_language: str | None = None
) -> str:
    """Append the clause to an already-formatted explanation-language rule."""
    clause = single_language_clause(
        fallback_enabled=fallback_enabled, native_language=native_language
    )
    return f"{rule.rstrip()} {clause}"
