"""W5a: the uniqueness gate, after it was found not to test uniqueness.

**What went wrong.** W5's gate asked the model for *its* answer. A correct answer
proves an item is RECOVERABLE. Unmarkability is caused by MULTI-ACCEPTABILITY,
which is a different property — PRD's own broken item returns `I'll` on every
run because `I'll` genuinely is the best completion, while `I can`, `I'm gonna`
and `let me` fit the same slot and a learner typing any of them is marked wrong.

Every test here is recorded-response and therefore proves reachability, not model
behaviour — the limit W5a exists because of. The behaviour is checked live by
`python -m core.items.verify --live`, in both directions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.items import (
    ANSWER_FAMILY,
    ITEM_TYPES,
    MAX_ACCEPTED_VARIANTS,
    PROBED_FAMILIES,
    VALIDATOR_VERSION,
    gates,
)
from core.items.grading import distinct_answers, equivalence_key
from core.items.schema import parse

FIXTURES = Path(__file__).parent / "fixtures" / "items"
PROBE_ONLY = json.loads((FIXTURES / "probe_only.json").read_text(encoding="utf-8"))
VALID = json.loads((FIXTURES / "valid.json").read_text(encoding="utf-8"))


def _item(raw: dict):
    from core.items.grading import normalise_variants

    draft = dict(raw)
    if draft.get("answer") is not None and "accepted_variants" not in draft:
        draft["accepted_variants"] = normalise_variants(draft["answer"])
    return parse(draft)


def _recorded(response: dict):
    def chat(*_args, **_kwargs):
        return response

    return chat


# ── the equivalence key: pure, no DB, no model ──────────────────────────────


def test_a_contraction_is_not_a_second_answer() -> None:
    assert equivalence_key("I'll") == equivalence_key("I will")
    assert equivalence_key("Went.") == equivalence_key("went")


def test_a_different_modal_is_a_second_answer() -> None:
    """The distinction the whole gate turns on."""
    assert equivalence_key("I'll") != equivalence_key("I'd")
    assert len(distinct_answers(["I'll", "I will", "I'd", "I can", "let me"])) == 4


def test_the_key_reuses_the_tokeniser_rather_than_a_second_table() -> None:
    """One notion of sameness. A second contraction table is how they drift."""
    from core.lexicon.normalize import CONTRACTIONS

    for contracted, expansion in list(CONTRACTIONS.items())[:20]:
        if "'" not in contracted:
            continue
        assert equivalence_key(contracted) == equivalence_key(" ".join(expansion))


# ── the fixtures nothing but the probe can catch ────────────────────────────


@pytest.mark.parametrize("row", PROBE_ONLY, ids=lambda r: r["name"])
def test_probe_only_fixtures_are_deterministically_clean(row) -> None:
    """If a deterministic check caught these, they would prove nothing."""
    from core.items.checks import deterministic_failures

    assert deterministic_failures(_item(row["item"])) == ()


@pytest.mark.parametrize("row", PROBE_ONLY, ids=lambda r: r["name"])
def test_the_probe_sees_the_expected_number_of_classes(row) -> None:
    assert len(distinct_answers(row["probe_response"]["acceptable"])) == (
        row["expect_classes"]
    )


@pytest.mark.parametrize("row", PROBE_ONLY, ids=lambda r: r["name"])
def test_each_family_widens_or_rejects_as_its_constant_says(row, monkeypatch) -> None:
    """Plumbing: GIVEN N classes, the family decides widen vs reject."""
    monkeypatch.setattr(gates, "_chat", _recorded(row["probe_response"]))
    item = _item(row["item"])
    result = gates.validate(item, judge=False)

    if row["expect_widened"]:
        assert result.report.verdict == "repaired"
        assert result.item is not None
        assert len(result.item.accepted_variants) > len(item.accepted_variants)
    else:
        assert result.report.verdict == "discarded"
        assert result.item is None


def test_the_prd_item_now_lives_in_the_fixture_set() -> None:
    """It was a Python constant, which is why `grep tests/fixtures` found nothing."""
    assert any(r["name"] == "prd_broken_item" for r in PROBE_ONLY)


# ── families ────────────────────────────────────────────────────────────────


def test_every_type_declares_an_answer_family() -> None:
    assert set(ANSWER_FAMILY) == set(ITEM_TYPES)
    assert set(ANSWER_FAMILY.values()) == {"slot", "message", "fixed_option", "exact"}


def test_only_the_slot_family_is_cue_repairable(monkeypatch) -> None:
    """A cue cannot rescue an item whose authored options are both correct.

    So a fixed-option item costs ONE call to reject, not three.
    """
    calls = []

    def chat(*_a, **_k):
        calls.append(1)
        return {"acceptable": ["have", "take"]}

    monkeypatch.setattr(gates, "_chat", chat)
    row = next(r for r in PROBE_ONLY if r["name"] == "shower_have_take")
    result = gates.validate(_item(row["item"]), judge=False)

    assert result.report.verdict == "discarded"
    assert len(calls) == 1
    assert result.report.cue_applied is None


def test_a_slot_item_is_never_widened(monkeypatch) -> None:
    """Accepting every fitting modal makes the item gradable and worthless.

    That is PRD §4.3 gate 3 failing, not gate 1 passing.
    """
    monkeypatch.setattr(
        gates, "_chat", _recorded({"acceptable": ["I'll", "I'd", "I can"]})
    )
    row = next(r for r in PROBE_ONLY if r["name"] == "prd_broken_item")
    item = _item(row["item"])
    result = gates.validate(item, judge=False)

    assert result.item is None
    assert "widened" not in result.report.blind_solver


def test_a_message_item_over_the_cap_is_under_specified(monkeypatch) -> None:
    """Past a point, many renderings means the L1 prompt is vague."""
    # The canonical must be among them, or `not_recoverable` fires first — the
    # recoverability check runs before the cap, and correctly so: an item whose
    # canonical nobody would accept is unanswerable as authored whatever else
    # came back.
    many = ["I went to the shops"] + [
        f"I went to shop number {n}" for n in range(MAX_ACCEPTED_VARIANTS + 3)
    ]
    monkeypatch.setattr(gates, "_chat", _recorded({"acceptable": many}))
    row = next(r for r in VALID if r["name"] == "l1_to_l2_production")
    result = gates.validate(_item(row["item"]), judge=False)

    assert result.report.verdict == "discarded"
    assert result.report.blind_solver[0] == "under_specified"


# ── recoverability, the W5 property, preserved ──────────────────────────────


def test_an_item_whose_canonical_is_not_offered_is_rejected(monkeypatch) -> None:
    """W5's own failure mode still fires: unanswerable as authored."""
    monkeypatch.setattr(gates, "_chat", _recorded({"acceptable": ["walked"]}))
    row = next(r for r in VALID if r["name"] == "cloze_cued")
    result = gates.validate(_item(row["item"]), judge=False)

    assert result.report.verdict == "discarded"
    assert result.report.blind_solver[0] in {"not_recoverable", "multi_acceptable"}


