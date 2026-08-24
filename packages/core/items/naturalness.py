"""PRD §4.6's naturalness gate: three rules are mechanical, one is not.

Ordering is part of the design. The mechanical rules here run **before** any
model call, so a Life-track item containing "deploy" costs **zero** model calls
to reject — which is exactly TASKS' acceptance criterion, and the cheapest gate
that can reject an item should be the one that rejects it.

Rule 1 ("would a real person say this to a friend?") is a judgement about idiom
and lives in `gates.py`, batched.
"""

from __future__ import annotations

import re

from core.items.grading import fold
from core.lexicon.normalize import CONTRACTIONS, lemmatize, tokenize

# ---------------------------------------------------------------------------
# Rule 2 — no domain jargon unless the item's track is Work
# ---------------------------------------------------------------------------
#
# **PROVENANCE: UNMEASURED.** This list is not derived from data, and the next
# person to edit it must know that.
#
# Known issue #57 asked for the v2 work-vocabulary fraction before W5 wrote its
# prompts. The queries ran against production on 2026-08-24 (`scripts/w5_57.sql`,
# committed at ec3ce8d) and **the corpus could not answer**: the largest source
# was 96 quiz prompts against a floor of 150, and its reading of 7.3% carried a
# 95% interval of 2.1–12.5%, straddling the 10% branch boundary. The gate's
# UNMEASURED branch was taken.
#
# The point estimate across all sources was 9.5%, which is *below* the 10% line,
# and the "measured below 10%" branch would have said: keep PRD's five terms and
# add nothing. That action was **considered and declined**, because the branch
# rules were written before the numbers precisely so a near-miss point estimate
# could not pull the action after the fact. Taking it would have been the
# post-hoc tuning the gate exists to prevent.
#
# **Why this list is nonetheless wider than PRD's five, when the "below 10%"
# branch would have kept it narrow.** The two branches answer different
# questions, and the asymmetry is deliberate:
#
#   * Measured below 10% is *evidence* the sentences are not jargon-heavy.
#     Expanding the list then adds false rejections against a corpus already
#     known to be clean, and buys nothing.
#   * Unmeasured is *absence* of evidence, and there the errors are not
#     symmetrical: a false reject costs one regenerated item overnight, a false
#     accept ships a Slack-sounding sentence to a learner. A modestly wider list
#     is the cheaper error.
#
# Matched on the **lemmatised** token stream, so one entry catches
# deploy/deploys/deployed/deploying — and does *not* fire on `redeploy` inside a
# Work item, which a raw substring list gets wrong in both directions.
JARGON: frozenset[str] = frozenset(
    {
        # PRD §4.6's own five, three of which are single words.
        "deploy",
        "stakeholder",
        # The four unambiguous additions the UNMEASURED branch permits. Each is
        # a word that has no ordinary non-work sense in everyday English.
        "sprint",
        "standup",
        "kpi",
        "deliverable",
    }
)

# Multi-word terms, matched on the folded string rather than the token stream.
# PRD names "Q3", "campaign performance" and "onboarding flow"; "q3" is here
# rather than in JARGON because the tokeniser splits it and a bare `q` would
# fire on anything.
#
# Words that are also perfectly ordinary English — `sync`, `leverage`,
# `bandwidth`, `client`, `meeting`, `budget`, `launch`, `report` — appear ONLY
# as part of a multi-word phrase, never alone. `client` scored 5 hits and
# `meeting` 4 in the #57 census, but "meeting a friend" and "my landlord's
# report" are exactly the everyday English §4.6 is asking for, and banning them
# outright would reject the content the track is meant to contain.
JARGON_PHRASES: tuple[str, ...] = (
    "q3",
    "q4",
    "campaign performance",
    "onboarding flow",
    "action item",
    "circle back",
    "touch base",
    "client call",
    "quarterly report",
)

# ---------------------------------------------------------------------------
# Rule 3 — no textbook English
# ---------------------------------------------------------------------------
# PRD's three, verbatim, plus three sentence-initial discourse markers nobody
# says out loud. "These are grammatically correct and nobody says them."
TEXTBOOK_PHRASES: tuple[str, ...] = (
    "indeed, it is quite interesting",
    "i am very fond of",
    "let us discuss the matter",
)
TEXTBOOK_OPENERS: tuple[str, ...] = ("indeed,", "moreover,", "furthermore,")

