"""`core.items.generate` — the human-run generator, without spending anything.

**The user action:** an operator running the command, reading 24 items, and
deciding whether they may reach a learner. Every test here drives the module's
own functions rather than reimplementing what they do, and `netguard` is armed
session-wide by `tests/conftest.py`, so anything that reached a provider would
raise instead of billing.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from core.items import gates
from core.items.generate import (
    ITEMS_PER_UNIT,
    SLOT_TYPES,
    Outcome,
    Slot,
    build_payload,
    dry_run,
    load_control,
    run_control,
    slot_plan,
    tally_of,
    track_for,
    unit_plan,
    verify_cohort,
)
from core.items.schema import parse

UNIT_1 = (
    "past simple: regular and irregular verbs",
    "past continuous for what was going on around it",
    "past simple and past continuous in the same sentence",
    "time linkers: then, after that, a bit later",
)


# ── the plan ────────────────────────────────────────────────────────────────


def test_every_permitted_type_is_drafted_so_168_gets_a_number_for_each():
    """#168 has waited three slices for evidence about which types serve a
    grammar target. Left to itself a generator writes three `mcq`s and five
    `cloze_cued`s and four types get none, which is why the slot is prescribed.
    """
    plan = slot_plan(1, UNIT_1)
    assert len(plan) == ITEMS_PER_UNIT
    drafted = Counter(slot.item_type for slot in plan)
    assert set(drafted) == set(SLOT_TYPES)
    assert drafted["cloze_cued"] == 2, "the slot family's only type gets the repeat"


def test_the_type_target_pairing_rotates_between_units():
    """Otherwise `mcq` lands on the FIRST target in every unit, and the
    `type x target` cross-tabulation carries three cells that are all the same
    position — which is the confound the table exists to expose, baked in."""
    first_target_of_mcq = {
        unit: slot_plan(unit, UNIT_1)[0].target for unit in (1, 2, 3)
    }
    assert len(set(first_target_of_mcq.values())) == 3


def test_the_plan_is_identical_on_every_run():
    """Deterministic, not shuffled: a random plan makes the numbers unrepeatable
    and a re-run of a billed command a different experiment."""
    assert all(slot_plan(2, UNIT_1) == slot_plan(2, UNIT_1) for _ in range(5))


def test_units_one_to_three_are_life_track():
    """#161: the only units with a real topic are 18-21. A constant, not a
    `topic` column on `syllabus_units`, which #161 ruled out."""
    assert [track_for(n) for n in (1, 2, 3)] == ["life"] * 3
    assert track_for(20) == "work"


def test_the_real_syllabus_permits_every_type_this_run_drafts():
    """The blueprint is authoritative about which types a unit's items may use.
    Generating one it does not permit would put an item in the bank that the
    unit's own checkpoint could never draw."""
    plan = unit_plan((1, 2, 3))
    for number, entry in plan.items():
        permitted = set(entry["unit"].checkpoint["item_types"])
        assert set(SLOT_TYPES) <= permitted, f"unit {number}"


def test_no_audio_type_is_drafted_so_nothing_bills_tts_or_stt():
    """`gates._audio_gate` bills two providers. Units 1-3 permit no audio type,
    and this asserts the run cannot reach it rather than trusting the blueprint."""
    from core.items import TYPES_WITH_AUDIO

    assert not set(SLOT_TYPES) & TYPES_WITH_AUDIO
    assert "speak_answer" not in SLOT_TYPES


# ── the payload ─────────────────────────────────────────────────────────────


def test_the_generator_is_never_given_a_murphy_citation():
    """#171's constraint at the seam where it matters most.

    A rendered citation is visible and removable; an assumption embedded in a
    generated sentence is neither. `tests/test_no_murphy_reaches_a_learner.py`
    carries the same assertion — this one is here so the generator's own suite
    fails too if the strip is ever bypassed.
    """
    plan = unit_plan((1, 2, 3))
    for number, entry in plan.items():
        wire = json.dumps(
            build_payload(number, entry["unit"].can_do, entry["slots"]),
            ensure_ascii=False,
        )
        assert "murphy" not in wire.lower()
        # The real units carry non-null ranges; if they ever stop, this test
        # would pass for the wrong reason.
        assert any(t.murphy_units for t in entry["unit"].grammar_targets)


def test_the_payload_carries_the_target_text_and_the_type_per_slot():
    payload = build_payload(1, "I can tell a friend what I did yesterday.", slot_plan(1, UNIT_1))
    assert [i["item_type"] for i in payload["items"]] == list(SLOT_TYPES)
    assert all(i["grammar_target"] in UNIT_1 for i in payload["items"])
    assert payload["track"] == "life"