# ── listening_gap gets a uniqueness gate for the first time ────────────────


def test_listening_gap_runs_the_probe_as_well_as_the_round_trip(monkeypatch) -> None:
    """W5 gated it on audio only.

    The round-trip proved the gapped word was AUDIBLE; nothing proved it was the
    only word that FITS. `"I forgot my ___ this morning"` round-trips perfectly
    and admits wallet, phone, bag and purse.
    """
    row = next(r for r in VALID if r["name"] == "listening_gap")
    item = _item(row["item"])
    monkeypatch.setattr(gates, "_synthesize", lambda *a, **k: b"audio")
    monkeypatch.setattr(gates, "_transcribe", lambda *a, **k: item.transcript)
    monkeypatch.setattr(
        gates, "_chat", _recorded({"acceptable": ["doesn't", "won't"]})
    )

    result = gates.validate(item, judge=False)
    assert result.report.verdict == "discarded", (
        "a clean round-trip must no longer be enough on its own"
    )
    assert result.report.solver_calls >= 1


def test_a_clean_listening_gap_passes_both_gates(monkeypatch) -> None:
    row = next(r for r in VALID if r["name"] == "listening_gap")
    item = _item(row["item"])
    monkeypatch.setattr(gates, "_synthesize", lambda *a, **k: b"audio")
    monkeypatch.setattr(gates, "_transcribe", lambda *a, **k: item.transcript)
    monkeypatch.setattr(gates, "_chat", _recorded({"acceptable": ["doesn't"]}))

    assert gates.validate(item, judge=False).report.verdict == "passed"


# ── the version bump ────────────────────────────────────────────────────────


def test_the_validator_version_records_the_tightened_gate() -> None:
    """W10 filters the bank on this; a version-1 row may be multi-acceptable."""
    assert VALIDATOR_VERSION == 2


def test_probed_families_are_exactly_the_non_exact_ones() -> None:
    probed = {t for t, f in ANSWER_FAMILY.items() if f in PROBED_FAMILIES}
    assert "match_pairs" not in probed
    assert {"cloze_cued", "listening_gap", "collocation_pick"} <= probed
