"""What the learner sees, and nothing else. The single serialiser.

PRD §4.3 defines the blind-solver gate as "a second model call sees *only what
the learner will see* — prompt text, cue, options". This module is that "only".

**If the projection leaks the answer the gate becomes a rubber stamp, and every
downstream number still reads green.** That is the failure this whole slice
exists to prevent, one level up: unmarkable items ship, validation records say
they passed, and nothing fails. `tests/test_items_projection.py` asserts, per
type, that the answer string appears nowhere in `json.dumps(projection)` — as a
value or as a substring.

**CROSS-SLICE CONTRACT.** Every learner-visible serialisation goes through this
function and nothing else. `core.services.items.presentations_for` is the single
caller outside this package, and W10's `GET /session/today` hydrates its five
blocks through it rather than building an envelope of its own. If a second
serialiser is written the two drift, the gate silently stops describing what
learners actually see, and the drift is invisible because both halves keep
working on their own terms.

(W5 wrote `GET /session/today` here as W6's. It is W10's — `docs/TASKS-v3-web.md`
line 42. The contract was right; the slice attribution was not.)

Held up by `tests/test_core_boundary.py::test_exactly_one_module_projects_an_item`,
which names the three modules permitted to call this, and by
`::test_the_api_never_reaches_the_hidden_half_of_an_item`.
"""

from __future__ import annotations

from core.items.schema import (
    BaseItem,
    CollocationPickItem,
    ErrorSpotItem,
    L1ToL2ProductionItem,
    MatchPairsItem,
    MCQItem,
    WordBankOrderItem,
)

# Never projected, on any type. Listed rather than derived: a derived exclusion
# list silently stops excluding when a field is renamed, and this is the one
# list in the package where that failure is unrecoverable.
#
# `transcript`, `rubric`, `wrong_index` and `correction` are the non-obvious
# ones. Each is the answer wearing a different hat: the spoken sentence behind a
# listening gap, what a good spoken answer must contain, which tile is wrong,
# and what it should say.
NEVER_VISIBLE: frozenset[str] = frozenset(
    {
        "answer",
        "accepted_variants",
        "explanation",
        "error_type",
        "lexeme",
        "unit_number",
        # W10c. Naming the grammar target on the wire would tell the blind
        # solver what CATEGORY of answer is wanted -- and `gates.probe_target`
        # is asked to recover that category from the item alone, so showing it
        # would make that gate unfalsifiable in the most direct way available.
        "grammar_target",
        # W11. Telling a learner -- or the blind solver, which sees exactly what
        # a learner sees -- that an item belongs to a checkpoint is a hint about
        # the population it was drawn from, and `probe_target` must never be able
        # to tell a checkpoint item from a practice one.
        "cohort",
        "track",
        "register",
        "register_tag",
        "validation",
        "transcript",
        "rubric",
        "wrong_index",
        "correction",
        "cue_type",
        # Cue material the generator authored in advance. Only the cue actually
        # APPLIED is projected, as `cue_text`; the unused ones stay hidden, or
        # a repair ladder would leak every rung at once.
        "definition",
        "l1_gloss",
    }
)


def visible_projection(item: BaseItem) -> dict:
    """The learner-visible face of an item, as a plain JSON-able dict.

    `cue_type` is excluded while `cue_text` is included: the learner sees the
    cue's *text* (`I'_ _ _`, a gloss, a word bank) and never its category name,
    and the category name is a hint about what kind of answer is wanted.
    """
    out: dict = {"item_type": item.item_type, "prompt_text": item.prompt_text}
    if item.cue_text:
        out["cue"] = item.cue_text

    if isinstance(item, (MCQItem, CollocationPickItem)):
        out["options"] = list(item.options)
    elif isinstance(item, WordBankOrderItem):
        out["bank"] = list(item.bank)
    elif isinstance(item, ErrorSpotItem):
        # Tiles yes, `wrong_index` and `correction` emphatically no — the whole
        # task is finding which tile is wrong.
        out["tiles"] = list(item.tiles)
    elif isinstance(item, L1ToL2ProductionItem):
        out["l1"] = item.l1
    elif isinstance(item, MatchPairsItem):
        # The two columns, independently sorted. Sorting rather than shuffling
        # because a random shuffle would make the gate non-reproducible and the
        # acceptance fixtures would solve differently on each run; sorting
        # destroys the pairing just as thoroughly, which is all that is needed.
        out["left"] = sorted(left for left, _ in item.pairs)
        out["right"] = sorted(right for _, right in item.pairs)

    # `dictation`, `listening_gap`, `speak_repeat` and `speak_answer` add
    # nothing: their content is audio, and `speak_answer`'s rubric is internal.
    # `cloze_cued` adds nothing because the gap lives inside `prompt_text`.
    return out
