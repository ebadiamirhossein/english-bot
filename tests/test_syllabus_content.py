"""W8: the authored content, and the gates that decide whether it may ship.

The sizing test is the one that matters, and it is written to fail in month six
rather than to pass today. See `test_every_unit_clears_the_floor_for_a_month_six_learner`.
"""

from __future__ import annotations

import json

import pytest

from core.items import ITEM_TYPES
from core.syllabus import (
    CHECKPOINT_ITEM_COUNT,
    STAGES,
    TARGET_LEXEME_FLOOR,
    UNIT_CANDIDATE_TARGET,
    UNIT_COUNT,
    UNITS_PER_STAGE,
    stage_of,
)
from core.syllabus.blueprint import (
    ContentError,
    parse_murphy,
    validate_checkpoint,
    validate_grammar_targets,
)
from core.syllabus.content import unit_lexemes, units


# ── the 24 units ────────────────────────────────────────────────────────────


def test_there_are_twenty_four_units_four_to_a_stage() -> None:
    all_units = units()
    assert len(all_units) == UNIT_COUNT
    for stage in range(1, len(STAGES) + 1):
        assert sum(1 for u in all_units if u.stage == stage) == UNITS_PER_STAGE, stage


def test_every_unit_has_three_to_five_grammar_targets() -> None:
    """PRD §3 says 3-5; the W8 row says >=3. The tighter of the two."""
    for unit in units():
        assert 3 <= len(unit.grammar_targets) <= 5, unit.unit_number


def test_every_unit_has_a_can_do_and_both_output_tasks() -> None:
    for unit in units():
        assert unit.can_do.strip()
        assert unit.output_task_spoken.strip()
        assert unit.output_task_written.strip()


def test_the_stage_of_a_unit_is_arithmetic_not_a_stored_guess() -> None:
    """Hardcoded on the left, computed on the right — never both computed."""
    assert [stage_of(n) for n in (1, 4, 5, 8, 9, 12, 13, 16, 17, 20, 21, 24)] == [
        1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6
    ]


# ── Murphy references: the finding, asserted rather than described ──────────


def test_exactly_twenty_of_twenty_four_units_carry_a_murphy_reference() -> None:
    """Stage 6 has no Murphy range in PRD §3, and the bar is not adjusted for it.

    §3's stage-6 cluster reads "collocation depth, idiom, connected speech,
    self-repair strategies, B2 exam task formats" and names no units. This is
    the number the record reports; it is asserted here so it cannot drift
    silently in either direction — a later slice inventing ranges for units
    21-24 would fail this, and so would one losing them from units 1-20.
    """
    with_reference = [
        u.unit_number
        for u in units()
        if any(t.murphy_units for t in u.grammar_targets)
    ]
    assert len(with_reference) == 20
    assert with_reference == list(range(1, 21))


def test_no_stage_six_target_carries_a_murphy_reference() -> None:
    for unit in units():
        if unit.stage == 6:
            assert all(t.murphy_units is None for t in unit.grammar_targets)


def test_every_murphy_reference_parses_and_is_inside_the_book() -> None:
    """Format and bounds are the whole of what CAN be verified here.

    There is no catalogue table to check against: `book_units` is a per-learner
    OCR study log, not a list of Murphy's units, so nothing in this repository
    knows what unit 43 contains. That limit is real and is stated rather than
    papered over — the human check is to open the book at three cited units.
    """
    for unit in units():
        for target in unit.grammar_targets:
            if target.murphy_units is None:
                continue
            spans = parse_murphy(target.murphy_units)
            assert spans
            for low, high in spans:
                assert 1 <= low <= high <= 145, (unit.unit_number, target.murphy_units)


def test_a_unit_only_cites_murphy_units_from_its_own_stage_ranges() -> None:
    """The split rule: each unit takes a slice of ITS STAGE's ranges.

    PRD §3 gives the ranges per stage, not per unit, and gives no rule for
    dividing them. The rule chosen is "a contiguous slice of the stage's own
    ranges", and this test is what makes it a rule rather than a habit.
    """
    for unit in units():
        allowed: set[int] = set()
        for span in STAGES[unit.stage - 1].murphy_ranges:
            for low, high in parse_murphy(span):
                allowed.update(range(low, high + 1))
        for target in unit.grammar_targets:
            if target.murphy_units is None:
                continue
            for low, high in parse_murphy(target.murphy_units):
                assert set(range(low, high + 1)) <= allowed, (
                    f"unit {unit.unit_number} cites Murphy {target.murphy_units}, "
                    f"outside stage {unit.stage}'s ranges "
                    f"{STAGES[unit.stage - 1].murphy_ranges}"
                )


