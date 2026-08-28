"""The typed shape of a lesson, and the contract the generator is given.

**No colour field, no font field, no coordinate field, anywhere in this module.**
That is what makes "no red in the lesson UI" structural rather than a promise:
the renderer owns every visual decision and the model has no field to express one
in. `tests/test_lessons_schema.py` asserts the absence, because a rule nothing
checks is a convention.

**The contract handed to the generator is DERIVED from these models**, the way
`core.items.schema.generator_contract` is derived from its own -- so the prompt
and the validator cannot disagree about what was asked for. #213 is what that
guarantee is for: a field the checks required and the contract excluded made an
entire item type impossible to pass under any input, nine times running with no
stochastic component.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from core.lessons import (
    BRANCHES,
    CALLOUTS,
    CLAUSE_WORDS,
    DIAGRAM_KINDS,
    EXAMPLES_PER_SECTION,
    EXPLANATION_WORDS,
    FORM_SLOTS,
    TIMELINE_POINTS,
    WHY_WORDS,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


# ── the prose half ──────────────────────────────────────────────────────────


class Mistake(BaseModel):
    """One natural-sounding mistake, its correction, and one line of why.

    **Named `Mistake`/`said` rather than `WrongExample`/`wrong`, and the rename
    was forced by a test rather than chosen.** `test_web_shell.py`'s no-guilt scan
    reads raw `.tsx` source, so the IDENTIFIER `wrong` tripped it ten times even
    though the only string a learner reads is `"Not: "`. The scan's crudeness is
    what makes it hard to evade, so the code was renamed rather than the guard
    weakened -- adjusting a shipped criterion to fit new code is the move rule 7
    forbids. #110's split still governs the CONTENT: `content_offenders` permits
    the word *wrong* inside a lesson's prose, which is where it belongs.

    **This field is the reason lesson prose is scanned with
    `copy_rules.content_offenders` and not the wider `offenders`.** The wide rule
    bans `wrong / incorrect / missed / failed / broke`, which is right for a
    string the app says ABOUT a learner and wrong for a field whose entire job is
    to show a mistake. Using the wide rule here would reject the content the
    lesson exists to carry.
    """

    model_config = _FROZEN

    #: What a learner might really say. The word itself is fine in the
    #: VALUE -- `content_offenders` permits it -- and only the field NAME
    #: moved.
    said: str
    corrected: str
    why: str


class Section(BaseModel):
    """One grammar target, taught."""

    model_config = _FROZEN

    #: **The grammar target's exact text**, byte-for-byte from
    #: `data/syllabus_units.json`. Not an index and not a slug: this is already
    #: the key `checkpoint.per_target` uses and that
    #: `blueprint.validate_checkpoint` compares with plain set membership and
    #: plain set difference -- no normalisation anywhere. Normalising on one side
    #: and not the other is exactly how the two would drift.
    #:
    #: **The model returns it rather than the runner assigning it by position.**
    #: Assigning would make the bijection a tautology: a runner that zips
    #: sections onto targets can never produce a mismatch, so the check would
    #: measure the runner instead of the lesson. Asking the model to copy the
    #: string character for character makes the bijection a real measurement, and
    #: the failure codes tell the two ways it can go wrong apart.
    target: str
    explanation: str
    when_to_use: str
    when_not_to: str
    examples: tuple[str, ...]
    mistake: Mistake


# ── the five diagram kinds ──────────────────────────────────────────────────
#
# Every kind carries `target`, and it must be one of the unit's own. A diagram
# names exactly one target and a target carries at most one diagram -- the rule
# is stated rather than left a habit, because the deterministic "every label
# appears in the section's own prose" check is defined PER SECTION, and two
# diagrams against one section makes it ambiguous which prose a label must
# appear in.


class _Diagram(BaseModel):
    model_config = _FROZEN
    target: str


class TimelinePoint(BaseModel):
    model_config = _FROZEN
    label: str
    #: Ordering only. Not a coordinate: the renderer decides where this lands on
    #: the page, and `at` says only what comes before what.
    at: int
    now: bool = False


class TimelineDiagram(_Diagram):
    """A line, one `now`, ordered points. Present perfect vs past simple."""

    kind: Literal["timeline"] = "timeline"
    points: tuple[TimelinePoint, ...]


class ContrastSide(BaseModel):
    model_config = _FROZEN
    form: str
    example: str


class ContrastPairDiagram(_Diagram):
    """One situation, two forms, one line on what changes."""

    kind: Literal["contrast_pair"] = "contrast_pair"
    situation: str
    #: **`first` and `second`, NOT `left` and `right`.** The names were `left`
    #: and `right` until `test_the_diagram_schema_has_no_colour_font_or_coordinate_field`
    #: refused them, and it was right to: on a phone the two sides are stacked,
    #: not side by side, so `left` is the model making a LAYOUT decision in a
    #: schema that exists to have none. The renderer owns where they go.
    first: ContrastSide
    second: ContrastSide
    what_changes: str


class FormBuildDiagram(_Diagram):
    """Labelled slots: `subject + have/has + past participle`."""

    kind: Literal["form_build"] = "form_build"
    slots: tuple[str, ...]
    example: str


class Branch(BaseModel):
    model_config = _FROZEN
    answer: str
    form: str


class DecisionTreeDiagram(_Diagram):
    """A question, 2-3 branches, each to a form. *Is the time finished?*"""

    kind: Literal["decision_tree"] = "decision_tree"
    question: str
    branches: tuple[Branch, ...]


class Callout(BaseModel):
    model_config = _FROZEN
    part: str
    note: str


class AnnotatedExampleDiagram(_Diagram):
    """One sentence with callouts on its parts."""

    kind: Literal["annotated_example"] = "annotated_example"
    sentence: str
    callouts: tuple[Callout, ...]


Diagram = Annotated[
    Union[
        TimelineDiagram,
        ContrastPairDiagram,
        FormBuildDiagram,
        DecisionTreeDiagram,
        AnnotatedExampleDiagram,
    ],
    Field(discriminator="kind"),
]

MODEL_FOR_KIND: dict[str, type[_Diagram]] = {
    "timeline": TimelineDiagram,
    "contrast_pair": ContrastPairDiagram,
    "form_build": FormBuildDiagram,
    "decision_tree": DecisionTreeDiagram,
    "annotated_example": AnnotatedExampleDiagram,
}

# The set and the constant cannot drift apart without this failing at import.
assert set(MODEL_FOR_KIND) == set(DIAGRAM_KINDS)


class Lesson(BaseModel):
    """One unit's teaching. One section per grammar target, 0-5 diagrams."""

    model_config = _FROZEN

    unit_number: int
    sections: tuple[Section, ...]
    diagrams: tuple[Diagram, ...] = ()