# ── the accounting identity ─────────────────────────────────────────────────


def _outcome(state, stage=None, codes=()):
    slot = Slot(index=0, item_type="mcq", target=UNIT_1[0])
    return Outcome(slot=slot, unit_number=1, state=state, stage=stage, codes=codes)


def test_the_identity_balances():
    """drafted = accepted + discarded + duplicate."""
    tally = tally_of([
        _outcome("accepted"),
        _outcome("accepted"),
        _outcome("duplicate"),
        _outcome("discarded", "probe", ("multi_acceptable",)),
        _outcome("discarded", "target", ("ranked_2",)),
    ])
    assert (tally.drafted, tally.accepted, tally.duplicate, tally.discarded) == (5, 2, 1, 2)
    assert tally.balances


def test_discards_are_broken_out_by_stage():
    """A total tells you the yield; the stage tells you which half to fix."""
    tally = tally_of([
        _outcome("discarded", "judge", ("unnatural",)),
        _outcome("discarded", "judge", ("unnatural",)),
        _outcome("discarded", "target", ("ranked_2",)),
    ])
    assert tally.by_stage == Counter({"judge": 2, "target": 1})


def test_a_short_unit_is_reported_short_and_never_padded(capsys):
    """CLAUDE.md §3 rule 7. Six good items beat eight with two bad ones, and the
    criterion is 8 — so the number is reported, not the bar moved."""
    from core.items.generate import _print_tally

    tally = tally_of([_outcome("accepted")] * 6 + [_outcome("discarded", "probe")] * 2)
    _print_tally("unit 1", tally, target=ITEMS_PER_UNIT)
    out = capsys.readouterr().out
    assert "6/8" in out
    assert "SHORT BY 2" in out


def test_an_identity_that_does_not_balance_is_printed_as_a_finding(capsys):
    """Reported rather than asserted: a crash here would destroy the evidence of
    a run that has already been paid for."""
    from core.items.generate import Tally, _print_tally

    broken = Tally(drafted=8, accepted=3, discarded=2, duplicate=0)
    assert not broken.balances
    _print_tally("unit 1", broken, target=ITEMS_PER_UNIT)
    assert "FINDING" in capsys.readouterr().out


# ── the cohort, with every model call stubbed ───────────────────────────────


def _draft(n, item_type, target):
    """A well-formed draft of each type, as the generator would return it.

    Per type rather than one shape with extras bolted on: `extra="forbid"` and
    the per-type checks in `core.items.checks` are exactly what a real generator
    has to satisfy, and a fixture that dodges them would make this whole file
    assert over items that could never ship (#115's second branch).
    """
    base = {
        "item_type": item_type,
        "grammar_target": target,
        "explanation": "Past simple, because the time is finished.",
        "definition": "past of go",
        "l1_gloss": "رفتم",
    }
    if item_type == "mcq":
        base |= {
            "prompt_text": f"I ___ there {n} times last year.",
            "answer": "went",
            "options": ["went", "goed", "gone", "going"],
        }
    elif item_type == "cloze_cued":
        base |= {
            "prompt_text": f"I ___ there {n} times last year.",
            "answer": "went",
        }
    elif item_type == "collocation_pick":
        base |= {
            "prompt_text": f"We ___ a taxi home after the {n}th round.",
            "answer": "caught",
            "options": ["caught", "grabbed", "seized", "captured"],
        }
    elif item_type == "word_bank_order":
        base |= {
            "prompt_text": "Put these in order.",
            "answer": "I went there twice last year",
            "bank": ["last", "there", "I", "twice", "went", "year"],
        }
    elif item_type == "error_spot":
        base |= {
            "prompt_text": "Tap the word that is wrong.",
            "answer": "goed",
            "tiles": ["I", "goed", "there", "twice", "last", "year"],
            "wrong_index": 1,
            "correction": "went",
        }
    elif item_type == "match_pairs":
        base |= {
            "prompt_text": "Match each one to its meaning.",
            "answer": None,
            # 3-6 pairs; two is a `pair_count` failure.
            "pairs": [
                ["went", "past of go"],
                ["saw", "past of see"],
                ["took", "past of take"],
            ],
        }
    elif item_type == "l1_to_l2_production":
        base |= {
            "prompt_text": "من دیروز به مغازه رفتم",
            "answer": "I went to the shop yesterday",
            "accepted_variants": [
                "i went to the shop yesterday",
                "yesterday i went to the shop",
            ],
        }
    else:  # pragma: no cover - the slot table has no other types
        raise AssertionError(f"no draft shape for {item_type}")
    return base


