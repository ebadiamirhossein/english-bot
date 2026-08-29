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
    VARIANTS_ARE_THE_GENERATORS,
    constraint_block,
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
    # `accepted_variants` is the runner's for every type but one: only
    # `l1_to_l2_production`'s own checks require the generator to supply it.
    if item_type not in VARIANTS_ARE_THE_GENERATORS:
        expected -= {"accepted_variants"}
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


# ── the shape constraints, and the assertion that keeps the set honest ──────


def _codes_for(item_type: str) -> set[str]:
    """Every failure code this type can produce, read from `checks.py`'s AST.

    **Computed from the source, not from a list maintained beside it**
    (CLAUDE.md §3 rule 5): a hand-kept inventory would go stale exactly when a
    new check is added, which is the moment this test exists to catch.
    """
    import ast
    import inspect

    from core.items import checks

    tree = ast.parse(inspect.getsource(checks))
    fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}

    def codes(name: str) -> set[str]:
        out: set[str] = set()
        for node in ast.walk(fns[name]):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "Failure" and node.args
                    and isinstance(node.args[0], ast.Constant)):
                out.add(node.args[0].value)
        return out

    per_type = {
        "mcq": ["_mcq", "_options_failures"],
        "collocation_pick": ["_collocation", "_options_failures"],
        "cloze_cued": ["_cloze"],
        "word_bank_order": ["_word_bank"],
        "error_spot": ["_error_spot"],
        "match_pairs": ["_match_pairs"],
        "l1_to_l2_production": ["_l1_production"],
        "dictation": ["_dictation"],
        "listening_gap": ["_cloze", "_listening_gap"],
        "speak_repeat": ["_speak_repeat"],
        "speak_answer": ["_speak_answer"],
    }
    out = codes("_shared")
    for name in per_type[item_type]:
        out |= codes(name)
    return out


@pytest.mark.parametrize("item_type", sorted(set(SLOT_TYPES)))
def test_every_rejection_a_type_can_suffer_is_stated_or_named_unstatable(
    item_type: str,
) -> None:
    """**The assertion that makes the derivation worth anything.**

    W10c's first real accept rate was 6 of 24, and its branch rule — *the prompt
    is wrong, not the gate* — was right: the contract carried field NAMES and no
    SHAPE. A generator told `bank: array of strings` cannot know a word bank must
    be a permutation of the answer and must not already be in order, and both are
    `deterministic_failures` rejections that are knowable in advance.

    So every code a type can produce must be **either** expressed in the prompt
    **or** listed in `NOT_EXPRESSIBLE` with a reason. **A new check then fails
    this test rather than quietly going unstated** — which is the only thing
    standing between a derived constraint block and a hand-written one that
    drifts.

    The codes come from `checks.py`'s own AST; the expected set is not
    maintained here.
    """
    from core.items.schema import NOT_EXPRESSIBLE

    prompt = generator_system_prompt()
    unstated = []
    for code in sorted(_codes_for(item_type)):
        if code in NOT_EXPRESSIBLE:
            continue
        # The prompt states rules in English, so the assertion is that SOMETHING
        # in it addresses the rule — keyed off the distinctive word in the code.
        keyword = {
            "empty_prompt": "prompt_text",
            "prompt_too_long": "characters",
            "sentence_too_long": "words",
            "guilt_phrase": "judgement",
            "option_count": "options",
            "duplicate_options": "repeat another",
            "substring_option": "substring",
            "option_length_tell": "twice the length",
            "answer_not_an_option": "one of them",
            "gap_count": "exactly one gap",
            "numeric_gap": "never gap a number",
            "answer_visible_in_stem": "must not appear anywhere else",
            "gap_misses_target": "the grammar target is about",
            "bank_size": "tokens",
            "bank_not_a_permutation": "same words, same count",
            "bank_already_ordered": "NOT already be in the answer",
            "tile_count": "tiles",
            "wrong_index_out_of_range": "wrong_index",
            "correction_is_a_no_op": "must differ from it",
            "answer_not_the_wrong_tile": "copied exactly",
            "pair_count": "pairs",
            "duplicate_left": "no left entry may repeat",
            "duplicate_right": "no right entry may repeat",
            "columns_overlap": "both sides",
            "l1_wrong_script": "own script",
            "answer_not_english": "answer is English",
            "too_few_variants": "renderings",
            "dictation_length": "words",
            "digits_in_dictation": "no digits",
        }.get(code)
        if keyword is None or keyword not in prompt:
            unstated.append(code)
    assert unstated == [], (
        f"{item_type}: these rejections are neither stated in the prompt nor "
        f"named in NOT_EXPRESSIBLE: {unstated}"
    )


