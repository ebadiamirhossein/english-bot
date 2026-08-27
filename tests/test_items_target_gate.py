"""`gates.probe_target` — the gate that asks what nothing else in the seam asks.

**The user action these exercise:** a learner opening block 3 and answering one
of the eight items. Every other gate in `core.items` establishes that the item is
well-formed, unambiguous and natural; not one of them establishes that it tests
the grammar target the app has just told the learner it is practising. An item
that has drifted to a neighbouring point is scored, and the learner is marked
wrong on something the app never claimed to be teaching.

No call is made here. `tests/conftest.py` arms `netguard` session-wide, so a test
that reached a provider would raise rather than spend money; `gates._chat` is the
module-level seam and is what these patch.
"""

from __future__ import annotations

import json

import pytest

from core.items import gates
from core.items.generate import target_candidates
from core.items.schema import parse

UNIT_3 = (
    "for and since with the present perfect",
    "present perfect continuous: how long you've been doing it",
    "used to for habits that have stopped",
)


def _item(**over):
    draft = {
        "item_type": "cloze_cued",
        "track": "life",
        "prompt_text": "I ___ smoke, but I gave up two years ago.",
        "answer": "used to",
        "accepted_variants": ["used to"],
        "unit_number": 3,
        "grammar_target": "used to for habits that have stopped",
    }
    draft.update(over)
    return parse(draft)


@pytest.fixture
def recorded(monkeypatch):
    """Patch `gates._chat` and keep what it was sent, so both halves are testable."""
    sent: dict = {}

    def install(ranking, confidence="high"):
        def _chat(messages, **kwargs):
            sent["messages"] = messages
            sent["system"] = kwargs.get("system")
            sent["payload"] = json.loads(messages[0]["content"])
            return {"ranking": list(ranking), "confidence": confidence}

        monkeypatch.setattr(gates, "_chat", _chat)
        return sent

    return install


def test_the_claimed_target_ranking_first_passes(recorded):
    recorded([UNIT_3[2], UNIT_3[0]])
    verdict = gates.probe_target(
        _item(), claimed=UNIT_3[2], candidates=UNIT_3
    )
    assert verdict.ok
    assert verdict.claimed_rank == 1
    assert verdict.first == UNIT_3[2]


def test_a_sibling_ranking_first_fails(recorded):
    """The drift this gate exists for: a neighbouring point, not an absurd one."""
    recorded([UNIT_3[0], UNIT_3[2]])
    verdict = gates.probe_target(
        _item(), claimed=UNIT_3[2], candidates=UNIT_3
    )
    assert not verdict.ok
    assert verdict.claimed_rank == 2
    assert verdict.first == UNIT_3[0]


def test_a_sibling_ranking_second_is_recorded_and_does_not_fail(recorded):
    """#119: the diagnostic the gate already has is kept, not dropped.

    When the claimed target wins, the runner-up is the distinction the item came
    closest to blurring — the single most useful line for whoever rewrites the
    generator prompt. `judge_naturalness` parsed its `reason` and discarded it one
    line later, and recovering it cost the whole of W5b.
    """
    recorded([UNIT_3[2], UNIT_3[1]])
    verdict = gates.probe_target(
        _item(), claimed=UNIT_3[2], candidates=UNIT_3
    )
    assert verdict.ok
    assert verdict.runner_up == UNIT_3[1]


def test_the_target_name_is_never_shown_to_the_classifier(recorded):
    """The gate cannot be handed the answer to its own question.

    `grammar_target` is in `projection.NEVER_VISIBLE`, so `visible_projection`
    never emits it — and the payload names the claimed target nowhere else
    either. Asserted over the ACTUAL bytes sent, not over the projection in
    isolation, because the claim is about the whole request.
    """
    sent = recorded([UNIT_3[2]])
    item = _item()
    gates.probe_target(item, claimed=UNIT_3[2], candidates=UNIT_3)

    wire = json.dumps(sent["payload"], ensure_ascii=False)
    assert "grammar_target" not in wire
    # The claimed target appears exactly once — inside `candidates`, where it is
    # indistinguishable from the others. Anywhere else would be a label.
    assert wire.count(UNIT_3[2]) == 1
    assert sent["payload"]["candidates"].count(UNIT_3[2]) == 1


def test_the_candidates_are_sorted_so_authored_order_carries_nothing(recorded):
    sent = recorded([UNIT_3[2]])
    gates.probe_target(_item(), claimed=UNIT_3[2], candidates=reversed(UNIT_3))
    assert sent["payload"]["candidates"] == sorted(UNIT_3)


