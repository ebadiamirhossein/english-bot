"""The three checks that need a model. C1, C2, C3.

**This and `generate.py` are the only modules in `core.lessons` that reach a
model**, and `tests/test_core_boundary.py::test_lessons_package_is_pure` names
them. That test is a TIGHTENING, not an exemption: without it the package would
be pure by accident rather than by rule, which is verbatim what
`test_cards_package_is_pure`'s docstring says W8a existed to fix.

**All three are blind and PRODUCTIVE, never confirmatory.** W5a's finding, which
this project has now applied to three different questions: a gate asked *"does
this teach the present perfect?"* returns a yes and becomes the rubber stamp the
single-answer solve was. C1 and C2 are handed a candidate list and RANK it; C3 is
asked to LIST contradictions, never to rate the lesson.

**C1 and C2 are `gates.probe_target`'s second and third callers, not a second
implementation.** W10c built the ranking engine and the record ruled that W10b
becomes its caller. What W10b found is that a plain call was impossible --
`probe_target` builds its payload from `visible_projection(item)` and
`item.answer`, and a section is not an item and has no answer -- so W10b split
`probe_ranked` out of it. One implementation of candidate normalisation, the
sorted-not-shuffled rule, invention-dropping and the ranking parse; two payload
shapes and two prompts on top of it.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from core.config import Settings
from core.items import gates as item_gates
from core.items.gates import LLMError, TargetVerdict, probe_ranked

# **One seam, not two.** `_chat` is reached through the module rather than
# imported by name so that monkeypatching `core.items.gates._chat` covers
# everything here -- C1 and C2 through `probe_ranked`, and C3's own call. A
# name-import would have made a test patch one and silently miss the other,
# which is the shape of every "the test passed and the path was dead" finding in
# this record.
from core.lessons.schema import Lesson, Section, diagram_text

#: One list of contradictions over a whole lesson. Longer than a ranking, and
#: still nowhere near a rewrite -- if it needs more than this it is listing
#: rather than finding.
CONTRADICTION_MAX_TOKENS = 1500


def _section_payload(section: Section, diagram: str | None) -> dict:
    """One section as C1 sees it. **The target name is not in it.**

    Everything the learner would read, minus the one field that would hand the
    classifier the answer to its own question. This is `probe_target`'s own
    discipline -- `grammar_target` sits in `projection.NEVER_VISIBLE` for exactly
    this reason -- applied to prose.

    The diagram travels **as text**, which is how a diagram gets model-checked at
    no extra cost: one that teaches a different point from the prose beside it
    fails C1 along with the prose.
    """
    payload = {
        "explanation": section.explanation,
        "when_to_use": section.when_to_use,
        "when_not_to": section.when_not_to,
        "examples": list(section.examples),
        "mistake": {
            "said": section.mistake.said,
            "corrected": section.mistake.corrected,
            "why": section.mistake.why,
        },
    }
    if diagram:
        payload["diagram"] = diagram
    return payload


def on_target(
    section: Section,
    *,
    candidates: Sequence[str],
    diagram: str | None = None,
    settings: Settings | None = None,
) -> TargetVerdict:
    """C1 — does this section teach the target it claims? **Ranked.**

    One call per section. The classifier sees the prose with the target name
    removed and a candidate list of the unit's own targets plus decoys, and
    ranks. **Pass: the claimed target ranks first.**

    **The decoys that matter are the SIBLING targets of the same unit** -- the
    nearest neighbours. Unit 1's four points are all past-tense and are each
    other's closest confusions, so a section on *past continuous* that has slid
    into *past simple* ranks a sibling first and fails. That is what makes this
    catch a drift to an adjacent point rather than only an absurd one.

    **A sibling ranking SECOND is recorded and never failed** (#119). On a
    section that passed, second place is the distinction the prose came closest
    to blurring, and it is the most useful single line for whoever rewrites the
    generator prompt.
    """
    return probe_ranked(
        {"section": _section_payload(section, diagram)},
        claimed=section.target,
        candidates=candidates,
        system="lesson_on_target.txt",
        settings=settings,
    )


def example_demonstrates(
    sentence: str,
    *,
    claimed: str,
    candidates: Sequence[str],
    settings: Settings | None = None,
) -> TargetVerdict:
    """C2 — does this example actually SHOW the structure? **One call each.**

    **Per example, not batched, and for `probe_acceptable`'s exact reason:** this
    asks the model to recover an answer, so a neighbouring sentence from the same
    section would leak it. Three examples of the present perfect in one payload
    make the fourth obvious without the model reading it.

    **The judge receives the sentence alone** -- no label, no target name, no
    section around it. W5c's rule stated as a bar: the judge must receive the
    thing itself, never the claim about it.

    No deterministic grammar detector backs this up, deliberately. Eighty-two
    hand-written structure matchers would be a second grammar engine, and one
    that is wrong is worse than none. Said plainly rather than implied by an
    absent check.
    """
    return probe_ranked(
        {"sentence": sentence},
        claimed=claimed,
        candidates=candidates,
        system="lesson_structure.txt",
        settings=settings,
    )


def contradictions(
    lesson: Lesson, *, settings: Settings | None = None
) -> tuple[str, ...]:
    """C3 — does the lesson contradict itself? **One call over the whole thing.**

    Every section's prose, every example, every wrong example and its correction,
    and each diagram rendered to text. **Asked to LIST contradictions, not to
    rate the lesson** -- a rating is a confirmatory question wearing a number,
    and it would come back reassuring.

    **Pass: the list is empty.** A non-empty list is returned and stored, so the
    regeneration that follows is informed rather than blind.

    This is also the second place a diagram is model-checked: a timeline that
    contradicts the paragraph beside it is a contradiction like any other.
    """
    by_target: dict[str, str] = {
        spec.target: diagram_text(spec) for spec in lesson.diagrams
    }
    payload = {
        "sections": [
            {
                "teaches": section.target,
                **_section_payload(section, by_target.get(section.target)),
            }
            for section in lesson.sections
        ]
    }
    response = item_gates._chat(
        [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        system=item_gates._prompt("lesson_contradiction.txt"),
        json_mode=True,
        max_tokens=CONTRADICTION_MAX_TOKENS,
        reject_truncation=True,
        settings=settings,
    )
    if not isinstance(response, dict):
        raise LLMError("contradiction check did not return an object")

    found = response.get("contradictions") or []
    if not isinstance(found, list):
        raise LLMError(
            f"contradiction check returned {type(found).__name__}, not a list"
        )
    # **C3 carries `teaches` where C1 does not, and that is deliberate.** C1 must
    # not see the target it is classifying; C3 is not classifying anything, and
    # a contradiction between what a section CLAIMS to teach and what it says is
    # exactly one of the things worth finding.
    return tuple(str(one).strip() for one in found if str(one).strip())
