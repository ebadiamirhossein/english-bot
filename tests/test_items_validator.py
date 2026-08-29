"""W5: the validator, proved without a database and without a model.

**Expected verdicts live in the fixture JSON, never computed from the validator
under test** (CLAUDE.md §3 rule 5). In W1 `assert_path_outside_repo` was broken
by a move and its test stayed green because the test derived its fixture from
the same broken function. Here the JSON is the specification: if a check changes
behaviour, the fixture has to be edited by a person who decides the new
behaviour is right.

That already earned itself once. `mcq_duplicate_options` was written expecting
only `duplicate_options`, and the validator also reported
`multiple_correct_options` — correctly, because two options folding to one
string are also two accepted answers. The fixture was wrong, not the code, and
the comparison is what surfaced it.

**W5a's limit on all of it, learned the hard way.** A recorded-response test can
prove a branch is REACHABLE and can never prove a model TAKES it. W5's
`test_the_prd_broken_item_is_rejected_by_the_blind_solver` fed the solver a
hardcoded `{"answer": "I'd"}`, so it asserted *if the solver disagrees, the item
is discarded* — a true statement about the plumbing, and silent on the fact that
the live solver returned `I'll` every time. 1250 green and a permissive live gate
were always consistent. Any gate whose value depends on what a model actually
does needs a live check with a stated polarity, and **that** live check is the
acceptance criterion — not the recorded one. See `core.items.verify`.

No test in this file makes a network call. `tests/conftest.py` installs
`netguard` autouse and session-scoped, so one that tried would raise rather than
spend money — structural, not a promise (CLAUDE.md §5b).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.items import ITEM_TYPES, RESPONSE_MODE, TYPES_WITHOUT_ANSWER
from core.items import gates
from core.items.checks import deterministic_failures
from core.items.grading import normalise_variants
from core.items.schema import parse

FIXTURES = Path(__file__).parent / "fixtures" / "items"


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _item(raw: dict):
    """Fill `accepted_variants` the way the generator path does, then parse."""
    draft = dict(raw)
    if draft.get("answer") is not None and "accepted_variants" not in draft:
        draft["accepted_variants"] = normalise_variants(draft["answer"])
    return parse(draft)


VALID = _load("valid.json")
INVALID = _load("invalid.json")


# ── the fixture set ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("row", VALID, ids=lambda r: r["name"])
def test_every_type_has_a_valid_fixture_that_passes(row) -> None:
    assert deterministic_failures(_item(row["item"])) == ()


def test_every_one_of_the_eleven_types_is_covered() -> None:
    """A type with no fixture is a type nobody has checked.

    Asserted against `ITEM_TYPES` rather than a count, so adding a twelfth type
    fails here until someone writes its fixtures.
    """
    covered = {row["item"]["item_type"] for row in VALID}
    assert covered == set(ITEM_TYPES)


@pytest.mark.parametrize("row", INVALID, ids=lambda r: r["name"])
def test_every_invalid_fixture_fails_for_exactly_the_stated_reasons(row) -> None:
    got = sorted({f.code for f in deterministic_failures(_item(row["item"]))})
    assert got == sorted(row["expect"])


def test_the_invalid_set_covers_every_type() -> None:
    """A type with only a passing fixture has had none of its failures checked."""
    covered = {row["item"]["item_type"] for row in INVALID}
    assert covered == set(ITEM_TYPES)


# ── the item that started the rebuild ───────────────────────────────────────

# PRD §4.3's own example, verbatim. It has its own named test rather than a
# parametrise case so the failure message says which item.
PRD_BROKEN = {
    "item_type": "cloze_cued",
    "track": "work",
    "prompt_text": "Head home if you want — ___ stay and push the deploy.",
    "answer": "I'll",
    "lexeme": "will",
    "definition": "a decision made at this moment",
    "l1_gloss": "من می‌مونم",
}


def test_the_prd_broken_item_survives_the_deterministic_checks() -> None:
    """It is ambiguous, not malformed — and the distinction is the point.

    PRD §4.3: "this is not a prompt-tuning problem; it is a missing validation
    layer." If a deterministic check rejected this item, the recorded reason in
    `items.validation` would send the next person to tune the wrong half of the
    generator prompt.
    """
    assert deterministic_failures(_item(PRD_BROKEN)) == ()


def test_a_multi_acceptable_probe_response_discards_a_slot_item(monkeypatch) -> None:
    """Plumbing: GIVEN more than one class, a slot item is discarded.

    **Named for what it proves.** The response below is a value this test
    chooses, so it establishes the discard branch is reachable and says nothing
    about what a model returns for this item — which is exactly the flaw W5's
    version of this test had while being read as proof the gate worked. The
    property it appears to assert is checked live, in `core.items.verify`.
    """
    monkeypatch.setattr(
        gates, "_chat", _recorded({"acceptable": ["I'll", "I'd", "I can"]})
    )
    result = gates.validate(_item(PRD_BROKEN), judge=False)

    assert result.report.verdict == "discarded"
    assert result.item is None
    assert result.report.blind_solver[0] == "multi_acceptable"


def test_a_repaired_item_is_kept_and_records_its_cue(monkeypatch) -> None:
    """Repair before rejection: a cue that narrows to one class rescues the item.

    PRD §4.3 offers `I'_ _ _` (4) for this very item, so `repaired` is a correct
    outcome and TASKS says "rejected **or** repaired".
    """
    answers = iter([
        {"acceptable": ["I'll", "I'd", "I can"]},
        {"acceptable": ["I'll"]},
    ])

    def chat(*_args, **_kwargs):
        return next(answers)

    monkeypatch.setattr(gates, "_chat", chat)
    result = gates.validate(_item(PRD_BROKEN), judge=False)

    assert result.report.verdict == "repaired"
    assert result.item is not None
    assert result.report.repair_count == 1
    assert result.report.cue_applied in {
        "first_letter_length", "definition", "l1_gloss", "word_bank", "converted_mcq"
    }


# ── the cap ─────────────────────────────────────────────────────────────────


def test_the_retry_cap_is_two_repairs_and_three_solver_calls(monkeypatch) -> None:
    """A gate with an uncapped retry is a cost leak that bills per item.

    Asserted on the call count, not on the verdict: a validator that gave up
    early would also produce `discarded`, and only the count distinguishes
    "capped" from "never tried".
    """
    calls = []

    def chat(*args, **kwargs):
        calls.append(kwargs.get("max_tokens"))
        return {"acceptable": ["I'll", "I'd", "I can"]}

    monkeypatch.setattr(gates, "_chat", chat)
    result = gates.validate(_item(PRD_BROKEN), judge=False)

    assert len(calls) == gates.MAX_REPAIRS + 1 == 3
    assert result.report.solver_calls == 3
    assert result.report.repair_count == gates.MAX_REPAIRS
    # **The assertion is that every probe call uses the SAME budget, which is the
    # property this test is for.** The VALUE moved 400 -> 4000 on 2026-08-29
    # (#265): 400 was chosen at W5a on the reasoning that a longer response is
    # narrating, and that reasoning silently assumed the model emits text first.
    # `claude-sonnet-5` runs adaptive thinking by default and thinking counts
    # against `max_tokens`, so 400 was spent before any text existed. Asserted
    # against the constant and the floor rather than a literal, so the next move
    # does not have to edit a number here too.
    assert set(calls) == {gates.SOLVER_MAX_TOKENS}
    assert gates.SOLVER_MAX_TOKENS >= gates.THINKING_HEADROOM_TOKENS


def test_a_solver_that_agrees_costs_exactly_one_call(monkeypatch) -> None:
    calls = []

    def chat(*args, **kwargs):
        calls.append(1)
        return {"acceptable": ["went"]}

    monkeypatch.setattr(gates, "_chat", chat)
    good = next(r for r in VALID if r["name"] == "cloze_cued")
    result = gates.validate(_item(good["item"]), judge=False)

    assert result.report.verdict == "passed"
    assert len(calls) == 1


def test_a_jargon_item_is_rejected_for_zero_model_calls(monkeypatch) -> None:
    """Cheapest-gate-first, asserted rather than assumed.

    This is the acceptance criterion in TASKS, and the thing it actually buys is
    cost: the mechanical rules run before anything billable.
    """

    def explode(*_args, **_kwargs):  # pragma: no cover - must never run
        raise AssertionError("a mechanical rejection must cost no model call")

    monkeypatch.setattr(gates, "_chat", explode)
    result = gates.validate(
        _item(
            {
                "item_type": "cloze_cued",
                "track": "life",
                "lexeme": "push",
                "prompt_text": "I ___ the deploy before lunch.",
                "answer": "pushed",
            }
        )
    )
    assert result.report.verdict == "discarded"
    assert result.report.naturalness == ("work_jargon",)
    assert result.report.solver_calls == 0


# ── production widens instead of cueing ─────────────────────────────────────


def test_production_widens_its_variants_rather_than_cueing(monkeypatch) -> None:
    """A second correct rendering is a fact about English, not a defect.

    W5 discovered alternatives one per call and could only ever find as many as
    it had attempts left. The probe returns the whole set in **one** call, which
    is both cheaper and more complete — asserted on the call count.
    """
    monkeypatch.setattr(
        gates,
        "_chat",
        _recorded({"acceptable": ["I went to the shop yesterday", "I went shopping yesterday"]}),
    )
    row = next(r for r in VALID if r["name"] == "l1_to_l2_production")
    result = gates.validate(_item(row["item"]), judge=False)

    assert result.report.verdict == "repaired"
    assert result.item is not None
    assert "i went shopping yesterday" in result.item.accepted_variants
    assert result.report.cue_applied is None
    assert result.report.solver_calls == 1


# ── the audio round-trip replaces the solver for the audio types ────────────


def test_dictation_is_gated_by_a_round_trip_and_not_by_a_solver(monkeypatch) -> None:
    row = next(r for r in VALID if r["name"] == "dictation")
    item = _item(row["item"])

    def explode(*_args, **_kwargs):  # pragma: no cover
        raise AssertionError("dictation has no blind solver")

    monkeypatch.setattr(gates, "_chat", explode)
    monkeypatch.setattr(gates, "_synthesize", lambda *a, **k: b"audio")
    monkeypatch.setattr(gates, "_transcribe", lambda *a, **k: item.answer)

    assert gates.validate(item, judge=False).report.verdict == "passed"


def test_a_failed_round_trip_discards_the_item(monkeypatch) -> None:
    """A fail is decisive: if the recogniser cannot hear it, a learner cannot."""
    row = next(r for r in VALID if r["name"] == "dictation")
    monkeypatch.setattr(gates, "_synthesize", lambda *a, **k: b"audio")
    monkeypatch.setattr(gates, "_transcribe", lambda *a, **k: "something else")

    result = gates.validate(_item(row["item"]), judge=False)
    assert result.report.verdict == "discarded"
    assert result.report.blind_solver == ("audio_round_trip_failed",)


def test_listening_gap_requires_the_gapped_word_to_be_heard(monkeypatch) -> None:
    row = next(r for r in VALID if r["name"] == "listening_gap")
    monkeypatch.setattr(gates, "_synthesize", lambda *a, **k: b"audio")
    # The sentence round-trips, but the gapped word itself is not in it.
    monkeypatch.setattr(gates, "_transcribe", lambda *a, **k: "I forgot my this morning")

    result = gates.validate(_item(row["item"]), judge=False)
    assert result.report.verdict == "discarded"


# ── the trichotomy W5 defines ───────────────────────────────────────────────


def test_every_type_declares_a_response_mode() -> None:
    """W6 renders from it, W10 mixes from it, W7's harvest decision reads it."""
    assert set(RESPONSE_MODE) == set(ITEM_TYPES)
    assert set(RESPONSE_MODE.values()) == {"tap", "typed", "spoken"}


