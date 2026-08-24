"""The blind-solver gate is only as good as what it is blind to.

If `visible_projection` leaks the answer, the gate becomes a rubber stamp and
every downstream number still reads green: unmarkable items ship, their
validation records say they passed, and nothing fails. That is the failure this
whole slice exists to prevent, one level up — so it gets its own test file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.items import ITEM_TYPES, RESPONSE_MODE
from core.items.grading import fold, normalise_variants
from core.items.projection import NEVER_VISIBLE, visible_projection
from core.items.schema import MODEL_FOR_TYPE, parse

FIXTURES = Path(__file__).parent / "fixtures" / "items"
VALID = json.loads((FIXTURES / "valid.json").read_text(encoding="utf-8"))


def _item(raw: dict):
    draft = dict(raw)
    if draft.get("answer") is not None and "accepted_variants" not in draft:
        draft["accepted_variants"] = normalise_variants(draft["answer"])
    return parse(draft)


@pytest.mark.parametrize("row", VALID, ids=lambda r: r["name"])
def test_the_projection_never_carries_the_answer(row) -> None:
    """Substring, not equality — an answer embedded in a field still leaks it."""
    item = _item(row["item"])
    blob = fold(json.dumps(visible_projection(item), ensure_ascii=False))

    # **Tap-mode types are exempt by construction, not by concession.** For
    # `mcq`, `error_spot`, `word_bank_order` and `collocation_pick` the answer
    # is necessarily on screen — the task is SELECTING it, not recalling it, and
    # a projection that hid it would be unanswerable. What must stay hidden for
    # those is *which* one, and the per-type tests below assert exactly that.
    # `speak_repeat`'s answer IS its prompt.
    exempt = RESPONSE_MODE[item.item_type] == "tap" or item.item_type == "speak_repeat"
    if item.answer and not exempt:
        assert fold(item.answer) not in blob, f"{item.item_type} leaks its answer"


@pytest.mark.parametrize("row", VALID, ids=lambda r: r["name"])
def test_the_projection_carries_no_internal_field(row) -> None:
    projection = visible_projection(_item(row["item"]))
    leaked = NEVER_VISIBLE & set(projection)
    assert leaked == set(), f"internal fields projected: {sorted(leaked)}"


def test_match_pairs_projects_two_columns_and_not_the_mapping() -> None:
    row = next(r for r in VALID if r["name"] == "match_pairs")
    item = _item(row["item"])
    projection = visible_projection(item)

    assert set(projection["left"]) == {left for left, _ in item.pairs}
    assert set(projection["right"]) == {right for _, right in item.pairs}
    # Independently sorted, so position carries no information about pairing.
    assert projection["left"] == sorted(projection["left"])
    assert projection["right"] == sorted(projection["right"])
    assert "pairs" not in projection


def test_error_spot_shows_the_tiles_and_hides_which_one_is_wrong() -> None:
    row = next(r for r in VALID if r["name"] == "error_spot")
    item = _item(row["item"])
    projection = visible_projection(item)

    assert projection["tiles"] == list(item.tiles)
    assert "wrong_index" not in projection
    assert fold(item.correction) not in fold(json.dumps(projection))


def test_listening_gap_hides_the_transcript() -> None:
    """The transcript is the answer wearing a different hat."""
    row = next(r for r in VALID if r["name"] == "listening_gap")
    projection = visible_projection(_item(row["item"]))
    assert "transcript" not in projection


def test_speak_answer_hides_the_rubric() -> None:
    row = next(r for r in VALID if r["name"] == "speak_answer")
    projection = visible_projection(_item(row["item"]))
    assert "rubric" not in projection


def test_unused_cue_material_stays_hidden() -> None:
    """A repair ladder that leaked every rung at once would not be a ladder."""
    item = parse({
        "item_type": "cloze_cued", "track": "life", "lexeme": "go",
        "prompt_text": "I ___ to the shops yesterday.", "answer": "went",
        "accepted_variants": normalise_variants("went"),
        "definition": "moved away from here", "l1_gloss": "رفتم",
    })
    projection = visible_projection(item)
    assert "definition" not in projection
    assert "l1_gloss" not in projection
    assert "cue" not in projection


def test_every_type_projects_something() -> None:
    """A type with no projection cannot be rendered or gated."""
    for row in VALID:
        projection = visible_projection(_item(row["item"]))
        assert projection["item_type"] in ITEM_TYPES
        assert projection["prompt_text"]
    assert {r["item"]["item_type"] for r in VALID} == set(MODEL_FOR_TYPE)
