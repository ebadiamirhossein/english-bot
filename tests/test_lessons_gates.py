"""C1, C2 and C3, driven in BOTH directions with the model seam monkeypatched.

**No call in this file reaches a provider.** `tests/conftest.py` installs
`netguard` autouse and session-scoped, so one that tried would raise rather than
spend money -- structural, not a promise.

Every test drives the gate in both directions. A gate exercised only on the
material it accepts passes the catch direction perfectly, which is `verify.py`'s
central finding and the reason the negative control exists at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.items import gates as item_gates
from core.lessons import gates as lesson_gates
from core.lessons.schema import Lesson, Section, parse_lesson

FIXTURES = Path(__file__).parent / "fixtures" / "lessons"

CANDIDATES = [
    "past simple: regular and irregular verbs",
    "past continuous for what was going on around it",
    "past simple and past continuous in the same sentence",
    "time linkers: then, after that, a bit later",
    "for and since with the present perfect",
]


def _specimen() -> Lesson:
    return parse_lesson(json.loads((FIXTURES / "specimen.json").read_text()))


def _control() -> dict:
    return json.loads((FIXTURES / "drifted.json").read_text())


@pytest.fixture
def seam(monkeypatch):
    """Capture what each gate SENDS, and control what it receives."""
    sent: list[dict] = []

    def install(response):
        def fake(messages, *, system, **kwargs):
            sent.append(
                {"payload": json.loads(messages[0]["content"]), "system": system}
            )
            return response(sent[-1]) if callable(response) else response

        monkeypatch.setattr(item_gates, "_chat", fake)
        return sent

    return install


# ── C1 ──────────────────────────────────────────────────────────────────────


def test_c1_passes_when_the_claimed_target_ranks_first(seam) -> None:
    section = _specimen().sections[0]
    seam({"ranking": [section.target, CANDIDATES[1]], "confidence": "high"})
    verdict = lesson_gates.on_target(section, candidates=CANDIDATES)
    assert verdict.ok
    assert verdict.claimed_rank == 1
    assert verdict.runner_up == CANDIDATES[1]


def test_c1_fails_when_a_sibling_ranks_first(seam) -> None:
    """The drift that matters: to a NEIGHBOUR, not to something absurd."""
    section = _specimen().sections[0]
    seam({"ranking": [CANDIDATES[1], section.target], "confidence": "high"})
    verdict = lesson_gates.on_target(section, candidates=CANDIDATES)
    assert not verdict.ok
    assert verdict.claimed_rank == 2
    assert verdict.first == CANDIDATES[1]


def test_c1_is_never_shown_the_target_it_is_classifying(seam) -> None:
    """**The whole discipline, asserted rather than intended.**

    Showing the classifier the target name would hand it the answer to its own
    question and turn C1 into the rubber stamp the single-answer solve was.
    """
    section = _specimen().sections[0]
    sent = seam({"ranking": [section.target], "confidence": "high"})
    lesson_gates.on_target(section, candidates=CANDIDATES)

    payload = sent[0]["payload"]
    assert "target" not in payload["section"]
    blob = json.dumps(payload["section"], ensure_ascii=False)
    assert section.target not in blob


def test_c1_sees_the_diagram_as_text_when_there_is_one(seam) -> None:
    """A diagram teaching a different point fails the same check the prose does."""
    section = _specimen().sections[0]
    sent = seam({"ranking": [section.target], "confidence": "high"})
    lesson_gates.on_target(
        section, candidates=CANDIDATES, diagram="A timeline: yesterday, then now."
    )
    assert sent[0]["payload"]["section"]["diagram"].startswith("A timeline")


def test_c1_uses_its_own_prompt_and_not_the_item_one(seam) -> None:
    """`item_target.txt` reasons about "one language exercise". A section is prose."""
    section = _specimen().sections[0]
    sent = seam({"ranking": [section.target], "confidence": "high"})
    lesson_gates.on_target(section, candidates=CANDIDATES)
    assert "grammar teaching" in sent[0]["system"]
    assert "one language exercise" not in sent[0]["system"]


def test_c1_drops_a_target_the_model_invented(seam) -> None:
    """A model that invents a point has not ranked the list it was given."""
    section = _specimen().sections[0]
    seam({"ranking": ["the subjunctive of regret", section.target], "confidence": "low"})
    verdict = lesson_gates.on_target(section, candidates=CANDIDATES)
    assert verdict.ranking == (section.target,)
    assert verdict.ok


def test_c1_refuses_a_claim_that_is_not_among_the_candidates(seam) -> None:
    """**The archived negative control would have raised here.**

    It claimed a target belonging to no unit in scope, so the gate meant to prove
    C1 discriminates could never have executed -- #213's family, in the control.
    """
    raw = json.loads((FIXTURES / "specimen.json").read_text())
    raw["sections"][0]["target"] = "must and can't for what you're fairly sure of"
    section = Section.model_validate(raw["sections"][0])
    seam({"ranking": [], "confidence": "low"})
    with pytest.raises(ValueError, match="not among the candidates"):
        lesson_gates.on_target(section, candidates=CANDIDATES)


# ── the negative control ────────────────────────────────────────────────────


def test_the_control_is_refused_when_c1_works(seam) -> None:
    control = _control()
    section = Section.model_validate(control["section"])
    seam({"ranking": [control["actually"], control["claims"]], "confidence": "high"})
    verdict = lesson_gates.on_target(section, candidates=control["candidates"])
    assert not verdict.ok, "a working C1 must refuse the drifted control"


def test_the_control_is_accepted_when_c1_is_inert(seam) -> None:
    """The direction that matters: an inert gate PASSES the control.

    That is the whole reason the control exists, and it is asserted so the
    control cannot become decorative.
    """
    control = _control()
    section = Section.model_validate(control["section"])
    seam({"ranking": [control["claims"]], "confidence": "high"})
    verdict = lesson_gates.on_target(section, candidates=control["candidates"])
    assert verdict.ok, "an inert C1 passes the control — this is the failure mode"


# ── C2 ──────────────────────────────────────────────────────────────────────


def test_c2_receives_the_sentence_alone(seam) -> None:
    """**W5c's rule as a bar: the judge receives the thing, never the claim.**

    A neighbouring sentence from the same section would leak the answer, which is
    `probe_acceptable`'s exact reason for not batching.
    """
    section = _specimen().sections[0]
    sent = seam({"ranking": [section.target], "confidence": "high"})
    lesson_gates.example_demonstrates(
        section.examples[0], claimed=section.target, candidates=CANDIDATES
    )
    payload = sent[0]["payload"]
    assert set(payload) == {"sentence", "candidates"}
    assert payload["sentence"] == section.examples[0]
    for other in section.examples[1:]:
        assert other not in json.dumps(payload, ensure_ascii=False)


def test_c2_fails_an_example_that_demonstrates_a_neighbour(seam) -> None:
    section = _specimen().sections[0]
    seam({"ranking": [CANDIDATES[3], section.target], "confidence": "high"})
    verdict = lesson_gates.example_demonstrates(
        section.examples[0], claimed=section.target, candidates=CANDIDATES
    )
    assert not verdict.ok


# ── C3 ──────────────────────────────────────────────────────────────────────


def test_c3_passes_on_an_empty_list(seam) -> None:
    seam({"contradictions": []})
    assert lesson_gates.contradictions(_specimen()) == ()


def test_c3_returns_what_it_found(seam) -> None:
    seam({"contradictions": ["Section 1 says X and its own example does Y."]})
    found = lesson_gates.contradictions(_specimen())
    assert found == ("Section 1 says X and its own example does Y.",)


def test_c3_is_asked_to_list_and_not_to_rate(seam) -> None:
    """A rating is a confirmatory question wearing a number."""
    sent = seam({"contradictions": []})
    lesson_gates.contradictions(_specimen())
    system = sent[0]["system"]
    assert "LIST" in system.upper()
    assert "not rating" in system.lower() or "not a rating" in system.lower()


def test_c3_does_see_what_each_section_claims_to_teach(seam) -> None:
    """**C3 carries `teaches` where C1 does not, and that is deliberate.**

    C1 must not see the target it is classifying. C3 is not classifying anything,
    and a section that claims one thing and says another is exactly one of the
    contradictions worth finding.
    """
    sent = seam({"contradictions": []})
    lesson_gates.contradictions(_specimen())
    sections = sent[0]["payload"]["sections"]
    assert all("teaches" in s for s in sections)


def test_c3_raises_when_the_model_returns_the_wrong_shape(seam) -> None:
    """Fail loudly. A gate that shrugs at a malformed response rejects nothing."""
    seam({"contradictions": "there is one"})
    with pytest.raises(item_gates.LLMError):
        lesson_gates.contradictions(_specimen())


def test_one_seam_covers_all_three_gates(seam) -> None:
    """If C3 held its own `_chat` reference, this would send a real request.

    Asserted because a test that patches one seam and misses another is how a
    green suite comes to cover a dead path.
    """
    sent = seam(lambda s: (
        {"contradictions": []} if "sections" in s["payload"]
        else {"ranking": [CANDIDATES[0]], "confidence": "high"}
    ))
    section = _specimen().sections[0]
    lesson_gates.on_target(section, candidates=CANDIDATES)
    lesson_gates.example_demonstrates(
        section.examples[0], claimed=section.target, candidates=CANDIDATES
    )
    lesson_gates.contradictions(_specimen())
    assert len(sent) == 3