@pytest.fixture
def stub_gates(monkeypatch):
    monkeypatch.setattr(
        gates, "judge_naturalness",
        lambda sentences, **k: tuple(
            gates.NaturalnessVerdict(True, "ok") for _ in sentences
        ),
    )
    monkeypatch.setattr(
        gates, "probe_acceptable",
        lambda item, **k: {"acceptable": [item.answer], "confidence": "high"},
    )
    monkeypatch.setattr(
        gates, "probe_target",
        lambda item, *, claimed, candidates, settings=None: gates.TargetVerdict(
            ranking=(claimed,), claimed_rank=1, first=claimed,
            runner_up=None, confidence="high",
        ),
    )
    # Stubbed too, and not because it is cheap to forget: unstubbed it reaches
    # `core.llm`, which retries three times before `netguard` finally wins, and
    # a 21-second unit test is how a suite stops being run.
    monkeypatch.setattr(gates, "back_translate", lambda item, **k: "بازگردانی")


def test_a_clean_cohort_accepts_and_binds_every_item_to_its_target(stub_gates):
    slots = slot_plan(1, UNIT_1)
    drafts = [_draft(s.index, s.item_type, s.target) for s in slots]
    outcomes = verify_cohort(
        slots, drafts, unit_number=1, candidates=UNIT_1, calls=Counter()
    )
    accepted = [o for o in outcomes if o.accepted]
    assert len(accepted) == ITEMS_PER_UNIT
    for outcome in accepted:
        assert outcome.item is not None
        assert outcome.item.grammar_target == outcome.slot.target
        assert outcome.item.unit_number == 1


def test_a_model_that_writes_to_a_different_target_is_caught_for_free(stub_gates):
    """The echo is compared, not overwritten silently.

    Overwriting `grammar_target` with the authoritative value is right — a
    generator does not get to reassign an item's unit — but doing it WITHOUT
    comparing first would destroy the evidence that the model disagreed, which is
    P2's failure arriving one stage earlier and for no calls at all.
    """
    slots = slot_plan(1, UNIT_1)
    drafts = [_draft(s.index, s.item_type, s.target) for s in slots]
    drafts[0]["grammar_target"] = "something else entirely"
    outcomes = verify_cohort(
        slots, drafts, unit_number=1, candidates=UNIT_1, calls=Counter()
    )
    assert outcomes[0].stage == "generation"
    assert outcomes[0].codes == ("target_echo_mismatch",)


def test_the_cohort_pays_one_naturalness_call_not_eight(stub_gates, monkeypatch):
    """#120, measured. `JUDGE_BATCH` has been declared since W5 and uncalled."""
    calls: list[int] = []
    monkeypatch.setattr(
        gates, "judge_naturalness",
        lambda sentences, **k: (
            calls.append(len(sentences))
            or tuple(gates.NaturalnessVerdict(True, "ok") for _ in sentences)
        ),
    )
    slots = slot_plan(1, UNIT_1)
    drafts = [_draft(s.index, s.item_type, s.target) for s in slots]
    spent: Counter = Counter()
    verify_cohort(slots, drafts, unit_number=1, candidates=UNIT_1, calls=spent)
    assert len(calls) == 1
    assert spent["naturalness"] == 1


def test_a_target_drift_is_discarded_and_keeps_its_diagnostics(monkeypatch, stub_gates):
    """A rejected item still has to say WHY — that is the run's whole value."""
    monkeypatch.setattr(
        gates, "probe_target",
        lambda item, *, claimed, candidates, settings=None: gates.TargetVerdict(
            ranking=(UNIT_1[1], claimed), claimed_rank=2, first=UNIT_1[1],
            runner_up=claimed, confidence="high",
        ),
    )
    slots = slot_plan(1, UNIT_1)[:1]
    drafts = [_draft(0, slots[0].item_type, slots[0].target)]
    outcomes = verify_cohort(
        slots, drafts, unit_number=1, candidates=UNIT_1, calls=Counter()
    )
    assert outcomes[0].stage == "target"
    assert outcomes[0].target is not None, "the verdict was thrown away"
    assert outcomes[0].target.first == UNIT_1[1]
    assert outcomes[0].item is not None, "the item was thrown away"


