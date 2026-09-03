"""W14 / #366 — **a zero-completeness result is a capture failure, not a score.**

────────────────────────────────────────────────────────────────────────────────
THE THRESHOLD IS `completeness == 0`, AND IT IS CHOSEN FROM THE THREE REAL
ATTEMPTS RATHER THAN GUESSED.

The first three live attempts (user 3, 2026-09-03), which are the entire
evidence base:

    #1  accuracy 52   fluency 79   completeness 50   11.90 s
    #2  accuracy 82   fluency 86   completeness 75    7.61 s
    #3  accuracy  0   fluency  0   completeness  0    4.03 s

**WHY COMPLETENESS AND NOT ACCURACY.** `CompletenessScore` is *how much of the
reference was said*. Zero means **none of it matched** — the app heard nothing it
was listening for. Accuracy is *how well what was heard was pronounced*, which
is a different question and is meaningless when nothing was heard.

**WHY EXACTLY ZERO AND NOT A BAND.** The observations are 0, 50 and 75. **There
is nothing between 0 and 50**, so any threshold in that interval — 10, 20, 30 —
would be a number this project cannot defend, and CLAUDE.md §3 rule 7 is the
standing rule against inventing one. Zero is also **categorical rather than a
tuning knob**: *nothing matched* and *something matched* are different kinds of
event, not two points on a scale.

**AND THE ASYMMETRY POINTS THE SAME WAY.** Erring high suppresses a genuinely
poor attempt, and **a poor attempt is information the learner should get** —
that is the whole surface. Erring at zero suppresses only the case where Azure
matched literally nothing, which is not information about the learner at all.

**NO ROW IS WRITTEN, AND THAT IS THE HALF THAT OUTLIVES THE SCREEN.** W17 reads
`speech_attempts.phonemes` for weak-spot detection; a capture failure
contributes ~23 phonemes at accuracy 0 and would read as catastrophic
pronunciation of every sound in the sentence. **One such row outweighs several
real attempts in any mean.** The accepted cost is that the quota ledger
under-counts those seconds (4.03 s in attempt #3) — the ledger is a guard with a
20% margin, not an accounting system.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.speech import NotRecognised, parse_assessment

FIXTURES = Path(__file__).parent / "fixtures" / "azure_pronunciation"
RECORDED = json.loads((FIXTURES / "assess_native_48000.json").read_text())


def _with(accuracy: float, fluency: float, completeness: float, pron: float) -> dict:
    """The real recording with its aggregates replaced. **Everything else real.**"""
    payload = json.loads(json.dumps(RECORDED))
    best = payload["NBest"][0]
    best["AccuracyScore"] = accuracy
    best["FluencyScore"] = fluency
    best["CompletenessScore"] = completeness
    best["PronScore"] = pron
    return payload


def test_attempt_three_is_refused_as_not_heard() -> None:
    """**The live 0/0/0, reproduced.** `RecognitionStatus` is `Success` and
    `Words` is non-empty, so both existing guards pass — which is exactly how
    this reached a learner's screen."""
    payload = _with(0, 0, 0, 0)
    assert payload["RecognitionStatus"] == "Success"
    assert payload["NBest"][0]["Words"], "the words are present — that is the trap"
    with pytest.raises(NotRecognised):
        parse_assessment(payload)


def test_attempts_one_and_two_are_still_scored() -> None:
    """**The positive controls, and they are the reason the threshold is safe.**

    Without these the refusal above would pass even if `parse_assessment` had
    been broken to reject everything (#345). These are the two REAL attempts,
    and #1 at 52/79/50 is a poor attempt that the learner must still be shown.
    """
    first = parse_assessment(_with(52, 79, 50, 60))
    assert first.completeness == 50.0 and first.accuracy == 52.0
    assert len(first.words) == 7

    second = parse_assessment(_with(82, 86, 75, 83))
    assert second.completeness == 75.0 and second.accuracy == 82.0
    assert len(second.words) == 7


def test_the_boundary_is_exactly_zero_and_nothing_above_it_is_suppressed() -> None:
    """**A learner who said one word of eight has been heard.**

    Suppressing a low-but-nonzero completeness would hide a real attempt behind
    *I didn't catch that*, which is a lie about what happened and removes the
    only feedback the surface exists to give.
    """
    lowest_real = parse_assessment(_with(30, 40, 1, 25))
    assert lowest_real.completeness == 1.0

    with pytest.raises(NotRecognised):
        parse_assessment(_with(30, 40, 0, 25))


def test_a_zero_completeness_result_writes_no_row_for_w17_to_read(
    monkeypatch,
) -> None:
    """#366's second harm, asserted at the parser boundary.

    `NotRecognised` propagates out of `score_attempt` before the INSERT, which
    `tests/test_shadow_route.py` asserts end-to-end for the `NoMatch` case. Here
    the point is narrower and worth its own name: **the phonemes are present and
    would have been stored.**
    """
    payload = _with(0, 0, 0, 0)
    phonemes = [
        item
        for word in payload["NBest"][0]["Words"]
        for item in word.get("Phonemes", [])
    ]
    assert len(phonemes) == 23, "23 phonemes would have entered W17's input"
    with pytest.raises(NotRecognised):
        parse_assessment(payload)