def test_an_invented_grammar_point_cannot_rank(recorded):
    """A model that does not rank the list it was given has not answered.

    Keeping the invention would let it occupy first place and fail every item —
    a gate that rejects everything, which is exactly what the negative control
    exists to catch one level up.
    """
    recorded(["the subjunctive in Latin", UNIT_3[2]])
    verdict = gates.probe_target(_item(), claimed=UNIT_3[2], candidates=UNIT_3)
    assert verdict.ranking == (UNIT_3[2],)
    assert verdict.ok


def test_a_claim_outside_the_candidates_is_refused_before_the_call(monkeypatch):
    """Spending a call to prove something the caller already knows is waste."""
    def _boom(*a, **k):  # pragma: no cover - must not be reached
        raise AssertionError("a call was made for a claim that cannot rank")

    monkeypatch.setattr(gates, "_chat", _boom)
    with pytest.raises(ValueError, match="not among the candidates"):
        gates.probe_target(_item(), claimed="something else", candidates=UNIT_3)


def test_the_candidate_list_is_the_unit_plus_three_decoys():
    """The unit's own targets are the decoys that discriminate; the rest is scale."""
    all_units = {
        1: ("past simple: regular and irregular verbs",),
        2: ("present perfect for experience: I've been to, I've tried",),
        3: UNIT_3,
        4: ("past perfect: the thing that happened first",),
    }
    candidates = target_candidates(3, UNIT_3, all_units)
    assert candidates[: len(UNIT_3)] == UNIT_3
    assert len(candidates) == len(UNIT_3) + gates.TARGET_DECOYS
    assert not set(candidates[len(UNIT_3):]) & set(UNIT_3)


def test_the_candidate_list_is_the_same_on_every_run():
    """Deterministic, not shuffled — a random plan makes the numbers unrepeatable."""
    all_units = {n: (f"target {n}",) for n in range(1, 25)}
    all_units[3] = UNIT_3
    first = target_candidates(3, UNIT_3, all_units)
    assert all(target_candidates(3, UNIT_3, all_units) == first for _ in range(5))


# ── #210: the probe is asked for the correction, not the token ──────────────


def test_the_probe_is_compared_against_the_correction_for_error_spot():
    """**#210's ruling, option 3.**

    `error_spot`'s `answer` is the WRONG word — the token the learner taps — and
    asking a probe to name it is a question with two defensible answers whenever
    the error spans two tokens: in *"I have went there twice"* the defective tile
    is arguably `went` (should be `been`) or `have` (should be dropped), and
    **both describe one error.** The probe naming the other one yielded
    `not_recoverable`, and `fixed_option` gives no widening and no cue repair, so
    the item was discarded on the first probe. Three of W10c's first real run
    died that way.

    **The correction is a question with one answer.** *What should this say?*
    does not depend on which token you consider defective.
    """
    from core.items.checks import probe_canonical

    item = parse({
        "item_type": "error_spot", "track": "life",
        "prompt_text": "Tap the word that is wrong.",
        "answer": "went", "accepted_variants": ["went"],
        "tiles": ["I", "have", "went", "there", "twice"], "wrong_index": 2,
        "correction": "been", "unit_number": 2,
    })
    assert probe_canonical(item) == "been", "the probe is judged on the correction"
    assert item.answer == "went", "the learner still taps the wrong tile"


def test_every_other_type_is_still_compared_against_its_answer():
    """The change is narrow, and narrowness is the property worth asserting.

    `probe_canonical` differing from `answer` for anything else would silently
    move what the uniqueness gate means for that type.
    """
    from core.items.checks import probe_canonical

    item = parse({
        "item_type": "cloze_cued", "track": "life",
        "prompt_text": "I ___ there twice last year.",
        "answer": "went", "accepted_variants": ["went"], "unit_number": 1,
    })
    assert probe_canonical(item) == item.answer


def test_an_answer_that_is_not_the_wrong_tile_is_refused():
    """**A learner taps the correct tile and is marked wrong.**

    `response.chosen_option` returns `item.tiles[tapped]` and `grade_text`
    compares it against `accepted_variants`, which is derived from `answer`. So
    an `answer` that is not the wrong tile breaks grading for every correct tap —
    the exact failure the v3 rebuild exists to end.

    W10c's first real run returned the FULL CORRECTED SENTENCE in `answer` while
    `tiles[wrong_index]` was `went`. It parsed and passed every deterministic
    check. `item_generate.txt` had stated the rule since the constraint block was
    derived; **nothing enforced it.**
    """
    from core.items.checks import deterministic_failures

    item = parse({
        "item_type": "error_spot", "track": "life",
        "prompt_text": "Tap the word that is wrong.",
        "answer": "I have been there twice",
        "accepted_variants": ["i have been there twice"],
        "tiles": ["I", "have", "went", "there", "twice"], "wrong_index": 2,
        "correction": "been", "unit_number": 2,
    })
    codes = [f.code for f in deterministic_failures(item)]
    assert "answer_not_the_wrong_tile" in codes