def test_the_two_prd_stage_range_overlaps_are_real_and_tolerated() -> None:
    """PRD §3 double-assigns three Murphy units, and that is legal here.

    Stage 1 is 5-20 and stage 3 is 19-24, so **19 and 20 are in both**.
    Stage 3 is 29-38 and stage 5 is 38-41, so **38 is in both**.

    References are TEXT with no foreign key and no UNIQUE, so an overlap costs
    nothing. This test exists so that a later slice which "tidies" the ranges
    into a unique mapping has to delete an assertion that says why it must not.
    """
    covered: dict[int, list[int]] = {}
    for stage in STAGES:
        for span in stage.murphy_ranges:
            for low, high in parse_murphy(span):
                for unit in range(low, high + 1):
                    covered.setdefault(unit, []).append(stage.number)
    shared = {u: s for u, s in covered.items() if len(s) > 1}
    assert shared == {19: [1, 3], 20: [1, 3], 38: [3, 5]}


# ── the checkpoint blueprints ──────────────────────────────────────────────


def test_every_checkpoint_is_twelve_items_at_eighty_percent() -> None:
    for unit in units():
        assert unit.checkpoint["item_count"] == CHECKPOINT_ITEM_COUNT
        assert unit.checkpoint["pass_pct"] == 80


def test_every_checkpoints_blocks_sum_to_twelve() -> None:
    """A blueprint that does not add up cannot be generated against."""
    for unit in units():
        total = sum(unit.checkpoint["per_target"].values()) + unit.checkpoint["lexeme_items"]
        assert total == CHECKPOINT_ITEM_COUNT, unit.unit_number


def test_every_checkpoint_tests_every_grammar_target_of_its_unit() -> None:
    """A target nothing checks is not a target."""
    for unit in units():
        assert set(unit.checkpoint["per_target"]) == {
            t.target for t in unit.grammar_targets
        }, unit.unit_number


def test_every_checkpoint_names_only_real_item_types() -> None:
    for unit in units():
        for item_type in unit.checkpoint["item_types"]:
            assert item_type in ITEM_TYPES, (unit.unit_number, item_type)


def test_no_checkpoint_contains_an_item() -> None:
    """W8 authors zero items. Standing rule 4: nothing ships unvalidated.

    An item authored here would carry a NULL `validator_version` and would never
    have seen the blind-solver or uniqueness gates — exactly the population
    W10's version filter exists to exclude.
    """
    banned = {"prompt_text", "answer", "items", "sentence", "options", "tiles"}
    for unit in units():
        assert not banned & set(unit.checkpoint), unit.unit_number


def test_a_blueprint_carrying_an_item_is_refused() -> None:
    """The gate is non-inert: it rejects the thing it exists to reject."""
    targets = validate_grammar_targets(
        [{"target": "a"}, {"target": "b"}, {"target": "c"}], unit_number=1
    )
    good = {
        "item_count": 12,
        "pass_pct": 80,
        "per_target": {"a": 3, "b": 3, "c": 3},
        "lexeme_items": 3,
        "item_types": ["mcq"],
    }
    assert validate_checkpoint(good, unit_number=1, targets=targets)
    with pytest.raises(ContentError, match="never contains one"):
        validate_checkpoint(
            {**good, "prompt_text": "I ___ to the shops."},
            unit_number=1,
            targets=targets,
        )


def test_a_blueprint_that_does_not_sum_to_twelve_is_refused() -> None:
    targets = validate_grammar_targets(
        [{"target": "a"}, {"target": "b"}, {"target": "c"}], unit_number=1
    )
    with pytest.raises(ContentError, match="sum to 11"):
        validate_checkpoint(
            {
                "item_count": 12,
                "pass_pct": 80,
                "per_target": {"a": 3, "b": 3, "c": 3},
                "lexeme_items": 2,
                "item_types": ["mcq"],
            },
            unit_number=1,
            targets=targets,
        )


def test_two_grammar_targets_are_refused() -> None:
    with pytest.raises(ContentError, match="PRD §3 requires 3-5"):
        validate_grammar_targets([{"target": "a"}, {"target": "b"}], unit_number=1)


# ── the candidate sets, and the sizing question ────────────────────────────


def test_every_unit_reaches_the_candidate_target() -> None:
    by_unit = unit_lexemes()
    assert set(by_unit) == set(range(1, UNIT_COUNT + 1))
    for unit, lemmas in by_unit.items():
        assert len(lemmas) >= UNIT_CANDIDATE_TARGET, (unit, len(lemmas))


