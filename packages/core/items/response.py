"""What the learner sent back, folded to the one string `grade_text` compares.

**The mirror image of `projection.py`, and the reason it exists at all.**
`visible_projection` branches on type in exactly one pure function so that
nothing else has to; this does the same for the return journey. A `tap` response
is a tile index, an option string, an ordering or a mapping depending on the
type, and every one of those has to become *an answer* before it can be graded.
Without a single place to do that, the conversion would land in the route (a
second serialiser's twin) or in TypeScript (a fourth fold).

**This does not weaken "no eleven-way switch in the grading path".** There is
still exactly one comparator — `grading.grade_text` — and exactly one notion of
"same answer". What varies per type is only which field of the submission *is*
the answer, which is a fact about the item's shape and not about grading. The
`isinstance` ladder below is the same shape `visible_projection` and
`checks.sentence_of` already use, for the same reason.

`match_pairs` is the one type with no answer string at all: `items.answer IS
NULL` by schema rule, so `grade_text` would fold `None` to `""` and mark every
submission wrong. It is compared as a mapping instead, folded with the **same**
`grading.fold` — one fold, three modules, still no fourth.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from core.items import RESPONSE_MODE
from core.items.grading import fold, grade_text
from core.items.schema import (
    BaseItem,
    CollocationPickItem,
    ErrorSpotItem,
    MatchPairsItem,
    MCQItem,
    WordBankOrderItem,
)


@dataclass(frozen=True, slots=True)
class Submission:
    """One learner response, before it is known what kind of answer it is.

    Every field is optional because the client sends the one its response mode
    produces. Which one is read is decided here and nowhere else.
    """

    #: `typed` — what they typed, verbatim and unnormalised.
    text: str | None = None
    #: `tap` on `mcq` / `collocation_pick` — the option string tapped.
    option: str | None = None
    #: `tap` on `error_spot` — the index of the tile tapped.
    tile_index: int | None = None
    #: `tap` on `word_bank_order` — the bank tokens in the order chosen.
    order: tuple[str, ...] = ()
    #: `tap` on `match_pairs` — left-hand key to right-hand value.
    pairs: Mapping[str, str] = field(default_factory=dict)
    #: `spoken` — the learner's own mark. W6 has no scoring instrument; W14 does.
    self_marked: bool | None = None


def submitted_text(item: BaseItem, sub: Submission) -> str | None:
    """The single string `grade_text` sees, whatever the response mode was."""
    if isinstance(item, (MCQItem, CollocationPickItem)):
        return sub.option
    if isinstance(item, ErrorSpotItem):
        index = sub.tile_index
        if index is None or not 0 <= index < len(item.tiles):
            return None
        return item.tiles[index]
    if isinstance(item, WordBankOrderItem):
        return " ".join(sub.order) if sub.order else None
    if isinstance(item, MatchPairsItem):
        return None  # graded as a mapping; see `mapping_matches`
    if RESPONSE_MODE[item.item_type] == "spoken":
        return None  # nothing is captured in W6; the mark is the learner's
    return sub.text


def chosen_option(item: BaseItem, sub: Submission) -> str | None:
    """`item_attempts.chosen_option` — which distractor pulled them.

    NULL for `word_bank_order` and `match_pairs` is a decision, not a gap: there
    is no single option to name, and the permutation and the mapping go to
    `response_payload` instead.
    """
    if isinstance(item, (MCQItem, CollocationPickItem)):
        return sub.option
    if isinstance(item, ErrorSpotItem):
        index = sub.tile_index
        if index is not None and 0 <= index < len(item.tiles):
            return item.tiles[index]
    return None


def mapping_matches(item: MatchPairsItem, submitted: Mapping[str, str]) -> bool:
    """A bijection is right or it is not. Folded with `grading.fold`."""
    expected = {fold(left): fold(right) for left, right in item.pairs}
    got = {fold(str(k)): fold(str(v)) for k, v in submitted.items()}
    return bool(expected) and expected == got


def response_payload(item: BaseItem, sub: Submission) -> dict:
    """The structured half, for `item_attempts.response_payload`.

    Kept because it cannot be reconstructed from a boolean: *which* order they
    built and *which* pairs they drew are the evidence W7's leech rewrite reads.
    """
    if isinstance(item, WordBankOrderItem):
        return {"order": list(sub.order)}
    if isinstance(item, MatchPairsItem):
        return {"pairs": dict(sub.pairs)}
    if isinstance(item, ErrorSpotItem) and sub.tile_index is not None:
        return {"tile_index": sub.tile_index}
    return {}


def grade(item: BaseItem, sub: Submission) -> tuple[bool, str]:
    """``(correct, graded_by)``. One comparator, three instruments.

    `graded_by` is NOT decoration. Without it an accuracy number silently mixes
    a string match, a rubric and a learner's own judgement, and W19's progress
    line stops being comparable over time — the same argument PRD §6 makes for
    keeping the placement instrument fixed. W6 produces two of the three:
    `deterministic` for the nine tap/typed types, and `self` for the two spoken
    ones, which have no scoring instrument until W14 (migration 018).
    """
    if RESPONSE_MODE[item.item_type] == "spoken":
        return bool(sub.self_marked), "self"
    if isinstance(item, MatchPairsItem):
        return mapping_matches(item, sub.pairs), "deterministic"
    return grade_text(submitted_text(item, sub), item), "deterministic"
