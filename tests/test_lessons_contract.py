"""The two structural pre-checks, run before a single billed call. #213's lesson.

**#213 is why this file exists.** `l1_to_l2_production` was structurally
impossible to pass under ANY input: `accepted_variants` was placed in the set the
generator contract excludes while `checks` still required at least two of them,
so a draft obeying the contract perfectly failed. Nine consecutive failures with
no stochastic component -- which is what should have been suspicious about it --
and it was found by running a PERFECT DRAFT THROUGH THE GATES rather than by
reading the prompt.

So both checks here answer the same question in two ways, and both run free:

1. **Is any field the checks read excluded from the contract?** Derived by
   parsing `checks.py` and `gates.py` for attribute access -- **independently of
   the contract-building code**, because a test that asked `schema.py` which
   fields it asks for would be deriving its expected value from the function
   under test (CLAUDE.md §3 rule 5) and would have passed cheerfully through
   #213.
2. **Does a perfect lesson pass every deterministic check?** The specimen is
   hand-authored, committed, and checked against the real unit 1.

**Check 2 has already earned its place.** On its first run it failed three times
-- and the defect was in the CHECK, not the specimen: the diagram label rule read
every string on a spec, including a `form_build`'s grammatical slot names and an
`annotated_example` callout's own commentary, which made two of the five diagram
kinds impossible to pass. That is #213's family, in the check written to prevent
#213, caught by this file before it cost a call.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from core.lessons import schema as lessons_schema
from core.lessons.checks import deterministic_failures
from core.lessons.schema import (
    MODEL_FOR_KIND,
    NOT_THE_GENERATORS,
    Lesson,
    Section,
    contract_block,
    diagram_contract,
    parse_lesson,
    section_contract,
)
from core.syllabus.content import units

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE = REPO_ROOT / "packages" / "core"
FIXTURES = Path(__file__).parent / "fixtures" / "lessons"


def _attributes_read(path: Path) -> set[str]:
    """Every attribute name this module reads off anything.

    Deliberately coarse. A wider set makes the assertion STRICTER, never weaker:
    an irrelevant name that happens to match a model field only adds an
    obligation on the contract, and a real one can never be missed.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
    }


def _model_fields() -> set[str]:
    fields = set(Section.model_fields)
    for model in MODEL_FOR_KIND.values():
        fields |= set(model.model_fields)
    return fields


def test_no_field_the_checks_read_is_excluded_from_the_contract() -> None:
    """#213, as a test rather than as a memory.

    A field that `checks.py` or `gates.py` reads, and that the generator is never
    asked for, is a field no draft can supply -- and every lesson fails on it
    forever, with a diagnostic that names the field rather than the contract.
    """
    read: set[str] = set()
    for name in ("checks.py", "gates.py"):
        path = CORE / "lessons" / name
        if path.exists():
            read |= _attributes_read(path)

    required = read & _model_fields()
    assert required, "the AST walk found no model fields at all -- it is broken"

    offered = set(section_contract())
    for kind in MODEL_FOR_KIND:
        offered |= set(diagram_contract(kind))

    missing = sorted(required - offered)
    assert not missing, (
        "the checks read fields the generator contract never asks for, so no "
        f"draft can supply them and every lesson fails forever: {missing}. "
        "This is #213 exactly."
    )


def test_the_excluded_set_is_empty_and_that_is_deliberate() -> None:
    """`NOT_THE_GENERATORS` is where #213 actually lived.

    Every field of a lesson is the generator's, including `target`. If a later
    slice adds a name here, the test above is what tells it whether the checks
    still require that field -- so this assertion is a tripwire on the set, not a
    restatement of it.
    """
    assert NOT_THE_GENERATORS == frozenset()


def test_every_diagram_kind_appears_in_the_contract() -> None:
    block = contract_block()
    for kind in MODEL_FOR_KIND:
        assert f"diagram · {kind}" in block


def _unit_targets(unit_number: int) -> list[str]:
    for unit in units():
        if unit.unit_number == unit_number:
            return [t.target for t in unit.grammar_targets]
    raise AssertionError(f"no unit {unit_number}")


#: **Two specimens, and the reason is a constraint rather than a preference.** A
#: lesson carries at most ONE diagram per grammar target; unit 1 has four
#: targets and there are five diagram kinds, so one fixture structurally cannot
#: exercise them all. Unit 9 carries `decision_tree`, which `specimen.json`
#: could not, and a second `contrast_pair` in the descriptive shape.
SPECIMENS = (("specimen.json", 1), ("specimen_unit9.json", 9))


