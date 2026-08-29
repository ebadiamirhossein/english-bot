"""Where a checkpoint's twelve items come from, and what stops block 3 eating them.

Two properties in this file are the ones W11's plan reached review three times
without getting right, so each is asserted against the mechanism that was WRONG
as well as the one that shipped:

* **the reserve** -- a recency proxy (`created_at DESC LIMIT 12`) protects the
  wrong rows the moment a second generation run happens, and a unit needs two;
* **the selector's quotas** -- filling the BLUEPRINT's `per_target` makes a
  re-weighted retake cohort unselectable, so the fail path never opens.
"""

from __future__ import annotations

from collections import Counter

import pytest

from core.syllabus import CHECKPOINT_ITEM_COUNT, CHECKPOINT_PASS_PCT
from core.syllabus.checkpoint import (
    CheckpointError,
    pass_mark,
    passed,
    quota_map,
    score_pct,
    slot_plan,
)

UNIT_1 = {
    "past simple: regular and irregular verbs": 4,
    "past continuous for what was going on around it": 3,
    "past simple and past continuous in the same sentence": 3,
    "time linkers: then, after that, a bit later": 2,
}
T1, T2, T3, T4 = list(UNIT_1)


# ── the pass mark ───────────────────────────────────────────────────────────


def test_ten_of_twelve_passes_and_nine_does_not() -> None:
    """PRD §3's 80%, computed from the constants and never hardcoded."""
    assert pass_mark(CHECKPOINT_ITEM_COUNT) == 10
    assert passed(10)
    assert not passed(9)


