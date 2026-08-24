"""The eleven item types as pydantic models, and what feeds `content_hash`.

**PRD gives eleven names and no field shapes.** Everything below is defined by
W5. Where a choice was available the one that makes an item *markable* wins,
because an unmarkable item is the defect that started this rebuild.

Why a discriminated union rather than eleven dataclasses with hand-rolled
dispatch: the validator's core job is parsing an eleven-variant JSON payload
produced by a model, and `Field(discriminator=...)` does that in one declaration
with the type error attached to the right field. Hand-rolled dispatch is ~400
repetitive lines and its failure mode is a silently-ignored key.

`extra="forbid"` everywhere is load-bearing. A generator that invents a field —
`"hint"`, `"difficulty"` — must fail loudly here rather than have the field
dropped on the floor and the item shipped without whatever it was for.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from core.items import CUE_TYPES, ITEM_TYPES, REGISTERS, TRACKS
from core.items.grading import fold

Track = Literal["work", "life", "curiosity"]
Register = Literal["formal", "neutral", "informal", "slang", "taboo"]
CueType = Literal[
    "first_letter_length", "l1_gloss", "definition", "word_bank", "converted_mcq"
]

# The gap marker. Three underscores, one token, and `checks.py` counts
# occurrences of exactly this string — a variable-length run would make "how
# many gaps does this item have" ambiguous, and a two-gap cloze is unmarkable
# for the same reason the PRD's broken item is.
GAP = "___"


class BaseItem(BaseModel):
    """Fields every one of the eleven carries."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", populate_by_name=True
    )

    track: Track

    #: PRD §8.5.1's register tag. **The Python attribute is `register_tag` and
    #: the wire/column name is `register`.** `BaseModel`'s metaclass is an
    #: `ABCMeta`, which already carries a `register` method, so a field of that
    #: name is shadowed: it parses without error and then reads back as a bound
    #: method. That failure is silent -- which is exactly the class of bug this
    #: slice exists to stop -- so the field is aliased rather than renamed
    #: everywhere else. JSON in and out says `register`, migration 012's column
    #: is `register`, and only Python attribute access differs.
    register_tag: Register = Field(
        default="neutral", alias="register", serialization_alias="register"
    )

    #: What the learner reads. The naturalness gate, the blind-solver
    #: projection and `content_hash` all operate on this and nothing else.
    prompt_text: str

    #: Canonical answer in display form. ``None`` only for the two types that
    #: genuinely have none; migration 012 enforces the same rule as a CHECK.
    answer: str | None = None

    #: Additional correct answers. Stored folded (see `grading.normalise_variants`).
    accepted_variants: tuple[str, ...] = ()

    #: Which of PRD §4.3's five cues was applied, if repair happened.
    cue_type: CueType | None = None
    #: The cue's rendered text — shape differs per cue, so it is one string.
    cue_text: str | None = None

    #: Target lemma. The service resolves it to `items.lexeme_id`; the pure
    #: layer never sees an id because ids come from a database.
    lexeme: str | None = None
    #: Target grammar point, an `error_types.code`.
    error_type: str | None = None
    #: PRD §3's fixed 24-unit sequence.
    unit_number: int | None = None

    #: Shown after grading, never before — see `projection.visible_projection`.
    explanation: str | None = None

    #: Cue material, authored by the generator in the SAME call that produced
    #: the item and used only if the blind-solver gate demands a repair.
    #:
    #: PRD §4.3's repair ladder must be deterministic — a model-chosen cue would
    #: be an extra billed call per repair, and would make the acceptance
    #: fixtures repair differently on each run. But two of the five cues need
    #: *content* (a definition, an L1 gloss) that cannot be derived from the
    #: item. Asking the generator for them up front costs nothing extra: it is
    #: already writing the item, and unused cues are simply never rendered.
    #: `projection.visible_projection` never exposes them.
    definition: str | None = None
    l1_gloss: str | None = None


class MCQItem(BaseItem):
    item_type: Literal["mcq"] = "mcq"
    #: Four, one of which IS the answer. This is the only type where the answer
    #: appearing among the options is correct rather than a leak.
    options: tuple[str, ...]


class ClozeCuedItem(BaseItem):
    item_type: Literal["cloze_cued"] = "cloze_cued"
    #: The gap is `___` inside `prompt_text`; there is no separate field,
    #: because two representations of one gap is how they disagree.


class WordBankOrderItem(BaseItem):
    item_type: Literal["word_bank_order"] = "word_bank_order"
    #: Shuffled tokens. Their multiset must equal the answer's — see `checks`.
    bank: tuple[str, ...]


class ErrorSpotItem(BaseItem):
    item_type: Literal["error_spot"] = "error_spot"
    #: The sentence split into tappable tokens.
    tiles: tuple[str, ...]
    #: Index into `tiles` of the one wrong token.
    wrong_index: int
    #: What that token should have been.
    correction: str


class L1ToL2ProductionItem(BaseItem):
    item_type: Literal["l1_to_l2_production"] = "l1_to_l2_production"
    #: BCP-47-ish tag for the prompt's language. Both learners are `fa`; `lt`
    #: exists because one of them is also a Lithuanian speaker and PRD §1 says
    #: so. The field is here so `checks` can pick the right script test rather
    #: than assume Farsi.
    l1: Literal["fa", "lt"] = "fa"


class DictationItem(BaseItem):
    item_type: Literal["dictation"] = "dictation"
    #: The full sentence is `answer`; the learner hears it and types it.
    #: `prompt_text` is the instruction ("Type what you hear").


class ListeningGapItem(BaseItem):
    item_type: Literal["listening_gap"] = "listening_gap"
    #: What is spoken in full. `prompt_text` is the same sentence with one
    #: `___`, and `answer` is the gapped word.
    transcript: str


