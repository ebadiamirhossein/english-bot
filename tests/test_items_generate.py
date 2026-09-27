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
from core.items.checks import probe_canonical
from core.items.generate import (
    journal_line,
    ITEMS_PER_UNIT,
    SLOT_TYPES,
    Outcome,
    Slot,
    build_payload,
    coverage_reference,
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


def test_the_slot_plan_drafts_every_type_still_in_the_mix():
    """#168 has waited three slices for evidence about which types serve a
    grammar target. Left to itself a generator writes three `mcq`s and five
    `cloze_cued`s and four types get none, which is why the slot is prescribed.
    """
    plan = slot_plan(1, UNIT_1)
    assert len(plan) == ITEMS_PER_UNIT
    drafted = Counter(slot.item_type for slot in plan)
    assert set(drafted) == set(SLOT_TYPES)


def test_mcq_and_collocation_pick_are_dropped_for_grammar_targets():
    """**#207's ruling, option (c), asserted rather than left in a constant.**

    `checks._options_failures` rejects an option set where one option contains
    another — a guessability rule from W5, written beside `option_length_tell`
    for a bank of vocabulary items whose options are unrelated words. **For a
    grammar target it rejects the distractor set the item must have:**
    `walk / walked / was walking` are substrings of one another because that is
    what testing a verb form means.

    These two types are the ONLY callers of `_options_failures`, so dropping
    them resolves the conflict **without touching the rule** — which is right
    for the population it was written for.
    """
    from core.items.generate import DROPPED_FOR_GRAMMAR

    assert set(DROPPED_FOR_GRAMMAR) == {"mcq", "collocation_pick"}
    assert not set(SLOT_TYPES) & set(DROPPED_FOR_GRAMMAR)


def test_the_doubled_slots_are_the_ones_with_gates_not_the_ones_without():
    """**The distribution is a decision, and the direction matters.**

    `match_pairs` has the FEWEST gates in front of it — its family is `exact`,
    so `_probe_and_repair` never runs and its uniqueness gate is dead code
    (#192) — and it is also the only type `substring_option` cannot reject,
    having no options. **Giving the least-checked type more slots is the wrong
    direction**, so it stays at one. `l1_to_l2_production` stays at one because
    each costs an extra back-translation call and #102 is unresolved.
    """
    drafted = Counter(SLOT_TYPES)
    assert drafted["cloze_cued"] == 2, "the only cue-repairable type gets a repeat"
    assert drafted["match_pairs"] == 1, "the least-gated type must not be doubled"
    assert drafted["l1_to_l2_production"] == 1
    assert drafted["match_pairs"] <= min(
        drafted[t] for t in ("cloze_cued", "word_bank_order", "error_spot")
    )


def test_the_new_mix_raises_168s_per_type_n_for_three_types():
    """#168's sample size, restated after the ruling — **and it still does not
    close.** Three types go from n=3 to n=6 across three units; two stay at 3;
    and the two dropped types now get **n=0**, so this run can produce no yield
    evidence about them at all. Their removal is a STRUCTURAL ruling, not a
    measured one, and the record says so.
    """
    per_unit = Counter(SLOT_TYPES)
    across_three_units = {t: n * 3 for t, n in per_unit.items()}
    assert across_three_units == {
        "cloze_cued": 6, "word_bank_order": 6, "error_spot": 6,
        "match_pairs": 3, "l1_to_l2_production": 3,
    }
    # Far from the 24 per type that #168 closes on.
    assert max(across_three_units.values()) < 24


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


# ── coverage: measured, never enforced ──────────────────────────────────────


def test_the_coverage_reference_is_a_level_not_a_learner():
    """W10c's ruling on #197, and the measurement that produced it.

    The obvious instrument is `services.lexicon.known_lemmas(user_id)`, and it is
    the WRONG one today: it is W4's top-2,000 frequency floor, it is a **strict
    subset** of this reference, and against it every everyday-register probe
    sentence failed the 90% floor — on `dentist`, `landlord`, `neighbour`,
    `umbrella`, `tram`, all of which `item_generate.txt` orders the generator to
    use.
    """
    reference = coverage_reference()
    # The words a 2,000-lemma ledger rejects and a B1 learner plainly knows.
    for lemma in ("dentist", "neighbour", "umbrella", "parcel", "tram"):
        assert lemma in reference, f"{lemma} is not in the B1 reference"
    assert len(reference) > 4000


def test_coverage_is_recorded_on_every_accepted_item(stub_gates):
    """The number exists per item, so P7 is computed from real generated items
    rather than from the twelve sentences someone probed by hand."""
    slots = slot_plan(1, UNIT_1)
    drafts = [_draft(s.index, s.item_type, s.target) for s in slots]
    outcomes = verify_cohort(
        slots, drafts, unit_number=1, candidates=UNIT_1, calls=Counter(),
        reference=coverage_reference(),
    )
    measured = [o for o in outcomes if o.accepted and o.coverage_pct is not None]
    assert measured, "no accepted item carried a coverage number"
    assert all(0 <= o.coverage_pct <= 100 for o in measured)


def test_a_low_coverage_item_is_reported_and_NOT_rejected(stub_gates):
    """**The whole point of the ruling, asserted so it cannot drift into a gate.**

    An item whose sentence sits below the floor is still ACCEPTED, and carries the
    number and the unknown lemmas. If someone later turns this into a rejection
    they will have to delete this test, which is the intended obstacle: at the
    90% floor a twelve-word sentence may carry one unknown word, and 4 of 8
    correctly-written everyday sentences fall below it.
    """
    # `cloze_cued`, at index 0 because `verify_cohort` reads drafts by
    # `slot.index`. Changing an `mcq`'s answer without its options would fail on
    # `answer_not_an_option` and test the wrong thing.
    slots = (Slot(index=0, item_type="cloze_cued", target=UNIT_1[0], cohort="focus"),)
    draft = _draft(0, slots[0].item_type, slots[0].target)
    draft["prompt_text"] = "The landlord ___ the boiler while we were out."
    draft["answer"] = "fixed"
    outcomes = verify_cohort(
        slots, [draft], unit_number=1, candidates=UNIT_1, calls=Counter(),
        reference=coverage_reference(),
    )
    outcome = outcomes[0]
    assert outcome.accepted, "a below-floor item must be reported, not rejected"
    assert outcome.coverage_pct is not None
    assert outcome.coverage_pct < 90
    assert "boiler" in outcome.coverage_unknown


def test_the_floor_itself_is_not_lowered():
    """CLAUDE.md §3 rule 7. The bar is untouched; only its ENFORCEMENT is off,
    and the run reports what it would have cost."""
    from core.items.checks import probe_canonical, COVERAGE_FLOOR

    assert COVERAGE_FLOOR == 0.90


def test_the_dry_run_states_the_floor_is_measured_and_not_enforced(capsys, monkeypatch):
    """A printed absence with no number behind it is what this replaced.

    `learner_l1` is stubbed: user 3 is production's learner and has no row on
    the development database, and since #424 a run for a learner with no row
    raises rather than guessing a language."""
    monkeypatch.setattr("core.items.generate.learner_l1", lambda _uid: "fa")
    dry_run(3, (1,))
    out = capsys.readouterr().out
    assert "MEASURED, NOT ENFORCED" in out
    assert "STRICT SUBSET" in out
    assert "90%" in out


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
            build_payload(number, entry["unit"].can_do, entry["slots"], l1="fa"),
            ensure_ascii=False,
        )
        assert "murphy" not in wire.lower()
        # The real units carry non-null ranges; if they ever stop, this test
        # would pass for the wrong reason.
        assert any(t.murphy_units for t in entry["unit"].grammar_targets)


