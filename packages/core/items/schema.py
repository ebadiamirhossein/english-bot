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
from collections.abc import Sequence
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from core.items import CUE_TYPES, ITEM_TYPES, REGISTERS, TRACKS, TYPES_WITHOUT_ANSWER
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

    #: **Which of the unit's 3-5 grammar targets this item tests, verbatim.**
    #:
    #: W10c. `unit_number` says which unit an item belongs to and `error_type`
    #: names one of nineteen coarse journal codes -- and NEITHER can name one of
    #: the 82 grammar targets. All four of unit 1's targets (`past simple`,
    #: `past continuous`, the two in one sentence, `time linkers`) map to the
    #: single code `verb_tense_past`, so an item bound only that way has lost the
    #: thing it was generated against. #169 records the same gap from the other
    #: side: block-3 items link at unit granularity.
    #:
    #: **Bound by the target's exact text**, which is the established convention
    #: rather than a new one: `checkpoint.per_target` is a map keyed by target
    #: string and `core.syllabus.blueprint.validate_checkpoint` already refuses a
    #: key that is not one of the unit's own targets.
    #:
    #: **No migration.** `payload_of` derives `items.payload` by SUBTRACTING the
    #: promoted columns, so this field persists from the moment it exists, and
    #: `services.items.StoredItem.as_item` rehydrates it through `**payload`.
    #: That is exactly the property `payload_of`'s docstring was written to give,
    #: collected here for the first time. `schema_version` stays at 16.
    #:
    #: In `projection.NEVER_VISIBLE`: naming the target on the wire would hand
    #: the blind solver the answer's category, and `probe_target` specifically
    #: must never see it.
    grammar_target: str | None = None

    #: **Which POPULATION this item was generated for: block 3's practice, or a
    #: checkpoint sitting.** W11.
    #:
    #: `focus_items` excludes an unattempted `checkpoint` item and
    #: `checkpoint_items` selects one, so a checkpoint cohort generated on Friday
    #: is still there on Saturday instead of having been served as practice --
    #: `focus_items` orders least-recently-attempted NULLS FIRST, so without this
    #: the freshly generated cohort is exactly what block 3 reaches for.
    #:
    #: **DECLARED, NOT INFERRED, and the alternative was live.** W11's plan
    #: reached review three times carrying a recency proxy -- *withhold the
    #: newest twelve unattempted items of the unit* -- which holds only while the
    #: checkpoint run is the unit's most recent generation. A unit needs 8 + 12 =
    #: 20 items, so there are TWO runs; a block-3 top-up after the checkpoint run
    #: makes the newest twelve *eight top-up items plus four checkpoint ones*,
    #: and the reserve then protects the wrong rows **silently**.
    #:
    #: **`grammar_target`'s precedent, one slice on.** No migration: `payload_of`
    #: derives `items.payload` by SUBTRACTING the promoted columns, so this
    #: persists from the moment it exists and `StoredItem.as_item` rehydrates it
    #: through `**payload`. `content_hash` does not read `payload`
    #: (`item_type`, folded stem, discriminator), so **no existing row's hash
    #: moves**.
    #:
    #: **ABSENT MEANS `focus`, and that is what the fourteen live rows ARE**
    #: rather than a default chosen for convenience: they were written by the
    #: 8-slot block-3 run (`ITEMS_PER_UNIT = 8`). No data pass, no backfill.
    #:
    #: In `NOT_THE_GENERATORS` -- the run's mode is not the model's to choose --
    #: and in `projection.NEVER_VISIBLE`, because telling a learner (or the blind
    #: solver) that an item is a checkpoint item is a category hint.
    cohort: Literal["focus", "checkpoint"] | None = None

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


