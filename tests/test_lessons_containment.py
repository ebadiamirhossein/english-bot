"""Containment: C2 accepts a composite claim under-read as one of its parts.

**#237, operator ruling 2026-08-28.** Measured, not argued: the same sentence,
same candidate list, same model, same session, twelve calls -- `'I was cooking
dinner when the phone rang.'` ranked its claimed target first in **5 of 10** and
second in 5 of 10, `confidence: 'low'` on all ten. A single C2 rejection of it
carries no more information than a coin.

**The relation is CONTAINMENT and containment is ASYMMETRIC**, which is exactly
why it works where a sibling allowance did not:

    claimed = composite, ranked first = a part   -> the judge UNDER-READ it.
                                                    The sentence does instantiate
                                                    the composite. ACCEPT.
    claimed = a part, ranked first = composite   -> the GENERATOR erred. The
                                                    example instantiates more
                                                    structure than it claims.
                                                    REJECT.

Same rank, same runner-up, opposite directions along the relation. Every test
below drives one of those two directions with unit 1's REAL targets.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.items import gates as item_gates
from core.lessons import generate as gen
from core.lessons.schema import parse_lesson
from core.syllabus.blueprint import ContentError, validate_grammar_targets
from core.syllabus.content import units

FIXTURES = Path(__file__).parent / "fixtures" / "lessons"

#: Hardcoded: this list IS the specification (rule 5).
COMPOSITE = "past simple and past continuous in the same sentence"
PART_SIMPLE = "past simple: regular and irregular verbs"
PART_CONTINUOUS = "past continuous for what was going on around it"
LINKERS = "time linkers: then, after that, a bit later"


# ── the declaration ─────────────────────────────────────────────────────────


def test_unit_one_declares_the_containment_and_nothing_else_does() -> None:
    """Declared only where it is evidenced. Units 9 and 20 are the operator's."""
    declared = {
        (u.unit_number, t.target): t.contains
        for u in units() for t in u.grammar_targets if t.contains
    }
    assert declared == {(1, COMPOSITE): (PART_SIMPLE, PART_CONTINUOUS)}


def test_no_target_text_changed_and_no_checkpoint_key_moved() -> None:
    """**ADDITIVE ONLY, so #212's rewording risk is not triggered.**

    The target string is the identity everywhere in this system -- the bijection,
    `checkpoint.per_target`, `probe_ranked`'s candidate list. Containment adds a
    field beside it and moves nothing.
    """
    for unit in units():
        names = {t.target for t in unit.grammar_targets}
        assert names == set(unit.checkpoint["per_target"]), (
            f"unit {unit.unit_number}: a target string and a checkpoint key "
            "have drifted apart"
        )


def test_the_declaration_is_withheld_from_learners() -> None:
    """#171's seam covers it by construction: `visible_target` NAMES what travels."""
    from core.sessions.blocks import visible_target

    unit = next(u for u in units() if u.unit_number == 1)
    composite = next(t for t in unit.grammar_targets if t.target == COMPOSITE)
    assert composite.contains
    assert visible_target(composite) == {"target": COMPOSITE}


# ── the declaration is validated ────────────────────────────────────────────


def _targets(*entries):
    return [{"target": t, "murphy_units": None, **extra} for t, extra in entries]


def test_containment_of_a_target_the_unit_does_not_have_is_refused() -> None:
    raw = _targets((COMPOSITE, {"contains": [PART_SIMPLE, "third conditional"]}),
                   (PART_SIMPLE, {}), (PART_CONTINUOUS, {}))
    with pytest.raises(ContentError, match="not targets of this unit"):
        validate_grammar_targets(raw, unit_number=1)


def test_a_target_containing_itself_is_refused() -> None:
    raw = _targets((COMPOSITE, {"contains": [COMPOSITE, PART_SIMPLE]}),
                   (PART_SIMPLE, {}), (PART_CONTINUOUS, {}))
    with pytest.raises(ContentError, match="contains itself"):
        validate_grammar_targets(raw, unit_number=1)


