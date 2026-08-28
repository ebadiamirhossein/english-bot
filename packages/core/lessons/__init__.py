"""Grammar lessons: the teaching the 82 syllabus targets never had (#182).

The syllabus carries 24 can-dos and 82 grammar targets, and until this slice
nothing in the app explained one of them. W10 shipped block 3 honestly -- a
can-do, four bare labels, and the line *"The written explanation for these is on
its way."* This package is what that line was waiting for.

**The pure half, mirroring `core.items`.** `core.services.lessons` holds every
query; `gates.py` and `generate.py` are the only modules here permitted to reach
a model, and `tests/test_core_boundary.py::test_lessons_package_is_pure` names
them. Everything else is a pure function of its arguments. That split is what
keeps `test_no_sql_outside_services` unexempted, so #59 stays the only boundary
exemption in the repository.

**Lessons are GLOBAL.** Present perfect is present perfect for every learner, so
`grammar_lessons` has no `user_id` column at all -- one row per unit, 24 rows
forever, however many learners arrive. PRODUCT-PRINCIPLES §2 is satisfied
trivially and §3's per-user-scaling flag does not fire.

**A lesson is English only.** No L1 gloss, ever: a gloss is per-learner by nature
(#159) and one on a lesson would make the lesson per-learner and break the line
above.
"""

from __future__ import annotations

#: Bumped whenever a check tightens, exactly as `VALIDATOR_VERSION` is. A row
#: verified under retired rules is not a verified row, so
#: `core.services.lessons.for_unit` REFUSES anything below this -- the same
#: policy `bank_for_session` applies to `validator_version`, and for the same
#: reason. Retrofitting the field is impossible, so it starts here.
LESSON_VERSION = 1

#: The three units this slice generates for. **Unit 1 rather than the archived
#: plan's unit 2**, because `core.services.syllabus.current_unit` returns 1 for
#: both learners and cannot advance (#188) -- so unit 1 is the only lesson a
#: learner can reach, and lessons for unreachable units would be teaching nobody
#: can see. 9 and 20 keep the three-stage range test the original scope was
#: chosen for: whether one prompt and one gate set hold across the syllabus,
#: which three consecutive stage-1 units would not answer.
SCOPE_UNITS: tuple[int, ...] = (1, 9, 20)

#: A closed set, and closed is the point: the renderer owns every kind, so the
#: model cannot invent a shape `apps/web` has no code for.
#:
#: Re-checked against the twelve targets of units 1, 9 and 20 when the scope
#: moved off the archived plan's 2/9/20 -- all twelve admit one of these five,
#: so the set survived the scope change unchanged. Recorded as a positive so it
#: is not re-derived.
DIAGRAM_KINDS: tuple[str, ...] = (
    "timeline",
    "contrast_pair",
    "form_build",
    "decision_tree",
    "annotated_example",
)

#: Sections per lesson. **Mirrors `syllabus_units_three_to_five_grammar_targets`
#: rather than describing today's data**, and the real rule is a BIJECTION that
#: this range cannot express -- see `checks.bijection_failures`.
SECTIONS_PER_LESSON: tuple[int, int] = (3, 5)

#: Diagrams per lesson. **Both ends are deliberate and both were wrong once.**
#:
#: ZERO is permitted because "fewer rather than false" declares it legitimate:
#: if no target admits a kind, the correct output is no diagram and a reported
#: count. A floor of 1 would make that state unstorable and the run would die on
#: an INSERT, with a diagnostic naming Postgres rather than the condition the
#: design anticipated.
#:
#: FIVE is the ceiling because the real rule is ONE DIAGRAM PER TARGET AT MOST,
#: so the maximum is the unit's target count -- 3 to 5 by the syllabus CHECK.
#: A cap of 3 forbids the output a four-target unit naturally produces, which is
#: the floor's defect at the other end; a cap of 4 would encode today's measured
#: maximum as a rule, which `SECTIONS_PER_LESSON` deliberately declines to do.
DIAGRAMS_PER_LESSON: tuple[int, int] = (0, 5)

#: Same number as `gates.MAX_REPAIRS` and for the same reason: a lesson still
#: failing after two informed rewrites is reported as unshippable and the run
#: stops. Never shipped with a warning, never with a bar adjusted.
MAX_REGENERATIONS = 2

# ── field limits, which are what make the 90-second promise checkable ────────
#
# PRD §4.1 block 3 reads "This week's grammar target: 90-second explanation + 8
# generated items" -- singular TARGET. Block 3 expands one section and collapses
# the rest, so the 90 seconds is a section, not the whole lesson.

#: A section's `explanation`, in words. ~40-70 reads in about 30 seconds at B1.
EXPLANATION_WORDS: tuple[int, int] = (40, 70)

#: `when_to_use` and `when_not_to`, each. One sentence, not a paragraph.
CLAUSE_WORDS = 20

#: `mistake.why`. One line, which is the whole point of the field.
WHY_WORDS = 20

#: Example sentences per section.
EXAMPLES_PER_SECTION: tuple[int, int] = (2, 3)

#: Callouts on an `annotated_example`, branches on a `decision_tree`,
#: points on a `timeline`, slots on a `form_build`.
CALLOUTS: tuple[int, int] = (2, 4)
BRANCHES: tuple[int, int] = (2, 3)
TIMELINE_POINTS: tuple[int, int] = (2, 4)
FORM_SLOTS: tuple[int, int] = (2, 5)

__all__ = [
    "BRANCHES",
    "CALLOUTS",
    "CLAUSE_WORDS",
    "DIAGRAMS_PER_LESSON",
    "DIAGRAM_KINDS",
    "EXAMPLES_PER_SECTION",
    "EXPLANATION_WORDS",
    "FORM_SLOTS",
    "LESSON_VERSION",
    "MAX_REGENERATIONS",
    "SCOPE_UNITS",
    "SECTIONS_PER_LESSON",
    "TIMELINE_POINTS",
    "WHY_WORDS",
]