# ---------------------------------------------------------------------------
# Rule 4 — contractions by default
# ---------------------------------------------------------------------------
# Built by REVERSING `core.lexicon.normalize.CONTRACTIONS` so there is one
# table, not two. That module expands `don't → (do, not)` for the tokeniser;
# here the same table says which uncontracted pairs *should* have been
# contracted. A second hand-written table is how the two stop agreeing.
#
# Only the negative and pronoun forms are reversed. `gonna`, `kinda`, `dunno`
# and friends expand to pairs (`going to`, `kind of`) that are perfectly normal
# uncontracted — demanding "gonna" would be inventing informality, and §4.6
# marks those as informal rather than default.
_REVERSIBLE = {
    contracted: expansion
    for contracted, expansion in CONTRACTIONS.items()
    if "'" in contracted and contracted not in {"'cause"}
}
CONTRACTION_REPAIRS: dict[tuple[str, ...], str] = {
    expansion: contracted for contracted, expansion in _REVERSIBLE.items()
}

# `I *am* going`, `you DO know` — emphatic uncontracted forms are correct and
# common in speech. Rule 4 must not rewrite them.
_EMPHASIS = re.compile(r"[*_]|\b(?:DO|AM|IS|ARE|WILL|NOT)\b")


def jargon_hits(text: str, *, track: str) -> tuple[str, ...]:
    """Work terms present in a non-Work item. Empty tuple on the Work track.

    Returns the offending terms rather than a boolean so a rejection can name
    what it rejected — a gate that says only "no" cannot be debugged, and the
    generator prompt is what has to change.
    """
    if track == "work":
        return ()
    folded = fold(text)
    hits: list[str] = []
    for phrase in JARGON_PHRASES:
        if phrase in folded:
            hits.append(phrase)
    # Lemmatised, so inflections are caught without a stem list. `lemmatize`
    # returns None for anything it cannot account for, and an unresolvable token
    # is not jargon.
    for token in tokenize(text):
        if token.lower in JARGON:
            hits.append(token.lower)
            continue
        lemma = lemmatize(token.surface)
        if lemma is not None and lemma in JARGON:
            hits.append(lemma)
    # Order-stable dedupe, so the message reads the same every run.
    seen: set[str] = set()
    return tuple(h for h in hits if not (h in seen or seen.add(h)))


def textbook_hits(text: str) -> tuple[str, ...]:
    """Textbook-English phrases present. PRD §4.6 rule 3."""
    folded = fold(text)
    hits = [phrase for phrase in TEXTBOOK_PHRASES if phrase in folded]
    hits += [opener for opener in TEXTBOOK_OPENERS if folded.startswith(opener)]
    return tuple(hits)


def uncontracted(text: str) -> tuple[tuple[str, ...], ...]:
    """Word pairs that should have been contracted. PRD §4.6 rule 4.

    Returns the expansions found, so `contract` can rewrite them and a report
    can name them.
    """
    if _EMPHASIS.search(text):
        return ()
    words = [w.lower() for w in re.findall(r"[A-Za-z']+", text)]
    found: list[tuple[str, ...]] = []
    for expansion in CONTRACTION_REPAIRS:
        span = len(expansion)
        for i in range(len(words) - span + 1):
            if tuple(words[i : i + span]) == expansion:
                found.append(expansion)
                break
    return tuple(found)


def contract(text: str) -> str:
    """Rewrite uncontracted pairs to their contractions, preserving case.

    **This is the one gate that repairs without a model call.** Rule 4's failure
    is mechanical and its fix is mechanical, so rejecting the item and paying to
    regenerate it would be waste.
    """
    if _EMPHASIS.search(text):
        return text
    out = text
    for expansion, contracted in CONTRACTION_REPAIRS.items():
        pattern = re.compile(
            r"\b" + r"\s+".join(re.escape(w) for w in expansion) + r"\b",
            re.IGNORECASE,
        )

        def _replace(match: re.Match[str], contracted=contracted) -> str:
            return (
                contracted.capitalize()
                if match.group(0)[:1].isupper()
                else contracted
            )

        out = pattern.sub(_replace, out)
    return out
