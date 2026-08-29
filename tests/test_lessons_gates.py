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


# ── a failed gate call must fail the LESSON, not the RUN ────────────────────


def test_a_truncated_gate_response_fails_the_lesson_and_leaves_the_run_alive(
    monkeypatch, tmp_path, capsys
) -> None:
    """**#233. One bad response destroyed a run that had already spent ~38 calls.**

    On 2026-08-28 C3 returned `output_tokens=1500 chars=0
    blocks=['ThinkingBlock']` -- its whole budget spent thinking -- and the
    `LLMError` propagated out of `verify_lesson` into `run` and killed the
    process. No outcome block, no axes, no report, and the attempt in flight was
    never journaled because it was never decided.

    This drives the real `run` loop with a seam that raises exactly that error,
    and asserts three things: the process survives, the attempt is journaled as
    a failure with its reason, and the axis block still prints.
    """
    from core.items import gates as item_gates
    from core.lessons import generate as gen

    def explode(*args, **kwargs):
        raise item_gates.LLMError(
            "response truncated stop_reason=max_tokens output_tokens=1500 chars=0"
        )

    # The generation call succeeds; the first gate call does not.
    monkeypatch.setattr(gen, "generate_lesson", lambda *a, **k: _specimen())
    monkeypatch.setattr(gen.lesson_gates, "on_target", explode)
    monkeypatch.setattr(gen, "coverage_reference", lambda: frozenset({"a"}))
    monkeypatch.setattr(gen, "confirm", lambda *a, **k: True)

    journal = tmp_path / "j.jsonl"
    code = gen.run((1,), apply=False, journal_path=journal, skip_control=True)

    out = capsys.readouterr().out
    assert code == 0, "a gate failure killed the run"
    assert "LLM ERROR in a gate" in out
    assert "The run continues" in out

    # The axis block still printed — the summary of a run already paid for.
    assert "── outcome ─" in out
    assert "0 of 1 lesson(s) SHIPPABLE" in out
    assert "pre-registered axes" in out

    # And every attempt reached disk, with the reason.
    rows = gen.attempts_of(gen.read_journal(journal))
    assert len(rows) == gen.MAX_REGENERATIONS + 1, (
        "the failed attempts were not journaled"
    )
    assert all(r["stage"] == "llm_error" for r in rows)
    assert "truncated" in rows[0]["details"][0]


def test_a_truncated_generation_call_is_also_survivable(
    monkeypatch, tmp_path, capsys
) -> None:
    """The same guarantee one step earlier. W10c's attempt 1 died exactly here."""
    from core.items import gates as item_gates
    from core.lessons import generate as gen

    def explode(*args, **kwargs):
        raise item_gates.LLMError("response truncated stop_reason=max_tokens")

    monkeypatch.setattr(gen, "generate_lesson", explode)
    monkeypatch.setattr(gen, "coverage_reference", lambda: frozenset({"a"}))
    monkeypatch.setattr(gen, "confirm", lambda *a, **k: True)

    journal = tmp_path / "j.jsonl"
    assert gen.run((1,), apply=False, journal_path=journal, skip_control=True) == 0
    out = capsys.readouterr().out
    assert "LLM ERROR at generation" in out
    assert "0 of 1 lesson(s) SHIPPABLE" in out


def test_the_three_lesson_gates_state_their_own_token_budgets(monkeypatch) -> None:
    """**They inherited 400 from the items path, and C3 ran out on thinking.**

    Asserted as numbers rather than as "bigger than the default", so a later
    edit that reverts one to the inherited value fails here.
    """
    from core.lessons import gates as lg

    assert lg.ON_TARGET_MAX_TOKENS == 2000
    assert lg.STRUCTURE_MAX_TOKENS == 1000
    assert lg.CONTRADICTION_MAX_TOKENS == 8000

    seen: list[int] = []

    def capture(messages, *, system, max_tokens, **kwargs):
        seen.append(max_tokens)
        return {"ranking": [CANDIDATES[0]], "confidence": "high",
                "contradictions": []}

    monkeypatch.setattr(item_gates, "_chat", capture)
    section = _specimen().sections[0]
    lesson_gates.on_target(section, candidates=[section.target, *CANDIDATES[1:]])
    lesson_gates.example_demonstrates(
        section.examples[0], claimed=section.target,
        candidates=[section.target, *CANDIDATES[1:]],
    )
    lesson_gates.contradictions(_specimen())
    assert seen == [2000, 1000, 8000], (
        f"a lesson gate is not passing its own budget: {seen}"
    )


def test_the_items_probe_budget_is_above_the_thinking_floor(monkeypatch) -> None:
    """**This test PINNED THE DEFECT IT WAS WRITTEN BESIDE, and that is the point.**

    It read `assert TARGET_MAX_TOKENS == 400` and was called *the split must not
    have moved the items path* — written in the same slice whose own header says
    the lessons gates *silently inherited `core.items.gates.TARGET_MAX_TOKENS =
    400`, a number sized for ranking a short list about one exercise*, after C3
    returned `output_tokens=1500 chars=0 blocks=['ThinkingBlock']`.

    **W10b diagnosed the thinking-budget defect, fixed its own three gates, named
    the items path as carrying the same 400 — and then asserted that 400 was
    unchanged.** The guard was right about its intent (the split must not move the
    items path) and, expressed as a literal, it locked the exposure in. fill-4
    paid for it on 2026-08-29 (#265).

    The intent survives and the instrument changes: the items path must sit above
    the same floor these gates were raised over, and no literal is asserted.
    """
    from core.items.gates import THINKING_HEADROOM_TOKENS, TARGET_MAX_TOKENS

    assert TARGET_MAX_TOKENS >= THINKING_HEADROOM_TOKENS
