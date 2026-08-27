"""The no-guilt rule reaching item content for the first time (#110).

**The user action:** a learner answering a generated item and reading whatever
the app put in front of them. Until W10c the banned-phrase scan ran over `.tsx`
files and over hand-written bot copy; `prompt_text`, `cue_text`, options, tiles,
the canonical answer and the explanation live in `items` and are model-generated,
and **no check touched a single one of them.** They are the highest-volume
user-facing copy in the app.

These are the negative control's free half. The billed control (`probe_target`
against a deliberately mis-targeted item) lives in `core.items.generate`; this
one costs nothing, so it runs in the suite on every commit.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from core.copy_rules import (
    BANNED,
    BANNED_IN_CONTENT,
    CONTENT_NARROWS,
    COPY_TERMS,
    content_offenders,
)
from core.items.checks import deterministic_failures
from core.items.grading import normalise_variants
from core.items.schema import parse


def _item(**over):
    draft = {
        "item_type": "cloze_cued",
        "track": "life",
        "prompt_text": "I ___ late again this morning.",
        "answer": "was",
        "accepted_variants": ["was"],
        "unit_number": 1,
    }
    draft.update(over)
    return parse(draft)


def _codes(item):
    return [f.code for f in deterministic_failures(item)]


# ── the control, both directions ────────────────────────────────────────────


def test_a_guilty_item_is_discarded_by_the_validator():
    item = _item(explanation="You failed that one — try harder.")
    assert "guilt_phrase" in _codes(item)


def test_error_spots_own_shipped_instruction_is_not_guilt():
    """**The direction that makes the other one mean anything.**

    `error_spot`'s prompt has read *"Tap the word that is wrong."* since W5 and
    #110's own text calls it fine: it describes the sentence, not the learner.
    The copy pattern bans a bare `wrong`, so applying `BANNED` to item content
    would reject correct, shipped content — and a check that fires on correct
    content is a check the next person switches off, after which nothing is
    covered at all.
    """
    item = parse({
        "item_type": "error_spot",
        "track": "life",
        "prompt_text": "Tap the word that is wrong.",
        "answer": "goed",
        "accepted_variants": ["goed"],
        "tiles": ["I", "goed", "to", "the", "shops"],
        "wrong_index": 1,
        "correction": "went",
        "unit_number": 1,
    })
    assert "guilt_phrase" not in _codes(item)


@pytest.mark.parametrize(
    "sentence",
    [
        "I missed the bus and had to walk.",
        "We took the wrong turning near the bridge.",
        "The boiler broke again last night.",
        "My phone died so I failed to call you back.",
    ],
)
def test_ordinary_english_a_learner_practises_is_not_guilt(sentence):
    """Everyday life is what §4 asks the generator for. These are that."""
    assert content_offenders(sentence) == ()
    # And each of them WOULD have been rejected by the copy pattern, which is
    # the whole reason the two are different.
    assert BANNED.search(sentence) is not None


@pytest.mark.parametrize(
    "text",
    [
        "You failed that one.",
        "You missed it again.",
        "Try harder next time.",
        "You always get this wrong.",
        "You got it wrong 😞",
        "Wrong! Read it again.",
    ],
)
def test_the_app_addressing_the_learner_is_always_guilt(text):
    assert content_offenders(text) != ()


# ── the two patterns cannot drift apart in the wrong direction ──────────────


def test_the_content_rule_is_a_narrowing_of_the_copy_rule():
    """Anything the content rule forbids, the copy rule forbids too.

    Declared as a mapping and asserted at import time in `core.copy_rules`, and
    asserted again here over the terms themselves — if the narrower rule ever
    came to forbid something the looser one permits, the two would have swapped
    roles and every caller of `BANNED` would be reasoning about the wrong set.
    """
    assert set(CONTENT_NARROWS.values()) <= set(COPY_TERMS)


def test_every_content_term_is_caught_by_both_patterns():
    """The subset relation as BEHAVIOUR, not only as a declaration.

    A mapping can be right and the regexes still wrong. This drives an actual
    string through both, which is the property that matters, and is the reason
    the mapping is not trusted on its own (CLAUDE.md §3 rule 5: the expected
    value is not derived from the thing under test).
    """
    probes = {
        r"you\s+failed": "you failed",
        r"you\s+missed": "you missed",
        r"you\s+(?:got|get|keep\s+getting|always\s+get|still\s+get)"
        r"\s+(?:it|that|this|them|these)?\s*wrong": "you always get this wrong",
        r"wrong!": "wrong!",
        r"try harder": "try harder",
        r"you lost": "you lost",
        r"should have": "should have",
    }
    for term, probe in probes.items():
        assert term in CONTENT_NARROWS, f"{term} left CONTENT_NARROWS"
        assert BANNED_IN_CONTENT.search(probe), f"content rule misses {probe!r}"
        assert BANNED.search(probe), f"copy rule misses {probe!r}"


def test_the_shim_and_the_source_are_one_object():
    """No sixth copy. #46 is narrowed by one, not widened by one."""
    from tests.support import no_guilt

    assert no_guilt.BANNED is BANNED


# ── the scan reaches every field a learner can read ─────────────────────────


@pytest.mark.parametrize(
    "field,value",
    [
        ("prompt_text", "You failed. I ___ late again."),
        ("explanation", "You always get this wrong."),
        ("cue_text", "(try harder)"),
        ("definition", "what you missed 😞"),
    ],
)
def test_guilt_is_caught_in_every_generated_free_text_field(field, value):
    """Not just the stem. `explanation` is new at W10c and is the sharp one:
    it is the only teaching a learner gets on an item, and it is the field most
    likely to reach for a verdict about the person reading it."""
    item = _item(**{field: value})
    failures = [f for f in deterministic_failures(item) if f.code == "guilt_phrase"]
    assert failures, f"{field} was not scanned"
    assert field in failures[0].detail


def test_the_scan_names_the_field_it_found_it_in():
    """A gate that says only "no" cannot be debugged; the prompt is what changes."""
    item = _item(explanation="You failed that one.")
    detail = next(
        f.detail for f in deterministic_failures(item) if f.code == "guilt_phrase"
    )
    assert detail.startswith("explanation:")
    assert "You failed" in detail


def test_the_eleven_committed_fixtures_are_all_clean():
    """The regression this whole split exists to prevent.

    If adding the gate had rejected a committed fixture, ~1,340 tests would be
    asserting over items the validator itself refuses (#115's second branch), and
    the correct response would be to fix the pattern rather than the fixtures.
    """
    rows = json.loads(
        pathlib.Path("tests/fixtures/items/valid.json").read_text(encoding="utf-8")
    )
    offenders = []
    for row in rows:
        draft = dict(row["item"])
        if draft.get("answer") is not None and "accepted_variants" not in draft:
            draft["accepted_variants"] = list(normalise_variants(draft["answer"]))
        codes = _codes(parse(draft))
        if "guilt_phrase" in codes:
            offenders.append(row["name"])
    assert offenders == []