def test_declaring_containment_of_one_target_is_refused() -> None:
    """A co-occurrence names two. One is a different claim nobody has ruled on."""
    raw = _targets((COMPOSITE, {"contains": [PART_SIMPLE]}),
                   (PART_SIMPLE, {}), (PART_CONTINUOUS, {}))
    with pytest.raises(ContentError, match="at least"):
        validate_grammar_targets(raw, unit_number=1)


def test_a_chain_of_composites_is_refused() -> None:
    """Containment is one level deep; a chain makes "properly contains"
    a transitive question nobody has ruled on."""
    raw = _targets(
        (COMPOSITE, {"contains": [PART_SIMPLE, PART_CONTINUOUS]}),
        (PART_SIMPLE, {"contains": [PART_CONTINUOUS, LINKERS]}),
        (PART_CONTINUOUS, {}), (LINKERS, {}),
    )
    with pytest.raises(ContentError, match="one level deep"):
        validate_grammar_targets(raw, unit_number=1)


def test_a_unit_with_no_declaration_parses_exactly_as_before() -> None:
    parsed = validate_grammar_targets(
        _targets((PART_SIMPLE, {}), (PART_CONTINUOUS, {}), (LINKERS, {})),
        unit_number=1,
    )
    assert all(t.contains == () for t in parsed)


# ── C2, both directions, through the real verify_lesson ─────────────────────


def _lesson_claiming(target: str, sentence: str):
    """The specimen with `sentence` added to one section's examples.

    **Diagrams are dropped and the example count is kept at 2-3**, so the lesson
    still passes every deterministic check and C2 is the only thing under test.
    A lesson with zero diagrams is valid by construction ("fewer rather than
    false"), which is what makes this a clean harness rather than a fixture that
    has to be kept in sync with the diagram rules.
    """
    raw = json.loads((FIXTURES / "specimen.json").read_text())
    raw["diagrams"] = []
    for section in raw["sections"]:
        if section["target"] == target:
            section["examples"] = [sentence, section["examples"][0]]
        else:
            section["examples"] = section["examples"][:2]
    return parse_lesson(raw)


def _run_c2(monkeypatch, lesson, *, first_ranked: str, claimed: str):
    """Drive `verify_lesson` with C1 and the naturalness judge passing, so the
    only thing under test is C2's treatment of one ranking."""
    info = gen.unit_plan((1,))[1]

    monkeypatch.setattr(
        gen.lesson_gates, "on_target",
        lambda section, **k: item_gates.TargetVerdict(
            ranking=(section.target,), claimed_rank=1, first=section.target,
            runner_up=None, confidence="high"),
    )
    monkeypatch.setattr(
        gen.item_gates, "judge_naturalness",
        lambda sentences, **k: tuple(
            item_gates.NaturalnessVerdict(True, "") for _ in sentences),
    )
    monkeypatch.setattr(gen.lesson_gates, "contradictions", lambda *a, **k: ())

    def fake_c2(sentence, *, claimed, candidates, settings=None):
        if claimed != _run_c2.claimed:
            return item_gates.TargetVerdict(
                ranking=(claimed,), claimed_rank=1, first=claimed,
                runner_up=None, confidence="high")
        return item_gates.TargetVerdict(
            ranking=(_run_c2.first, claimed), claimed_rank=2,
            first=_run_c2.first, runner_up=claimed, confidence="low")

    _run_c2.claimed = claimed
    _run_c2.first = first_ranked
    monkeypatch.setattr(gen.lesson_gates, "example_demonstrates", fake_c2)
    return gen.verify_lesson(lesson, info, reference=frozenset({"a"}))