def parse_lesson(raw: dict) -> Lesson:
    """One JSON object from the generator → a typed lesson, or a ValidationError."""
    return Lesson.model_validate(raw)


# ── what a diagram says, as text ────────────────────────────────────────────


def diagram_labels(spec: _Diagram) -> tuple[str, ...]:
    """EVERY learner-visible string on this diagram, for the no-guilt scan.

    A diagram is generated content like any other, so every string on it is
    scanned. This is the wide set; `diagram_sentences` is the narrow one.
    """
    if isinstance(spec, TimelineDiagram):
        return tuple(p.label for p in spec.points)
    if isinstance(spec, ContrastPairDiagram):
        return (
            spec.situation, spec.first.form, spec.first.example,
            spec.second.form, spec.second.example, spec.what_changes,
        )
    if isinstance(spec, FormBuildDiagram):
        return (*spec.slots, spec.example)
    if isinstance(spec, DecisionTreeDiagram):
        return (spec.question, *(b.answer for b in spec.branches),
                *(b.form for b in spec.branches))
    if isinstance(spec, AnnotatedExampleDiagram):
        return (spec.sentence, *(c.part for c in spec.callouts),
                *(c.note for c in spec.callouts))
    raise ValueError(f"unknown diagram kind: {spec!r}")


def diagram_sentences(spec: _Diagram) -> tuple[str, ...]:
    """Only the fields that carry an EXAMPLE SENTENCE.

    **These, and only these, are matched against the section's own examples.**
    See `checks.diagram_failures` for the full per-kind, per-field table and the
    reasoning; the short version is the line that decides it:

        A field is string-checked when it must be VERBATIM, and verbatim matters
        for exactly one reason -- gate provenance. Everything else is paraphrase
        by nature and is checked by C1 and C3 reading the diagram as text.

    An example sentence on a diagram that is not one of the section's own is a
    sentence that never went through C2 (does it demonstrate the target) or
    `judge_naturalness` (would a real person say this). **It reaches a learner
    ungated**, which is a specific structural gap and the only one string
    matching can close. A `situation`, a slot name, a `form` label, a tree
    question, a branch answer, a callout note or `what_changes` are the diagram
    restating the section's point in its own words -- which is what a diagram is
    FOR, and if it restates it wrongly, C1 and C3 see it.

    **`timeline` returns nothing here, deliberately**: it has no sentence field.
    Its point labels are quote-or-paraphrase by nature and are checked by the
    model gates plus its own ordering rules.
    """
    if isinstance(spec, ContrastPairDiagram):
        return (spec.first.example, spec.second.example)
    if isinstance(spec, FormBuildDiagram):
        return (spec.example,)
    if isinstance(spec, AnnotatedExampleDiagram):
        return (spec.sentence,)
    if isinstance(spec, (TimelineDiagram, DecisionTreeDiagram)):
        return ()
    raise ValueError(f"unknown diagram kind: {spec!r}")


