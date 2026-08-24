"""The ledger's state machine: states, sources, ranks and who may lower what.

This module is the single source of truth. ``core.services.lexicon`` generates
its SQL from these constants rather than repeating them, and a test asserts the
generated SQL still matches — two hand-maintained copies of an ordering is how
a conflict rule quietly stops meaning what its docstring says.
"""

from __future__ import annotations

# ``unknown`` is deliberately absent. It is the *absence of a row*, never a
# stored value, and migration 010's CHECK permits only these four. A row means
# "we have evidence about this lemma"; materialising ignorance would give 15k
# rows per user a fake `first_seen_at` and a fake source, turn every ingestion
# into an UPDATE, and stop "how many lemmas do we have evidence for" being
# COUNT(*). Forgetting lands at `seen` — a word cannot be un-encountered.
STATES: tuple[str, ...] = ("seen", "learning", "known", "mastered")
STATE_RANK: dict[str, int] = {state: i for i, state in enumerate(STATES, start=1)}

# PRD §2.1. `learning` does not count: coverage answers "can the learner follow
# this in real time", and `learning` is exactly the state where they cannot
# retrieve at speed. Counting it would inflate the number and push the learner
# above the comprehensible-input band, which is the drowning direction.
COVERED_STATES = frozenset({"known", "mastered"})

# Rank orders *inferences* — how much a proxy signal is worth. It deliberately
# does not order the two direct measurements against each other; see
# AUTHORITATIVE_SOURCES.
SOURCE_RANK: dict[str, int] = {
    "assumption": 0,      # the top-N frequency floor: a hypothesis, nothing more
    "v2_encountered": 1,  # readings, chunk sentences — exposure only
    "v2_studied": 2,      # chunks actually presented, book word banks
    "tapped": 2,          # a tap is proof of *not* knowing
    "skipped_easy": 3,    # the learner's own judgement on running text
    "v2_produced": 3,     # self-produced, from the v2 error journal
    "correction": 4,      # self-produced, current, timestamped
    "review": 5,          # measured retrieval
    "placement": 6,       # direct measurement, the only diagnostic source
}

# A source is authoritative when it observes the learner directly and therefore
# owns the state it writes. An authoritative write is **not rank-gated at all**.
#
# Both halves of that matter, and both are failures the rank-only rule caused:
#
#   Equal rank. An FSRS lapse is `review` over an earlier `review`. A rule
#   requiring a strictly higher state would discard it, and every lapse from
#   W7 onward would vanish.
#
#   Lower rank, the commoner case. `placement` is 6 and `review` is 5, so once
#   a monthly placement writes a state, every subsequent review of that word
#   would be dropped — promotions as well as lapses. The deck measures
#   retrieval daily and placement measures monthly; a rank gate lets the
#   monthly instrument freeze out the daily one for up to thirty days, and W7's
#   reviewer would appear to work while changing nothing.
#
# Between two direct measurements the newer one wins. Idempotency is kept by
# the IS DISTINCT FROM guard in the upsert, not by rank.
AUTHORITATIVE_SOURCES = frozenset({"review", "placement"})

# Which sources may lower a state, and it is not the same question as rank.
#
# Rank measures **authority** — how much a channel is trusted. Demotion asks
# something else entirely: does this source carry evidence that the learner
# knows the lemma *less well* than the row already records? Only three things do:
#
#   `review`     a measured lapse
#   `placement`  a diagnostic result
#   `tapped`     the learner stopped at the word because they did not know it
#
# Exposure and inference never qualify. A word appearing in a reading the bot
# sent, or in a chunk shown to the learner, is evidence they have **met** it —
# never evidence they have failed to learn it, and for a top-2000 lemma the
# frequency band is by far the stronger prior.
#
# W4 gated demotion on rank alone, and the consequence was perverse: at rank 1,
# `v2_encountered` outranked the rank-0 frequency floor, so a passive exposure
# dragged `known` down to `seen`. **The more a learner had used the app, the
# lower their coverage** — 231 of one learner's 2,000 floor lemmas fell out on
# the first production harvest. Nothing read coverage yet, so a learner would
# have inherited it later as an unexplained number.
#
# This is a superset of AUTHORITATIVE_SOURCES and must not be collapsed into it.
# The two sets answer different questions — "may this write ignore rank?" and
# "may this write lower a state?" — and `tapped` is in one and not the other.
MAY_LOWER = frozenset({"review", "placement", "tapped"})