def test_the_payload_carries_the_target_text_and_the_type_per_slot():
    payload = build_payload(1, "I can tell a friend what I did yesterday.", slot_plan(1, UNIT_1), l1="fa")
    assert [i["item_type"] for i in payload["items"]] == list(SLOT_TYPES)
    assert all(i["grammar_target"] in UNIT_1 for i in payload["items"])
    assert payload["track"] == "life"


# ── the accounting identity ─────────────────────────────────────────────────


def _row(state, stage=None, codes=()):
    """A JOURNAL ROW, because that is what the accounting reads now.

    `Tally.add` takes a row rather than an `Outcome` so the numbers are
    recomputable from disk without re-buying a call — the property the journal
    exists for. A test that fed it an `Outcome` would be exercising a path that
    only works while the process is alive.
    """
    slot = Slot(index=0, item_type="mcq", target=UNIT_1[0], cohort="focus")
    return journal_line(
        Outcome(slot=slot, unit_number=1, state=state, stage=stage, codes=codes)
    )


def test_the_identity_balances():
    """drafted = accepted + discarded + duplicate."""
    tally = tally_of([
        _row("accepted"),
        _row("accepted"),
        _row("duplicate"),
        _row("discarded", "probe", ("multi_acceptable",)),
        _row("discarded", "target", ("ranked_2",)),
    ])
    assert (tally.drafted, tally.accepted, tally.duplicate, tally.discarded) == (5, 2, 1, 2)
    assert tally.balances