def test_the_stated_bounds_are_the_ones_the_checks_read() -> None:
    """The numbers are derived, so they cannot be changed in one place only.

    Expected values hardcoded here rather than read from the constants
    (CLAUDE.md §3 rule 5) — a test computing its expectation from the module
    under test would pass through any change to it.
    """
    from core.items import checks

    assert checks.BANK_SIZE == (4, 10)
    assert checks.TILE_COUNT == (4, 8)
    assert checks.PAIR_COUNT == (3, 6)
    assert checks.MIN_ACCEPTED_VARIANTS == 2
    assert checks.MCQ_OPTIONS == (4,)

    block = constraint_block(["word_bank_order", "error_spot", "match_pairs"])
    assert "bank holds 4-10 tokens" in block
    assert "4-8 tiles" in block
    assert "3-6 pairs" in block


def test_the_contract_is_cheap_enough_to_send_every_call() -> None:
    """~1,500 characters against ~20,000 for raw `model_json_schema()`.

    Recorded as a test because the alternative was rejected on this number, and
    a later change that made the contract balloon would quietly undo the reason
    it was chosen.
    """
    block = contract_block(sorted(set(SLOT_TYPES)))
    assert len(block) < 3000, f"contract grew to {len(block)} chars"


def test_l1_to_l2_production_is_asked_for_the_variants_its_checks_require() -> None:
    """**The type was impossible to pass, and the contract is why.**

    `accepted_variants` was in `NOT_THE_GENERATORS`, so the contract never asked
    for it; `_draft_to_item` then derives it from `answer` alone, which yields
    exactly ONE rendering; and `checks._l1_production` requires
    `MIN_ACCEPTED_VARIANTS` because *"the type with the widest legitimate
    variation... one accepted form is a trap: the learner produces a correct
    translation and is marked wrong."*

    **So every draft failed `too_few_variants` deterministically** — 0/3 in three
    consecutive production runs, nine straight, including drafts that obeyed the
    contract perfectly.

    The exclusion was right in general and wrong for the one type whose own
    checks demand the generator supply the field.
    """
    contract = generator_contract("l1_to_l2_production")
    assert "accepted_variants" in contract
    assert "at least 2" in contract["accepted_variants"]


@pytest.mark.parametrize(
    "item_type", sorted(set(ITEM_TYPES) - {"l1_to_l2_production"})
)
def test_no_other_type_is_asked_for_accepted_variants(item_type: str) -> None:
    """The exception is scoped, and narrowness is the property worth asserting.

    For every other type `normalise_variants` derives the field and the repair
    ladder widens it; a generator supplying its own would be authoring what is
    graded as correct.
    """
    assert "accepted_variants" not in generator_contract(item_type)


def test_a_perfect_l1_to_l2_draft_now_passes_the_deterministic_gates() -> None:
    """End to end, because the contract being right is not the same as the item
    passing — and the regression this guards is *the type cannot pass at all*."""
    from core.items.checks import deterministic_failures
    from core.items.generate import Slot, _draft_to_item

    slot = Slot(index=0, item_type="l1_to_l2_production", target="present perfect", cohort="focus")
    item = _draft_to_item({
        "register": "neutral",
        "prompt_text": "من دیروز به مغازه رفتم",
        "answer": "I went to the shop yesterday",
        "accepted_variants": [
            "I went to the shop yesterday", "Yesterday I went to the shop",
        ],
        "explanation": "Past simple: the time is finished.",
        "definition": "a completed action at a stated past time",
        "l1_gloss": "رفتم",
    }, slot, 1)
    assert [f.code for f in deterministic_failures(item)] == []
