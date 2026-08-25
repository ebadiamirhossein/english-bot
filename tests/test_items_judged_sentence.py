"""W5c: the string the naturalness judge is given, and the reason it gives back.

**What went wrong.** `gates.validate` judged `checks.sentence_of(item)`, which
falls through to `prompt_text` for `mcq`, `cloze_cued` and `collocation_pick` —
the **gapped stem** — and returns the joined tiles for `error_spot`, the
sentence **with its deliberate error still in it**. `item_naturalness.txt` asks
whether a real person would say this to a friend, never mentions gaps or
exercises, and instructs rejection of anything *"nobody actually phrases that
way"*. W5b measured the counterfactual: 0/5 natural as shipped and 5/5 filled
for all four types, forty observations with no exception. The judge was right
and the input was wrong (#115).

**Two kinds of test live here and they prove different things.** The
`judged_sentence` tests are pure and prove the string is right. The
`validate(..., judge=True)` tests go through the gate and prove the string
reaches the judge and the verdict reaches the report — a path that had **no
test at all** before this slice, because every `validate` call in the suite
passed `judge=False` (CLAUDE.md §3 rule 4). Neither proves the model accepts
the new string; that is `python -m core.items.judge_observe --live`, human-run
and billed (CLAUDE.md §3 rule 2, §5b).
"""

from __future__ import annotations

import json
from pathlib import Path

from core.items import gates
from core.items.checks import judged_sentence, sentence_of
from core.items.schema import GAP, parse

FIXTURES = Path(__file__).parent / "fixtures" / "items"
VALID = json.loads((FIXTURES / "valid.json").read_text(encoding="utf-8"))

#: The four whose judged string was defective, named rather than derived. A
#: derived set would agree with a `judged_sentence` that stopped filling gaps.
FORMERLY_DEFECTIVE = {"mcq", "cloze_cued", "collocation_pick", "error_spot"}

#: The seven whose sentence is already prose. Named too, and asserted to
#: partition the eleven with the four above, so neither list can rot quietly.
ALREADY_PROSE = {
    "word_bank_order",
    "l1_to_l2_production",
    "dictation",
    "listening_gap",
    "speak_repeat",
    "speak_answer",
    "match_pairs",
}


def _item(raw: dict):
    from core.items.grading import normalise_variants

    draft = dict(raw)
    if draft.get("answer") is not None and "accepted_variants" not in draft:
        draft["accepted_variants"] = normalise_variants(draft["answer"])
    return parse(draft)


def _by_name() -> dict:
    return {row["name"]: _item(row["item"]) for row in VALID}


def _forbidden(*_args, **_kwargs):
    raise AssertionError("no model call may be made here")


# ── the string ──────────────────────────────────────────────────────────────


def test_no_fixture_puts_a_gap_in_front_of_the_judge() -> None:
    """**The acceptance criterion, and the test W5b could not write.**

    W5b left this inverted on purpose: it fails on four fixtures as shipped,
    and an `xfail` would have been quiet bar-lowering. It goes green here or
    the slice has not landed.
    """
    for name, item in _by_name().items():
        assert GAP not in judged_sentence(item), name


def test_error_spot_is_judged_on_its_correction_not_its_error() -> None:
    """`"I goed to the shops"` is what earned `textbook`x3 `stilted`x2.

    Correctly: nobody says it. That is the point of the item and the reason it
    must never be the string the naturalness judge is shown.
    """
    item = _by_name()["error_spot"]
    assert judged_sentence(item) == "I went to the shops"
    assert item.correction in judged_sentence(item)
    assert item.tiles[item.wrong_index] not in judged_sentence(item).split()


def test_the_gap_is_filled_with_the_canonical_answer() -> None:
    by_name = _by_name()
    assert judged_sentence(by_name["mcq"]) == "I went to the shops yesterday."
    assert judged_sentence(by_name["cloze_cued"]) == "I went to the shops yesterday."
    assert (
        judged_sentence(by_name["collocation_pick"])
        == "She took a photo of us at the beach."
    )


def test_it_is_identical_to_sentence_of_for_the_seven_prose_types() -> None:
    """**The change is provably narrow, asserted rather than claimed.**

    Both directions: identical for the seven, different for exactly the four.
    A one-directional assertion would pass for a function that changed
    everything or nothing.
    """
    by_name = _by_name()
    assert ALREADY_PROSE | FORMERLY_DEFECTIVE == set(by_name)
    assert not (ALREADY_PROSE & FORMERLY_DEFECTIVE)

    for name in ALREADY_PROSE:
        assert judged_sentence(by_name[name]) == sentence_of(by_name[name]), name

    differ = {n for n, i in by_name.items() if judged_sentence(i) != sentence_of(i)}
    assert differ == FORMERLY_DEFECTIVE


def test_match_pairs_still_has_nothing_to_judge() -> None:
    """A mapping has no sentence, so the gate skips the call entirely."""
    assert judged_sentence(_by_name()["match_pairs"]) == ""


def test_it_is_deterministic_and_costs_no_model_call(monkeypatch) -> None:
    """W5b's arm B was built this way deliberately.

    A model call inside the thing that decides adds a second source of
    ambiguity to a gate about ambiguity, and an unfalsifiable gate is worse
    than no gate.
    """
    monkeypatch.setattr(gates, "_chat", _forbidden)
    for item in _by_name().values():
        assert judged_sentence(item) == judged_sentence(item)