#: Fields the GENERATOR must not set, because something else owns them.
#:
#: `_draft_to_item` overwrites the first four from the slot -- a generator does
#: not get to reassign an item's unit or its target -- and the repair ladder owns
#: the rest: `cue_type`/`cue_text` are chosen by `repair.apply_cue` from the
#: probe's own wrong answers, and `accepted_variants` is derived by
#: `grading.normalise_variants`. Asking for them would invite a model to author a
#: cue the ladder then overwrites, which is worse than not asking.
NOT_THE_GENERATORS: frozenset[str] = frozenset(
    {
        "item_type",
        "track",
        "unit_number",
        "grammar_target",
        "cohort",
        "cue_type",
        "cue_text",
        # **Added 2026-08-27, and the rule-2 call is what found them.** Both are
        # bindings into tables the generator has no business writing:
        #
        # `error_type` is `TEXT REFERENCES error_types(code)` (012:111) over a
        # closed set of NINETEEN codes. The confirming call returned
        # `error_type: "tense confusion"` on seven of eight drafts -- reasonable
        # English, not a code -- which parses, passes every gate, and then
        # **raises a ForeignKeyViolation inside `insert_item`.** Nothing before
        # the write would have caught it: `parse` has no constraint on the field
        # and every committed fixture uses a real code. It would have surfaced at
        # `--apply`, on production, after a whole run had been paid for.
        #
        # `lexeme` is worse in kind if milder in effect: `insert_item` calls
        # `ensure_lexeme`, which CREATES the row when it is absent
        # (`origin='grown'`). A model-invented lemma therefore writes to
        # `lexemes` silently -- the generator growing the lexicon as a side
        # effect of writing an exercise.
        #
        # Neither is needed: `_shared`'s `no_target` is satisfied by
        # `unit_number`, which `_draft_to_item` always sets.
        "error_type",
        "lexeme",
    }
)

#: How a field's type is described to a model. Deliberately plain English rather
#: than JSON Schema notation: `model_json_schema()` for the eleven types is
#: ~20,000 characters of mostly `$defs` noise, against ~1,500 for this.
_WIRE_TYPE: dict[str, str] = {
    "str": "string",
    "int": "integer",
    "tuple": "array of strings",
}


#: `accepted_variants` is the runner's for every type EXCEPT this one.
#:
#: **It was in `NOT_THE_GENERATORS` and that made `l1_to_l2_production`
#: impossible to pass.** `_draft_to_item` derives the field from `answer` alone,
#: which yields exactly ONE rendering; `checks._l1_production` requires
#: `MIN_ACCEPTED_VARIANTS` (2) because *"the type with the widest legitimate
#: variation... one accepted form is a trap: the learner produces a correct
#: translation and is marked wrong."* So every draft of this type failed
#: `too_few_variants` **deterministically** -- 0/3 in three consecutive runs,
#: nine straight, and a draft obeying the contract perfectly failed too.
#:
#: The exclusion was right in general (the repair ladder and
#: `normalise_variants` own the field) and wrong for the one type whose own
#: checks demand the generator supply it.
VARIANTS_ARE_THE_GENERATORS: frozenset[str] = frozenset({"l1_to_l2_production"})


def generator_contract(item_type: str) -> dict[str, str]:
    """What one item type requires, DERIVED FROM THE MODEL. ``{field: type}``.

    **This exists because `core/prompts/item_generate.txt` never stated the
    contract and a whole billed run died on it.** The prompt named five fields
    and closed with *"the fields that type requires"* -- listing none -- so every
    draft in W10c's third `--live` attempt failed `prompt_text Field required`,
    on a rule the model was never told. The drafts' content was GOOD; they were
    answering a schema nobody showed them.

    **Derived and not hand-written, and that is the whole point.** A field list in
    the prompt text would be a second copy of a schema that lives here, and this
    project's history is drift between a hand-maintained copy and its source:
    #100's stale Build columns, #46's five copies of one regex, `spacing_step`,
    `approved_onboarded_users`, the S24 Meaning/Translation trap. A twelfth item
    type, or a renamed field, must not be able to leave the prompt quietly wrong
    -- so `tests/test_items_contract.py` asserts this against `model_fields` for
    every type.

    **Types are carried, not just names.** A bare list of field names would not
    have prevented the crash that came with the same run: the model returned
    `answer` as an ARRAY, which is defensible for a gap it thought had two
    fillers and which nothing had told it otherwise. `answer (string)` tells it.
    """
    from core.items.checks import MIN_ACCEPTED_VARIANTS

    model = MODEL_FOR_TYPE[item_type]
    out: dict[str, str] = {}
    for name, field in model.model_fields.items():
        wire = field.serialization_alias or field.alias or name
        if wire in NOT_THE_GENERATORS:
            continue
        if wire == "accepted_variants" and item_type not in VARIANTS_ARE_THE_GENERATORS:
            continue
        annotation = field.annotation
        text = str(annotation)
        # `str | None` is a `types.UnionType` with no `__name__`; strip the
        # None arm and describe the base, or the model is handed the phrase
        # "str | None" and has to guess what this codebase means by it.
        base = text.replace("| None", "").replace("Optional[", "").strip(" []")
        raw = getattr(annotation, "__name__", base)
        described = _WIRE_TYPE.get(raw, _WIRE_TYPE.get(base, base))
        if raw == "Literal":
            described = "one of " + "/".join(
                repr(a) for a in getattr(annotation, "__args__", ())
            )
        if wire == "pairs":
            described = "array of [left, right] string pairs"

        # **Optionality comes from `checks.py`, not from the annotation**, and
        # the two genuinely disagree. `answer` is `str | None` on the MODEL
        # because two of the eleven types have no single canonical answer -- but
        # for the other nine `checks._shared`'s `answer_presence` REQUIRES it,
        # and migration 012 mirrors that as a CHECK. Reading optionality off the
        # annotation would tell the generator `answer` is optional for
        # `cloze_cued`, which is the same class of omission that cost attempt 3.
        if wire == "answer":
            note = (
                ", MUST be omitted for this type"
                if item_type in TYPES_WITHOUT_ANSWER
                else " (required)"
            )
        elif wire in ("explanation", "definition", "l1_gloss"):
            note = " (required — see the instructions above)"
        elif wire == "accepted_variants":
            note = (
                " (required — at least "
                f"{MIN_ACCEPTED_VARIANTS}, INCLUDING the one in `answer`)"
            )
        else:
            note = ""
        out[wire] = described + note
    return out