def test_discards_are_broken_out_by_stage():
    """A total tells you the yield; the stage tells you which half to fix."""
    tally = tally_of([
        _row("discarded", "judge", ("unnatural",)),
        _row("discarded", "judge", ("unnatural",)),
        _row("discarded", "target", ("ranked_2",)),
    ])
    assert tally.by_stage == Counter({"judge": 2, "target": 1})


def test_a_short_unit_is_reported_short_and_never_padded(capsys):
    """CLAUDE.md §3 rule 7. Six good items beat eight with two bad ones, and the
    criterion is 8 — so the number is reported, not the bar moved."""
    from core.items.generate import _print_tally

    tally = tally_of([_row("accepted")] * 6 + [_row("discarded", "probe")] * 2)
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
        # **`probe_canonical`, not `answer` (#210).** A perfect probe returns
        # what the gate compares against, and for `error_spot` those differ:
        # its `answer` is the wrong TILE and the probe is now asked for the
        # CORRECTION. A stub returning `answer` models the contract as it was
        # BEFORE the ruling, and fails the item for the reason the ruling
        # removed.
        lambda item, **k: {
            "acceptable": [probe_canonical(item)], "confidence": "high",
        },
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


def test_a_non_string_answer_is_refused_as_a_MODEL_failure_not_a_crash(stub_gates):
    """Attempt 3, unit 1 item 2: `'list' object has no attribute 'translate'`.

    `_draft_to_item` normalised variants BEFORE pydantic saw the draft, so an
    `answer` that arrived as an array reached `fold_apostrophes`, which called
    `.translate()` on a list. **Our crash, on our line** — and it was reported as
    `schema_error`, i.e. as the model's fault.

    Now it is refused with a `ValueError` naming the type, which IS a model
    failure and is labelled as one. The contract stops it being sent; this stops
    us crashing on whatever arrives anyway.
    """
    slots = (Slot(index=0, item_type="cloze_cued", target=UNIT_1[0], cohort="focus"),)
    draft = _draft(0, "cloze_cued", UNIT_1[0])
    draft["answer"] = ["was walking", "was going"]
    outcomes = verify_cohort(
        slots, [draft], unit_number=1, candidates=UNIT_1, calls=Counter()
    )
    assert outcomes[0].stage == "generation"
    assert "answer must be a string" in outcomes[0].codes[0]
    assert "got list" in outcomes[0].codes[0]


def test_a_runner_crash_is_not_reported_as_the_models_schema_failure(monkeypatch):
    """**The mislabel, split.** Three classes of our own `AttributeError` were
    filed under `schema_error` alongside genuine pydantic failures, and the bare
    `except Exception`'s comment read *"pydantic ValidationError, ValueError"* —
    **naming a narrower catch than the code performed.**

    A run already paid for must still finish and report, so the crash is caught
    rather than raised — but at its own stage, under its own code, and with a
    traceback in the log, which `schema_error` never carried.
    """
    import core.items.generate as module

    def _boom(*a, **k):
        raise AttributeError("'list' object has no attribute 'translate'")

    monkeypatch.setattr(module, "_draft_to_item", _boom)
    slots = (Slot(index=0, item_type="cloze_cued", target=UNIT_1[0], cohort="focus"),)
    outcomes = verify_cohort(
        slots, [_draft(0, "cloze_cued", UNIT_1[0])],
        unit_number=1, candidates=UNIT_1, calls=Counter(),
    )
    assert outcomes[0].stage == "runner", "a runner bug is still blamed on the model"
    assert outcomes[0].codes[0].startswith("runner_error:")


