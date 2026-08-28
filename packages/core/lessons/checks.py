"""Every deterministic check on a lesson. Pure — no model, no database.

Cheapest first, exactly as `gates.validate` orders its stages: **every free check
runs before any call costs money.** A lesson that fails one of these has cost
nothing but the generation call that produced it.

**The two checks that matter most cannot be expressed in SQL**, and both are here
for the same reason the blocks-sum invariant lives in
`blueprint.validate_checkpoint` rather than in migration 014 (#167): the row does
not know its unit's target count.

- the **bijection** -- one section per grammar target, both directions;
- **at most one diagram per target**, and every diagram naming a real target.

`migrations/017_lessons.sql` says so in its own comments rather than leaving a
reader to assume the CHECK is the guarantee.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from core.copy_rules import content_offenders
from core.items.checks import MAX_SENTENCE_WORDS
from core.items.naturalness import jargon_hits, textbook_hits, uncontracted
from core.lessons import (
    BRANCHES,
    CALLOUTS,
    CLAUSE_WORDS,
    DIAGRAMS_PER_LESSON,
    EXAMPLES_PER_SECTION,
    EXPLANATION_WORDS,
    FORM_SLOTS,
    SECTIONS_PER_LESSON,
    TIMELINE_POINTS,
    WHY_WORDS,
)
from core.lessons.schema import (
    AnnotatedExampleDiagram,
    ContrastPairDiagram,
    DecisionTreeDiagram,
    FormBuildDiagram,
    Lesson,
    Section,
    TimelineDiagram,
    diagram_claims,
    diagram_labels,
)

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")

#: Units 18-21 are the Work track; every other unit is Life. **Imported from
#: `core.items.generate` rather than re-declared** -- a second copy of a mapping
#: is how the two halves of `docs/TASKS-v3-web.md` came to disagree (#130) --
#: except that importing a CLI module for one frozenset would drag its argparse
#: and its constants along, so the import is deferred to `track_for` below.


@dataclass(frozen=True, slots=True)
class Failure:
    """One reason a lesson is invalid. `code` is stable; `detail` is for humans."""

    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


def track_for(unit_number: int) -> str:
    """The track this unit's language belongs to. One source, `core.items`."""
    from core.items.generate import track_for as _track_for

    return _track_for(unit_number)


def words(text: str | None) -> list[str]:
    return _WORD.findall(text or "")


def section_prose(section: Section) -> str:
    """Everything in a section a diagram label could legitimately echo.

    One place builds it, so the label check and the C1 payload cannot disagree
    about what "the section's own prose" means.
    """
    return " ".join(
        [
            section.explanation,
            section.when_to_use,
            section.when_not_to,
            *section.examples,
            section.mistake.said,
            section.mistake.corrected,
            section.mistake.why,
        ]
    )


# ── the bijection ───────────────────────────────────────────────────────────


def bijection_failures(
    lesson: Lesson, targets: Sequence[str]
) -> tuple[Failure, ...]:
    """One section per grammar target. **Both directions, as a failure.**

    **The one-directional version is the trap.** Unit 1 has four targets; a
    lesson with three sections satisfies `grammar_lessons_sections_three_to_five`
    (3-5) AND `syllabus_units_three_to_five_grammar_targets` (3-5) while the
    counts disagree. It would pass C1 on each of its three sections, pass C2,
    pass C3, and have no orphan section -- and leave one target untaught, which
    carries 2 of unit 1's 12 checkpoint items. **Orphan detection looks the wrong
    way for this; the missing direction is the one that hurts.**

    **Byte-exact, and that is read from the code rather than assumed.**
    `blueprint.validate_checkpoint` compares `checkpoint.per_target` keys against
    target text with plain set membership and plain set difference -- it
    normalises nothing, and it already enforces this same bijection in that
    direction. Normalising here and not there is how the two would drift.
    """
    authored = list(targets)
    named = [s.target for s in lesson.sections]
    out: list[Failure] = []

    low, high = SECTIONS_PER_LESSON
    if not low <= len(named) <= high:
        out.append(
            Failure(
                "section_count",
                f"{len(named)} sections; the schema permits {low}-{high}",
            )
        )

    seen: set[str] = set()
    for name in named:
        if name not in authored:
            out.append(
                Failure(
                    "target_not_in_unit",
                    f"section names {name!r}, which is not one of unit "
                    f"{lesson.unit_number}'s grammar targets",
                )
            )
        if name in seen:
            out.append(
                Failure("target_duplicated", f"two sections both name {name!r}")
            )
        seen.add(name)

    for name in authored:
        if name not in seen:
            out.append(
                Failure(
                    "target_missing",
                    f"no section teaches {name!r} -- a target the lesson never "
                    "mentions is a target the learner sits a checkpoint on "
                    "untaught",
                )
            )
    return tuple(out)