#: Failure codes a type can produce that the prompt does NOT try to express, and
#: why. **An explicit list, because the alternative is silence:** without it a
#: check nobody described looks identical to a check nobody noticed.
#:
#: These are the codes a generator cannot design around by being told about
#: them -- they need the probe's own answer set, a lemma table, or a judgement
#: no instruction can front-run.
NOT_EXPRESSIBLE: dict[str, str] = {
    # Needs the probe: whether a SECOND option is also correct is a fact about
    # English, discovered by asking, not something a rule can state up front.
    "multiple_correct_options": "needs the probe",
    # Needs the lemma table (`looks_proper_noun` -> `core.lexicon`).
    "proper_noun_gap": "needs the lemma table",
    "proper_noun_target": "needs the lemma table",
    # Needs the learner's ledger; measured and not enforced (#197).
    "below_coverage_floor": "measured, not enforced",
    # Structural facts the runner sets, never the generator.
    "no_target": "set by the runner",
    "answer_presence": "stated as a per-field rule instead",
    "answer_not_accepted": "derived by the runner",
    # Applies only to a repaired item, whose cue the ladder chooses.
    "cue_contradicts_answer": "the repair ladder owns the cue",
}


def constraint_block(
    item_types: Sequence[str], *, avoid: Sequence[str] = ()
) -> str:
    """The SHAPE rules each type must satisfy, derived from `core.items.checks`.

    **This exists because the first real accept rate was 6 of 24 and its own
    branch rule was right: the prompt was wrong, not the gate.** The contract
    carried field NAMES and no shape -- a generator told `bank: array of
    strings` has no way to know a word bank must be a permutation of the answer,
    must not already be in order, and must hold between four and ten tokens.
    Every one of those is a `deterministic_failures` rejection, and every one is
    knowable in advance.

    **Derived, not written.** The numbers come from the named constants in
    `checks.py` that the checks themselves read, so a bound cannot be changed in
    one place and stated in the other -- the same guarantee `generator_contract`
    gives for field names, and for the same reason.

    **Honest about its own limits.** The English sentence around each number is
    ours; what is derived is the SET of rules and their VALUES. What keeps the
    set honest is `tests/test_items_contract.py`, which asserts that every
    failure code a type can produce is either expressed here or named in
    `NOT_EXPRESSIBLE` -- so a new check fails a test rather than quietly going
    unstated.

    ── `avoid` — W10d COMMIT 2, F2 ──────────────────────────────────────────
    **THE SENTENCES THE BANK ALREADY HOLDS, SO THE GENERATOR STOPS WRITING THEM
    AGAIN.** This is #299's third cause and the one that decided the slice:
    `seen` is a list of item TYPES, so a second run sent a **byte-identical
    request**, and its output either bounced off `content_hash` or passed as the
    same sentence in different clothes (#169, ids 21 and 29). **More runs on a
    generator that is never told what the bank holds cannot reach 56** -- F1
    raises the target and, without this, sends the whole yield to duplicates.

    **Cheap and it scales:** ~590 input tokens for 40 items, ~800 at 56.
    `GENERATE_MAX_TOKENS` is an OUTPUT budget, so the two never compete.

    **EMPTY MEANS NO SECTION AT ALL, NOT AN EMPTY HEADING.** A first run has
    nothing to avoid; a heading with nothing under it spends tokens saying
    nothing and reads to a model as a constraint it cannot satisfy.

    **WHAT THIS CANNOT DO, AND #271 IS THE RULE: it reduces duplication and
    cannot detect it.** A guard can refuse a bad draft; it can never show the
    model understood. **#169 stays open across both commits of W10d.**
    """
    from core.items.checks import (
        BANK_SIZE,
        COLLOCATION_OPTIONS,
        DICTATION_WORDS,
        MAX_PROMPT_CHARS,
        MAX_SENTENCE_WORDS,
        MCQ_OPTIONS,
        MIN_ACCEPTED_VARIANTS,
        PAIR_COUNT,
        TILE_COUNT,
    )

    shared = [
        f"prompt_text is at most {MAX_PROMPT_CHARS} characters",
        f"the English sentence is at most {MAX_SENTENCE_WORDS} words",
        "nothing you write may pass judgement on the learner",
    ]
    per_type: dict[str, list[str]] = {
        "mcq": [
            f"exactly {'/'.join(str(n) for n in MCQ_OPTIONS)} options",
            "the answer must be one of them, copied character for character",
            "no option may repeat another, or contain another as a substring",
            "the longest option must be under twice the length of the shortest",
        ],
        "collocation_pick": [
            f"{' or '.join(str(n) for n in COLLOCATION_OPTIONS)} options",
            "the answer must be one of them, copied character for character",
            "no option may repeat another, or contain another as a substring",
            "the longest option must be under twice the length of the shortest",
        ],
        "cloze_cued": [
            "exactly one gap, written ___ (three underscores)",
            "never gap a number",
            "the answer must not appear anywhere else in prompt_text",
            "the gapped word must be the one the grammar target is about",
        ],
        "word_bank_order": [
            f"bank holds {BANK_SIZE[0]}-{BANK_SIZE[1]} tokens",
            "the bank must be exactly the words of the answer, reordered — "
            "same words, same count, nothing added or dropped",
            "the bank must NOT already be in the answer's order",
        ],
        "error_spot": [
            "prompt_text is the INSTRUCTION and never the sentence — write "
            "\"Tap the word that is wrong.\" The sentence lives in `tiles` and "
            "is rendered from them; putting it in prompt_text shows it twice "
            "and leaves the learner with no instruction at all",
            f"{TILE_COUNT[0]}-{TILE_COUNT[1]} tiles, one word each",
            "wrong_index points at the ONE wrong tile (0-based)",
            "answer is that wrong tile, copied exactly",
            "correction is what it should say, and must differ from it",
        ],
        "match_pairs": [
            f"{PAIR_COUNT[0]}-{PAIR_COUNT[1]} pairs",
            "no left entry may repeat, and no right entry may repeat",
            "no string may appear on both sides",
        ],
        "l1_to_l2_production": [
            "prompt_text is in the learner's own script, not English",
            "answer is English",
            f"accepted_variants holds at least {MIN_ACCEPTED_VARIANTS} "
            "renderings, INCLUDING the one you put in `answer` — a second "
            "natural way to say the same thing. Supplying only one means a "
            "learner who writes a correct translation is marked wrong",
        ],
        "dictation": [
            f"the sentence is {DICTATION_WORDS[0]}-{DICTATION_WORDS[1]} words",
            "no digits — write numbers as words",
        ],
    }
    lines: list[str] = ["  every type", *(f"    - {rule}" for rule in shared)]
    for item_type in item_types:
        rules = per_type.get(item_type)
        if rules:
            lines.append(f"  {item_type}")
            lines.extend(f"    - {rule}" for rule in rules)
    if avoid:
        lines.append("")
        lines.append(
            "ALREADY IN THIS LEARNER'S BANK — do not write these sentences "
            "again, and do not rephrase them:"
        )
        lines.extend(f"- {one}" for one in avoid)
    return "\n".join(lines)


def contract_block(item_types: Sequence[str]) -> str:
    """The contract for several types, as the lines a prompt carries.

    One place builds this string, so the prompt and the validator cannot disagree
    about what was asked for.
    """
    lines: list[str] = []
    for item_type in item_types:
        fields = generator_contract(item_type)
        rendered = "\n".join(f"    {k}: {v}" for k, v in fields.items())
        lines.append(f"  {item_type}\n{rendered}")
    return "\n".join(lines)


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
