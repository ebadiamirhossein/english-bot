"""The pydantic shapes, and the absences that make "no red" structural."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.lessons import DIAGRAM_KINDS
from core.lessons.schema import (
    MODEL_FOR_KIND,
    Lesson,
    Section,
    contract_block,
    diagram_claims,
    diagram_labels,
    diagram_text,
    parse_lesson,
)

FIXTURES = Path(__file__).parent / "fixtures" / "lessons"

#: Hardcoded, not derived: this list IS the specification (rule 5).
FORBIDDEN_FIELDS = {
    "colour", "color", "font", "font_size", "fill", "stroke", "style",
    "css", "class_name", "x", "y", "width", "height", "top", "left",
}


def _specimen() -> Lesson:
    return parse_lesson(json.loads((FIXTURES / "specimen.json").read_text()))


def _all_field_names() -> set[str]:
    names = set(Section.model_fields)
    for model in MODEL_FOR_KIND.values():
        names |= set(model.model_fields)
        for field in model.model_fields.values():
            inner = getattr(field.annotation, "__args__", ())
            for arg in inner:
                names |= set(getattr(arg, "model_fields", {}))
    names |= set(Lesson.model_fields)
    return names


def test_the_diagram_schema_has_no_colour_font_or_coordinate_field() -> None:
    """**This is what makes "no red in the lesson UI" STRUCTURAL.**

    The renderer owns every visual decision, so the model has no field to express
    one in. A rule that lives only in a prompt is a rule the model can decline.
    """
    offenders = sorted(_all_field_names() & FORBIDDEN_FIELDS)
    assert offenders == [], (
        "the model can choose a visual property, so 'no red' is a promise "
        f"rather than a structure: {offenders}"
    )


def test_timeline_at_is_an_ordering_and_not_a_coordinate() -> None:
    """`at` is the one field that could be mistaken for a coordinate."""
    from core.lessons.schema import TimelinePoint

    assert set(TimelinePoint.model_fields) == {"label", "at", "now"}


def test_the_kinds_constant_and_the_models_cannot_drift() -> None:
    assert set(MODEL_FOR_KIND) == set(DIAGRAM_KINDS)


def test_an_unknown_diagram_kind_is_refused() -> None:
    raw = json.loads((FIXTURES / "specimen.json").read_text())
    raw["diagrams"][0]["kind"] = "pie_chart"
    with pytest.raises(Exception):
        parse_lesson(raw)


def test_an_extra_field_is_refused() -> None:
    """`extra="forbid"`: a field nobody validates is a field nobody renders."""
    raw = json.loads((FIXTURES / "specimen.json").read_text())
    raw["sections"][0]["colour"] = "red"
    with pytest.raises(Exception):
        parse_lesson(raw)


def test_a_lesson_may_carry_no_diagrams(_=None) -> None:
    raw = json.loads((FIXTURES / "specimen.json").read_text())
    raw["diagrams"] = []
    assert parse_lesson(raw).diagrams == ()


def test_every_kind_renders_to_text_and_names_its_claims() -> None:
    """`diagram_text` feeds C1 and C3; `diagram_claims` feeds the prose check."""
    for spec in _specimen().diagrams:
        text = diagram_text(spec)
        assert text and isinstance(text, str)
        assert diagram_claims(spec)
        # Claims are a SUBSET of labels: the wide set adds slot names and notes.
        assert set(diagram_claims(spec)) <= set(diagram_labels(spec))


def test_form_build_slots_are_labels_but_not_claims() -> None:
    """The distinction that stopped two kinds being impossible to pass."""
    form = next(d for d in _specimen().diagrams if d.kind == "form_build")
    assert set(form.slots) <= set(diagram_labels(form))
    assert not set(form.slots) & set(diagram_claims(form))


def test_a_callout_note_is_a_label_but_not_a_claim() -> None:
    annotated = next(
        d for d in _specimen().diagrams if d.kind == "annotated_example"
    )
    notes = {c.note for c in annotated.callouts}
    assert notes <= set(diagram_labels(annotated))
    assert not notes & set(diagram_claims(annotated))


def test_every_kind_appears_in_the_contract_the_generator_is_given() -> None:
    block = contract_block()
    for kind in DIAGRAM_KINDS:
        assert kind in block


def test_a_lesson_has_no_user_field_anywhere() -> None:
    """PRODUCT-PRINCIPLES §2/§3: lessons are global. Asserted, not assumed."""
    names = _all_field_names()
    assert not {n for n in names if "user" in n or "learner" in n}


def test_a_lesson_has_no_l1_or_gloss_field_anywhere() -> None:
    """A gloss is per-learner by nature (#159) and would break the global line."""
    names = _all_field_names()
    assert not {n for n in names if n in {"l1", "l1_gloss", "gloss", "translation"}}