def diagram_text(spec: _Diagram) -> str:
    """The diagram as a line of prose, for C1's and C3's payloads.

    **This is how a diagram is model-checked at no extra cost.** The spec is
    rendered to text and included in the section payload C1 classifies and the
    whole-lesson payload C3 reads, so a diagram teaching a different point, or
    contradicting the prose beside it, fails the same two checks the prose does.

    It is NOT a rendering. Whether the picture READS is checked by nobody here --
    that is the operator's eyes, and it is the one judgement in this slice he can
    actually make.
    """
    if isinstance(spec, TimelineDiagram):
        points = ", then ".join(
            f"{p.label}{' (NOW)' if p.now else ''}"
            for p in sorted(spec.points, key=lambda p: p.at)
        )
        return f"A timeline: {points}."
    if isinstance(spec, ContrastPairDiagram):
        return (
            f"Two forms for one situation ({spec.situation}): "
            f"{spec.first.form} — \"{spec.first.example}\"; versus "
            f"{spec.second.form} — \"{spec.second.example}\". "
            f"What changes: {spec.what_changes}."
        )
    if isinstance(spec, FormBuildDiagram):
        return (
            f"The form is built as: {' + '.join(spec.slots)}. "
            f"For example: \"{spec.example}\"."
        )
    if isinstance(spec, DecisionTreeDiagram):
        branches = "; ".join(f"{b.answer} → {b.form}" for b in spec.branches)
        return f"A choice — {spec.question} {branches}."
    if isinstance(spec, AnnotatedExampleDiagram):
        notes = "; ".join(f"\"{c.part}\": {c.note}" for c in spec.callouts)
        return f"The sentence \"{spec.sentence}\", annotated — {notes}."
    raise ValueError(f"unknown diagram kind: {spec!r}")


# ── the generator contract, derived ─────────────────────────────────────────

#: Fields the runner supplies and the generator must never invent. Kept EMPTY
#: and stated rather than omitted: every field of a lesson is the generator's,
#: including `target`, for the reason in `Section.target`. #213 was a field
#: placed in the items equivalent of this set while the checks still required
#: it -- so a set that is empty on purpose is worth saying out loud.
NOT_THE_GENERATORS: frozenset[str] = frozenset()

_WIRE_TYPE = {
    "str": "string",
    "int": "integer",
    "bool": "true or false",
    "tuple": "array of strings",
}


def _describe(name: str, annotation: object) -> str:
    text = str(annotation)
    base = text.replace("| None", "").replace("Optional[", "").strip(" []")
    raw = getattr(annotation, "__name__", base)
    return _WIRE_TYPE.get(raw, _WIRE_TYPE.get(base, base))


def section_contract() -> dict[str, str]:
    """Every field a section must carry, derived from `Section` itself."""
    out: dict[str, str] = {}
    for name, field in Section.model_fields.items():
        wire = field.serialization_alias or field.alias or name
        if wire in NOT_THE_GENERATORS:
            continue
        if wire == "target":
            out[wire] = (
                "string — one of the unit's grammar targets, COPIED CHARACTER "
                "FOR CHARACTER from the list you were given"
            )
        elif wire == "examples":
            out[wire] = (
                f"array of {EXAMPLES_PER_SECTION[0]}-{EXAMPLES_PER_SECTION[1]} "
                "English sentences"
            )
        elif wire == "mistake":
            out[wire] = (
                "object with `said` (a mistake a learner really makes), "
                "`corrected`, and `why` (one line)"
            )
        else:
            out[wire] = _describe(wire, field.annotation) + " (required)"
    return out


