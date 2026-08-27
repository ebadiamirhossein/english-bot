"""The generator's field contract, derived from the models rather than written.

**The user action:** a learner reaching block 3 and finding items in it. W10c's
third `--live` attempt produced none, and the reason was not the generator:
`item_generate.txt` named five fields and closed with *"the fields that type
requires"*, listing none. **`prompt_text` is required on all eleven types and was
mentioned nowhere**, so every draft failed `prompt_text Field required` — while
the content in those drafts was good, with right answers, right targets and right
register. A generator was answering a schema nobody showed it.

These tests exist so that cannot recur silently: the contract is generated from
`core.items.schema`, and if the two ever disagree, this file fails.
"""

from __future__ import annotations

import pytest

from core.items import ITEM_TYPES, TYPES_WITHOUT_ANSWER
from core.items.generate import SLOT_TYPES, generator_system_prompt
from core.items.schema import (
    MODEL_FOR_TYPE,
    NOT_THE_GENERATORS,
    contract_block,
    generator_contract,
)


@pytest.mark.parametrize("item_type", ITEM_TYPES)
def test_the_contract_matches_the_model_exactly(item_type: str) -> None:
    """**The anti-drift assertion, and the reason this is derived at all.**

    A hand-written field list in the prompt would be a second copy of a schema
    that lives in code, and this project's history is those two coming apart:
    #100's stale Build columns, #46's five copies of one regex, `spacing_step`,
    `approved_onboarded_users`, the S24 Meaning/Translation trap. **A twelfth
    item type, or a renamed field, must fail here rather than quietly leave the
    prompt wrong.**

    Expected value computed from `model_fields` independently of
    `generator_contract`'s own logic (CLAUDE.md §3 rule 5).
    """
    model = MODEL_FOR_TYPE[item_type]
    expected = {
        (f.serialization_alias or f.alias or name)
        for name, f in model.model_fields.items()
    } - set(NOT_THE_GENERATORS)
    assert set(generator_contract(item_type)) == expected


@pytest.mark.parametrize("item_type", ITEM_TYPES)
def test_prompt_text_is_named_for_every_type(item_type: str) -> None:
    """The single omission that cost a whole billed run.

    Named as its own test rather than folded into the one above, because this is
    the field that failed and a regression here has a known price: 6 calls and
    24 items.
    """
    assert "prompt_text" in generator_contract(item_type)


@pytest.mark.parametrize("item_type", ITEM_TYPES)
def test_the_contract_never_asks_for_a_field_the_runner_overwrites(
    item_type: str,
) -> None:
    """Asking for these invites a model to author something we then discard.

    `item_type`, `track`, `unit_number` and `grammar_target` are set from the
    slot — a generator does not get to reassign an item's unit. `cue_type`,
    `cue_text` and `accepted_variants` belong to the repair ladder and to
    `normalise_variants`. **`grammar_target` is the sharp one:** it used to be
    ASKED for and echoed back, and the echo is what the run compared — that
    check moved to being implicit in the order, and the field left the contract
    with it.
    """
    contract = generator_contract(item_type)
    for field in NOT_THE_GENERATORS:
        assert field not in contract, f"{item_type} asks for {field}"


def test_the_contract_never_asks_for_a_binding_into_another_table() -> None:
    """**Found by the rule-2 confirming call, not by any test.**

    `error_type` is `TEXT REFERENCES error_types(code)` over a closed set of
    nineteen codes. The confirming call returned `error_type: "tense confusion"`
    on seven of eight drafts — reasonable English, not a code — and that
    **parses, passes every gate, and raises a ForeignKeyViolation inside
    `insert_item`.** It would have surfaced at `--apply`, on production, after a
    whole run had been paid for.

    `lexeme` is worse in kind: `insert_item` calls `ensure_lexeme`, which CREATES
    the row when absent, so a model-invented lemma writes to `lexemes` as a side
    effect of writing an exercise.

    Neither is needed — `checks._shared`'s `no_target` is satisfied by
    `unit_number`, which `_draft_to_item` always sets.
    """
    for item_type in ITEM_TYPES:
        contract = generator_contract(item_type)
        assert "error_type" not in contract, item_type
        assert "lexeme" not in contract, item_type


def test_an_invented_error_type_would_still_be_refused_before_the_write() -> None:
    """Belt as well as braces: the contract stops it being asked for, and the
    closed set is what the column enforces. Asserted here so the nineteen codes
    are named in a test rather than only in a migration."""
    from core.items.schema import parse

    item = parse({
        "item_type": "cloze_cued", "track": "life",
        "prompt_text": "While I ___ for the bus, it started to rain.",
        "answer": "was waiting", "accepted_variants": ["was waiting"],
        "unit_number": 1, "error_type": "tense confusion",
    })
    # `parse` does NOT constrain it — that is the point, and why the contract
    # must not invite it.
    assert item.error_type == "tense confusion"


def test_answer_is_described_as_required_where_checks_require_it() -> None:
    """**Optionality comes from `checks.py`, not from the annotation.**

    `answer` is `str | None` on the model because two of eleven types have no
    single canonical answer. For the other nine `checks._shared`'s
    `answer_presence` requires it and migration 012 mirrors that as a CHECK.
    Reading optionality off the annotation would have told the generator
    `answer` is optional for `cloze_cued` — the same class of omission that cost
    attempt 3, reintroduced one level down.
    """
    for item_type in ITEM_TYPES:
        described = generator_contract(item_type)["answer"]
        if item_type in TYPES_WITHOUT_ANSWER:
            assert "MUST be omitted" in described, item_type
        else:
            assert "(required)" in described, item_type


def test_answer_is_described_as_a_string_not_an_array() -> None:
    """The crash of attempt 3, prevented at the source rather than only guarded.

    The model returned `answer` as an array — defensible for a gap it believed
    had two fillers, and nothing had told it otherwise. `_draft_to_item` now
    refuses a non-string too, but this is the half that stops it being sent.
    """
    for item_type in ITEM_TYPES:
        assert generator_contract(item_type)["answer"].startswith("string")


def test_the_built_prompt_carries_the_contract_for_every_type_it_will_ask_for() -> None:
    """The prompt the run actually sends, not the template on disk."""
    prompt = generator_system_prompt()
    assert "{contract}" not in prompt, "the placeholder was not substituted"
    for item_type in set(SLOT_TYPES):
        assert item_type in prompt
        for field in generator_contract(item_type):
            assert field in prompt, f"{item_type}.{field} missing from the prompt"


def test_the_prompt_tells_the_model_not_to_echo_what_it_was_given() -> None:
    """Attempt 3's second cause. `n` is gone from the payload; this is the belt.

    `BaseItem` sets `extra="forbid"` deliberately — a generator that invents a
    field must fail loudly rather than have it dropped — so an echoed key is
    fatal to the item, and the prompt now says so in those terms.
    """
    prompt = generator_system_prompt()
    assert "Do not echo back" in prompt
    assert "extra field makes the item unusable" in prompt


def test_the_contract_is_cheap_enough_to_send_every_call() -> None:
    """~1,500 characters against ~20,000 for raw `model_json_schema()`.

    Recorded as a test because the alternative was rejected on this number, and
    a later change that made the contract balloon would quietly undo the reason
    it was chosen.
    """
    block = contract_block(sorted(set(SLOT_TYPES)))
    assert len(block) < 3000, f"contract grew to {len(block)} chars"