def test_no_lemma_is_taught_by_two_units() -> None:
    by_unit = unit_lexemes()
    everything = [lemma for lemmas in by_unit.values() for lemma in lemmas]
    assert len(everything) == len(set(everything))


def test_every_unit_clears_the_floor_at_the_end_of_the_programme() -> None:
    """**The acceptance criterion, measured where it can actually fail.**

    The bar is ">=30 target lexemes", and a target lexeme is one that survives
    the learner's own ledger. Measuring that against TODAY'S ledger would prove
    nothing: post-#91 the heaviest learner has 2,003 covered lemmas and exactly
    three of them sit above rank 2000, so the diff currently removes almost
    nothing and even a 40-candidate unit would pass while measuring nothing.

    So the stress is the END of the programme, taken from PRD §2.1's own
    numbers rather than from a round figure: the vocabulary budget is
    **1,500-2,000 new known words** over the 24 weeks, against a candidate pool
    of 3,759 lemmas. That is **40% to 53% erosion**, and the units a learner
    reaches last are the ones that have eroded longest.

    53% is asserted here because it is the worse end of the PRD's own range. It
    is what set UNIT_CANDIDATE_TARGET: at 60 candidates a unit tolerates exactly
    50% and yields 28 at the top of the range, which is a fail; at 65 it
    tolerates 53.8%. **The bar was not moved to fit the content** (CLAUDE.md §3
    rule 7) -- the pool was widened and the candidate count raised until the bar
    held.

    The erosion is deterministic -- every Nth lemma by frequency -- so this is a
    fixed assertion, not a sampled one, and the expected value (30) is hardcoded
    rather than derived from the function under test.
    """
    by_unit = unit_lexemes()
    for unit, lemmas in by_unit.items():
        ordered = sorted(lemmas)
        # WHICH words are known does not matter to a count, only HOW MANY, so
        # this takes a flat 53% rather than trying to spread them. The first
        # version of this test wrote `i % 100 < 53` over a 65-item list, which
        # marks the first 53 of 65 -- 81% erosion, not 53% -- and failed for a
        # reason that had nothing to do with the content.
        known = set(ordered[: round(len(ordered) * 0.53)])
        survivors = len([w for w in ordered if w not in known])
        assert survivors >= TARGET_LEXEME_FLOOR, (
            f"unit {unit} yields {survivors} targets once 53% of its candidates "
            f"are known -- the top of PRD §2.1's own projected range. "
            "The bar is not lowered (CLAUDE.md §3 rule 7): widen the pool and "
            "raise UNIT_CANDIDATE_TARGET."
        )


def test_the_erosion_tolerance_is_stated_and_holds() -> None:
    """How much of its own set a unit may lose before it breaks the floor.

    Written as its own assertion because it is the number that decides
    UNIT_CANDIDATE_TARGET, and a number that only exists inside a comment is a
    number nobody re-checks when the content changes.
    """
    by_unit = unit_lexemes()
    for unit, lemmas in by_unit.items():
        tolerance = (len(lemmas) - TARGET_LEXEME_FLOOR) / len(lemmas)
        assert tolerance >= 0.53, (unit, len(lemmas), tolerance)


def test_no_candidate_sits_inside_the_assumption_floor() -> None:
    """A top-2000 lemma is assumed known for EVERY learner.

    `assume_top_frequency_known` writes `known/assumption` for every lemma at or
    above `freq_rank` 2000, so such a word could never survive the per-learner
    diff. One in a candidate set would be a target that is structurally
    impossible to hit — and it would inflate the shared count while contributing
    nothing to the per-learner one.
    """
    from core.syllabus import CANDIDATE_CEFR, CANDIDATE_MIN_FREQ_RANK
    from core.syllabus.content import LEXEMES_FILE

    for line in LEXEMES_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or line.startswith("lemma\t") or not line.strip():
            continue
        lemma, _unit, rank, _band, cefr = line.split("\t")
        assert int(rank) > CANDIDATE_MIN_FREQ_RANK, lemma
        assert cefr in CANDIDATE_CEFR, (lemma, cefr)


def test_the_committed_json_is_what_the_loader_validates() -> None:
    """The file on disk is the artefact; nothing regenerates it at import time."""
    from core.syllabus.content import UNITS_FILE

    raw = json.loads(UNITS_FILE.read_text(encoding="utf-8"))
    assert len(raw) == UNIT_COUNT
    assert [u["unit_number"] for u in raw] == list(range(1, UNIT_COUNT + 1))