def test_only_two_types_lack_an_answer() -> None:
    """Migration 012 encodes the same rule as an equality CHECK."""
    assert TYPES_WITHOUT_ANSWER == {"speak_answer", "match_pairs"}


def _recorded(response: dict):
    def chat(*_args, **_kwargs):
        return response

    return chat


# ── #265: a gate budget must leave room for thinking ───────────────────────


def test_every_gate_budget_leaves_room_for_thinking() -> None:
    """**RED BEFORE THE FIX. The probe budget was entirely consumed by thinking.**

    fill-4's probe returned `stop_reason=max_tokens output_tokens=400 chars=0
    blocks=['ThinkingBlock']`, twice — first attempt and top-up — so `probe_error`
    fired on an item nothing had found fault with.

    **`claude-sonnet-5` runs ADAPTIVE THINKING BY DEFAULT.** `core/llm.py` sets no
    `thinking` parameter anywhere, and on this model omitting it means thinking is
    ON, not off. **Thinking tokens count against `max_tokens`**, so a 400-token
    ceiling is spent before a single text block is emitted.

    `max_tokens` is a CEILING, not a spend: adaptive thinking uses what it needs
    either way, so raising it prevents truncation without materially changing the
    bill. That is why the repair is the ceiling rather than the thinking config —
    and `gates.py`'s own note is why: *"If a gate ever needs a parameter `chat()`
    does not have, the slice stops and says so rather than adding one quietly."*
    Adding `thinking` is exactly that, fires CLAUDE.md §3 rule 2, and is filed
    (#266) rather than smuggled in here.
    """
    from core.items import gates

    for name, value in (
        ("SOLVER_MAX_TOKENS", gates.SOLVER_MAX_TOKENS),
        ("JUDGE_MAX_TOKENS", gates.JUDGE_MAX_TOKENS),
        ("TARGET_MAX_TOKENS", gates.TARGET_MAX_TOKENS),
    ):
        assert value >= gates.THINKING_HEADROOM_TOKENS, (
            f"{name}={value} is below the thinking headroom "
            f"({gates.THINKING_HEADROOM_TOKENS}); a thinking-enabled model can "
            f"consume the whole budget and emit no text block"
        )


def test_the_headroom_constant_is_not_quietly_lowered() -> None:
    """The bar itself, pinned — §3 rule 7's instrument, as `test_the_floor_itself
    _is_not_lowered` is for coverage."""
    from core.items import gates

    assert gates.THINKING_HEADROOM_TOKENS >= 2000


def test_a_thinking_only_truncation_names_its_cause() -> None:
    """**RED BEFORE THE FIX.** The operator had to diagnose this by hand.

    `stop_reason=max_tokens` with content that is entirely `ThinkingBlock`s has
    exactly one cause — the budget was spent thinking — and the error said only
    that the response was truncated. #198 taught this module to keep the blocks;
    this makes it say what they mean.
    """
    from core.llm import _describe_truncation

    assert "thinking" in _describe_truncation(["ThinkingBlock"], 0).lower()
    assert "max_tokens" in _describe_truncation(["ThinkingBlock"], 0)
    # A truncation with real text is a different thing and must not claim this.
    assert "thinking" not in _describe_truncation(["TextBlock"], 812).lower()
