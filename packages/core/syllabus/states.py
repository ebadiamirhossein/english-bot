"""The skill map's state machine: which states exist, and which moves are legal.

This module is the single source of truth. Migration 014's CHECK is compared
against `UNIT_STATES` by `tests/test_migration_014.py`, the same instrument
`test_migration_013` uses for the card types -- two hand-maintained copies of a
state set is how a CHECK quietly stops meaning what its docstring says.
"""

from __future__ import annotations

# `locked` is deliberately absent. It is the ABSENCE OF A `user_unit_state` ROW,
# never a stored value, and migration 014's CHECK permits only these four.
#
# This mirrors `core.lexicon.states.STATES`, where `unknown` is absent for the
# same reason, and the reason is the same one: a row means "this learner has
# REACHED this unit". Materialising the negative would give every learner 23
# rows of "not yet" carrying a fake `entered_at`, turn every advance into an
# UPDATE, and stop "how many units has this learner started" being COUNT(*).
#
# W9 renders a locked unit from `syllabus_units LEFT JOIN user_unit_state`,
# which it has to do anyway to show all 24 with the learner's dot on one of
# them. **What unlocks a unit is undefined in the PRD** and needs no data: unit
# N is available when N = 1 or unit N-1 is `passed`, derivable entirely from
# this table. W9 owns that rule and its copy; W8 authors no unlock predicate.
UNIT_STATES: tuple[str, ...] = ("available", "in_progress", "passed", "mastered")
LOCKED = "locked"

# ── which moves are legal, enumerated rather than derived ───────────────────
#
# **There is deliberately NO "a state may never decrease" rule**, and the reason
# is W4's, written out because it cost this project a production defect.
#
# W4 gated ledger demotion on `source_rank` -- an ORDERING -- and the ordering
# was the wrong question. `v2_encountered` (rank 1) outranked the rank-0
# frequency floor, so a passive exposure dragged `known` down to `seen`, and
# **231 of one learner's 2,000 floor lemmas fell out**. The fix (W4a) was not a
# better ordering; it was to stop deriving the rule from one and to enumerate
# the three sources that may lower a state (`MAY_LOWER`). The lesson generalises:
# a rule stated as an ordering blocks legitimate transitions the ordering did
# not anticipate.
#
# Here the trap is concrete. PRD §3: "**If you fail a checkpoint:** the unit
# stays `in_progress`." A monotonic rule would have to decide whether
# `in_progress -> in_progress` is a decrease, and either answer is wrong for
# some path. And `passed -> in_progress` must NEVER happen -- a failed retake
# after a pass is not a demotion, because §3's failure path applies to a unit
# that was never passed. Enumerating says both things exactly; an ordering says
# neither.
#
# Read as: from this state, these are the states a write may move to. A state is
# always allowed to be re-asserted (a re-entry, an idempotent write), so each
# state includes itself.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    # The unit is open and untouched. Starting it is the only move.
    "available": frozenset({"available", "in_progress"}),
    # PRD §3's failure path lands here and STAYS here: "the unit stays
    # `in_progress`, the missed targets are injected into the next week's review
    # queue, and you retake in 4 days." So `in_progress -> in_progress` is a
    # legal, meaningful write -- it bumps `checkpoint_attempts` and sets
    # `retake_due_on` -- and a monotonic rule would have had to special-case it.
    "in_progress": frozenset({"in_progress", "passed"}),
    # A checkpoint pass. From here the only move is mastery, and only after
    # MASTERY_RETENTION_DAYS. **A later failed checkpoint does not come back
    # here**: PRD §3's "drops are silent, raises are announced" is about what the
    # learner is TOLD, not licence to un-pass a unit they passed. Un-passing
    # would also make `passed_at` meaningless, and W11 needs it to time mastery.
    "passed": frozenset({"passed", "mastered"}),
    # Terminal. Nothing demotes a mastered unit.
    "mastered": frozenset({"mastered"}),
}