# Which states each source is entitled to assert. W4 writes only `assumption`
# and the three `v2_*` sources; the rest are declared now so a later slice adds
# a caller rather than a migration.
SOURCE_STATES: dict[str, frozenset[str]] = {
    "assumption": frozenset({"known"}),
    "v2_encountered": frozenset({"seen"}),
    "v2_studied": frozenset({"learning"}),
    "tapped": frozenset({"seen"}),
    "skipped_easy": frozenset({"known"}),
    "v2_produced": frozenset({"known"}),
    "correction": frozenset({"known"}),
    "review": frozenset({"learning", "known", "mastered"}),
    "placement": frozenset({"seen", "learning", "known"}),
}

SOURCES: tuple[str, ...] = tuple(SOURCE_RANK)

# PRD §8.5.1. Five values, on `cards`, `items` and `user_lexemes`.
REGISTERS: tuple[str, ...] = ("formal", "neutral", "informal", "slang", "taboo")

# ── which `errors.source` values may feed the ledger ────────────────────────
#
# W4 established the axis and W5 widened the CHECK, so the classification lives
# here rather than as an inline list in one query. The axis is: DID THE LEARNER
# TYPE IT, OR DID A RECOGNISER GUESS IT? ASR output is not evidence that a
# learner produces a word, and a mishearing promoted to `known` is a permanently
# known word they never said. A wrong row is permanent damage; a missing one is
# recoverable, so the doubtful cases are excluded rather than downgraded.
#
# Migration 012 added six values and every one is classified below, in the same
# slice that added it — not left for whichever later slice first writes one.
# `tests/test_items_sources.py` asserts the CHECK and these two sets agree
# exactly, so a seventh value cannot be added without a decision.
HARVESTED_SOURCES = frozenset(
    {
        "quiz",       # W4: keyboard-authored
        "text",       # W4: keyboard-authored
        "reading",    # W4: keyboard-authored
        "conversation",  # W4: keyboard-authored
        "answer",     # W5: free written answer -- `text`'s class
        "retell",     # W5: written retell of a passage -- `text`'s class
    }
)

NOT_HARVESTED_SOURCES = frozenset(
    {
        "voice",      # W4: ASR
        "diary",      # W4: ASR
        "capture",    # W4: someone else's English, and barred from the journal
        "shadow",     # W5: ASR -- `voice`'s class
        "video",      # W5: the source line is someone else's English
        "item",       # W5: covers typed AND ASR-graded responses under one
                      #     value, so harvesting it would let a `speak_answer`
                      #     mishearing promote a word. `core.items.RESPONSE_MODE`
                      #     is shipped so W6/W7 can split them honestly instead
                      #     of widening this set and hoping.
        "placement",  # W5: PRD §6 requires the instrument not to change.
                      #     Harvesting from it feeds the measurement back into
                      #     the thing being measured.
    }
)


def state_rank(state: str) -> int:
    return STATE_RANK[state]


def source_rank(source: str) -> int:
    return SOURCE_RANK[source]


def is_authoritative(source: str) -> bool:
    return source in AUTHORITATIVE_SOURCES


def validate(source: str, state: str) -> None:
    """Raise before a write that a source is not entitled to make."""
    if source not in SOURCE_RANK:
        raise ValueError(f"unknown ledger source: {source!r}")
    if state not in STATE_RANK:
        raise ValueError(
            f"{state!r} is not a storable state; `unknown` is the absence of a row"
        )
    if state not in SOURCE_STATES[source]:
        allowed = ", ".join(sorted(SOURCE_STATES[source]))
        raise ValueError(f"source {source!r} may not set {state!r} (allowed: {allowed})")