def test_the_payload_no_longer_sends_a_slot_number_to_be_echoed():
    """Attempt 3's second cause, removed at the source.

    `n` was the runner's own slot index, sent as a per-item key. A model
    mirroring the input shape echoed it back, and `extra="forbid"` rejected every
    item. **Order carries the same information and cannot be echoed.**
    """
    payload = build_payload(1, "can-do", slot_plan(1, UNIT_1), l1="fa")
    assert all("n" not in item for item in payload["items"])
    assert [i["item_type"] for i in payload["items"]] == list(SLOT_TYPES)


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


def test_a_partially_evaluated_axis_is_NOT_COMPARABLE_not_met(capsys):
    """**#201 fixed the zero case and reverted to the old claim at n=1.**

    Attempt 5 drafted 8 items, 1 reached `probe_target`, and P2 printed
    `0 of 8 — MET` — which reads as *eight items were checked and none drifted*
    when one was checked. The `exercised == 0` branch printed NOT EVALUATED and
    then fell through to the band comparison the instant a single item arrived,
    so the fix held at exactly the value where the bug misleads least.

    **Ninth appearance of *a guarantee never evaluated against the thing it
    names*, and the second inside a fix written for the family** — after #198.
    """
    from core.items.generate import ControlResult, journal_line, print_verdicts

    rows = []
    for index in range(8):
        rows.append(journal_line(Outcome(
            slot=Slot(index=index, item_type="mcq", target=UNIT_1[0], cohort="focus"),
            unit_number=1,
            state="accepted" if index == 0 else "discarded",
            stage=None if index == 0 else "deterministic",
            codes=() if index == 0 else ("substring_option",),
        )))
    print_verdicts(rows, ControlResult(runs=3, failures=3, ranks=(None, None, None)))
    out = capsys.readouterr().out

    for axis in ("P2 target drift", "P3 unnatural", "P4 ambiguity"):
        line = next(l for l in out.splitlines() if axis in l)
        assert "NOT COMPARABLE" in line, line
        assert "MET" not in line.replace("NOT COMPARABLE", ""), line
    # Both numbers, so a reader can see the gap rather than infer it.
    assert "0 of 1 EVALUATED (8 drafted)" in out
    # P1 is measured over DRAFTS and is unaffected — it is the accept rate.
    assert "P1 accept rate    : 1 of 8" in out


def test_a_fully_evaluated_axis_still_reports_met(capsys):
    """The partial rule must not swallow the case it was carved out of."""
    from core.items.generate import ControlResult, journal_line, print_verdicts

    rows = [
        journal_line(Outcome(
            slot=Slot(index=i, item_type="mcq", target=UNIT_1[0], cohort="focus"),
            unit_number=1, state="accepted", stage=None,
        ))
        for i in range(4)
    ]
    print_verdicts(rows, ControlResult(runs=3, failures=3, ranks=(None, None, None)))
    out = capsys.readouterr().out
    assert "P2 target drift   : 0 of 4 (all 4 evaluated) — predicted 0-3 — MET" in out


def test_two_of_three_is_acceptable_and_says_so_in_those_words(monkeypatch, capsys):
    """P5's prediction (3 of 3) and P5's bar (2 of 3) are different numbers on
    purpose, and the module prints the distinction rather than quietly preferring
    whichever reading is more comfortable."""
    from core.items.generate import ControlResult, print_verdicts

    print_verdicts([], ControlResult(runs=3, failures=2, ranks=(2, 1, 3)))
    out = capsys.readouterr().out
    assert "prediction NOT MET, run acceptable" in out


# ── the dry run ─────────────────────────────────────────────────────────────


def test_the_dry_run_sends_nothing_and_prints_the_call_ceiling(capsys, monkeypatch):
    """Structurally, not by promise: `netguard` is armed session-wide, so a call
    would raise. What this adds is that the operator can read the exact prompt
    and the exact cost before deciding. (`learner_l1` stubbed: see above.)"""
    monkeypatch.setattr("core.items.generate.learner_l1", lambda _uid: "fa")
    assert dry_run(3, (1, 2, 3)) == 0
    out = capsys.readouterr().out
    assert "nothing was sent and nothing was written" in out
    assert "billed calls" in out
    assert "ZERO TTS and ZERO STT" in out
    # The whole system prompt, so the record can carry it verbatim.
    assert "NEVER ADDRESS THE LEARNER'S PERFORMANCE" in out
    assert "murphy" not in out.lower()
    # **EVERY system prompt the run will send, not just the generator's.**
    # #210's ruling changed what `item_probe.txt` asks for `error_spot`, and the
    # dry run did not show that file — so the one thing that changed could not
    # be read before it was paid for. #202 one step out.
    assert "the CORRECTION" in out, "item_probe.txt is not shown"
    assert "Rank the candidates, best first" in out, "item_target.txt is not shown"
    assert "Reply with ONLY this JSON object" in out