def diagram_contract(kind: str) -> dict[str, str]:
    """Every field one diagram kind must carry, derived from its model."""
    model = MODEL_FOR_KIND[kind]
    out: dict[str, str] = {}
    for name, field in model.model_fields.items():
        wire = field.serialization_alias or field.alias or name
        if wire in NOT_THE_GENERATORS:
            continue
        if wire == "kind":
            out[wire] = f"the string {kind!r}"
        elif wire == "target":
            out[wire] = (
                "string — the ONE grammar target this diagram is about, copied "
                "character for character"
            )
        elif wire == "points":
            out[wire] = (
                "array of objects, each {label: string, at: integer for "
                "ordering only, now: true or false}. EXACTLY ONE has now=true"
            )
        elif wire in ("first", "second"):
            out[wire] = "object with {form: string, example: string}"
        elif wire == "branches":
            out[wire] = "array of objects, each {answer: string, form: string}"
        elif wire == "callouts":
            out[wire] = "array of objects, each {part: string, note: string}"
        elif wire == "slots":
            out[wire] = (
                "array of strings — the parts of the form in order, e.g. "
                "[\"subject\", \"have/has\", \"past participle\"]"
            )
        else:
            out[wire] = _describe(wire, field.annotation) + " (required)"
    return out


def contract_block() -> str:
    """The section contract and all five diagram contracts, as prompt lines."""
    lines = ["  section"]
    lines += [f"    {k}: {v}" for k, v in section_contract().items()]
    for kind in DIAGRAM_KINDS:
        lines.append(f"  diagram · {kind}")
        lines += [f"    {k}: {v}" for k, v in diagram_contract(kind).items()]
    return "\n".join(lines)


def constraint_block() -> str:
    """The SHAPE rules, derived from the constants `checks.py` itself reads.

    Same guarantee `contract_block` gives for field names: a bound cannot be
    changed in one place and stated in the other.
    """
    lines = [
        "  every section",
        # **AIM AT THE CENTRE, NOT THE EDGE.** Stage 1 produced explanations of
        # 36 and 37 words against a 40-70 band -- both just under the floor,
        # which is what a model does when it is given a range and writes toward
        # its lower bound. The band is UNCHANGED (rule 7); what changed is that
        # the prompt names a target inside it and says a short one is rejected.
        f"    - explanation is {EXPLANATION_WORDS[0]}-{EXPLANATION_WORDS[1]} "
        f"words. **AIM FOR ABOUT "
        f"{(EXPLANATION_WORDS[0] + EXPLANATION_WORDS[1]) // 2}**, which is four "
        f"or five full sentences. An explanation UNDER "
        f"{EXPLANATION_WORDS[0]} words is rejected, and a short one is the "
        f"single most common way this fails -- write the *when not to* thinking "
        f"out in full rather than compressing it",
        f"    - when_to_use and when_not_to are at most {CLAUSE_WORDS} words each",
        f"    - mistake.why is at most {WHY_WORDS} words",
        "    - every example sentence is at most 12 words",
        "    - contractions by default: I'll, don't, we're, it's",
        "    - nothing you write may pass judgement on the learner",
        "    - no translation, no gloss, no language but English",
        "  every diagram",
        "    - every label, form and example on a diagram must also appear in "
        "the prose of the section it belongs to",
        f"    - a timeline has {TIMELINE_POINTS[0]}-{TIMELINE_POINTS[1]} points, "
        "strictly ordered by `at`, and EXACTLY ONE marked now",
        f"    - a decision_tree has {BRANCHES[0]}-{BRANCHES[1]} branches with "
        "distinct answers",
        f"    - an annotated_example has {CALLOUTS[0]}-{CALLOUTS[1]} callouts",
        f"    - a form_build has {FORM_SLOTS[0]}-{FORM_SLOTS[1]} slots",
        "    - at most ONE diagram per grammar target, and a target that suits "
        "none of the five kinds gets NO diagram — fewer rather than false",
    ]
    return "\n".join(lines)
