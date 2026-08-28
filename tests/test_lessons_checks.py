"""Every deterministic check, driven in BOTH directions.

Each test names the user action it exercises (rule 4) and hardcodes its expected
value rather than computing it from the function under test (rule 5). The
fixtures are unit 1's REAL four targets, so these are tests about the content
that actually ships rather than about invented material.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.lessons.checks import (
    bijection_failures,
    deterministic_failures,
    diagram_failures,
    section_failures,
    track_for,
)
from core.lessons.schema import Lesson, parse_lesson
from core.syllabus.content import units

FIXTURES = Path(__file__).parent / "fixtures" / "lessons"

UNIT_1_TARGETS = [
    "past simple: regular and irregular verbs",
    "past continuous for what was going on around it",
    "past simple and past continuous in the same sentence",
    "time linkers: then, after that, a bit later",
]


def _specimen() -> Lesson:
    return parse_lesson(json.loads((FIXTURES / "specimen.json").read_text()))


def _as_dict() -> dict:
    return json.loads((FIXTURES / "specimen.json").read_text())


def test_the_hardcoded_targets_are_the_real_ones() -> None:
    """Rule 5: the list above is the specification, so it is checked once.

    If the syllabus is reworded, this fails here rather than every test below
    failing for a reason nobody can read. #212 makes that a live possibility --
    rewording a target is an open operator question.
    """
    real = [t.target for u in units() if u.unit_number == 1 for t in u.grammar_targets]
    assert real == UNIT_1_TARGETS


# ── the bijection, BOTH directions ──────────────────────────────────────────


def test_a_complete_lesson_satisfies_the_bijection() -> None:
    assert bijection_failures(_specimen(), UNIT_1_TARGETS) == ()


def test_a_three_section_lesson_for_a_four_target_unit_is_refused() -> None:
    """**The case the SQL CHECK cannot see, and the one that actually hurts.**

    Three sections satisfies `grammar_lessons_sections_three_to_five` AND
    `syllabus_units_three_to_five_grammar_targets` while the counts disagree. It
    would pass C1 on each of its three, pass C2, pass C3, and have no orphan
    section -- leaving one target untaught that carries 2 of unit 1's 12
    checkpoint items.
    """
    raw = _as_dict()
    raw["sections"] = raw["sections"][:3]
    raw["diagrams"] = [
        d for d in raw["diagrams"] if d["target"] != UNIT_1_TARGETS[3]
    ]
    codes = {f.code for f in bijection_failures(parse_lesson(raw), UNIT_1_TARGETS)}
    assert "target_missing" in codes


def test_a_section_naming_a_target_the_unit_does_not_have_is_refused() -> None:
    raw = _as_dict()
    raw["sections"][0]["target"] = "third conditional"
    raw["diagrams"] = [
        d for d in raw["diagrams"] if d["target"] != UNIT_1_TARGETS[0]
    ]
    codes = {f.code for f in bijection_failures(parse_lesson(raw), UNIT_1_TARGETS)}
    assert "target_not_in_unit" in codes
    assert "target_missing" in codes


def test_two_sections_on_one_target_are_refused() -> None:
    raw = _as_dict()
    raw["sections"][1]["target"] = UNIT_1_TARGETS[0]
    raw["diagrams"] = [
        d for d in raw["diagrams"] if d["target"] != UNIT_1_TARGETS[1]
    ]
    codes = {f.code for f in bijection_failures(parse_lesson(raw), UNIT_1_TARGETS)}
    assert "target_duplicated" in codes


def test_the_comparison_is_byte_exact() -> None:
    """A trailing space is a different target, and it must fail.

    `blueprint.validate_checkpoint` compares `checkpoint.per_target` keys against
    target text with no normalisation at all. Normalising here and not there is
    how the two would drift, and the same string is the key on both sides.
    """
    raw = _as_dict()
    raw["sections"][0]["target"] = UNIT_1_TARGETS[0] + " "
    raw["diagrams"] = [
        d for d in raw["diagrams"] if d["target"] != UNIT_1_TARGETS[0]
    ]
    codes = {f.code for f in bijection_failures(parse_lesson(raw), UNIT_1_TARGETS)}
    assert "target_not_in_unit" in codes


# ── the diagrams, BOTH directions ───────────────────────────────────────────


def test_the_specimen_diagrams_pass() -> None:
    assert diagram_failures(_specimen(), UNIT_1_TARGETS) == ()


def test_a_lesson_with_no_diagrams_at_all_is_accepted() -> None:
    """**Fewer rather than false, as a test.**

    Zero is a legitimate outcome -- a unit whose targets suit none of the five
    kinds should produce no diagram and a reported count. An earlier draft of
    this slice made zero unstorable, which is #213's shape, so the permission is
    pinned here as well as in the migration.
    """
    raw = _as_dict()
    raw["diagrams"] = []
    assert diagram_failures(parse_lesson(raw), UNIT_1_TARGETS) == ()


def test_one_diagram_per_target_is_accepted_and_two_are_not() -> None:
    """The ceiling's own rule, which the 0-5 CHECK deliberately cannot see."""
    raw = _as_dict()
    assert len(raw["diagrams"]) == 4  # one per target: the natural output
    raw["diagrams"].append(dict(raw["diagrams"][0]))
    codes = {f.code for f in diagram_failures(parse_lesson(raw), UNIT_1_TARGETS)}
    assert "diagram_target_twice" in codes


def test_a_diagram_naming_a_target_the_unit_does_not_have_is_refused() -> None:
    raw = _as_dict()
    raw["diagrams"][0]["target"] = "third conditional"
    codes = {f.code for f in diagram_failures(parse_lesson(raw), UNIT_1_TARGETS)}
    assert "diagram_target_not_in_unit" in codes