def _specimen(name: str):
    return parse_lesson(json.loads((FIXTURES / name).read_text()))


@pytest.mark.parametrize("name,unit", SPECIMENS)
def test_a_perfect_specimen_lesson_passes_every_deterministic_check(
    name: str, unit: int
) -> None:
    """Run a perfect draft through the gates. The way #213 was found.

    The expected value is hardcoded -- zero failures -- and never computed from
    the checks (rule 5). The specimens are committed, so a check that tightens
    against real content fails here first, before a billed run discovers it.
    """
    failures = deterministic_failures(_specimen(name), _unit_targets(unit))
    assert failures == (), (
        f"{name}: a hand-authored, deliberately correct lesson cannot pass the "
        "deterministic checks, so no generated one can either:\n"
        + "\n".join(f"  - {f}" for f in failures)
    )


@pytest.mark.parametrize("name,unit", SPECIMENS)
def test_each_specimen_is_a_real_unit(name: str, unit: int) -> None:
    """A specimen against invented targets passes the bijection trivially."""
    lesson = _specimen(name)
    assert lesson.unit_number == unit
    assert [s.target for s in lesson.sections] == _unit_targets(unit)


def test_the_specimens_exercise_EVERY_diagram_kind() -> None:
    """**THE LIMIT OF THE PRE-CHECK, as a test. This is the whole finding.**

    A perfect specimen only proves the checks pass ON THE SPECIMEN. The label
    rule was fixed for `form_build` and `annotated_example` during
    implementation -- caught here -- and was **still structurally unpassable for
    `contrast_pair` and `decision_tree`, because no fixture exercised those two
    in a realistic shape.** `decision_tree` was not exercised at all. Stage 1 hit
    it on the host and it cost billed calls.

    **The pre-check passed while the rule was unpassable. Its blind spot was
    coverage, not logic**, so coverage is now asserted: a sixth kind cannot
    arrive without a specimen that exercises it.
    """
    exercised = {
        spec.kind for name, _ in SPECIMENS for spec in _specimen(name).diagrams
    }
    missing = sorted(set(MODEL_FOR_KIND) - exercised)
    assert not missing, (
        "diagram kinds no specimen exercises, so the deterministic checks are "
        f"unproven against them and a billed run is where that is found: {missing}"
    )


def test_the_specimens_exercise_commentary_FIELDS_and_not_only_kinds() -> None:
    """Coverage of kinds is not coverage of shapes, which is the same trap again.

    A `contrast_pair` whose `situation` was lifted verbatim from the prose --
    which is what the first specimen carried -- exercises the kind and not the
    failure. So the fixtures are asserted to contain commentary that is genuinely
    NOT a quotation of the section, in every field that class covers.
    """
    from core.lessons.checks import section_prose

    checked = 0
    for name, _ in SPECIMENS:
        lesson = _specimen(name)
        prose = {s.target: section_prose(s).casefold() for s in lesson.sections}
        for spec in lesson.diagrams:
            body = prose.get(spec.target, "")
            for field in ("situation", "what_changes", "question"):
                value = getattr(spec, field, None)
                if value:
                    checked += 1
                    assert value.casefold() not in body, (
                        f"{name}: {spec.kind}.{field} is quoted from the prose, "
                        "so it exercises the kind but not the shape that failed"
                    )
    assert checked >= 3, (
        f"only {checked} commentary fields exercised; the fixtures have drifted "
        "back to shapes built to pass"
    )


def test_the_negative_control_can_actually_execute() -> None:
    """The archived plan's control could not, and that is why this exists.

    `probe_ranked` raises `ValueError` when the claimed target is not among the
    candidates. The archived control claimed a target belonging to no unit in
    scope, so the gate meant to prove C1 discriminates would have raised before
    spending a call -- #213's family, in the negative control itself.
    """
    control = json.loads((FIXTURES / "drifted.json").read_text())
    assert control["claims"] in control["candidates"]
    assert control["actually"] in control["candidates"]
    assert control["claims"] != control["actually"]

    # And both must be real targets of the same unit, so the drift is to a
    # SIBLING. A control that is easy to refuse proves nothing about a check
    # whose job is telling neighbours apart.
    targets = _unit_targets(1)
    assert control["claims"] in targets
    assert control["actually"] in targets

    Section.model_validate(control["section"])


def test_the_control_section_claims_what_it_does_not_teach() -> None:
    control = json.loads((FIXTURES / "drifted.json").read_text())
    assert control["section"]["target"] == control["claims"]