# ── the prose ───────────────────────────────────────────────────────────────


def section_failures(section: Section, *, track: str) -> tuple[Failure, ...]:
    """Length, register and no-guilt, on one section."""
    out: list[Failure] = []

    n = len(words(section.explanation))
    low, high = EXPLANATION_WORDS
    if not low <= n <= high:
        out.append(
            Failure("explanation_length", f"{n} words; {low}-{high} required")
        )

    for field in ("when_to_use", "when_not_to"):
        n = len(words(getattr(section, field)))
        if n > CLAUSE_WORDS:
            out.append(
                Failure(f"{field}_length", f"{n} words; at most {CLAUSE_WORDS}")
            )

    n = len(words(section.mistake.why))
    if n > WHY_WORDS:
        out.append(Failure("why_length", f"{n} words; at most {WHY_WORDS}"))

    low, high = EXAMPLES_PER_SECTION
    if not low <= len(section.examples) <= high:
        out.append(
            Failure(
                "example_count",
                f"{len(section.examples)} examples; {low}-{high} required",
            )
        )

    if section.mistake.said.strip() == section.mistake.corrected.strip():
        out.append(
            Failure(
                "mistake_identical",
                "the mistake and its correction are the same string, so the "
                "section demonstrates nothing",
            )
        )

    for i, sentence in enumerate(section.examples):
        n = len(words(sentence))
        if n > MAX_SENTENCE_WORDS:
            out.append(
                Failure(
                    "example_too_long",
                    f"example {i + 1} is {n} words; at most {MAX_SENTENCE_WORDS}",
                )
            )
        hits = jargon_hits(sentence, track=track)
        if hits:
            out.append(
                Failure("example_jargon", f"example {i + 1}: {', '.join(hits)}")
            )
        hits = textbook_hits(sentence)
        if hits:
            out.append(
                Failure("example_textbook", f"example {i + 1}: {', '.join(hits)}")
            )
        pairs = uncontracted(sentence)
        if pairs:
            shown = ", ".join(" ".join(p) for p in pairs)
            out.append(
                Failure("example_uncontracted", f"example {i + 1}: {shown}")
            )

    # **`content_offenders`, NOT the wider `offenders`.** The wide rule bans
    # `wrong / incorrect / missed / failed / broke`, which is right for a string
    # the app says ABOUT a learner and wrong for `mistake`, whose whole job
    # is to show a mistake. #110 closed by splitting the two for exactly this,
    # and using the wide rule here would reject the field the lesson exists to
    # carry.
    hits = content_offenders(section_prose(section))
    if hits:
        out.append(Failure("no_guilt", ", ".join(hits)))

    return tuple(out)


# ── the diagrams ────────────────────────────────────────────────────────────


def diagram_failures(lesson: Lesson, targets: Sequence[str]) -> tuple[Failure, ...]:
    """Structure, ordering, the per-target rule, and labels against the prose.

    **The per-target rule is a rule and not a habit**, and the reason makes it
    one: the label check below is defined PER SECTION, so two diagrams against
    one section makes it ambiguous which prose a label must appear in. A
    `contrast_pair` shared between two targets would have to name both and break
    the one-target attachment.

    **The COUNT range permits zero and permits five, and both ends are
    deliberate.** Zero because a unit whose targets suit none of the five kinds
    should produce no diagram and a reported count -- forcing one is the "false"
    half of *fewer rather than false*. Five because the maximum is the unit's own
    target count, which the syllabus permits to reach five; capping lower would
    forbid the output a four-target unit naturally produces.
    """
    out: list[Failure] = []
    low, high = DIAGRAMS_PER_LESSON
    if not low <= len(lesson.diagrams) <= high:
        out.append(
            Failure(
                "diagram_count",
                f"{len(lesson.diagrams)} diagrams; {low}-{high} permitted",
            )
        )

    prose_for = {s.target: section_prose(s) for s in lesson.sections}
    claimed: set[str] = set()

    for spec in lesson.diagrams:
        where = f"{spec.kind} for {spec.target!r}"

        if spec.target not in targets:
            out.append(
                Failure(
                    "diagram_target_not_in_unit",
                    f"{where}: not one of unit {lesson.unit_number}'s targets",
                )
            )
        if spec.target in claimed:
            out.append(
                Failure(
                    "diagram_target_twice",
                    f"{where}: a second diagram on the same target",
                )
            )
        claimed.add(spec.target)

        out.extend(_shape_failures(spec, where))

        # A diagram is generated content, so every string on it is scanned.
        hits = content_offenders(" ".join(str(s) for s in diagram_labels(spec)))
        if hits:
            out.append(Failure("diagram_no_guilt", f"{where}: {', '.join(hits)}"))

        # Every CONTENT CLAIM must appear in the section's own prose: a diagram
        # naming a form the lesson never mentions is a diagram inventing
        # content. `diagram_claims` and not `diagram_labels` -- the wide set
        # includes slot names and callout notes, and requiring those in the
        # prose made `form_build` and `annotated_example` impossible to pass.
        # See `diagram_claims`' docstring; found by running the specimen.
        prose = prose_for.get(spec.target)
        if prose is not None:
            folded = prose.casefold()
            for label in diagram_claims(spec):
                text = str(label).strip()
                if not text:
                    continue
                if not _echoes(text, folded):
                    out.append(
                        Failure(
                            "diagram_label_not_in_prose",
                            f"{where}: {text!r} appears on the diagram and "
                            "nowhere in the section that owns it",
                        )
                    )
    return tuple(out)