# The states in which a unit counts as "done" for the map's progress bars.
# `passed` counts: the learner cleared the checkpoint. Mastery is a stronger
# claim layered on top, not a different kind of completion.
COMPLETED_STATES = frozenset({"passed", "mastered"})

# The states that require a checkpoint score at or above the pass mark. Mirrored
# into migration 014's `user_unit_state_a_pass_needs_the_threshold`.
SCORED_STATES = frozenset({"passed", "mastered"})


def may_move(current: str, incoming: str) -> bool:
    """Is `current -> incoming` a legal transition?

    `current` is None-equivalent when the learner has no row -- see
    `may_enter`, which answers the `locked` case separately because "no row" is
    not a state and must not be spelled as one.
    """
    validate(incoming)
    validate(current)
    return incoming in ALLOWED_TRANSITIONS[current]


#: The legal FIRST states for a learner with no row yet. See `may_enter`.
#:
#: **W11 widened this from `{"available"}` on the operator's ruling of
#: 2026-08-29 (#217, candidate b), and the ruling did NOT touch ruling 2 of
#: 2026-08-27: W11 still writes no `available` row.**
ENTRY_STATES: frozenset[str] = frozenset({"available", "in_progress"})


def may_enter(incoming: str) -> bool:
    """Is `incoming` a legal FIRST state for a learner with no row yet?

    **`available` and `in_progress`.** `passed` and `mastered` are refused, and
    `locked` never reaches here -- `validate` raises for it first.

    THIS DOCSTRING READ, UNTIL 2026-08-29:

        "Only `available` is. A unit cannot be created already in progress: the
        `entered_at` of a row that skipped `available` would be a fact about a
        moment that never happened, and W19's history reads these timestamps."

    **Quoted rather than deleted, because the objection it raises is real and is
    what the restatement of `entered_at` answers.** Operator ruling 2026-08-29
    (#217, candidate b): `entered_at` no longer means *the moment the unit became
    available*; it means **"when this learner first reached this unit"**, which is
    the fact W19's history actually wants and the only one W11 can honestly write.
    Under ruling 2 (2026-08-27) nothing writes `available` at all -- that
    predicate is W9's and W9 does not exist -- so the old rule left PRD SS3's fail
    path with no row to write to. See #217.

    **WHAT THIS STILL REFUSES, stated because a rule that admits everything is
    not a rule:**

    * `passed` -- a first row in `passed` claims a checkpoint pass for a unit no
      row records the learner as ever having reached. **Migration 014 would
      accept it**: `user_unit_state_a_pass_needs_the_threshold` is satisfied by
      any directly-inserted row carrying `passed_at` and a score >= 80, so this
      function is the only thing that stops it -- and it is exactly the write
      `record_checkpoint` would produce if an entry write were ever skipped.
    * `mastered` -- worse in kind: it would claim a 21-day retention interval on
      a row created seconds ago. 014 refuses *that particular* row only because
      `mastered_at >= passed_at + 21 days` cannot hold when both are `NOW()`,
      which is a coincidence of the data rather than a statement about entry.
      This says the thing directly.
    * `locked` -- `validate` raises its own message before this returns.

    So the widening moves exactly ONE value across the line, and the rule still
    divides the four storable states two-and-two.
    """
    validate(incoming)
    return incoming in ENTRY_STATES


def validate(state: str) -> None:
    """Raise for anything migration 014 could not store.

    `locked` gets its own message. It is the one wrong value a caller is likely
    to reach for honestly, because PRD §2.3 lists five states and this module
    stores four, and a bare "unknown state" would send them looking for a typo.
    """
    if state == LOCKED:
        raise ValueError(
            "`locked` is the absence of a user_unit_state row, not a stored "
            "state -- delete the row or never create it (migration 014)"
        )
    if state not in UNIT_STATES:
        raise ValueError(f"unstorable unit state: {state!r}")


__all__ = [
    "ALLOWED_TRANSITIONS",
    "COMPLETED_STATES",
    "ENTRY_STATES",
    "LOCKED",
    "SCORED_STATES",
    "UNIT_STATES",
    "may_enter",
    "may_move",
    "validate",
]