class SpeakRepeatItem(BaseItem):
    item_type: Literal["speak_repeat"] = "speak_repeat"
    #: `answer` equals `prompt_text` — the learner repeats what they see.
    #: `checks` asserts that rather than trusting the generator.


class SpeakAnswerItem(BaseItem):
    item_type: Literal["speak_answer"] = "speak_answer"
    #: What a good spoken answer must contain, naming the target. Without it
    #: PRD §4.3 gate 3 is unverifiable for this type, so it is required.
    rubric: str


class MatchPairsItem(BaseItem):
    item_type: Literal["match_pairs"] = "match_pairs"
    #: The bijection. `answer` is None; this is the answer.
    pairs: tuple[tuple[str, str], ...]


class CollocationPickItem(BaseItem):
    item_type: Literal["collocation_pick"] = "collocation_pick"
    #: Three or four candidate collocates for one frame.
    options: tuple[str, ...]


Item = Annotated[
    Union[
        MCQItem,
        ClozeCuedItem,
        WordBankOrderItem,
        ErrorSpotItem,
        L1ToL2ProductionItem,
        DictationItem,
        ListeningGapItem,
        SpeakRepeatItem,
        SpeakAnswerItem,
        MatchPairsItem,
        CollocationPickItem,
    ],
    Field(discriminator="item_type"),
]

MODEL_FOR_TYPE: dict[str, type[BaseItem]] = {
    "mcq": MCQItem,
    "cloze_cued": ClozeCuedItem,
    "word_bank_order": WordBankOrderItem,
    "error_spot": ErrorSpotItem,
    "l1_to_l2_production": L1ToL2ProductionItem,
    "dictation": DictationItem,
    "listening_gap": ListeningGapItem,
    "speak_repeat": SpeakRepeatItem,
    "speak_answer": SpeakAnswerItem,
    "match_pairs": MatchPairsItem,
    "collocation_pick": CollocationPickItem,
}

# Fields promoted to typed columns in migration 012. Everything else on a model
# goes into `items.payload`, and `payload_of` derives that rather than listing
# it — a hand-maintained second list is how a new field silently stops being
# persisted.
_PROMOTED = frozenset(
    {
        "item_type",
        "track",
        "register",
        "prompt_text",
        "answer",
        "accepted_variants",
        "cue_type",
        "lexeme",
        "error_type",
        "unit_number",
    }
)


def parse(raw: dict) -> BaseItem:
    """One JSON object from a generator → a typed item, or a ValidationError."""
    item_type = raw.get("item_type")
    if item_type not in MODEL_FOR_TYPE:
        raise ValueError(
            f"unknown item_type {item_type!r}; PRD §4 names exactly "
            f"{len(ITEM_TYPES)}: {', '.join(ITEM_TYPES)}"
        )
    return MODEL_FOR_TYPE[item_type].model_validate(raw)


def payload_of(item: BaseItem) -> dict:
    """The type-specific half, for `items.payload`.

    Derived by subtracting the promoted columns, so a field added to a model is
    persisted from the moment it exists.
    """
    dumped = item.model_dump(mode="json", by_alias=True)
    return {k: v for k, v in dumped.items() if k not in _PROMOTED}


def payload_keys(item_type: str) -> frozenset[str]:
    """Which `payload` keys this type carries. Read from the model, not a list.

    `§9` of the plan flags payload key names as hard to reverse once thousands
    of rows exist. This function is the single authority a future data migration
    would read, which is what keeps that reversal a one-branch job.
    """
    model = MODEL_FOR_TYPE[item_type]
    wire = {
        (field.serialization_alias or field.alias or name)
        for name, field in model.model_fields.items()
    }
    return frozenset(wire - _PROMOTED)


def hash_contribution(item: BaseItem) -> str:
    """The per-type discriminator that joins `item_type` and the folded stem.

    Default is the folded answer, and ``None`` folds to the empty string. Two
    types override it, for opposite reasons:

    ``match_pairs`` **must** include the mapping. Its `prompt_text` is a
    near-constant instruction ("Match each word to its meaning"), so the default
    would make every `match_pairs` item for one learner hash identically and the
    second would be silently rejected as a duplicate by
    `UNIQUE (user_id, content_hash)`. Pairs are folded and sorted by folded left
    key before serialising, so a shuffled presentation of the same pairs hashes
    the same — correct, because shuffling is not a new item.

    ``speak_answer`` keeps the empty-string default and hashes on the stem
    alone. Two open-production items asking the same question *are* duplicates
    for the learner even when their rubrics name different targets, and letting
    the rubric discriminate would let a generator defeat dedupe by rewording an
    internal field the learner never sees.

    **Distractors deliberately do not participate, for any type.** Same stem
    plus same answer is a duplicate whatever the options around it, and hashing
    them would let a generator defeat dedupe by shuffling one option.
    """
    if isinstance(item, MatchPairsItem):
        pairs = sorted(
            (fold(left), fold(right)) for left, right in item.pairs
        )
        return json.dumps(
            pairs, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    return fold(item.answer)


def content_hash(item: BaseItem) -> str:
    """sha256 over the type, the folded stem and the type's discriminator."""
    material = "\x1f".join(
        (item.item_type, fold(item.prompt_text), hash_contribution(item))
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# Declared so a test can assert the module and the package agree, the same way
# migration 010's CHECK is asserted against `core.lexicon.states`.
assert set(MODEL_FOR_TYPE) == set(ITEM_TYPES)
assert set(CueType.__args__) == set(CUE_TYPES)  # type: ignore[attr-defined]
assert set(Register.__args__) == set(REGISTERS)  # type: ignore[attr-defined]
assert set(Track.__args__) == set(TRACKS)  # type: ignore[attr-defined]