def test_a_composite_claim_under_read_as_its_part_is_ACCEPTED(monkeypatch) -> None:
    """**The judge under-read it. The sentence does instantiate the composite.**

    `'I was cooking dinner when the phone rang.'` claimed for the composite and
    ranked as `past continuous` -- measured at 5/10, a coin.
    """
    lesson = _lesson_claiming(COMPOSITE, "I was cooking dinner when the phone rang.")
    out = _run_c2(monkeypatch, lesson,
                  first_ranked=PART_CONTINUOUS, claimed=COMPOSITE)
    assert out.state == "accepted", (
        f"rejected at {out.stage}: {out.details}"
    )
    row = next(r for r in out.example_verdicts if r["target"] == COMPOSITE)
    assert row["accepted_by"] == "containment"
    assert row["claimed_rank"] == 2


def test_a_component_claim_ranked_as_the_composite_is_STILL_REJECTED(
    monkeypatch,
) -> None:
    """**Run 2's genuine generator error, and it must stay rejected.**

    `'My phone was ringing when I left.'` claimed for `past continuous` while
    instantiating the composite -- measured at 9/10 against the claim. The
    generator wrote a two-clause sentence for a one-clause target.
    """
    lesson = _lesson_claiming(PART_CONTINUOUS, "My phone was ringing when I left.")
    out = _run_c2(monkeypatch, lesson,
                  first_ranked=COMPOSITE, claimed=PART_CONTINUOUS)
    assert out.state == "rejected"
    assert out.stage == "structure"
    assert "My phone was ringing when I left." in "; ".join(out.details)
    row = next(r for r in out.example_verdicts
               if r["sentence"] == "My phone was ringing when I left.")
    assert row["ok"] is False
    assert "accepted_by" not in row


def test_an_unrelated_first_ranked_target_is_STILL_REJECTED(monkeypatch) -> None:
    """Containment is not a general allowance. Only a CONTAINED target excuses."""
    lesson = _lesson_claiming(COMPOSITE, "I walked home yesterday.")
    out = _run_c2(monkeypatch, lesson, first_ranked=LINKERS, claimed=COMPOSITE)
    assert out.state == "rejected"
    assert out.stage == "structure"


def test_rank_three_is_STILL_REJECTED_even_for_a_contained_target(
    monkeypatch,
) -> None:
    """The allowance is rank 2 only. At rank 3 the claim is not close."""
    lesson = _lesson_claiming(COMPOSITE, "I was cooking when the phone rang.")
    info = gen.unit_plan((1,))[1]
    monkeypatch.setattr(
        gen.lesson_gates, "on_target",
        lambda section, **k: item_gates.TargetVerdict(
            ranking=(section.target,), claimed_rank=1, first=section.target,
            runner_up=None, confidence="high"))
    monkeypatch.setattr(
        gen.item_gates, "judge_naturalness",
        lambda sentences, **k: tuple(
            item_gates.NaturalnessVerdict(True, "") for _ in sentences))
    monkeypatch.setattr(gen.lesson_gates, "contradictions", lambda *a, **k: ())
    monkeypatch.setattr(
        gen.lesson_gates, "example_demonstrates",
        lambda sentence, *, claimed, candidates, settings=None:
            item_gates.TargetVerdict(
                ranking=(PART_CONTINUOUS, LINKERS, claimed), claimed_rank=3,
                first=PART_CONTINUOUS, runner_up=LINKERS, confidence="low")
            if claimed == COMPOSITE else
            item_gates.TargetVerdict(
                ranking=(claimed,), claimed_rank=1, first=claimed,
                runner_up=None, confidence="high"))
    out = gen.verify_lesson(lesson, info, reference=frozenset({"a"}))
    assert out.state == "rejected"


def test_a_unit_with_no_declaration_gets_no_allowance(monkeypatch) -> None:
    """Unit 9 is a candidate and is NOT declared, so C2 there is unchanged."""
    info = gen.unit_plan((9,))[9]
    assert info["contains"] == {}