def test_the_pass_mark_follows_its_constants_rather_than_a_literal() -> None:
    """A 10 written as `10` keeps passing after the threshold moves.

    The same drift `test_migration_014` exists to catch one layer down, where two
    hand-maintained copies of a state set stop agreeing.
    """
    assert pass_mark(12) == -((-12 * CHECKPOINT_PASS_PCT) // 100)
    assert pass_mark(10) == 8


def test_the_stored_score_can_never_turn_a_fail_into_a_pass() -> None:
    """`last_checkpoint_score` is rounded for a SMALLINT; the verdict is not.

    014's `user_unit_state_a_pass_needs_the_threshold` compares that column
    against 80, so a rounding that pushed a failing sitting to 80 would make the
    database disagree with `passed()`. Checked across every possible score
    rather than at the boundary, because the boundary is where rounding is least
    interesting.
    """
    for correct in range(CHECKPOINT_ITEM_COUNT + 1):
        stored = score_pct(correct, CHECKPOINT_ITEM_COUNT)
        assert (stored >= CHECKPOINT_PASS_PCT) == passed(correct), correct


# ── the quota map: ONE producer, two callers ────────────────────────────────


def test_a_first_sitting_is_the_blueprints_own_allocation() -> None:
    assert quota_map(UNIT_1) == UNIT_1
    assert sum(quota_map(UNIT_1).values()) == CHECKPOINT_ITEM_COUNT


def test_a_retake_is_reweighted_toward_the_missed_targets() -> None:
    """The fail path's half of the map, and it is NOT the blueprint's.

    This is the mismatch that would have killed the retake: a selector demanding
    4/3/3/2 cannot be filled by a cohort built to this shape, so the two must
    come from one producer.
    """
    got = quota_map(UNIT_1, [T4])
    assert got[T4] > UNIT_1[T4]
    assert got != UNIT_1
    assert sum(got.values()) == CHECKPOINT_ITEM_COUNT


def test_a_retake_still_covers_every_target_at_least_once() -> None:
    """`blueprint.validate_checkpoint`'s own rule -- *a target nothing checks is
    not a target* -- applied to the sitting rather than to the unit."""
    for missed in ([T1], [T4], [T1, T2], [T1, T2, T3, T4]):
        got = quota_map(UNIT_1, missed)
        assert set(got) == set(UNIT_1), missed
        assert all(count >= 1 for count in got.values()), missed


def test_the_reweighting_is_capped_at_the_blueprints_own_maximum() -> None:
    """**#169's arithmetic, enforced.**

    Uncapped, a learner who missed a single target gets NINE of twelve items on
    one narrow grammar point. #169 says where that leads in as many words:
    *"Four or five items on one narrow grammar point, generated in one pass, is
    where near-duplicates come from."* Nine is worse than the concentration that
    row was filed about.

    The cap is `max(per_target.values())` -- **the blueprint's own number** -- so
    a retake stays inside a concentration this record has already reasoned about
    and accepted, rather than inside one invented here.
    """
    cap = max(UNIT_1.values())
    for missed in ([T1], [T4], [T2, T3]):
        assert max(quota_map(UNIT_1, missed).values()) <= cap, missed


def test_the_map_is_deterministic() -> None:
    """Same inputs, same map -- `slot_plan`'s reason for being offset rather
    than shuffled, one level up. A random plan makes a run unrepeatable."""
    assert quota_map(UNIT_1, [T1, T3]) == quota_map(UNIT_1, [T1, T3])


def test_a_missed_target_that_is_not_this_units_is_refused() -> None:
    with pytest.raises(CheckpointError, match="not targets of this unit"):
        quota_map(UNIT_1, ["something else entirely"])


def test_a_blueprint_that_does_not_add_up_is_refused() -> None:
    """The invariant #167 says lives in the validator and not in SQL.

    Asserted here too, because this producer is the one thing both the generator
    and the selector trust, and a map that does not sum to twelve would make a
    short checkpoint reachable from either side.
    """
    with pytest.raises(CheckpointError, match="do not add up|sum to"):
        quota_map({"a": 4, "b": 4}, [])


# ── the slot plan ───────────────────────────────────────────────────────────


def test_a_checkpoint_is_twelve_items_in_the_sittings_proportions() -> None:
    """**Not eight, and not a rotation.**

    `core.items.generate.slot_plan` spreads block 3's eight items evenly across a
    unit's targets. A checkpoint is ALLOCATED. Generating one with the practice
    plan would ignore `checkpoint.per_target` -- which, until W11, nothing in
    this tree read for anything but validation.
    """
    from collections import Counter

    slots = slot_plan(1, quota_map(UNIT_1), ("cloze_cued", "error_spot"))
    assert len(slots) == CHECKPOINT_ITEM_COUNT
    assert Counter(one.target for one in slots) == Counter(UNIT_1)


def test_the_permitted_type_set_is_a_parameter() -> None:
    """#207's open half can be ruled without a code change.

    Seven types are permitted in all 24 blueprints and narrowing that set is the
    operator's. Passing a narrowed set must change the plan, so the ruling lands
    as data rather than as an edit here.
    """
    narrow = slot_plan(1, quota_map(UNIT_1), ("cloze_cued",))
    assert {one.item_type for one in narrow} == {"cloze_cued"}
    wide = slot_plan(1, quota_map(UNIT_1), ("cloze_cued", "error_spot", "match_pairs"))
    assert len({one.item_type for one in wide}) == 3


def test_a_plan_that_does_not_sum_to_twelve_is_refused() -> None:
    with pytest.raises(CheckpointError, match="sum to"):
        slot_plan(1, {"a": 3}, ("cloze_cued",))


# ── the run-level narrowing (§3.5's mechanism, NOT #207) ────────────────────


def test_a_run_can_narrow_the_permitted_types() -> None:
    """**OPERATOR RULING, 2026-08-29: unit 1's checkpoint run drops
    `l1_to_l2_production`.**

    That type is **0 of 14 accepted on production** and a checkpoint cohort is
    all-or-nothing — two failures return 10 of 12 and the run is spent for
    nothing. Twelve slots on unit 1 included two of it.

    **This is a RUN parameter and not a ruling on #207.** #207 asks whether
    `checkpoint.item_types` narrows in `data/syllabus_units.json` across all 24
    units; that stays open and stays the operator's. Nothing here edits the
    data, re-seeds `syllabus_units`, or touches `SLOT_TYPES`.
    """
    from core.items.generate import unit_plan

    narrow = ("cloze_cued", "word_bank_order", "error_spot", "match_pairs")
    slots = unit_plan((1,), checkpoint=True, types=narrow)[1]["slots"]
    assert len(slots) == CHECKPOINT_ITEM_COUNT
    assert {one.item_type for one in slots} <= set(narrow)
    assert not any(one.item_type == "l1_to_l2_production" for one in slots)


def test_narrowing_does_not_touch_the_syllabus() -> None:
    """The blueprint is unchanged by a run. If this ever fails, a run has been
    allowed to answer #207 by side effect."""
    from core.syllabus.content import units

    unit_1 = next(u for u in units() if u.unit_number == 1)
    assert "l1_to_l2_production" in unit_1.checkpoint["item_types"]
    assert len(unit_1.checkpoint["item_types"]) == 7


def test_a_run_may_narrow_but_never_widen() -> None:
    """A `--types` value the blueprint does not permit would put an item in the
    bank that its own checkpoint could never draw."""
    from core.items.generate import unit_plan

    with pytest.raises(ValueError, match="may only narrow"):
        unit_plan((1,), checkpoint=True, types=("dictation",))


def test_narrowing_to_nothing_usable_is_refused() -> None:
    from core.items.generate import unit_plan

    with pytest.raises(ValueError, match="cannot produce|leaves no usable"):
        unit_plan((1,), checkpoint=True, types=("mcq",))


def test_the_narrowed_ceiling_is_computed_and_its_equality_is_a_coincidence() -> None:
    """**Both plans cost 65, and that is arithmetic rather than the flag failing
    to bite** — recorded because an unchanged number is exactly what a reader
    would take as evidence that nothing happened.

    Dropping two `l1_to_l2_production` slots removes two back-translation calls;
    the twelve slots redistribute and `cloze_cued` gains one, which is the only
    `slot`-family type here and therefore costs `MAX_REPAIRS` (2) more. −2 +2 = 0.

    The assertion is on the TERMS, not on the total: the narrowed plan must cost
    no back-translation at all, which is the thing the ruling was made for.
    """
    from core.items import gates
    from core.items.generate import _expected_checkpoint_calls, unit_plan

    narrow = ("cloze_cued", "word_bank_order", "error_spot", "match_pairs")
    plan = unit_plan((1,), checkpoint=True, types=narrow)
    slots = plan[1]["slots"]
    assert sum(1 for s in slots if s.item_type == "l1_to_l2_production") == 0
    assert _expected_checkpoint_calls(plan) == _expected_checkpoint_calls(
        unit_plan((1,), checkpoint=True)
    ), "if this diverges the arithmetic above has changed, not the flag"
    unprobed = sum(
        1 for s in slots
        if gates.ANSWER_FAMILY.get(s.item_type) not in gates.PROBED_FAMILIES
    )
    assert unprobed == 2, "the two match_pairs, which #192 says are ungated"


# ── the top-up must not relabel the run (#260) ──────────────────────────────


def test_a_topped_up_slot_keeps_the_cohort_of_the_run_that_produced_it() -> None:
    """**RED BEFORE THE FIX. Reproduces production item id 28.**

    `--checkpoint --apply` on unit 1 reported writing 8 and the independent count
    returned **7 checkpoint items**. The eighth, id 28 (`word_bank_order`, *time
    linkers*), carries `payload->>'cohort' = 'focus'` — **an explicit wrong
    value, not an absent one**, so `focus_items` serves a checkpoint item to
    block 3 BY INSTRUCTION rather than by fallback.

    The cause is the re-index inside `_top_up`: it rebuilt each `Slot` by NAMING
    three of its four fields, so `cohort` fell to the dataclass default.
    """
    from core.items.generate import _reindexed_for_verifier, checkpoint_slot_plan

    slots = checkpoint_slot_plan(
        1,
        {
            "past simple: regular and irregular verbs": 4,
            "past continuous for what was going on around it": 3,
            "past simple and past continuous in the same sentence": 3,
            "time linkers: then, after that, a bit later": 2,
        },
        permitted=["cloze_cued", "word_bank_order", "error_spot", "match_pairs"],
    )
    assert {one.cohort for one in slots} == {"checkpoint"}

    # The three that failed, re-indexed for the retry payload -- id 28's path.
    short = (slots[1], slots[4], slots[9])
    reindexed = _reindexed_for_verifier(short)

    assert [one.index for one in reindexed] == [0, 1, 2], "re-indexed for the payload"
    assert [one.cohort for one in reindexed] == ["checkpoint"] * 3, (
        "a top-up item must carry the cohort of the run that produced it"
    )
    assert [one.target for one in reindexed] == [s.target for s in short]
    assert [one.item_type for one in reindexed] == [s.item_type for s in short]


def test_a_slot_cannot_be_built_without_saying_which_run_it_is_for() -> None:
    """**`cohort` has NO DEFAULT, and that is the fix rather than a tidy-up.**

    A default of `"focus"` meant *if you forget to say, assume block 3* — so the
    re-index above produced a plausible wrong answer instead of an error. With no
    default it raises at the point of the mistake, before anything is billed.
    """
    from core.items.generate import Slot

    with pytest.raises(TypeError, match="cohort"):
        Slot(index=0, item_type="cloze_cued", target="x")  # type: ignore[call-arg]


# ── --fill: plan the shortfall, not the sitting ─────────────────────────────


HELD_AFTER_THE_FIRST_RUN = {
    "past simple: regular and irregular verbs": 3,
    "past continuous for what was going on around it": 2,
    "past simple and past continuous in the same sentence": 1,
    "time linkers: then, after that, a bit later": 2,
}
NARROW = ("cloze_cued", "word_bank_order", "error_spot", "match_pairs")


def test_fill_plans_the_shortfall_and_not_the_sitting() -> None:
    """Production's real numbers: 8 held against a 5/4/1/2 demand is FOUR."""
    from core.items.generate import unit_plan

    slots = unit_plan(
        (1,), checkpoint=True, types=NARROW,
        held={1: HELD_AFTER_THE_FIRST_RUN},
    )[1]["slots"]
    counted = Counter(one.target for one in slots)
    assert len(slots) == 4
    assert counted["past simple: regular and irregular verbs"] == 2
    assert counted["past continuous for what was going on around it"] == 2
    assert "past simple and past continuous in the same sentence" not in counted
    assert "time linkers: then, after that, a bit later" not in counted
    assert {one.cohort for one in slots} == {"checkpoint"}


def test_fill_keeps_the_front_of_the_rotation() -> None:
    """Operator ruling, 2026-08-29. Deterministic, and the sitting's own order."""
    from core.items.generate import unit_plan

    full = unit_plan((1,), checkpoint=True, types=NARROW)[1]["slots"]
    fill = unit_plan(
        (1,), checkpoint=True, types=NARROW, held={1: HELD_AFTER_THE_FIRST_RUN},
    )[1]["slots"]
    for target in {one.target for one in fill}:
        kept = [one.item_type for one in fill if one.target == target]
        front = [one.item_type for one in full if one.target == target][: len(kept)]
        assert kept == front, target


def test_a_target_already_over_its_demand_yields_nothing_rather_than_raising() -> None:
    """A re-weighted retake can want fewer of a target than a first sitting bought."""
    from core.items.generate import unit_plan

    over = dict(HELD_AFTER_THE_FIRST_RUN)
    over["past simple: regular and irregular verbs"] = 99
    slots = unit_plan((1,), checkpoint=True, types=NARROW, held={1: over})[1]["slots"]
    assert not any(
        one.target == "past simple: regular and irregular verbs" for one in slots
    )
    assert len(slots) == 2


def test_the_sum_twelve_guard_is_REACHED_on_the_fill_path(monkeypatch) -> None:
    """**The guard must be shown to RUN on a fill run, not merely to still exist.**

    `--fill` keeps `slot_plan`'s *a sitting is twelve* guard by ORDERING: the full
    twelve are planned first, past the guard, and the surplus is dropped after.
    **That is exactly the shape in which a guard quietly stops being exercised** --
    a later refactor that built the shortfall map directly would skip it, four
    slots would still come back, and every assertion above would still pass.

    So this asserts what `slot_plan` was HANDED: a map summing to twelve. Asserting
    `len(slots) == 4` cannot see the difference, which is the whole point.
    """
    from core.syllabus import checkpoint as checkpoint_mod
    from core.items import generate as gen

    seen: list[dict[str, int]] = []
    real = checkpoint_mod.slot_plan

    def spy(unit_number, quotas, permitted):
        seen.append(dict(quotas))
        return real(unit_number, quotas, permitted)

    monkeypatch.setattr(gen, "checkpoint_plan", spy)

    slots = gen.unit_plan(
        (1,), checkpoint=True, types=NARROW, held={1: HELD_AFTER_THE_FIRST_RUN},
    )[1]["slots"]

    assert len(seen) == 1, "the planner ran exactly once"
    assert sum(seen[0].values()) == CHECKPOINT_ITEM_COUNT, (
        "the fill path must plan the FULL sitting and subtract after, so "
        "slot_plan's sum-twelve guard is still evaluated"
    )
    assert len(slots) == 4, "and the shortfall is what comes back"


# ── #261: the fill plan must be able to address its own drafts ─────────────


def test_a_fill_plan_is_reindexed_from_zero() -> None:
    """**ASSERTS INDICES, WHICH IS WHAT THE 2f80563 TESTS DID NOT.**

    `test_fill_plans_the_shortfall_and_not_the_sitting` and
    `test_fill_keeps_the_front_of_the_rotation` both passed while a fill run was
    structurally broken: they asserted the plan's TARGETS and its COUNT and never
    its INDICES. The kept slots carried their positions from the full twelve, so
    `verify_cohort` read `drafts[5]` and `drafts[6]` out of a four-item response
    and reported `missing_draft` — against the model, on whichever targets those
    positions happened to hold.

    **#256's third instance, in code written two commits after #256 was filed.**
    """
    from core.items.generate import unit_plan

    slots = unit_plan(
        (1,), checkpoint=True, types=NARROW, held={1: HELD_AFTER_THE_FIRST_RUN},
    )[1]["slots"]
    assert [one.index for one in slots] == list(range(len(slots))), (
        "a fill plan addresses drafts[0..n-1]; anything else is missing_draft"
    )
    # The property in the form the defect actually took:
    assert all(one.index < len(slots) for one in slots)
    assert {one.cohort for one in slots} == {"checkpoint"}, "replace() carried it"


def test_a_plan_that_cannot_address_its_own_drafts_is_refused_before_billing() -> None:
    """**RED WITHOUT THE GUARD.** The check is at the payload, not at the response.

    By the time `missing_draft` is raised the call has been paid for and the
    failure has been attributed to the model. A plan whose indices outrun the
    number of items it requests is a planner bug and is refused before a call.
    """
    from core.items.generate import Slot, build_payload

    broken = (
        Slot(index=0, item_type="cloze_cued", target="a", cohort="checkpoint"),
        Slot(index=5, item_type="error_spot", target="b", cohort="checkpoint"),
    )
    with pytest.raises(ValueError, match="cannot address its own drafts"):
        build_payload(1, "can-do", broken)


def test_the_full_sitting_and_block_three_still_address_their_drafts() -> None:
    """The guard must not fire on the two plans that were always correct."""
    from core.items.generate import build_payload, unit_plan

    for kwargs in ({"checkpoint": True, "types": NARROW}, {}):
        slots = unit_plan((1,), **kwargs)[1]["slots"]
        build_payload(1, "can-do", slots)  # must not raise
        assert [one.index for one in slots] == list(range(len(slots)))


def test_the_tally_denominator_is_the_plan_and_not_a_constant() -> None:
    """**#262. `served N/M` read `ITEMS_PER_UNIT` — block 3's 8 — in every mode.**

    A four-slot fill printed `served 2/8 ** SHORT BY 6 **`. It went unnoticed
    because the first checkpoint run accepted exactly 8 and printed `served 8/8`:
    **a wrong denominator that matches by accident reads as a right one.**

    Driven through the real reporting path over a synthetic journal, so it
    asserts what a reader would actually see.
    """
    import io
    from contextlib import redirect_stdout

    from core.items.generate import _print_tally, tally_of

    rows = [
        {"unit": 1, "slot": i, "state": "accepted" if i < 2 else "discarded",
         "stage": "generation", "codes": ["missing_draft"]}
        for i in range(4)
    ]
    out = io.StringIO()
    with redirect_stdout(out):
        _print_tally("unit 1", tally_of(rows), target=len(rows))
    printed = out.getvalue()
    assert "served 2/4" in printed, printed
    assert "SHORT BY 2" in printed, printed
    assert "2/8" not in printed and "SHORT BY 6" not in printed
