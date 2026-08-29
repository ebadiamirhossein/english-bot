"""The checkpoint's shape: which twelve items a sitting is made of.

Pure. No SQL, no HTTP, no model call -- `core/services/syllabus.py` and
`core/services/items.py` hold every query, which is what keeps
`tests/test_core_boundary.py::test_no_sql_outside_services` unexempted.

**THE ONE THING THIS MODULE EXISTS FOR: `quota_map` has a single producer and
two callers.** `core.items.generate` calls it to decide what to GENERATE, and
`core.services.items.checkpoint_items` calls it to decide what to SELECT. Two
expressions of one rule is how a retake becomes unopenable:

    W11's plan, revision 1 through 3, said the selector fills the blueprint's
    `per_target` -- 4/3/3/2 for unit 1 -- while the fail path re-weights a
    RETAKE toward the missed targets. Both cannot hold. A retake cohort in
    6/3/2/1 cannot fill a 4/3/3/2 demand, so the selector refuses and **the
    retake never opens** -- and the retake is half of what W11 promises.

So the map is computed here, once, and both sides ask for it. This is the same
move `core.items.generate` makes by importing `visible_targets` from the session
blocks rather than writing a second three-line strip: reused, not copied.

**THE TWELVE AND THE 80% DO NOT MOVE ON EITHER PATH** (CLAUDE.md SS3 rule 7).
What differs between a first sitting and a retake is *which targets the twelve
are spread across*, never how many there are or what passes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.syllabus import CHECKPOINT_ITEM_COUNT, CHECKPOINT_PASS_PCT


class CheckpointError(ValueError):
    """A checkpoint shape that must not reach a learner."""


@dataclass(frozen=True, slots=True)
class CheckpointSlot:
    """One of the twelve: which type, testing which target."""

    index: int
    item_type: str
    target: str


def pass_mark(item_count: int = CHECKPOINT_ITEM_COUNT) -> int:
    """How many correct answers pass. **10 of 12, and it is a ceiling.**

    `ceil(12 * 80 / 100)` = 10. Written as integer arithmetic rather than as the
    literal 10 so that the two constants stay the authority -- a hardcoded 10
    would keep passing if `CHECKPOINT_PASS_PCT` ever moved, which is exactly the
    drift `test_migration_014` exists to catch one layer down.

    **Ceiling and not rounding.** At 12 items 80% is 9.6; rounding gives 10 and
    so does the ceiling, but at an item count where they differ, the ceiling is
    the one that means "at or above the threshold" rather than "near it".
    """
    if item_count < 1:
        raise CheckpointError(f"an item count of {item_count} cannot be scored")
    return -((-item_count * CHECKPOINT_PASS_PCT) // 100)


def passed(correct: int, item_count: int = CHECKPOINT_ITEM_COUNT) -> bool:
    if correct < 0 or correct > item_count:
        raise CheckpointError(
            f"{correct} correct out of {item_count} is not a possible score"
        )
    return correct >= pass_mark(item_count)


def score_pct(correct: int, item_count: int = CHECKPOINT_ITEM_COUNT) -> int:
    """The percentage stored in `user_unit_state.last_checkpoint_score`.

    Rounded to an integer because the column is a SMALLINT, and 014's
    `user_unit_state_a_pass_needs_the_threshold` compares it against 80 -- so
    the rounding must never turn a fail into a pass. `passed()` is computed from
    the COUNT and never from this number, and a test pins the two together.
    """
    if item_count < 1:
        raise CheckpointError(f"an item count of {item_count} cannot be scored")
    return round(correct * 100 / item_count)


def quota_map(
    per_target: dict[str, int],
    missed: Sequence[str] = (),
    item_count: int = CHECKPOINT_ITEM_COUNT,
) -> dict[str, int]:
    """How many items each target gets in THIS sitting. The single producer.

    ``missed`` empty -> the blueprint's own `per_target`, unchanged. That is a
    first sitting, and the blueprint is the authority for it.

    ``missed`` non-empty -> a RETAKE, re-weighted toward the targets the learner
    got wrong, **while still covering every target at least once**. A target
    nothing checks is not a target -- `core.syllabus.blueprint`'s own rule
    (`validate_checkpoint` refuses a blueprint that ignores a target), applied
    one level out to the sitting rather than to the unit.

    **The re-weighting is deterministic, capped, and described rather than
    tuned.** Every target keeps a floor of one. The remaining items are dealt
    round-robin to the MISSED targets in the blueprint's key order, then -- once
    those reach the cap -- to the rest, so the same inputs always produce the
    same map and a run is reproducible. That is `slot_plan`'s reason for being
    offset rather than shuffled, one level up.

    **THE CAP IS `max(per_target.values())`, AND IT IS THE BLUEPRINT'S OWN
    NUMBER RATHER THAN A NEW ONE.** Without it a learner who missed a single
    target gets **nine of twelve items on one narrow grammar point**, and #169
    says in as many words where that leads: *"Four or five items on one narrow
    grammar point, generated in one pass, is where near-duplicates come from."*
    Nine is worse than the concentration that row was filed about. Capping at the
    blueprint's own maximum keeps a retake inside a concentration this record has
    already reasoned about and accepted -- 4 for unit 1, 5 for the worst of the
    units #169 names -- instead of inventing a bar.

    Unit 1, blueprint 4/3/3/2, cap 4:

        missed = []            -> 4/3/3/2   (the blueprint, untouched)
        missed = [t1, t2]      -> 4/4/2/2
        missed = [t4]          -> 3/3/2/4

    **The map always sums to `item_count`, and it is asserted rather than left to
    the caller** -- the whole point of one producer is that neither caller can be
    handed a map the other would reject. It is always fillable: `sum == 12` means
    `max >= ceil(12 / n)`, so `n * cap >= 12` for every blueprint that validates.
    """
    if not per_target:
        raise CheckpointError("a checkpoint needs at least one target")
    targets = list(per_target)
    if len(targets) > item_count:
        raise CheckpointError(
            f"{len(targets)} targets cannot each take an item out of {item_count}"
        )

    total = sum(per_target.values())
    if total != item_count:
        raise CheckpointError(
            f"the blueprint's blocks sum to {total}, not {item_count} -- "
            "a blueprint that does not add up cannot be generated against"
        )

    unknown = sorted(set(missed) - set(targets))
    if unknown:
        raise CheckpointError(
            f"missed target(s) {unknown} are not targets of this unit"
        )
    wanted = [t for t in targets if t in set(missed)]
    if not wanted:
        # A first sitting. The blueprint is the authority and is returned
        # unchanged -- not rebuilt from the floor, which would silently
        # re-derive a map the blueprint already states.
        return dict(per_target)

    cap = max(per_target.values())
    out = {t: 1 for t in targets}
    remaining = item_count - len(targets)

    # Missed targets first, then everything, both in the blueprint's key order.
    for pool in (wanted, targets):
        index = 0
        while remaining > 0 and any(out[t] < cap for t in pool):
            target = pool[index % len(pool)]
            index += 1
            if out[target] >= cap:
                continue
            out[target] += 1
            remaining -= 1

    if remaining or sum(out.values()) != item_count:
        # Unreachable for any blueprint `validate_checkpoint` accepts -- see the
        # arithmetic in the docstring. Raised rather than asserted because a
        # silently short map would reach a learner as a short checkpoint.
        raise CheckpointError(
            f"could not deal {item_count} items across {len(targets)} target(s) "
            f"at a cap of {cap}"
        )
    return out


def slot_plan(
    unit_number: int,
    quotas: dict[str, int],
    permitted: Sequence[str],
) -> tuple[CheckpointSlot, ...]:
    """The twelve slots for one sitting: target from `quotas`, type rotated.

    **The TARGET is the quota's, not a rotation's**, which is the difference
    between this and `core.items.generate.slot_plan`: block 3's eight items
    spread evenly across a unit's targets, and a checkpoint's twelve are
    allocated by the blueprint (or by the retake's re-weighting).

    The TYPE rotates across `permitted`, offset by the unit number for
    `slot_plan`'s own reason -- pairing type `i` with slot `i` would land the
    first permitted type on the first target in every unit.

    `permitted` is a PARAMETER and not a constant, so #207's open half -- whether
    the checkpoint blueprint's seven types narrow -- can be ruled without a code
    change. See the plan SS3.5 for what changes under each possible answer.
    """
    if not permitted:
        raise CheckpointError(f"unit {unit_number} permits no item types")
    total = sum(quotas.values())
    if total != CHECKPOINT_ITEM_COUNT:
        raise CheckpointError(
            f"unit {unit_number}: quotas sum to {total}, not {CHECKPOINT_ITEM_COUNT}"
        )

    slots: list[CheckpointSlot] = []
    index = 0
    for target in quotas:
        for _ in range(quotas[target]):
            slots.append(
                CheckpointSlot(
                    index=index,
                    item_type=permitted[(index + unit_number) % len(permitted)],
                    target=target,
                )
            )
            index += 1
    return tuple(slots)


__all__ = [
    "CheckpointError",
    "CheckpointSlot",
    "pass_mark",
    "passed",
    "quota_map",
    "score_pct",
    "slot_plan",
]
