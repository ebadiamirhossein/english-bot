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