def test_a_guilty_draft_never_reaches_a_billed_gate(monkeypatch):
    """#110, and the ordering matters as much as the rule: the free stages run
    first, so a guilty item costs nothing to reject."""
    def _boom(*a, **k):  # pragma: no cover
        raise AssertionError("a billed gate ran on an item the free gates refuse")

    monkeypatch.setattr(gates, "judge_naturalness", _boom)
    monkeypatch.setattr(gates, "probe_acceptable", _boom)
    monkeypatch.setattr(gates, "probe_target", _boom)

    slots = slot_plan(1, UNIT_1)[:1]
    draft = _draft(0, slots[0].item_type, slots[0].target)
    draft["explanation"] = "You failed that one — try harder."
    outcomes = verify_cohort(
        slots, [draft], unit_number=1, candidates=UNIT_1, calls=Counter()
    )
    assert outcomes[0].stage == "deterministic"
    assert "guilt_phrase" in outcomes[0].codes


def test_a_missing_draft_is_a_discard_and_not_a_crash(stub_gates):
    """A model that returns six items for eight slots must not take the run down
    after it has already been paid for."""
    slots = slot_plan(1, UNIT_1)
    drafts = [_draft(s.index, s.item_type, s.target) for s in slots[:6]]
    outcomes = verify_cohort(
        slots, drafts, unit_number=1, candidates=UNIT_1, calls=Counter()
    )
    assert len(outcomes) == ITEMS_PER_UNIT
    assert [o.codes for o in outcomes[6:]] == [("missing_draft",)] * 2


# ── the negative control ────────────────────────────────────────────────────


def test_the_control_fixture_claims_one_target_and_tests_another():
    """`verify.py`'s lesson: a check that rejects nothing passes the catch
    direction perfectly. `probe_target` is the one gate here that could be inert
    and still look like it works."""
    fixture = load_control()
    assert fixture["claims"] != fixture["actually"]
    assert fixture["item"]["grammar_target"] == fixture["claims"]
    assert fixture["claims"] in fixture["candidates"]
    assert fixture["actually"] in fixture["candidates"]
    parse(dict(fixture["item"]))


def test_the_control_drifts_to_a_sibling_not_to_something_absurd():
    """A control that is easy to refuse proves nothing about a check that has to
    tell neighbouring points apart."""
    from core.syllabus.content import units

    unit_3 = {t.target for t in units()[2].grammar_targets}
    fixture = load_control()
    assert {fixture["claims"], fixture["actually"]} <= unit_3


def test_an_inert_check_voids_the_run(monkeypatch):
    monkeypatch.setattr(
        gates, "probe_target",
        lambda item, *, claimed, candidates, settings=None: gates.TargetVerdict(
            ranking=(claimed,), claimed_rank=1, first=claimed,
            runner_up=None, confidence="high",
        ),
    )
    result = run_control()
    assert result.failures == 0
    assert not result.ok, "an inert probe_target must void the run"


def test_a_working_check_passes_the_control(monkeypatch):
    monkeypatch.setattr(
        gates, "probe_target",
        lambda item, *, claimed, candidates, settings=None: gates.TargetVerdict(
            ranking=("used to for habits that have stopped", claimed),
            claimed_rank=2, first="used to for habits that have stopped",
            runner_up=claimed, confidence="high",
        ),
    )
    result = run_control()
    assert result.failures == 3
    assert result.ok


def test_two_of_three_is_acceptable_and_says_so_in_those_words(monkeypatch, capsys):
    """P5's prediction (3 of 3) and P5's bar (2 of 3) are different numbers on
    purpose, and the module prints the distinction rather than quietly preferring
    whichever reading is more comfortable."""
    from core.items.generate import ControlResult, print_verdicts

    print_verdicts([], ControlResult(runs=3, failures=2, ranks=(2, 1, 3)))
    out = capsys.readouterr().out
    assert "prediction NOT MET, run acceptable" in out


# ── the dry run ─────────────────────────────────────────────────────────────


def test_the_dry_run_sends_nothing_and_prints_the_call_ceiling(capsys):
    """Structurally, not by promise: `netguard` is armed session-wide, so a call
    would raise. What this adds is that the operator can read the exact prompt
    and the exact cost before deciding."""
    assert dry_run(3, (1, 2, 3)) == 0
    out = capsys.readouterr().out
    assert "nothing was sent and nothing was written" in out
    assert "billed calls" in out
    assert "ZERO TTS and ZERO STT" in out
    # The whole system prompt, so the record can carry it verbatim.
    assert "NEVER ADDRESS THE LEARNER'S PERFORMANCE" in out
    assert "murphy" not in out.lower()