# ── W24a: an EMPTY extra key is dropped, a non-empty one is still refused ───


def _placement_listening_c1() -> dict:
    """The shape the operator's 2026-09-27 run discarded 6 of 6: a C1
    `listening_gap` whose draft carried `item_type_note: None`. The text is
    this file's, not the model's -- the run's drafts are in its journal."""
    return {
        "item_type": "listening_gap",
        "grammar_target": "modal_verb",
        "prompt_text": "She ___ have left already, the lights are off.",
        "answer": "must",
        "transcript": "She must have left already, the lights are off.",
        "explanation": "must have + past participle: a confident guess about the past.",
        "item_type_note": None,
    }


def _placement_slot(item_type: str) -> Slot:
    return Slot(index=0, item_type=item_type, target="modal_verb",
                cohort="placement", error_type="modal_verb")


def test_an_empty_extra_key_no_longer_throws_away_a_listening_item():
    """**W24a, RED BEFORE THE FIX.** `item_type_note: None` cost six billed
    listening C1 items on 2026-09-27 -- `schema_error … Extra inputs are not
    permitted [input_value=None]`. A key that carries nothing loses nothing by
    being dropped, so `extra="forbid"`'s reason (*"shipped without whatever it
    was for"*) does not apply to it."""
    from core.items.generate import _draft_to_item

    item = _draft_to_item(_placement_listening_c1(), _placement_slot("listening_gap"), 0)
    assert item.item_type == "listening_gap"
    assert not hasattr(item, "item_type_note")


def test_an_empty_tiles_list_on_a_cloze_is_dropped_too():
    """**W24a, RED BEFORE THE FIX.** The launch's first sighting:
    `w18-placement-journal.jsonl` line 4, a cloze carrying `tiles: []` --
    `tiles` is `error_spot`'s field, and a cloze has none."""
    from core.items.generate import _draft_to_item

    draft = {
        "item_type": "cloze_cued",
        "prompt_text": "You ___ have told me, I'd have helped.",
        "answer": "could",
        "explanation": "could have: a possibility that did not happen.",
        "tiles": [],
        "hint": "",
        "extra_map": {},
    }
    item = _draft_to_item(draft, _placement_slot("cloze_cued"), 0)
    assert item.item_type == "cloze_cued"


@pytest.mark.parametrize("key, value", [
    ("tiles", ["You", "could", "have"]),
    ("hint", "x"),
    ("l1_gloss_note", "an invented field"),
    ("difficulty", 0),
    ("flag", False),
])
def test_a_non_empty_extra_key_is_still_refused(key, value):
    """The invariant W24a keeps: an invented field WITH something in it fails
    loudly. `0` and `False` are values, not emptiness."""
    from pydantic import ValidationError

    from core.items.generate import _draft_to_item

    draft = {
        "item_type": "cloze_cued",
        "prompt_text": "You ___ have told me, I'd have helped.",
        "answer": "could",
        key: value,
    }
    with pytest.raises(ValidationError):
        _draft_to_item(draft, _placement_slot("cloze_cued"), 0)


def test_the_dropped_names_reach_the_journal(stub_gates):
    """**W24a, RED BEFORE THE FIX.** The drop is recorded by NAME, never by
    value, so a reader of the journal can count how often the model invents a
    key without the run having thrown the item away."""
    slots = (Slot(index=0, item_type="cloze_cued", target=UNIT_1[0], cohort="focus"),)
    draft = _draft(0, "cloze_cued", UNIT_1[0])
    draft["item_type_note"] = None
    draft["tiles"] = []
    outcomes = verify_cohort(
        slots, [draft], unit_number=1, candidates=UNIT_1, calls=Counter()
    )
    assert not any("schema_error" in c for c in outcomes[0].codes), outcomes[0].codes
    line = journal_line(outcomes[0])
    assert line["dropped_empty_extras"] == ["item_type_note", "tiles"]