def _echoes(label: str, folded_prose: str) -> bool:
    """Is this label's content present in the prose?

    Whole-string containment first, because that is the honest reading. Falling
    back to *every word of the label appears* rather than requiring the exact
    string keeps a legitimate diagram from being rejected for punctuation or word
    order -- a `form_build` slot reads `have/has` where the prose reads *have or
    has*, and rejecting that would be the check being wrong rather than the
    lesson.
    """
    text = label.casefold().strip()
    if text and text in folded_prose:
        return True
    tokens = [t for t in _WORD.findall(text) if len(t) > 2]
    return bool(tokens) and all(t in folded_prose for t in tokens)


def _shape_failures(spec, where: str) -> tuple[Failure, ...]:
    out: list[Failure] = []

    if isinstance(spec, TimelineDiagram):
        low, high = TIMELINE_POINTS
        if not low <= len(spec.points) <= high:
            out.append(
                Failure(
                    "timeline_points",
                    f"{where}: {len(spec.points)} points; {low}-{high} required",
                )
            )
        nows = sum(1 for p in spec.points if p.now)
        if nows != 1:
            out.append(
                Failure(
                    "timeline_now",
                    f"{where}: {nows} points marked now; exactly one required",
                )
            )
        ats = [p.at for p in spec.points]
        if len(set(ats)) != len(ats):
            out.append(
                Failure(
                    "timeline_not_ordered",
                    f"{where}: two points share a position, so the order the "
                    "diagram teaches is undefined",
                )
            )

    elif isinstance(spec, ContrastPairDiagram):
        if spec.first.form.strip() == spec.second.form.strip():
            out.append(
                Failure(
                    "contrast_identical",
                    f"{where}: both sides name the same form, so nothing "
                    "contrasts",
                )
            )

    elif isinstance(spec, FormBuildDiagram):
        low, high = FORM_SLOTS
        if not low <= len(spec.slots) <= high:
            out.append(
                Failure(
                    "form_slots",
                    f"{where}: {len(spec.slots)} slots; {low}-{high} required",
                )
            )

    elif isinstance(spec, DecisionTreeDiagram):
        low, high = BRANCHES
        if not low <= len(spec.branches) <= high:
            out.append(
                Failure(
                    "branch_count",
                    f"{where}: {len(spec.branches)} branches; {low}-{high} "
                    "required",
                )
            )
        answers = [b.answer.strip().casefold() for b in spec.branches]
        if len(set(answers)) != len(answers):
            out.append(
                Failure(
                    "branches_not_distinct",
                    f"{where}: two branches offer the same answer, so the "
                    "choice is not a choice",
                )
            )

    elif isinstance(spec, AnnotatedExampleDiagram):
        low, high = CALLOUTS
        if not low <= len(spec.callouts) <= high:
            out.append(
                Failure(
                    "callout_count",
                    f"{where}: {len(spec.callouts)} callouts; {low}-{high} "
                    "required",
                )
            )
        for callout in spec.callouts:
            if callout.part.casefold() not in spec.sentence.casefold():
                out.append(
                    Failure(
                        "callout_not_in_sentence",
                        f"{where}: callout {callout.part!r} annotates a part "
                        "the sentence does not contain",
                    )
                )

    return tuple(out)


# ── everything, in one call ─────────────────────────────────────────────────


def deterministic_failures(
    lesson: Lesson, targets: Sequence[str]
) -> tuple[Failure, ...]:
    """Every free check. **Runs before a single billed call.**"""
    track = track_for(lesson.unit_number)
    out: list[Failure] = list(bijection_failures(lesson, targets))
    for section in lesson.sections:
        out.extend(section_failures(section, track=track))
    out.extend(diagram_failures(lesson, targets))
    return tuple(out)