# ── through the gate ────────────────────────────────────────────────────────


def _probe_stub(response: dict):
    def chat(*_args, **_kwargs):
        return response

    return chat


def _judge_only(verdicts: dict | None, *, probe: dict | None = None):
    """Dispatch on the system prompt, so one stub serves both model gates."""
    calls: list[str] = []

    def chat(messages, *, system, **_kwargs):
        calls.append(messages[0]["content"])
        if "AMBIGUITY" in system:
            return probe or {"acceptable": [], "confidence": "low"}
        if "sentences" in system:
            return verdicts
        raise AssertionError("unrecognised system prompt")

    chat.calls = calls  # type: ignore[attr-defined]
    return chat


def test_an_unnatural_verdict_discards_and_records_its_reason(monkeypatch) -> None:
    """#119: the model was asked why, said why, and the answer was dropped.

    One `high` issue and one whole slice were spent recovering a word the gate
    already had in hand.
    """
    row = next(r for r in VALID if r["name"] == "cloze_cued")
    stub = _judge_only({"verdicts": [{"n": 1, "natural": False, "reason": "stilted"}]})
    monkeypatch.setattr(gates, "_chat", stub)

    report = gates.validate(_item(row["item"]), judge=True).report
    assert report.verdict == "discarded"
    assert report.naturalness == ("unnatural",)
    assert report.naturalness_reason == "stilted"
    assert report.as_json()["naturalness_reason"] == "stilted"


def test_a_natural_verdict_does_not_discard(monkeypatch) -> None:
    """The other direction, or the test above would pass on a dead gate.

    It also pins the truthiness trap: `judge_naturalness` returns a dataclass
    now, and a dataclass is always truthy, so a call site reading the object
    instead of `.natural` would reject nothing and show no symptom.
    """
    row = next(r for r in VALID if r["name"] == "cloze_cued")
    stub = _judge_only(
        {"verdicts": [{"n": 1, "natural": True, "reason": "ok"}]},
        probe={"acceptable": ["went"], "confidence": "high"},
    )
    monkeypatch.setattr(gates, "_chat", stub)

    report = gates.validate(_item(row["item"]), judge=True).report
    assert report.verdict == "passed"
    assert report.naturalness == ()
    assert report.naturalness_reason is None


def test_the_judge_receives_prose_not_the_stem(monkeypatch) -> None:
    """Asserted at the seam: what actually went out on the wire.

    A test over `judged_sentence` alone proves the string exists. This proves
    `validate` is the thing that sends it — the distinction that let #115 sit
    behind ~1,340 green tests.
    """
    row = next(r for r in VALID if r["name"] == "cloze_cued")
    stub = _judge_only(
        {"verdicts": [{"n": 1, "natural": True, "reason": "ok"}]},
        probe={"acceptable": ["went"], "confidence": "high"},
    )
    monkeypatch.setattr(gates, "_chat", stub)
    gates.validate(_item(row["item"]), judge=True)

    sent = stub.calls[0]  # type: ignore[attr-defined]
    assert GAP not in sent
    assert "I went to the shops yesterday." in sent


def test_a_missing_row_still_fails_open_and_says_so(monkeypatch) -> None:
    """Unchanged behaviour, newly diagnosable.

    Failing an item because a model omitted a row would reject good content for
    a transport reason. It still does not — but the record now distinguishes
    "the judge said ok" from "the judge said nothing".
    """
    row = next(r for r in VALID if r["name"] == "cloze_cued")
    stub = _judge_only(
        {"verdicts": []}, probe={"acceptable": ["went"], "confidence": "high"}
    )
    monkeypatch.setattr(gates, "_chat", stub)

    report = gates.validate(_item(row["item"]), judge=True).report
    assert report.verdict == "passed"
    assert report.naturalness_reason is None  # only a REJECTION records one

    verdict = gates.judge_naturalness(["anything"], settings=None)[0]
    assert (verdict.natural, verdict.reason) == (True, gates.MISSING_ROW)


def test_the_probe_confidence_reaches_the_report(monkeypatch) -> None:
    """#119's other half: `item_probe.txt` asks for it and nothing read it.

    *"Low confidence is a signal about the exercise, not about you."* Stored on
    both a passing and a discarding path, under the same "from the LAST probe
    call" convention `acceptable` already uses.
    """
    row = next(r for r in VALID if r["name"] == "cloze_cued")

    monkeypatch.setattr(
        gates, "_chat", _probe_stub({"acceptable": ["went"], "confidence": "high"})
    )
    passed = gates.validate(_item(row["item"]), judge=False).report
    assert passed.verdict == "passed"
    assert passed.probe_confidence == "high"
    assert passed.as_json()["probe_confidence"] == "high"

    monkeypatch.setattr(
        gates,
        "_chat",
        _probe_stub({"acceptable": ["went", "walked"], "confidence": "low"}),
    )
    rejected = gates.validate(_item(row["item"]), judge=False).report
    assert rejected.verdict == "discarded"
    assert rejected.probe_confidence == "low"


def test_a_probe_that_omits_confidence_records_none(monkeypatch) -> None:
    """Absent is absent. An invented default would misreport the evidence."""
    row = next(r for r in VALID if r["name"] == "cloze_cued")
    monkeypatch.setattr(gates, "_chat", _probe_stub({"acceptable": ["went"]}))

    report = gates.validate(_item(row["item"]), judge=False).report
    assert report.verdict == "passed"
    assert report.probe_confidence is None
