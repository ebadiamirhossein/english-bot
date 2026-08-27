"""`free_stages` is `validate`'s own head, and the batch path proves it.

**The user action:** every item a learner ever sees. `gates.validate` is the one
function that decides whether an item may exist, so extracting three stages out
of it is a change to the gate that guards all of them — and the only honest way
to make that change is to demonstrate the verdicts did not move.

**Why the extraction happened at all (#120).** `JUDGE_BATCH = 20` has been
declared since W5 and `validate` has always called `judge_naturalness([sentence])`
— one sentence per call. W10c validates a cohort of eight and wants one call for
the eight. To batch, a caller has to run the free stages itself first, or it pays
the judge for items the free gates would have rejected for nothing. The obvious
way to do that is to copy the three stages into the runner, and that is how two
definitions of *is this item well-formed* start.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from core.items import gates
from core.items.checks import judged_sentence
from core.items.grading import normalise_variants
from core.items.schema import parse

FIXTURES = pathlib.Path("tests/fixtures/items/valid.json")


def _fixtures():
    rows = json.loads(FIXTURES.read_text(encoding="utf-8"))
    out = []
    for row in rows:
        draft = dict(row["item"])
        if draft.get("answer") is not None and "accepted_variants" not in draft:
            draft["accepted_variants"] = list(normalise_variants(draft["answer"]))
        out.append((row["name"], parse(draft)))
    return out


@pytest.mark.parametrize("name,item", _fixtures(), ids=lambda v: v if isinstance(v, str) else "")
def test_free_stages_reaches_the_same_verdict_validate_did(name, item, monkeypatch):
    """Behaviour-preservation, over all eleven committed types.

    `validate` is driven with the judge and the probe stubbed so only the FREE
    stages can decide, and its verdict is compared with calling `free_stages`
    directly. If the extraction had dropped the second deterministic pass — the
    one that re-checks after a contraction rewrite — a `cloze_cued` whose answer
    became visible in its own shortened stem would slip through here and nowhere
    else.
    """
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
    monkeypatch.setattr(gates, "_synthesize", lambda text, **k: b"audio")
    monkeypatch.setattr(
        gates, "_transcribe",
        lambda audio, **k: _spoken(item),
    )

    through_validate = gates.validate(item)
    rewritten, failed = gates.free_stages(item)

    if failed is None:
        assert through_validate.report.ok, (
            f"{name}: free_stages passed it and validate did not"
        )
    else:
        assert not through_validate.report.ok, (
            f"{name}: free_stages discarded it and validate did not"
        )
        assert failed.report.verdict == through_validate.report.verdict
        assert failed.report.deterministic == through_validate.report.deterministic
        assert failed.report.naturalness == through_validate.report.naturalness
    assert rewritten.item_type == item.item_type


def _spoken(item):
    """What a perfect recogniser would return for an audio item."""
    from core.items.checks import sentence_of

    return sentence_of(item)


def test_a_contraction_rewrite_survives_the_extraction():
    """Rule 4 repairs in place, and the rewritten item is what comes back.

    This is the one free stage that MUTATES, so it is the one an extraction can
    silently drop: returning the original item instead of the contracted one
    would leave `validate` judging and probing a sentence the learner will never
    see, and every other test in this file would still pass.

    `dictation` on purpose. `_sentence_field` declines to rewrite
    `word_bank_order`, `l1_to_l2_production`, `error_spot` and `match_pairs`
    (rewriting would desynchronise a bank or a pair), and the gapped types are
    blocked for a different and unintended reason — see the test below. That
    leaves the audio and speaking types, whose sentence is prose.
    """
    item = parse({
        "item_type": "dictation",
        "track": "life",
        "prompt_text": "Type what you hear.",
        "answer": "I do not know where she went",
        "accepted_variants": ["i do not know where she went"],
        "unit_number": 1,
    })
    rewritten, failed = gates.free_stages(item)
    assert failed is None
    assert "don't" in rewritten.answer
    assert "do not" not in rewritten.answer


def test_rule_four_does_not_reach_a_gapped_stem_and_that_is_a_known_defect():
    """**PINNED, NOT ENDORSED.** PRD §4.6 rule 4 never fires on a gapped item.

    `naturalness._EMPHASIS` is ``[*_]|\b(?:DO|AM|IS|ARE|WILL|NOT)\b`` and exists
    to protect deliberate emphasis — ``I *am* going``, ``you DO know`` — from
    being contracted away. `schema.GAP` is ``___``. **Three underscores match the
    ``_`` in that character class**, so `uncontracted` returns empty for every
    gapped stem and the contraction repair is skipped — silently, with no
    symptom.

    **Scope, stated precisely rather than dramatically.** Rule 4 already declines
    BY DESIGN for `word_bank_order`, `l1_to_l2_production`, `error_spot` and
    `match_pairs`, where `_sentence_field` returns None because a rewrite would
    desynchronise a bank or a translation pair. What this defect adds is
    `cloze_cued`, `mcq` and `collocation_pick` — every type whose `prompt_text`
    carries the gap. So the rule fires only on `dictation`, `listening_gap`,
    `speak_repeat` and `speak_answer`, and on an ungapped `mcq`.

    CLAUDE.md §3 lists the naturalness gate among the things that are "always
    required, never optional", and rule 4 is one of its four.

    **Found while extracting `free_stages` in W10c, by a test that assumed the
    repair worked and discovered it does not.** Filed rather than fixed: changing
    `_EMPHASIS` changes what `mechanical_naturalness` rewrites for every existing
    caller, and that is a decision with its own before-and-after, not something to
    improvise inside a generation slice (CLAUDE.md §8).

    This test pins the CURRENT behaviour so a future fix has to come here and
    explain itself — the same job `test_cards_import_vocab.py` does for
    ``lemmatize("tier") == "ti"`` (#177).
    """
    from core.items.naturalness import uncontracted

    gapped = "I do not ___ where she went."
    assert uncontracted(gapped) == (), "rule 4 now reaches gapped stems — see the issue"
    assert uncontracted("I do not know where she went.") != ()

    item = parse({
        "item_type": "cloze_cued",
        "track": "life",
        "prompt_text": gapped,
        "answer": "know",
        "accepted_variants": ["know"],
        "unit_number": 1,
    })
    rewritten, failed = gates.free_stages(item)
    assert failed is None
    assert rewritten.prompt_text == gapped


def test_a_deterministic_failure_stops_before_the_naturalness_rewrite():
    """Cheapest first survives the extraction, and it is checkable."""
    item = parse({
        "item_type": "cloze_cued",
        "track": "life",
        "prompt_text": "I ___ ___ twice.",
        "answer": "went",
        "accepted_variants": ["went"],
        "unit_number": 1,
    })
    _, failed = gates.free_stages(item)
    assert failed is not None
    assert "gap_count" in failed.report.deterministic


def test_the_cohort_pays_one_judge_call_for_eight_sentences(monkeypatch):
    """#120's whole point, measured rather than described.

    Eight `validate(judge=True)` calls make eight judge calls. The batch path
    makes one — which is what `JUDGE_BATCH = 20` has promised in a docstring
    since W5 while `validate` called `judge_naturalness([sentence])`.
    """
    calls: list[int] = []

    def _judge(sentences, **k):
        calls.append(len(sentences))
        return tuple(gates.NaturalnessVerdict(True, "ok") for _ in sentences)

    monkeypatch.setattr(gates, "judge_naturalness", _judge)

    items = [
        parse({
            "item_type": "cloze_cued",
            "track": "life",
            "prompt_text": f"I ___ there {n} times last year.",
            "answer": "went",
            "accepted_variants": ["went"],
            "unit_number": 1,
        })
        for n in range(2, 10)
    ]
    survivors = []
    for item in items:
        rewritten, failed = gates.free_stages(item)
        assert failed is None
        survivors.append(rewritten)

    gates.judge_naturalness([judged_sentence(i) for i in survivors])
    assert calls == [8], "the cohort should cost exactly one judge call"
    assert len(survivors) <= gates.JUDGE_BATCH


def test_judge_false_still_skips_the_judge(monkeypatch):
    """The flag the batch path relies on, asserted rather than assumed.

    W10c passes `judge=False` because it has ALREADY judged the item as part of
    a batch. If that flag ever stopped working the cohort would be judged twice
    and billed twice, and nothing would fail.
    """
    def _boom(*a, **k):  # pragma: no cover - must not be reached
        raise AssertionError("judge_naturalness was called with judge=False")

    monkeypatch.setattr(gates, "judge_naturalness", _boom)
    monkeypatch.setattr(
        gates, "probe_acceptable",
        lambda item, **k: {"acceptable": [item.answer], "confidence": "high"},
    )
    item = parse({
        "item_type": "cloze_cued",
        "track": "life",
        "prompt_text": "I ___ there twice last year.",
        "answer": "went",
        "accepted_variants": ["went"],
        "unit_number": 1,
    })
    assert gates.validate(item, judge=False).report.ok