def test_a_timeline_needs_exactly_one_now() -> None:
    raw = _as_dict()
    timeline = next(d for d in raw["diagrams"] if d["kind"] == "timeline")
    for point in timeline["points"]:
        point["now"] = True
    codes = {f.code for f in diagram_failures(parse_lesson(raw), UNIT_1_TARGETS)}
    assert "timeline_now" in codes


def test_a_timeline_with_two_points_at_one_position_is_refused() -> None:
    raw = _as_dict()
    timeline = next(d for d in raw["diagrams"] if d["kind"] == "timeline")
    for point in timeline["points"]:
        point["at"] = 1
    codes = {f.code for f in diagram_failures(parse_lesson(raw), UNIT_1_TARGETS)}
    assert "timeline_not_ordered" in codes


def test_a_diagram_inventing_content_is_refused() -> None:
    """A diagram naming a form the lesson never mentions is inventing content."""
    raw = _as_dict()
    timeline = next(d for d in raw["diagrams"] if d["kind"] == "timeline")
    timeline["points"][0]["label"] = "the pluperfect subjunctive vanished"
    codes = {f.code for f in diagram_failures(parse_lesson(raw), UNIT_1_TARGETS)}
    assert "diagram_label_not_in_prose" in codes


def test_a_form_build_slot_need_not_appear_in_the_prose() -> None:
    """**The check that made two diagram kinds impossible to pass.**

    Slot names are grammatical metalanguage -- `subject`, `past participle`.
    Prose teaching the past simple has no reason to contain the word *subject*,
    and demanding it would force the lesson to recite the diagram. Found by
    running the specimen through the checks, which is what that pre-check is for.
    """
    raw = _as_dict()
    form = next(d for d in raw["diagrams"] if d["kind"] == "form_build")
    form["slots"] = ["subject", "auxiliary", "past participle"]
    codes = {f.code for f in diagram_failures(parse_lesson(raw), UNIT_1_TARGETS)}
    assert "diagram_label_not_in_prose" not in codes


def test_a_callout_must_annotate_a_part_the_sentence_contains() -> None:
    raw = _as_dict()
    annotated = next(d for d in raw["diagrams"] if d["kind"] == "annotated_example")
    annotated["callouts"][0]["part"] = "a phrase that is not in the sentence"
    codes = {f.code for f in diagram_failures(parse_lesson(raw), UNIT_1_TARGETS)}
    assert "callout_not_in_sentence" in codes


# ── the prose ───────────────────────────────────────────────────────────────


def test_the_specimen_sections_pass() -> None:
    for section in _specimen().sections:
        assert section_failures(section, track="life") == ()


def test_an_over_long_explanation_is_refused() -> None:
    raw = _as_dict()
    raw["sections"][0]["explanation"] = " ".join(["word"] * 120)
    codes = {f.code for f in section_failures(parse_lesson(raw).sections[0], track="life")}
    assert "explanation_length" in codes


def test_an_over_long_example_is_refused() -> None:
    raw = _as_dict()
    raw["sections"][0]["examples"][0] = " ".join(["word"] * 20)
    codes = {f.code for f in section_failures(parse_lesson(raw).sections[0], track="life")}
    assert "example_too_long" in codes


def test_a_mistake_identical_to_its_correction_is_refused() -> None:
    raw = _as_dict()
    raw["sections"][0]["mistake"]["corrected"] = raw["sections"][0]["mistake"]["said"]
    codes = {f.code for f in section_failures(parse_lesson(raw).sections[0], track="life")}
    assert "mistake_identical" in codes


def test_work_jargon_is_refused_on_a_life_unit_and_allowed_on_a_work_one() -> None:
    """Unit 20 is the Work track; units 1 and 9 are Life. Both directions."""
    raw = _as_dict()
    raw["sections"][0]["examples"][0] = "We had a sprint and it went badly."
    section = parse_lesson(raw).sections[0]
    assert "example_jargon" in {f.code for f in section_failures(section, track="life")}
    assert "example_jargon" not in {
        f.code for f in section_failures(section, track="work")
    }


def test_the_track_mapping_is_the_one_core_items_already_holds() -> None:
    """Imported, not re-declared. A second copy of a mapping is #130's shape."""
    assert track_for(20) == "work"
    assert track_for(1) == "life"
    assert track_for(9) == "life"


# ── no-guilt: the narrow rule, and why the wide one would be wrong ──────────


def test_a_sentence_judging_the_learner_is_refused() -> None:
    raw = _as_dict()
    raw["sections"][0]["explanation"] = (
        "You always get this wrong and you should try harder. " * 3
        + "Regular verbs take -ed and irregular verbs change shape instead."
    )
    codes = {f.code for f in section_failures(parse_lesson(raw).sections[0], track="life")}
    assert "no_guilt" in codes


def test_the_word_wrong_in_a_wrong_example_is_NOT_refused() -> None:
    """**The reason lesson prose uses `content_offenders`, not `offenders`.**

    #110 closed by splitting the banned-phrase pattern in two: the wide rule bans
    `wrong / incorrect / missed / failed / broke`, which is right for a string
    the app says ABOUT a learner and wrong for a field whose whole job is to show
    a mistake. Applying the wide rule here would reject the content the lesson
    exists to carry.
    """
    raw = _as_dict()
    raw["sections"][0]["mistake"]["why"] = (
        "This is wrong because buy is irregular and never takes -ed."
    )
    codes = {f.code for f in section_failures(parse_lesson(raw).sections[0], track="life")}
    assert "no_guilt" not in codes


def test_everything_together_on_the_real_unit_one() -> None:
    assert deterministic_failures(_specimen(), UNIT_1_TARGETS) == ()
