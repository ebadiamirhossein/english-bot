"""The item generator: eight validated items per unit, past every gate.

**Human-run. Never an acceptance check.** CLAUDE.md §5b bars a slice from making
a billed call, and `tests/conftest.py` makes that structural -- `netguard` is
autouse and session-scoped. This module is the deliberate exception, the same
category as `verify.py`, `seed_fixtures.py` and `core.cards.probe_cloze`:

    python -m core.items.generate --user N                  # dry: prints, sends nothing
    python -m core.items.generate --user N --live           # billed, writes nothing
    python -m core.items.generate --user N --apply          # billed, writes

**What this fills.** PRD §4.1 block 3 is *"this week's grammar target: 90-second
explanation + 8 generated items"*. W10 shipped that block with `items: []` and a
line on the screen reading *"Practice for this arrives with the exercise
generator."* This is the generator. The explanation is W10b.

`core/prompts/item_generate.txt` has existed since W5 and **this module is its
first caller** -- nothing in the tree has ever generated an item.

────────────────────────────────────────────────────────────────────────────────
THE CONSTRAINT THIS IS BUILT AROUND

**The operator cannot verify the English.** Every defect this project caught late
-- the leaked answer (#152), the deploy vocabulary, the double-printed source
line (#154) -- was caught by a person looking at a screen. For a generated grammar
item that instrument is weaker than it looks: an item that is fluent, well-formed
and testing the WRONG POINT reaches two B1 learners who cannot tell.

So the verification is the slice. What the operator's own reading is for is split
three ways, and the split is written here rather than left to be assumed:

  (a) HIS READING, and nothing else, establishes: the item reads as a question
      and not a fragment; the gap sits somewhere sensible; **the Farsi in an
      `l1_to_l2_production` prompt is correct Persian** -- he is the only
      instrument in this project that can check it (#102) -- and eight items in a
      row feel like practice rather than a form.
  (b) THE GATES, and not his reading, establish: uniqueness, naturalness,
      target-first, no-guilt. He reads the stored verdicts, not the English.
  (c) NEITHER establishes whether an item is correct English teaching a correct
      point. That rests on `probe_target`, which is a model checking a model.
      It is not quietly reassigned to a reader who has said he cannot do it.

────────────────────────────────────────────────────────────────────────────────
PRE-REGISTERED PREDICTIONS AND BRANCH RULES

Written here before `--live` was ever executed (#57, W5b, W8b), so the reading
cannot bend once the number arrives. `--live` evaluates every rule itself and
prints the verdict. W8b's transferable finding is carried: **a pre-registered
prediction constrains honesty about the axis it names and says nothing about an
axis it does not** -- so each axis gets its own number.

  P1  ACCEPT RATE -- 12-18 of 24 accepted on the first pass.
      This is the number `docs/TASKS-v3-web.md`'s W10 row asks for and W10
      correctly reported as unmeasurable, having generated nothing.
        >= 19  -> the gates may be weak at this n; P5 decides whether to believe it
        12-18  -> expected. Top up, record which stage caught what
        <= 11  -> THE GENERATOR PROMPT IS WRONG, NOT THE GATE. Fix the prompt and
                  re-run. Do not loosen a gate (CLAUDE.md §3 rule 7)
      Wide and low-centred because nothing has ever been generated under the v3
      gates: the only accept-rate datum in existence is 6/11, on HAND-WRITTEN
      fixtures (#115), and generated items will not be that good.

  P2  TARGET DRIFT -- 0-3 of 24 fail target-first.
        >= 7 -> the prompt is asking for grammar-flavoured sentences rather than
                for demonstrations of a named point. Rewrite the prompt, not the
                check.
      Low because the generator is GIVEN the target verbatim; not zero because
      unit 1's four targets share one tense and are genuinely close.

  P3  NATURALNESS -- 0-5 of 24 rejected by the judge.
        >= 10 -> read them before touching anything. #115 recorded 6/11 on
                 hand-written fixtures and the judge is strict.

  P4  AMBIGUITY -- 3-8 of 24 come back multi_acceptable or not_recoverable
      before repair.
        >= 14 -> grammar gaps are structurally more ambiguous than vocabulary
                 gaps, and the TYPE MIX is the fix, not the gate.

  P5  NEGATIVE CONTROL -- the mis-targeted fixture fails `probe_target` 3 of 3.
      **Pass bar: 2 of 3.** Below 2 of 3 the run is a FAILURE whatever the 24
      items did: the check does not discriminate, nothing is written, exit
      non-zero.
      **The prediction and the bar are different numbers on purpose.** The
      prediction is what a working check should do; the bar is what constitutes
      evidence that it discriminates at all. One stochastic miss on a borderline
      classification is not the same event as a check that cannot tell
      `past simple` from `time linkers`. 2 of 3 prints as
      `prediction NOT MET, run acceptable`, in those words.

  P7  COVERAGE -- 4-10 of 24 accepted items fall below the 90% floor when
      measured against `coverage_reference()` (B1-and-below plus the top 2,000).
        <= 3  -> the floor is compatible with the everyday register after all,
                 and `known_lemmas` should be wired in the slice that has a
                 ledger worth more than the frequency floor
        4-10  -> expected, and it matches the 4-of-8 hand probe. The floor and
                 CLAUDE.md §4's content rule are in genuine tension and the
                 operator rules on which gives
        >= 11 -> the reference is too small for the register, and RAISING THE
                 REFERENCE is the fix, not lowering the floor (rule 7)
      **This axis exists because the alternative was leaving a printed absence
      with no number behind it.** It replaces an argument with an observation.

  P6  PER-TYPE YIELD -- no type accepts 0 of 3. `match_pairs` is the likeliest to.
      **This produces #168's numbers and does NOT close #168.** n is 3 per type
      (6 for `cloze_cued`). A type that is genuinely bad gets 1 of 3 by luck often
      enough that no retention bar at this n could separate it from one that
      works, so no retention bar is written. Closing on n=3 would be a claim true
      of three draws written as a claim about the type -- #82's shape, which this
      record has already counted five times. #168 closes on the 21-unit run,
      where n reaches 24 per type.

────────────────────────────────────────────────────────────────────────────────
WHAT IS MEASURED, AND THE CONFOUND IN MEASURING IT

The item type per slot is PRESCRIBED (see `SLOT_TYPES`), not chosen by the model.
Left to itself a generator writes three `mcq`s and five `cloze_cued`s and four
types get zero evidence -- which is exactly the evidence #168 has waited three
slices for.

**Prescription creates a confound, and it is recorded here where the measurement
is defined rather than as a caveat at the end.** A prescribed slot forces a type
onto whichever target the slot lands on, so a low yield measures EITHER *this
type is weak* OR *this type was asked to carry a target it does not suit*.
`collocation_pick` against *time linkers: then, after that, a bit later* is a
plausible item; `collocation_pick` against *past perfect in reported
explanations* probably is not, **and its rejection says nothing about the type.**

**So yield is reported as `type x target`, never as type alone.** Both fields are
on every row, so the cross-tabulation costs nothing but the table. A type that
fails only against targets it was never suited to is a DIFFERENT FINDING from a
type that fails everywhere, and only the second is an argument for narrowing
`checkpoint.item_types`.

────────────────────────────────────────────────────────────────────────────────
WHAT THIS RUN DOES NOT DO, SAID PLAINLY

* **The coverage floor is MEASURED AND NOT ENFORCED, and the reason is a
  measurement.** `checks.deterministic_failures` enforces PRD §2.1's 90% band
  when handed `known_lemmas`; this run passes None and computes the number
  separately, per item, against `coverage_reference()`. Probed on 2026-08-27:
  against a learner's real ledger **8 of 8** everyday-register sentences fell
  below the floor -- on `dentist`, `landlord`, `neighbour`, `umbrella`, `tram`
  -- **every one of them vocabulary this module's own prompt orders the
  generator to use**; and that ledger is a STRICT SUBSET of the level reference,
  carrying zero per-learner signal. Enforcing it would reject the content
  CLAUDE.md §4 asks for and **P1 would misreport it as a prompt failure**. The
  floor is not lowered (rule 7); its effect becomes **P7**.
* **`assign_daily` still generates nothing** and this module is not wired to it.
  Automating a billed pipeline that writes learner-facing English unattended, on
  content whose quality this slice is the first to measure, is its own slice.
* **One learner.** `items` is per-learner and #159 is unresolved: nothing carries
  a learner's L1 onto the surfaces that write a gloss, so generating for both
  learners today writes Farsi for the Lithuanian one. The rows are NOT copied to
  the second `user_id` -- that costs nothing and ships a silently wrong gloss,
  which is #159's stated failure rather than a shortcut past it.

**No SQL lives here.** The write is `core.services.items.insert_item`, so
`tests/test_core_boundary.py::test_no_sql_outside_services` and
`::test_exactly_one_module_writes_an_item` stay unexempted and #59 remains the
only boundary exemption in this project.

**`logging.basicConfig` at entry -- #140.** `core/llm.py` logs exact per-call
token usage at INFO on every call, and a script that leaves the root logger bare
drops every one of those lines through `logging.lastResort`. That is how W8's
tagger had 138 calls and $6.60 reconstructed after the fact against a $1-2
estimate. **#140 stays open** and still names `judge_observe.py` and `verify.py`,
which both spend and both still leave the root logger bare.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, replace, replace
from pathlib import Path

from pydantic import ValidationError

from core import PROMPTS_DIR
from core.config import Settings, load_settings
from core.items import gates
from core.items.checks import COVERAGE_FLOOR, judged_sentence, sentence_of
from core.items.gates import MAX_REPAIRS, TARGET_DECOYS, TargetVerdict, ValidationReport
from core.items.grading import normalise_variants
from core.items.schema import (
    BaseItem,
    constraint_block,
    contract_block,
    parse,
)
from core.runs import band, confirm
from core.sessions.blocks import visible_targets
from core.syllabus import CHECKPOINT_ITEM_COUNT
from core.syllabus.checkpoint import quota_map as checkpoint_quotas
from core.syllabus.checkpoint import slot_plan as checkpoint_plan

logger = logging.getLogger(__name__)

#: PRD §4.1 block 3: "90-second explanation + **8 generated items**".
ITEMS_PER_UNIT = 8

#: The units this run covers. Three, and units 1-3 rather than a spread, because
#: `core.services.syllabus.current_unit` returns 1 for both learners and cannot
#: advance (#188 -- `user_unit_state` is empty and W11 owns every write to it).
#: Unit 1 is the only unit a learner can actually reach; 2 and 3 exist so the
#: bank is not one unit deep the moment W11 lands, and so #168's per-type sample
#: is 3 rather than 1.
DEFAULT_UNITS = (1, 2, 3)

#: The prescribed type per slot, in order. **Five types across eight slots since
#: the #207 ruling** -- `mcq` and `collocation_pick` are out (see
#: `DROPPED_FOR_GRAMMAR`).
#:
#: **The three doubled slots are chosen, not spread evenly, and each has a
#: reason.** `cloze_cued` because it is the only `slot`-family type here and
#: therefore the only one `repair.LADDER` can rescue. `word_bank_order` and
#: `error_spot` because neither touches `_options_failures` and both test a
#: grammar point directly.
#:
#: **`match_pairs` and `l1_to_l2_production` stay at one each, deliberately.**
#: `match_pairs` is the type with the FEWEST gates in front of it -- its family
#: is `exact`, so `_probe_and_repair` never runs for it and its uniqueness gate
#: is dead code (#192) -- and giving the least-checked type more slots is the
#: wrong direction. `l1_to_l2_production` costs an extra back-translation call
#: each and #102 is unresolved, so one per unit is what the evidence can carry.
#:
#: **Zero TTS and zero STT calls.** `dictation`, `listening_gap`, `speak_repeat`
#: and `speak_answer` are not permitted by units 1-3's blueprints, so
#: `gates._audio_gate` -- which bills two providers -- is never reached.
SLOT_TYPES: tuple[str, ...] = (
    "cloze_cued",
    "word_bank_order",
    "error_spot",
    "match_pairs",
    "l1_to_l2_production",
    "cloze_cued",
    "word_bank_order",
    "error_spot",
)

#: Dropped from the mix on the #207 ruling, 2026-08-27. **Named rather than
#: deleted**, so the next reader sees a decision instead of an absence.
#:
#: `checks._options_failures` rejects any option set where one option contains
#: another -- a GUESSABILITY rule, written in W5 beside `option_length_tell`
#: (*"the odd one out is guessable without reading the stem"*) for a bank of
#: vocabulary items whose options are unrelated words. **For a grammar target it
#: rejects the distractor set the item must have**: `walk / walked / was walking`
#: are substrings of one another because that is what testing a verb form means.
#:
#: These are the only two types that call `_options_failures` (`checks.py:380`
#: and `:649`), so dropping them removes the conflict without touching the rule
#: -- and the rule is right for the population it was written for.
DROPPED_FOR_GRAMMAR: tuple[str, ...] = ("mcq", "collocation_pick")

#: #161 read the syllabus and found that "the only units with a real topic are
#: 18-21 -- work, price and terms, email, collocations". Everything else is
#: grammar with no subject matter, so it is Life. A constant here and NOT a
#: `topic` column on `syllabus_units`, which #161 ruled out.
WORK_UNITS: frozenset[int] = frozenset({18, 19, 20, 21})

#: CEFR bands at or below the learners' current level. PRD §1 puts both at B1
#: heading for B2, so B1-and-below is what "already comprehensible" means today.
COVERAGE_BANDS: frozenset[str] = frozenset({"A1", "A2", "B1"})

#: The frequency tail that is assumed known regardless of CEFR tag -- W4's own
#: `assume_top_frequency_known` number, reused rather than re-chosen.
COVERAGE_FREQ_FLOOR = 2000


def coverage_reference() -> frozenset[str]:
    """The vocabulary a B1 learner is assumed to have. **Not a learner's ledger.**

    ``{lemma : freq_rank <= 2000} | {lemma : cefr in A1/A2/B1}``, read from
    `core.lexicon.normalize.lexeme_rows` -- pure, no database, no per-learner
    read. The same reference W10b's approved plan specifies for lesson prose.

    **Why not `services.lexicon.known_lemmas(user_id)`, which exists and is one
    call away.** Measured on 2026-08-27 against the real ledger rather than
    argued:

    * the ledger is **2,000 lemmas** and is a **STRICT SUBSET** of this
      reference -- `ledger - reference` is EMPTY -- so it carries **zero**
      per-learner signal today. It is W4's top-frequency floor and almost
      nothing has been evidenced on top of it yet.
    * against it, **8 of 8** probe sentences in the everyday register failed the
      90% floor, on `dentist`, `landlord`, `boiler`, `parcel`, `sushi`,
      `neighbour`, `umbrella`, `tram`, `primary` and `leak` -- **every one of
      them vocabulary `item_generate.txt` explicitly instructs the generator to
      use.** Against this reference, 4 of 8.

    A per-learner ledger becomes the right reference the moment it holds more
    than the floor. Today it would reject the content CLAUDE.md §4 asks for,
    while telling the caller nothing a level constant does not.
    """
    from core.lexicon.normalize import lexeme_rows

    return frozenset(
        lemma
        for (lemma, _pos, rank, _band, cefr) in lexeme_rows()
        if (rank and rank <= COVERAGE_FREQ_FLOOR) or cefr in COVERAGE_BANDS
    )


#: Where the run writes its outcomes. **Not under `/tmp`'s auto-cleaned root by
#: accident** -- a record that a reboot deletes is a log. Overridable with
#: `--journal`, and the path is printed at the top of every run so it is never a
#: thing somebody has to know.
DEFAULT_JOURNAL = Path("w10c-journal.jsonl")

#: Where a `--checkpoint` run writes, so a checkpoint cohort and a block-3 cohort
#: never append to one journal -- `read_journal` takes the LAST write per
#: `(unit, slot)`, and two runs sharing a file would make the older one vanish
#: from the report. **In `.gitignore` beside the other two (#231)**: the run
#: writes it at the repo root on the production host, and deploy step 0a's rule
#: is that a non-empty `git status` is a `high` finding -- a guard that fires on
#: every deploy is a guard nobody reads.
DEFAULT_CHECKPOINT_JOURNAL = Path("w11-checkpoint-journal.jsonl")


#: The negative control. Committed so the fixture the check is proved against is
#: readable beside the check.
CONTROL_FIXTURE = Path("tests") / "fixtures" / "items" / "mistargeted.json"

#: P5's bar, and it is deliberately not P5's prediction. See the docstring.
CONTROL_RUNS = 3
CONTROL_MUST_FAIL = 2

#: Pre-registered bands, inclusive. Read by `_verdicts` so the branch rules are
#: applied by the module and not by whoever is looking at the output.
P1_LOW, P1_HIGH = 12, 18
P2_LOW, P2_HIGH = 0, 3
P3_LOW, P3_HIGH = 0, 5
P4_LOW, P4_HIGH = 3, 8
P7_LOW, P7_HIGH = 4, 10


# ── the plan for one unit ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Slot:
    """One of the eight -- or, in `--checkpoint`, one of the twelve.

    `cohort` is what the item is written FOR, and it travels onto the item so
    `focus_items` and `checkpoint_items` can tell the two populations apart. See
    `core.items.schema.BaseItem.cohort` for why it is declared rather than
    inferred from recency.
    """

    index: int
    item_type: str
    target: str
    #: **NO DEFAULT, and that is deliberate — it was `"focus"` until 2026-08-29.**
    #: A default meant *if you forget to say, assume block 3*, and the re-index in
    #: `_reindexed_for_verifier` forgot to say: it rebuilt each Slot by naming
    #: three of four fields, so every topped-up item was written `cohort:
    #: "focus"`. That is production item id 28 (#260) -- an EXPLICIT wrong value,
    #: so `focus_items` served a checkpoint item to block 3 by instruction rather
    #: than by fallback, and the run reported 8 while the bank held 7.
    #: Required, so a missing run mode raises at the point of the mistake instead
    #: of producing a plausible wrong answer.
    cohort: str


def track_for(unit_number: int) -> str:
    return "work" if unit_number in WORK_UNITS else "life"


def slot_plan(unit_number: int, targets: tuple[str, ...]) -> tuple[Slot, ...]:
    """The eight slots for one unit: type prescribed, target rotated.

    **The rotation is offset by the unit number on purpose.** Pairing slot `i`
    with target `i % n` would make `mcq` land on the unit's FIRST target in every
    unit, and the `type x target` cross-tabulation this run exists to produce
    would carry three cells for `mcq` that are all first-targets. Offsetting
    spreads each type across different positions in different units.

    Deterministic, not shuffled -- the same reason `visible_projection` sorts
    `match_pairs`' columns rather than shuffling them: a random plan makes the
    run unreproducible and the numbers unrepeatable.
    """
    if not targets:
        raise ValueError(f"unit {unit_number} has no grammar targets")
    return tuple(
        Slot(
            index=index,
            item_type=item_type,
            target=targets[(index + unit_number) % len(targets)],
            cohort="focus",
        )
        for index, item_type in enumerate(SLOT_TYPES)
    )


def checkpoint_slot_plan(
    unit_number: int,
    per_target: dict[str, int],
    permitted: Sequence[str],
    missed: Sequence[str] = (),
) -> tuple[Slot, ...]:
    """The TWELVE slots for one checkpoint sitting. **A different rule from
    `slot_plan`, and the difference is the whole reason this exists.**

    `slot_plan` spreads eight practice items evenly across a unit's targets by
    rotation. A checkpoint is ALLOCATED: the blueprint says how many items each
    target gets, and a RETAKE re-weights that toward the targets the learner
    missed. Rotating a checkpoint would ignore `checkpoint.per_target`, which
    until W11 nothing in this tree had ever read for anything but validation.

    **The quota map is `core.syllabus.checkpoint.quota_map`'s, and this function
    does not compute it.** `core.services.items.checkpoint_items` calls the same
    producer to know what to SELECT, so the generator and the selector cannot
    disagree -- and if they did, a re-weighted retake cohort could never be
    selected and the fail path would refuse every time.
    """
    quotas = checkpoint_quotas(per_target, missed)
    return tuple(
        Slot(
            index=one.index,
            item_type=one.item_type,
            target=one.target,
            cohort="checkpoint",
        )
        for one in checkpoint_plan(unit_number, quotas, tuple(permitted))
    )



def _shortfall_slots(
    slots: tuple[Slot, ...],
    demand: dict[str, int],
    held: dict[str, int],
) -> tuple[Slot, ...]:
    """The sitting's plan, minus what the learner already holds. **`--fill`.**

    **THE SUBTRACTION HAPPENS AFTER THE PLAN, NOT INSTEAD OF IT, AND THAT IS THE
    WHOLE DESIGN.** `core.syllabus.checkpoint.slot_plan` REFUSES a quota map that
    does not sum to twelve -- *a sitting is twelve* -- and that guard is right and
    is not relaxed. So the full twelve are planned first, through the single
    producer and past its guard, and the surplus is dropped here. Nothing
    recomputes what to generate; this only removes.

    **THE FRONT OF THE ROTATION IS KEPT** (operator ruling, 2026-08-29). Within a
    target the retained slots are the first N, so the choice is deterministic and
    a fill run's type mix is the front of the sitting's rotation rather than the
    sitting's mix. That is intended: **the sitting's type mix is a property of the
    sitting, and the bank only needs items on the target.**

    A target already at or over its demand yields nothing. A held count larger
    than the demand is not an error -- a re-weighted retake can want fewer of a
    target than a first sitting bought -- so it clamps at zero rather than
    raising.
    """
    wanted = {t: max(0, demand.get(t, 0) - held.get(t, 0)) for t in demand}
    kept: list[Slot] = []
    taken: dict[str, int] = {}
    for one in slots:
        if taken.get(one.target, 0) < wanted.get(one.target, 0):
            kept.append(one)
            taken[one.target] = taken.get(one.target, 0) + 1
    # **RE-INDEXED 0..n-1, and this line is the whole of #261.**
    #
    # The first version returned the kept slots carrying THEIR INDICES FROM THE
    # FULL TWELVE. `build_payload` then asked for four items, the model returned
    # `drafts[0..3]`, and `verify_cohort` read `drafts[slot.index]` for indices
    # `[0, 1, 5, 6]` -- so two slots were `missing_draft` before the model's work
    # was ever looked at, and `_top_up`'s `merged[original.slot.index]` raised
    # `IndexError` on a length-4 list, which the top-up's own `except` turned into
    # "TOP-UP FAILED". **The model was never at fault and its drafts were never
    # read.**
    #
    # **It looked like a target problem and was positional**, because the
    # surviving indices are always the LATER ones in the quota order -- so every
    # small fill on unit 1 fails on past continuous, deterministically, and would
    # have gone on looking like evidence about that target.
    #
    # `_reindexed_for_verifier` is the SAME function #260 needed, reused rather
    # than re-written: it is `dataclasses.replace`, so `cohort` and every future
    # field travel with the slot.
    return _reindexed_for_verifier(tuple(kept))


def target_candidates(
    unit_number: int, targets: tuple[str, ...], other_units: dict[int, tuple[str, ...]]
) -> tuple[str, ...]:
    """`probe_target`'s candidate list: this unit's targets plus decoys.

    **The unit's own targets are the decoys that matter.** Unit 1's four points
    are all past-tense and are each other's nearest neighbours, so an item that
    has drifted from *past continuous* to *past simple* ranks a sibling first and
    fails. Decoys from other units make a confidently wrong answer visible; they
    are not what discriminates.

    Decoys are taken deterministically -- the nearest units by number, first
    target each -- so a re-run asks the same question. Sorted at the call site by
    `gates.probe_target`, so authored order carries no information either.
    """
    own = tuple(targets)
    decoys: list[str] = []
    for number in sorted(other_units, key=lambda n: (abs(n - unit_number), n)):
        if number == unit_number:
            continue
        for candidate in other_units[number]:
            if candidate not in own and candidate not in decoys:
                decoys.append(candidate)
                break
        if len(decoys) >= TARGET_DECOYS:
            break
    return own + tuple(decoys)


def _assert_indices_addressable(slots: tuple[Slot, ...]) -> None:
    """**Every slot must be able to find its own draft. #261's guard.**

    The model is asked for `len(slots)` items and returns them in order, so
    `verify_cohort` reads `drafts[slot.index]`. A slot whose index is >= the
    number requested can never be matched to a draft: it is `missing_draft`
    before the response is looked at, and the failure is attributed to the model
    and to whatever target that slot happened to carry.

    **This is asserted where the payload is BUILT rather than where the drafts
    come back**, because by then the run has been billed. A plan that cannot
    address its own answers is a bug in the planner, and it is refused before a
    call is made.
    """
    out_of_range = [one for one in slots if one.index >= len(slots)]
    if out_of_range:
        raise ValueError(
            f"slot index {[o.index for o in out_of_range]} >= {len(slots)} "
            f"requested items — this plan cannot address its own drafts; "
            f"re-index with `_reindexed_for_verifier` before sending it "
            f"(targets: {sorted({o.target for o in out_of_range})})"
        )


def build_payload(unit_number: int, can_do: str, slots: tuple[Slot, ...]) -> dict:
    """The user message for one unit's generation call. **No citation reaches it.**

    `can_do` and the target TEXT and nothing else. The targets arrive through
    `core.sessions.blocks.visible_targets` at the call site -- the seam #171's
    ruling is asserted at -- so `murphy_units` was never in the object this
    function is handed. **This matters more here than on any screen**: a rendered
    citation is visible and removable, and an assumption embedded in a generated
    sentence is neither.
    """
    _assert_indices_addressable(tuple(slots))
    return {
        "unit_number": unit_number,
        "can_do": can_do,
        "track": track_for(unit_number),
        # **`n` was REMOVED after attempt 3.** It was the runner's own slot
        # number, sent as a per-item key -- and a model that mirrors the input
        # shape echoed it back, where `BaseItem`'s `extra="forbid"` rejected
        # every item. Order carries the same information and cannot be echoed:
        # the prompt asks for one item per slot in the order requested, and
        # `verify_cohort` reads `drafts[slot.index]`.
        "items": [
            {"item_type": slot.item_type, "grammar_target": slot.target}
            for slot in slots
        ],
    }


# ── one item's fate ─────────────────────────────────────────────────────────


@dataclass
class Outcome:
    """One slot, start to finish. Every field a report or a table needs."""

    slot: Slot
    unit_number: int
    item: BaseItem | None = None
    report: ValidationReport | None = None
    target: TargetVerdict | None = None
    back_translation: str | None = None
    #: Known-word coverage of this item's sentence against `coverage_reference`,
    #: as a percentage. **MEASURED, NEVER ENFORCED IN THIS RUN** -- see
    #: `_measure_coverage` for why the floor is reported rather than applied.
    coverage_pct: float | None = None
    coverage_unknown: tuple[str, ...] = ()
    #: "accepted" | "discarded" | "duplicate"
    state: str = "discarded"
    #: Which stage ended it: generation / deterministic / naturalness / judge /
    #: probe / target. `None` when it was accepted.
    stage: str | None = None
    codes: tuple[str, ...] = ()
    item_id: int | None = None
    topped_up: bool = False

    @property
    def accepted(self) -> bool:
        return self.state == "accepted"


def _discard(slot: Slot, unit: int, stage: str, *codes: str) -> Outcome:
    """A slot that never became an item. Used only before one exists."""
    return Outcome(
        slot=slot, unit_number=unit, state="discarded", stage=stage,
        codes=tuple(codes),
    )


def _fail(outcome: Outcome, stage: str, *codes: str) -> None:
    """Mark an existing outcome discarded **without losing what it gathered.**

    Mutates rather than rebuilding, and that is the whole reason it exists: the
    first draft of this module replaced `outcomes[position]` with a fresh
    `Outcome`, which threw away the `ValidationReport` and the `TargetVerdict`
    attached moments earlier -- the diagnostics that say WHY an item was
    rejected, which is the entire value of the run.
    """
    outcome.state = "discarded"
    outcome.stage = stage
    outcome.codes = tuple(str(c) for c in codes if c)


def _draft_to_item(raw: dict, slot: Slot, unit_number: int) -> BaseItem:
    """One JSON object from the generator -> a typed item bound to its slot.

    **The bindings are set here, not trusted from the model.** `track`,
    `unit_number` and `grammar_target` are facts the caller already knows, and a
    generator that got one wrong would otherwise write an item into the wrong
    unit. The model is still ASKED to echo `grammar_target`, and the echo is
    compared before this runs -- asking it to commit to the target while writing
    is worth a free check, and overwriting silently would have destroyed the
    evidence that it disagreed.
    """
    draft = dict(raw)
    draft["item_type"] = slot.item_type
    draft["track"] = track_for(unit_number)
    draft["unit_number"] = unit_number
    draft["grammar_target"] = slot.target
    draft["cohort"] = slot.cohort

    answer = draft.get("answer")
    if answer is not None and not isinstance(answer, str):
        # **This line is here because it CRASHED.** Attempt 3, unit 1 item 2:
        # the model returned `answer` as an ARRAY -- defensible for a gap it
        # believed had two fillers, and nothing in the prompt said otherwise --
        # and `normalise_variants` handed it to `fold_apostrophes`, which called
        # `.translate()` on a list. `'list' object has no attribute 'translate'`
        # was reported as `schema_error`, i.e. as the model's fault.
        #
        # The contract now tells the generator `answer` is a string, and this
        # refuses one that is not. **Both, deliberately:** the contract stops it
        # being sent, and the guard stops us crashing on whatever does arrive.
        # A `ValueError` here is caught as a MODEL failure, which is what it is.
        raise ValueError(
            f"answer must be a string, got {type(answer).__name__}: {answer!r}"
        )

    if answer is not None and not draft.get("accepted_variants"):
        draft["accepted_variants"] = list(normalise_variants(answer))
    return parse(draft)


# ── the cohort: one unit, eight slots, cheapest gate first ──────────────────


def generator_system_prompt(item_types: Sequence[str] = SLOT_TYPES) -> str:
    """`item_generate.txt` with the field contract substituted in.

    **The contract is DERIVED from `core.items.schema`, never written here.**
    W10c's third `--live` attempt died because the prompt closed with *"the
    fields that type requires"* and listed none: every draft failed
    `prompt_text Field required`, on a rule the model was never told, while the
    CONTENT it produced was good. A hand-written list in the prompt file would be
    a second copy of a schema that lives in code, and this record is largely a
    history of those two drifting apart.
    """
    template = (PROMPTS_DIR / "item_generate.txt").read_text(encoding="utf-8")
    seen: list[str] = []
    for item_type in item_types:
        if item_type not in seen:
            seen.append(item_type)
    return (
        template
        .replace("{contract}", contract_block(seen))
        .replace("{constraints}", constraint_block(seen))
    )


def generate_drafts(
    payload: dict, *, settings: Settings | None = None
) -> list[dict]:
    """One billed call. The raw drafts, in the order the model returned them."""
    response = gates._chat(
        [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        system=generator_system_prompt(),
        json_mode=True,
        max_tokens=GENERATE_MAX_TOKENS,
        reject_truncation=True,
        settings=settings,
    )
    if not isinstance(response, dict):
        raise gates.LLMError("generator did not return an object")
    drafts = response.get("items")
    return [d for d in drafts if isinstance(d, dict)] if isinstance(drafts, list) else []


#: Eight items with explanations and cue material. Generous, and
#: `reject_truncation=True` means a response that needs more is a failure rather
#: than a silently half-written cohort.
#: **16,000, raised from 8,000 on the 2026-08-27 ruling.**
#:
#: `settings.llm_model` is `claude-sonnet-5`, and **omitting the `thinking`
#: parameter runs ADAPTIVE THINKING** on that model -- `core/llm.py` never sets
#: it, so thinking has been on for every call this project has made. **Thinking
#: tokens are billed and count against `max_tokens`**, which is therefore a
#: ceiling on reasoning PLUS text. Attempt 4's top-up spent the whole 8,000 on
#: thinking and returned `blocks=['ThinkingBlock','TextBlock']` with an empty
#: text block.
#:
#: **This RETURNS TO A DEFAULT rather than picking a number:** the Anthropic
#: reference's own guidance for non-streaming requests is ~16,000, and 8,000 was
#: below it.
#:
#: **`output_config.effort` is deliberately NOT touched.** It defaults to `high`
#: and controls thinking depth, so lowering it would change item quality --
#: **before P1 has ever been read.** That would contaminate the first real
#: measurement of the accept rate with a change to the thing being measured.
GENERATE_MAX_TOKENS = 16000


def verify_cohort(
    slots: tuple[Slot, ...],
    drafts: list[dict],
    *,
    unit_number: int,
    candidates: tuple[str, ...],
    settings: Settings | None = None,
    calls: Counter | None = None,
    reference: frozenset[str] | None = None,
) -> list[Outcome]:
    """Every gate over one unit's cohort, cheapest first, batching the judge.

    **The ordering is `gates.validate`'s, lifted to the cohort.** Each stage may
    only cost money once every free stage has said yes -- so the free stages run
    over all eight drafts first, the naturalness judge runs ONCE over the
    survivors, and only then does anything probe.

    **This is the first caller of `gates.JUDGE_BATCH` in the project's history.**
    It has been declared since W5 and `validate` has always called
    `judge_naturalness([sentence])` -- one sentence at a time (#120). Eight calls
    become one. **It does not close #120**: `validate(judge=True)`'s per-item call
    is still there for `verify.py` and `seed_fixtures.py`, which validate one item
    at a time and have nothing to batch with.
    """
    spent = calls if calls is not None else Counter()
    outcomes: list[Outcome] = []
    survivors: list[tuple[int, BaseItem]] = []

    # --- stage 0: the model returned something item-shaped, for the right slot
    for slot in slots:
        raw = drafts[slot.index] if slot.index < len(drafts) else None
        if raw is None:
            outcomes.append(_discard(slot, unit_number, "generation", "missing_draft"))
            continue
        echoed = str(raw.get("grammar_target", "") or "").strip()
        if echoed and echoed != slot.target:
            # Free, and it catches the model quietly reassigning itself to a
            # neighbouring point -- which is P2's failure arriving one stage
            # earlier and for nothing.
            outcomes.append(
                _discard(slot, unit_number, "generation", "target_echo_mismatch")
            )
            continue
        if str(raw.get("item_type", slot.item_type)) != slot.item_type:
            outcomes.append(
                _discard(slot, unit_number, "generation", "item_type_mismatch")
            )
            continue
        try:
            item = _draft_to_item(raw, slot, unit_number)
        except (ValidationError, ValueError) as exc:
            # The MODEL's fault: a field missing, an extra field, a wrong type.
            outcomes.append(
                _discard(slot, unit_number, "generation", f"schema_error: {exc}"[:200])
            )
            continue
        except Exception as exc:  # noqa: BLE001 — see below
            # **OURS.** Anything that is not a validation failure is a bug in
            # this runner, and labelling it `schema_error` blamed the model for
            # our own crash. Attempt 3 hid `'list' object has no attribute
            # 'translate'` -- a real `AttributeError` on `generate.py`'s own line
            # -- under that label, and the comment on the old bare `except`
            # read *"pydantic ValidationError, ValueError"*: **it named a
            # narrower catch than the code performed.**
            #
            # It is still caught rather than raised, because a run that has
            # already been paid for must finish and report; but it is reported
            # as `runner_error`, at its own stage, and **logged with a
            # traceback**, which `schema_error` never was.
            logger.exception(
                "runner crash on unit %s slot %s (%s)",
                unit_number, slot.index + 1, slot.item_type,
            )
            outcomes.append(
                _discard(slot, unit_number, "runner", f"runner_error: {exc}"[:200])
            )
            continue
        outcomes.append(Outcome(slot=slot, unit_number=unit_number, item=item))
        survivors.append((len(outcomes) - 1, item))

    # --- stage 1: every free gate, for all survivors, before anything is billed
    judged: list[tuple[int, BaseItem]] = []
    for position, item in survivors:
        item, failed = gates.free_stages(item)
        if failed is not None:
            report = failed.report
            outcomes[position].report = report
            _fail(
                outcomes[position],
                "deterministic" if report.deterministic else "naturalness",
                *(report.deterministic or report.naturalness),
            )
            continue
        outcomes[position].item = item
        _measure_coverage(outcomes[position], reference)
        judged.append((position, item))

    # --- stage 2: ONE naturalness call for the whole cohort (#120)
    sentences: list[str] = []
    judged_positions: list[int] = []
    for position, item in judged:
        sentence = judged_sentence(item)
        if sentence.strip():
            sentences.append(sentence)
            judged_positions.append(position)
    if sentences:
        verdicts = gates.judge_naturalness(sentences, settings=settings)
        spent["naturalness"] += 1
        for position, verdict in zip(judged_positions, verdicts, strict=True):
            if not verdict.natural:
                outcomes[position].report = ValidationReport(
                    "discarded", naturalness=("unnatural",),
                    naturalness_reason=verdict.reason,
                )
                # The judge's one-word reason is CARRIED, not dropped. Parsing a
                # diagnostic and discarding it one line later is #119, and it
                # cost this project the whole of W5b.
                _fail(outcomes[position], "judge", "unnatural", verdict.reason)

    # --- stage 3: the probe, per item, with the repair ladder
    #
    # `MAX_REPAIRS` is unchanged and untouched: it applies to the `slot` family,
    # which is `cloze_cued` here. `fixed_option` and `message` items are
    # discarded on the first probe by design -- a cue cannot rescue an item whose
    # options are already on screen.
    for position, item in judged:
        outcome = outcomes[position]
        if outcome.stage is not None:
            continue
        result = gates.validate(item, settings=settings, judge=False)
        outcome.report = result.report
        spent["probe"] += max(result.report.solver_calls, 0)
        if not result.report.ok or result.item is None:
            _fail(
                outcome, "probe",
                *(result.report.blind_solver or result.report.deterministic
                  or ("discarded",)),
            )
            continue
        outcome.item = result.item

    # --- stage 4: does it test the target it claims? (W10c)
    for position, _ in judged:
        outcome = outcomes[position]
        if outcome.stage is not None or outcome.item is None:
            continue
        verdict = gates.probe_target(
            outcome.item,
            claimed=outcome.slot.target,
            candidates=candidates,
            settings=settings,
        )
        spent["target"] += 1
        outcome.target = verdict
        # #194. The verdict was printed and then lost, so the evidence for
        # "this item tests its target" survived only in a run's stdout. It now
        # travels into `items.validation` on the report that will be written --
        # including the RUNNER-UP, which on a PASSING item is the distinction it
        # came closest to blurring. No migration: `items.validation` is JSONB and
        # 012's CHECK requires three keys rather than forbidding a fourth.
        # `replace` and not attribute assignment: `ValidationReport` is
        # `frozen=True, slots=True`, so the mutating form raises at runtime and
        # would have done so on the first real run.
        if outcome.report is not None:
            outcome.report = replace(
                outcome.report,
                target_ranking=tuple(verdict.ranking),
                target_claimed_rank=verdict.claimed_rank,
                target_first=verdict.first,
                target_runner_up=verdict.runner_up,
                target_confidence=verdict.confidence,
            )
        if not verdict.ok:
            _fail(outcome, "target", f"ranked_{verdict.claimed_rank or 'absent'}")
            continue
        outcome.state = "accepted"

        # #102's evidence, for `l1_to_l2_production` only. Produced, printed
        # beside the item's own L1 prompt, and NOT compared in code -- see
        # `gates.back_translate` for why the planned comparison was inert.
        if outcome.item.item_type == "l1_to_l2_production":
            try:
                outcome.back_translation = gates.back_translate(
                    outcome.item, settings=settings
                )
                spent["backtranslate"] += 1
            except gates.LLMError as exc:
                logger.warning("back-translation failed: %s", exc)

    return outcomes


# ── the journal: the run's record, on disk, as it happens ───────────────────


def journal_line(outcome: Outcome) -> dict:
    """One outcome, flattened to everything the report needs to be rebuilt.

    **Everything, because the file is the record and not a summary of it.** If a
    field is needed to print the report or recompute the accounting, it is here;
    otherwise `--report` would be a lossy view and the file would be a log.
    """
    item = outcome.item
    report = outcome.report
    target = outcome.target
    return {
        "unit": outcome.unit_number,
        "slot": outcome.slot.index,
        "item_type": outcome.slot.item_type,
        "target": outcome.slot.target,
        "state": outcome.state,
        "stage": outcome.stage,
        "codes": list(outcome.codes),
        "topped_up": outcome.topped_up,
        "item": None if item is None else {
            "prompt_text": item.prompt_text,
            "answer": item.answer,
            "explanation": item.explanation,
            "cue_text": item.cue_text,
            "options": list(getattr(item, "options", ()) or ()),
            "bank": list(getattr(item, "bank", ()) or ()),
            "tiles": list(getattr(item, "tiles", ()) or ()),
            "pairs": [list(pair) for pair in getattr(item, "pairs", ()) or ()],
        },
        "validation": None if report is None else report.as_json(),
        "target_rank": None if target is None else target.claimed_rank,
        "target_first": None if target is None else target.first,
        "target_runner_up": None if target is None else target.runner_up,
        "target_confidence": None if target is None else target.confidence,
        "coverage_pct": outcome.coverage_pct,
        "coverage_unknown": list(outcome.coverage_unknown),
        "back_translation": outcome.back_translation,
    }


class Journal:
    """Append-only JSONL. **The report survives the run, not the other way round.**

    **Why this exists, and it is a class of defect rather than one bug.** W10c
    lost its diagnostics twice, for two unrelated reasons: the third attempt was
    piped through `tail -60` and the per-slot codes were cut; the fourth crashed
    inside `_top_up` and the traceback ended the process before `_print_items`
    ever ran. **Both times the report depended on the run surviving, and both
    times the cheapest information in the slice was the thing destroyed** -- while
    the model calls that produced it had already been paid for.

    Fixing either symptom leaves the class alone. So the outcomes are written to
    disk **as each cohort is decided**, before anything downstream can fail, and
    `_print_items` and the accounting become VIEWS of the file. A crash costs the
    remainder of the run and nothing that was already established.

    **Flushed on every write.** A buffered journal is the same defect with a
    smaller window: the process dies and the last cohort -- the one that was
    being worked on when it died, and therefore the interesting one -- is the
    part still sitting in the buffer.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.written = 0

    def record(self, outcomes: Sequence[Outcome]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            for outcome in outcomes:
                handle.write(
                    json.dumps(journal_line(outcome), ensure_ascii=False) + "\n"
                )
                self.written += 1
            handle.flush()


def read_journal(path: Path) -> list[dict]:
    """The run, back off disk. **Last write per (unit, slot) wins.**

    A topped-up slot is written twice -- once when the initial cohort was decided
    and once when its replacement was -- and the second is the outcome that
    stands. Ordering by file position rather than by a timestamp keeps this
    independent of the clock, which `Date.now`-free reproducibility elsewhere in
    this project already depends on.
    """
    latest: dict[tuple[int, int], dict] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        latest[(row["unit"], row["slot"])] = row
    return [latest[key] for key in sorted(latest)]


# ── the accounting ──────────────────────────────────────────────────────────


@dataclass
class Tally:
    """The identity the run prints, per unit and in total.

        drafted  = accepted + discarded + duplicate
        accepted = passed + repaired
        served   = accepted, against THE PLAN THAT WAS BUILT (#262) —
                   the number of distinct slots this unit's journal
                   rows carry, so it is 8 for block 3, 12 for a
                   checkpoint and the shortfall for a `--fill` run

    **A count that does not balance is printed as a finding**, not quietly
    reconciled. `balances` is checked and reported rather than asserted, because
    a crash here would destroy the evidence of a run that has already been paid
    for.
    """

    drafted: int = 0
    accepted: int = 0
    duplicate: int = 0
    discarded: int = 0
    repaired: int = 0
    by_stage: Counter = field(default_factory=Counter)
    by_code: Counter = field(default_factory=Counter)

    @property
    def balances(self) -> bool:
        return self.drafted == self.accepted + self.discarded + self.duplicate

    def add(self, row: dict) -> None:
        """One JOURNAL ROW, not an `Outcome`.

        The accounting reads the file so that it is recomputable without
        re-buying anything -- which is the property the whole journal exists for.
        Taking an `Outcome` here would leave a second path that only works while
        the process is alive, and the two would drift the first time one gained a
        field.
        """
        self.drafted += 1
        state = row.get("state")
        if state == "accepted":
            self.accepted += 1
            validation = row.get("validation") or {}
            if validation.get("repair_count"):
                self.repaired += 1
        elif state == "duplicate":
            self.duplicate += 1
        else:
            self.discarded += 1
            self.by_stage[row.get("stage") or "unknown"] += 1
            for code in row.get("codes") or ():
                self.by_code[code] += 1


def tally_of(rows: Sequence[dict]) -> Tally:
    out = Tally()
    for row in rows:
        out.add(row)
    return out


def _print_tally(name: str, tally: Tally, *, target: int | None) -> None:
    served = f"{tally.accepted}/{target}" if target else str(tally.accepted)
    flag = ""
    if target and tally.accepted < target:
        flag = f"   ** SHORT BY {target - tally.accepted} **"
    print(
        f"  {name:<10} drafted {tally.drafted:>3} · accepted {tally.accepted:>3} "
        f"(repaired {tally.repaired}) · discarded {tally.discarded:>3} · "
        f"duplicate {tally.duplicate:>3} · served {served}{flag}"
    )
    if tally.by_stage:
        stages = " · ".join(f"{k} {v}" for k, v in sorted(tally.by_stage.items()))
        print(f"             discarded by stage: {stages}")
    if not tally.balances:
        print(
            f"             FINDING: drafted {tally.drafted} != "
            f"{tally.accepted}+{tally.discarded}+{tally.duplicate}. "
            "The identity does not balance; do not reconcile this by hand."
        )


def _print_cross_tab(rows: Sequence[dict]) -> None:
    """#168's numbers: `type x target`, never type alone.

    A type that fails only against targets it was never suited to is a different
    finding from a type that fails everywhere, and only the second is an argument
    for narrowing `checkpoint.item_types`. Printing type alone would merge them.
    """
    print("\n#168 — yield by TYPE x TARGET. n is small; see P6.")
    def _ok(r: dict) -> bool:
        return r.get("state") == "accepted"

    cells: dict[tuple[str, str], list[dict]] = {}
    by_type: dict[str, list[dict]] = {}
    for row in rows:
        cells.setdefault((row["item_type"], row["target"]), []).append(row)
        by_type.setdefault(row["item_type"], []).append(row)

    for item_type in sorted(by_type):
        group = by_type[item_type]
        accepted = sum(1 for r in group if _ok(r))
        print(f"\n  {item_type}  —  {accepted}/{len(group)} accepted")
        for (cell_type, target), entries in sorted(cells.items()):
            if cell_type != item_type:
                continue
            ok = sum(1 for e in entries if _ok(e))
            stages = Counter(
                e.get("stage") for e in entries if not _ok(e) and e.get("stage")
            )
            why = ("  " + ", ".join(f"{k}:{v}" for k, v in sorted(stages.items()))) if stages else ""
            print(f"      {ok}/{len(entries)}  u{entries[0]['unit']}  {target!r}{why}")

    zero = [t for t, group in by_type.items() if not any(_ok(r) for r in group)]
    if zero:
        print(
            f"\n  ZERO ACCEPTED: {sorted(zero)}. **This does not by itself justify "
            "removing a type\n  from `checkpoint.item_types`** — n is 3 (6 for "
            "cloze_cued) and no bar at that n\n  separates a bad type from an "
            "unlucky one. A removal needs a STRUCTURAL finding\n  beside it; today "
            "`match_pairs` is the only type that has one (its uniqueness\n  gate is "
            "unreachable — see the known issues). #168 stays open."
        )


def _print_targets(rows: Sequence[dict]) -> None:
    """Where the claimed target ranked, and what came second.

    **The runner-up is recorded on items that PASSED** (#119). When the claimed
    target wins, second place is the distinction the item came closest to
    blurring, and it is the single most useful line for whoever rewrites the
    generator prompt. A gate that reports only pass/fail throws that away.
    """
    interesting = [r for r in rows if r.get("target_rank") is not None
                   or r.get("target_first") is not None]
    if not interesting:
        return
    print("\nprobe_target — rank of the claimed target, and the runner-up:")
    for row in sorted(interesting, key=lambda r: (r["unit"], r["slot"])):
        rank = row.get("target_rank")
        mark = "ok " if rank == 1 else "**FAIL**"
        runner = (f" · runner-up {row['target_runner_up']!r}"
                  if row.get("target_runner_up") else "")
        print(
            f"  {mark} u{row['unit']} slot {row['slot'] + 1} "
            f"{row['item_type']:<20} rank {rank or 'absent'}"
            f" ({row.get('target_confidence') or '-'}){runner}"
        )
        if rank != 1 and row.get("target_first"):
            print(f"        ranked first instead: {row['target_first']!r}")


def _print_back_translations(rows: Sequence[dict]) -> None:
    """#102's evidence, for a person. **Nothing here is compared in code.**

    `l1_to_l2_production`'s canonical is trusted and not verified: no gate is
    shown both sides of the relation. The planned fix was to back-translate and
    compare with `grading.equivalence_key` — **and that comparison is inert**,
    because `equivalence_key` tokenises on `[A-Za-z]` and every Farsi string
    folds to the empty tuple, so any two compare equal and a completely wrong
    rendering would pass silently.

    So the two strings are printed side by side and the comparison belongs to the
    operator, who is the only Persian reader in this project. **#102 does not
    close and its severity is unchanged.**
    """
    pairs = [r for r in rows if r.get("back_translation")]
    if not pairs:
        return
    print(
        "\n#102 — READ THESE TWO LINES AGAINST EACH OTHER. Nothing in this "
        "pipeline can.\n  The gates never see both sides of an L1→L2 relation; "
        "you are the only reader who does."
    )
    for row in pairs:
        item = row.get("item") or {}
        print(f"\n  u{row['unit']} slot {row['slot'] + 1}")
        print(f"    prompt as authored : {item.get('prompt_text')}")
        print(f"    English answer     : {item.get('answer')}")
        print(f"    back-translated    : {row['back_translation']}")


def _print_report(
    rows: Sequence[dict], numbers: Sequence[int], control: "ControlResult"
) -> None:
    """The whole report, from journal rows. **`run` and `--report` share it.**

    One function, so a run's output and a rebuild from disk cannot differ. Two
    renderers would be two descriptions of one file, and the one nobody looks at
    is the one that goes wrong.
    """
    by_unit: dict[int, list[dict]] = {}
    for row in rows:
        by_unit.setdefault(row["unit"], []).append(row)

    for number in numbers:
        if number not in by_unit:
            continue
        print("\n" + "=" * 78)
        print(f"UNIT {number}")
        print("=" * 78)
        _print_items(by_unit[number])

    print("\n" + "=" * 78)
    print("ACCOUNTING — drafted = accepted + discarded + duplicate")
    print("=" * 78)
    # **THE DENOMINATOR IS THE PLAN THAT WAS BUILT, NOT A CONSTANT (#262).**
    #
    # This read `target=ITEMS_PER_UNIT` -- a hardcoded 8, block 3's number --
    # for every run, including `--checkpoint` (12) and `--fill` (whatever the
    # shortfall is). A four-slot fill printed `served 2/8 ** SHORT BY 6 **`,
    # blaming the run for six items it was never asked to produce.
    #
    # **It went unnoticed because the first checkpoint run accepted exactly 8 and
    # printed `served 8/8` with no SHORT flag: a wrong denominator that matches
    # by accident reads as a right one.**
    #
    # `len(by_unit[number])` is the number of DISTINCT SLOTS in that unit's
    # journal rows -- `read_journal` already keeps the last write per
    # `(unit, slot)` -- so it is the plan that was actually built, in every mode,
    # and it is derivable by `--report` from the journal alone with no extra
    # state. `_expected_checkpoint_calls` branches on run mode at its own call
    # site; this needs no branch at all, which is why it is preferred to one.
    for number in numbers:
        if number in by_unit:
            _print_tally(f"unit {number}", tally_of(by_unit[number]),
                         target=len(by_unit[number]))
    _print_tally("TOTAL", tally_of(rows), target=len(rows))

    _print_targets(rows)
    _print_back_translations(rows)
    _print_cross_tab(rows)
    print_verdicts(rows, control)


def report_only(path: Path) -> int:
    """`--report` — rebuild everything from a journal. **Zero calls, zero spend.**

    This is the proof that the file is the record rather than a log beside one.
    If a run dies, this prints what it had already established; if a number in
    the record is ever questioned, this recomputes it from the same bytes.
    """
    if not path.exists():
        print(f"No journal at {path}.")
        return 1
    rows = read_journal(path)
    if not rows:
        print(f"{path} holds no outcomes.")
        return 1
    numbers = sorted({row["unit"] for row in rows})
    print(f"=== report rebuilt from {path} ===")
    print(f"{len(rows)} outcome(s) across unit(s) {numbers}. No calls were made.")
    # The control is not in the journal: it is a property of the RUN, not of an
    # item. Rebuilding shows its banked value and says so rather than implying
    # this rebuild re-measured it.
    _print_report(rows, numbers, ControlResult(
        runs=CONTROL_RUNS, failures=CONTROL_RUNS, ranks=(None, None, None)
    ))
    return 0


# ── the pre-registered verdicts, applied by the module ──────────────────────


#: **Promoted to `core.runs.band` by W10b and aliased here, not copied.**
#: This function has produced a false reading twice in the same way (#201, and
#: its ninth-appearance sequel that reverted to the old claim at n=1). W10b
#: needed the identical behaviour for lesson axes; a second copy would be a
#: second place for that family to reappear. The name stays private here so
#: every existing call site and test is unchanged.
_band = band


def print_verdicts(rows: Sequence[dict], control: "ControlResult") -> None:
    """Every branch rule, evaluated here rather than by whoever reads the output.

    W8b's finding, carried: a pre-registered prediction constrains honesty about
    the axis it names and says nothing about an axis it does not. Each of these
    is its own axis and each gets its own line.
    """
    total = len(rows)
    accepted = sum(1 for r in rows if r.get("state") == "accepted")
    stages = [r.get("stage") for r in rows]
    # How many items actually REACHED each gate. An axis nothing reached cannot
    # be met -- see `_band`.
    past_generation = sum(1 for st in stages if st not in ("generation", "runner"))
    judged_n = sum(
        1 for st in stages
        if st not in ("generation", "runner", "deterministic", "naturalness")
    )
    probed_n = sum(1 for st in stages if st in (None, "target"))
    # Reaching the PROBE is not the same as reaching the judge: an item the
    # judge rejected never got there, so P4's denominator is its own.
    probe_reached = sum(1 for st in stages if st in (None, "target", "probe"))
    drift = sum(1 for st in stages if st == "target")
    unnatural = sum(1 for st in stages if st == "judge")
    ambiguous = sum(
        1 for r in rows
        if any(c in ("multi_acceptable", "not_recoverable", "under_specified",
                     "widened")
               for c in ((r.get("validation") or {}).get("blind_solver") or ()))
    )

    print("\n" + "=" * 78)
    print("PRE-REGISTERED PREDICTIONS — written before this run, evaluated by it")
    print("=" * 78)
    if past_generation == 0:
        print(f"  **{total} of {total} ITEMS DIED AT THE GENERATION STAGE.** "
              "Nothing reached a\n  billed gate, so every axis below except P1 "
              "is unevaluated rather than met.")
    _band("P1 accept rate    ", accepted, P1_LOW, P1_HIGH, total,
          "≥19 → gates may be weak at this n; P5 decides whether to believe it. "
          "≤11 → THE PROMPT IS WRONG, NOT THE GATE (rule 7): fix the prompt and "
          "re-run; do not loosen a gate.")
    _band("P2 target drift   ", drift, P2_LOW, P2_HIGH, total,
          "≥7 → the prompt is asking for grammar-flavoured sentences rather than "
          "demonstrations of a named point. Rewrite the prompt, not the check.", exercised=probed_n)
    _band("P3 unnatural      ", unnatural, P3_LOW, P3_HIGH, total,
          "≥10 → read them before touching anything; #115 recorded 6/11 on "
          "hand-written fixtures and the judge is strict.", exercised=judged_n)
    _band("P4 ambiguity      ", ambiguous, P4_LOW, P4_HIGH, total,
          "≥14 → grammar gaps are structurally more ambiguous than vocabulary "
          "gaps; the TYPE MIX is the fix, not the gate.", exercised=probe_reached)

    print(f"  P5 control        : {control.failures} of {control.runs} runs "
          f"correctly refused the mis-targeted item")
    if control.ranks == (None, None, None):
        print("      **BANKED FROM ATTEMPT 1 (2026-08-27), NOT RE-MEASURED "
              "ON THIS RUN.**\n      Skipped deliberately: the question is "
              "answered and re-buying it costs 3 calls.")
    if control.failures == control.runs:
        print("      prediction MET — the check discriminates.")
    elif control.ok:
        # The exact words the plan pre-registered, so neither reading can be
        # quietly preferred over the other after the fact.
        print("      prediction NOT MET, run acceptable — the bar is 2 of 3 and "
              "the prediction\n      was 3 of 3. They answer different questions: "
              "whether the check\n      discriminates at all, and how reliably. "
              "Both go in the record.")
    else:
        print("      **FAILED** — below the 2-of-3 bar. `probe_target` does not "
              "discriminate,\n      so every target-first verdict above is "
              "worthless. NOTHING IS WRITTEN.")

    measured = [r for r in rows if r.get("state") == "accepted"
                and r.get("coverage_pct") is not None]
    below = sum(1 for r in measured if r["coverage_pct"] < COVERAGE_FLOOR * 100)
    if measured:
        _band("P7 below floor    ", below, P7_LOW, P7_HIGH, len(measured),
              "≤3 → the floor is compatible with the everyday register; wire "
              "`known_lemmas` in the slice whose ledger is worth more than the "
              "frequency floor. ≥11 → RAISE THE REFERENCE, do not lower the "
              "floor (rule 7).")
        print("      MEASURED, NOT ENFORCED — no item was rejected for this. "
              "The floor is 90%\n      and untouched; this is its effect on real "
              "generated items for the first time.")

    print("  P6 per-type yield : see the TYPE x TARGET table above. "
          "**#168 stays open** —\n      n is 3 per type and closing on three "
          "draws would be a claim true of three\n      draws written as a claim "
          "about the type (#82's shape, sixth appearance).")


# ── the negative control ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ControlResult:
    runs: int
    failures: int
    ranks: tuple[int | None, ...]

    @property
    def ok(self) -> bool:
        return self.failures >= CONTROL_MUST_FAIL


def load_control() -> dict:
    from core.services.paths import repo_root

    return json.loads((repo_root() / CONTROL_FIXTURE).read_text(encoding="utf-8"))


def run_control(*, settings: Settings | None = None) -> ControlResult:
    """The mis-targeted fixture through `probe_target`, three times.

    **`verify.py`'s central lesson, carried: a check that rejects nothing passes
    the catch direction perfectly.** `probe_target` is the one gate in this run
    that could be inert and still look like it is working -- every item would
    rank its claimed target first and every item would pass.

    So a committed item that genuinely tests *used to for habits that have
    stopped*, while claiming *for and since with the present perfect*, is run
    first. Both are real unit-3 targets, so the drift is to a SIBLING rather than
    to something absurd -- a control that is easy to reject proves nothing.

    **It runs before the 24 items, so a dead check costs three calls rather than
    a hundred.** If it passes in more than one of three, the whole run is void:
    nothing is written, whatever the items did.
    """
    fixture = load_control()
    item = parse(dict(fixture["item"]))
    claimed = fixture["claims"]
    candidates = tuple(fixture["candidates"])

    ranks: list[int | None] = []
    for attempt in range(CONTROL_RUNS):
        verdict = gates.probe_target(
            item, claimed=claimed, candidates=candidates, settings=settings
        )
        ranks.append(verdict.claimed_rank)
        outcome = "correctly refused" if not verdict.ok else "** PASSED — BAD **"
        print(
            f"  run {attempt + 1}: claimed target ranked "
            f"{verdict.claimed_rank or 'absent'}, first was {verdict.first!r} "
            f"— {outcome}"
        )
    return ControlResult(
        runs=CONTROL_RUNS,
        failures=sum(1 for r in ranks if r != 1),
        ranks=tuple(ranks),
    )


# ── loading the syllabus, through its one door ──────────────────────────────


def unit_plan(
    numbers: Sequence[int],
    *,
    checkpoint: bool = False,
    missed: dict[int, tuple[str, ...]] | None = None,
    types: Sequence[str] | None = None,
    held: dict[int, dict[str, int]] | None = None,
) -> dict[int, dict]:
    """Everything the run needs about each unit. **The Murphy strip is here.**

    `core.sessions.blocks.visible_targets` and NOT `unit.grammar_targets`. That
    function builds `{"target": ...}` by naming the one field that may travel, so
    `murphy_units` is never in the object anything downstream sees -- and it is
    the seam #171's ruling is already asserted at, reused rather than copied.

    **Reused rather than copied is the whole point.** A second three-line strip
    written here would hold today and drift the first time someone adds an
    operator-only field to `GrammarTarget`; going through the existing seam means
    a new field is withheld by default. An item generator importing a
    session-block helper reads oddly, and that is the cost.
    """
    from core.syllabus.content import units

    everything = {u.unit_number: u for u in units()}
    missed = missed or {}
    all_targets = {
        number: tuple(t["target"] for t in visible_targets(unit.grammar_targets))
        for number, unit in everything.items()
    }
    plan: dict[int, dict] = {}
    for number in numbers:
        if number not in everything:
            raise ValueError(f"unit {number} is not one of the 24")
        unit = everything[number]
        targets = all_targets[number]
        permitted = tuple(unit.checkpoint.get("item_types") or ())
        unknown = [t for t in SLOT_TYPES if t not in permitted]
        if unknown:
            # The blueprint is authoritative about which types a unit's items may
            # use. Generating a type it does not permit would put an item in the
            # bank that its own checkpoint could never draw.
            raise ValueError(
                f"unit {number} does not permit {sorted(set(unknown))}; "
                f"it permits {list(permitted)}"
            )
        if checkpoint:
            # **The permitted set is a RUN-LEVEL PARAMETER, and `--types` is how
            # a narrowing is exercised without touching the syllabus.**
            #
            # Three layers, narrowest last: the unit's blueprint says which types
            # a checkpoint MAY use; `SLOT_TYPES` says which this generator can
            # produce; `--types` says which THIS RUN should use. A `--types`
            # value the blueprint does not permit is refused below rather than
            # silently honoured -- narrowing a run is a run decision, and
            # WIDENING past the blueprint would put an item in the bank its own
            # checkpoint could never draw.
            #
            # **This is deliberately NOT a way to answer #207.** That row asks
            # whether `checkpoint.item_types` narrows in `data/syllabus_units.json`
            # across all 24 units, and it is the operator's. A flag on one run
            # changes nothing in the data and leaves the question open.
            chosen = [t for t in SLOT_TYPES if t in permitted]
            if types is not None:
                outside = [t for t in types if t not in permitted]
                if outside:
                    raise ValueError(
                        f"unit {number} does not permit {sorted(set(outside))}; "
                        f"--types may only narrow, never widen"
                    )
                unproducible = [t for t in types if t not in SLOT_TYPES]
                if unproducible:
                    raise ValueError(
                        f"this generator cannot produce {sorted(set(unproducible))}; "
                        f"it produces {sorted(set(SLOT_TYPES))}"
                    )
                chosen = [t for t in chosen if t in types]
                if not chosen:
                    raise ValueError(f"unit {number}: --types leaves no usable type")
            demand = dict(unit.checkpoint["per_target"])
            slots = checkpoint_slot_plan(
                number,
                demand,
                permitted=chosen or list(permitted),
                missed=missed.get(number, ()) if missed else (),
            )
            if held is not None:
                slots = _shortfall_slots(
                    slots,
                    checkpoint_quotas(
                        demand, missed.get(number, ()) if missed else ()
                    ),
                    held.get(number, {}),
                )
        else:
            slots = slot_plan(number, targets)
        plan[number] = {
            "unit": unit,
            "targets": targets,
            "slots": slots,
            "candidates": target_candidates(number, targets, all_targets),
            "checkpoint": checkpoint,
        }
    return plan


# ── dry run ─────────────────────────────────────────────────────────────────


def _expected_calls(numbers: tuple[int, ...]) -> int:
    """The ceiling, itemised. Printed before anything is spent."""
    per_unit = (
        1                       # generation
        + 1                     # one batched naturalness call for the cohort
        + (len(SLOT_TYPES) - 1)  # probes; match_pairs is unprobed (family `exact`)
        + MAX_REPAIRS * 2       # cue re-probes, the two slot-family items
        + len(SLOT_TYPES)       # probe_target, one per surviving item
        + 1                     # back-translation, the one l1_to_l2_production
    )
    return CONTROL_RUNS + len(numbers) * per_unit * 2  # x2 allows one top-up round


def _expected_checkpoint_calls(plan: dict[int, dict]) -> int:
    """The ceiling for a `--checkpoint` run, itemised **from the actual slot
    plan** rather than from a constant.

    **Every term is derived at call time**, so a change to `gates.ANSWER_FAMILY`
    or `gates.PROBED_FAMILIES` -- or to which types a unit permits -- moves this
    number instead of leaving a stale literal behind. `_expected_calls` above
    hardcodes `len(SLOT_TYPES)` because its plan is a constant; this one's is
    not.

    Per unit, from that unit's twelve slots:

        1                     generation
      + 1                     one batched naturalness call for the cohort
      + n_probed              probes. A slot whose type's ANSWER_FAMILY is not
                              in PROBED_FAMILIES is never probed -- `match_pairs`
                              is `exact`, which is #192.
      + MAX_REPAIRS * n_slot  cue re-probes, for the slot-family items only
      + len(slots)            probe_target, one per surviving item
      + n_l1                  back-translation, per l1_to_l2_production
      + 1                     **#169's checkpoint-level uniqueness pass over the
                              twelve as a SET.** One batched call per cohort.

    times 2, which allows exactly one top-up round -- and the x2 covers the #169
    re-pass too, because a #169 rejection tops the cohort up and the replacement
    set must be re-checked as a set.

    plus CONTROL_RUNS for the negative control.

    **The #169 term was missing from the first three drafts of W11's plan while
    the test list described that call as "on the ceiling".** A ceiling that omits
    a call the run makes is the defect this function exists to prevent, so the
    term is named in the arithmetic rather than in a comment beside it.
    """
    total = CONTROL_RUNS
    for entry in plan.values():
        slots = entry["slots"]
        n_probed = sum(
            1 for one in slots
            if gates.ANSWER_FAMILY.get(one.item_type) in gates.PROBED_FAMILIES
        )
        n_slot = sum(
            1 for one in slots if gates.ANSWER_FAMILY.get(one.item_type) == "slot"
        )
        n_l1 = sum(1 for one in slots if one.item_type == "l1_to_l2_production")
        per_unit = (
            1
            + 1
            + n_probed
            + MAX_REPAIRS * n_slot
            + len(slots)
            + n_l1
            + 1
        )
        total += per_unit * 2
    return total


def dry_run(
    user_id: int,
    numbers: tuple[int, ...],
    journal_path: Path = DEFAULT_JOURNAL,
    *,
    checkpoint: bool = False,
    missed: dict[int, tuple[str, ...]] | None = None,
    types: Sequence[str] | None = None,
    held: dict[int, dict[str, int]] | None = None,
) -> int:
    settings = load_settings()
    plan = unit_plan(numbers, checkpoint=checkpoint, missed=missed, types=types, held=held)

    print("=== model ===")
    print(settings.llm_model)
    per_unit = CHECKPOINT_ITEM_COUNT if checkpoint else ITEMS_PER_UNIT
    kind = "CHECKPOINT cohort" if checkpoint else "block-3 practice"
    print(f"\n=== target ===\nusers.id = {user_id} · units {list(numbers)} · "
          f"{per_unit} items each · {kind}")
    if checkpoint:
        print("  cohort tag written onto every item: `cohort: \"checkpoint\"`.")
        print("  `focus_items` will not serve these; `checkpoint_items` selects "
              "only these.")
        for number in numbers:
            quotas: dict[str, int] = {}
            for one in plan[number]["slots"]:
                quotas[one.target] = quotas.get(one.target, 0) + 1
            were = dict(plan[number]["unit"].checkpoint["per_target"])
            reweighted = bool(missed and missed.get(number))
            how = "RETAKE, re-weighted" if reweighted else "first sitting, the blueprint"
            print(f"  unit {number} quota map ({how}):")
            for target, count in quotas.items():
                mark = " *" if missed and target in (missed.get(number) or ()) else ""
                print(f"    {count} (blueprint {were.get(target, 0)}) {target}{mark}")

    print("\n=== system (item_generate.txt, contract substituted) ===")
    # **`generator_system_prompt()` and NOT the template file.** The first draft
    # of this line read the file directly and printed a literal `{contract}`
    # placeholder, so the dry run showed something the live run does not send --
    # on the very change the dry run exists to let somebody read before paying
    # for it. That is W5a's lesson in the harness rather than in the gate: **the
    # thing that verifies must measure the thing it reports on.**
    print(generator_system_prompt())

    # **Every system prompt the run will send, not just the generator's.**
    # #202 was the dry run printing an unsubstituted `{contract}` placeholder;
    # this is the same lesson one step out. #210's ruling changed
    # `item_probe.txt` -- what the blind solver is ASKED for `error_spot` -- and
    # the dry run did not show it, so the one thing that changed could not be
    # read before it was paid for. A dry run that shows some of the request is
    # a dry run somebody can be surprised by.
    for name in ("item_probe.txt", "item_target.txt", "item_backtranslate.txt"):
        print(f"=== system ({name}) ===")
        print((PROMPTS_DIR / name).read_text(encoding="utf-8"))

    for number in numbers:
        entry = plan[number]
        print(f"=== user payload — unit {number} ===")
        print(json.dumps(
            build_payload(number, entry["unit"].can_do, entry["slots"]),
            ensure_ascii=False, indent=2,
        ))
        print(f"\n--- probe_target candidates for unit {number} "
              f"({len(entry['targets'])} own + "
              f"{len(entry['candidates']) - len(entry['targets'])} decoys) ---")
        for candidate in sorted(entry["candidates"]):
            own = "own  " if candidate in entry["targets"] else "decoy"
            print(f"  [{own}] {candidate}")
        print()

    print("=== max_tokens ===")
    print(f"generate {GENERATE_MAX_TOKENS} · probe {gates.SOLVER_MAX_TOKENS} · "
          f"judge {gates.JUDGE_MAX_TOKENS} · target {gates.TARGET_MAX_TOKENS} "
          "(reject_truncation=True on all four)")

    reference = coverage_reference()
    print("\n=== coverage ===")
    print(f"reference: {len(reference)} lemmas — CEFR A1/A2/B1 plus the top "
          f"{COVERAGE_FREQ_FLOOR} by frequency.")
    print(f"floor:     {COVERAGE_FLOOR:.0%}, UNCHANGED — and MEASURED, NOT ENFORCED.")
    print("  `deterministic_failures` enforces the floor only when handed "
          "`known_lemmas`;\n  this run passes None and reports the number per item "
          "instead (P7).")
    print("  Measured 2026-08-27: against a learner's real ledger, 8 of 8 "
          "everyday-register\n  sentences fell below the floor — on `dentist`, "
          "`landlord`, `neighbour`,\n  `umbrella`, `tram` — every one of them "
          "vocabulary the prompt above ORDERS the\n  generator to use. That ledger "
          "is a STRICT SUBSET of this reference and adds\n  zero per-learner "
          "signal. Enforcing it would reject the content CLAUDE.md §4\n  asks for, "
          "and P1 would misreport it as a prompt failure.")

    print("\n=== negative control ===")
    fixture = load_control()
    print(f"  {CONTROL_FIXTURE}")
    print(f"  claims  : {fixture['claims']!r}")
    print(f"  actually: {fixture['actually']!r}")
    print(f"  {CONTROL_RUNS} runs, and the run is VOID unless at least "
          f"{CONTROL_MUST_FAIL} of them refuse it.")

    print("\n=== journal ===")
    print(f"  {journal_path}")
    print("  Outcomes are appended AS EACH COHORT IS DECIDED, before the top-up "
          "runs and\n  before anything is printed — so a crash costs the "
          "remainder of the run and\n  nothing already established. The report "
          "is a view of this file:")
    print(f"    python -m core.items.generate --report {journal_path}")
    if journal_path.exists():
        # Appending to a previous run's journal would silently merge two
        # experiments into one report, and `read_journal` takes the LAST write
        # per slot -- so the older run would be the one that vanished.
        print(f"  ** {journal_path} ALREADY EXISTS ({journal_path.stat().st_size} "
              "bytes). A live run\n     APPENDS, and the rebuilt report takes the "
              "last write per slot — move it\n     aside first unless you mean to "
              "continue it. **")

    print("\n=== billed calls ===")
    ceiling = (
        _expected_checkpoint_calls(plan) if checkpoint else _expected_calls(numbers)
    )
    print(f"  ceiling {ceiling} "
          f"(control {CONTROL_RUNS} + {len(numbers)} units, one top-up allowed)")
    print("  ZERO TTS and ZERO STT: no audio type is permitted by these units.")

    print("\ndry run — nothing was sent and nothing was written.")
    return 0


# ── live ────────────────────────────────────────────────────────────────────


#: **Promoted to `core.runs.confirm` by W10b and aliased here, not copied.**
#: Two implementations of a typed confirmation is two places for the expected
#: string to drift from what the operator was told to type -- #223's shape one
#: field over.
_confirm = confirm


def run(
    user_id: int,
    numbers: tuple[int, ...],
    *,
    apply: bool,
    settings: Settings | None = None,
    skip_control: bool = False,
    journal_path: Path = DEFAULT_JOURNAL,
    checkpoint: bool = False,
    missed: dict[int, tuple[str, ...]] | None = None,
    types: Sequence[str] | None = None,
    held: dict[int, dict[str, int]] | None = None,
) -> int:
    settings = settings or load_settings()
    plan = unit_plan(numbers, checkpoint=checkpoint, missed=missed, types=types, held=held)
    spent: Counter = Counter()
    reference = coverage_reference()
    journal = Journal(journal_path)
    print(f"\njournal: {journal_path}")
    print("  Every outcome is written here as its cohort is decided, BEFORE "
          "anything\n  downstream can fail. Rebuild the whole report from it "
          "with:")
    print(f"    python -m core.items.generate --report {journal_path}")

    ceiling = (
        _expected_checkpoint_calls(plan) if checkpoint else _expected_calls(numbers)
    ) - (CONTROL_RUNS if skip_control else 0)
    print(f"\nAbout to make up to {ceiling} billed model calls.")
    print("Nothing is written to any database by this step." if not apply
          else f"Accepted items WILL BE WRITTEN to items for users.id = {user_id}.")
    if not _confirm("", str(user_id) if apply else str(ceiling)):
        print("Stopped. Nothing was sent.")
        return 1

    # --- the control first, so a dead check costs three calls and not a hundred
    print("\n" + "=" * 78)
    print("NEGATIVE CONTROL — before anything else is spent")
    print("=" * 78)
    if skip_control:
        # **SKIPPED DELIBERATELY, NOT FORGOTTEN, and the distinction is the
        # whole reason this branch prints instead of staying silent.**
        #
        # Attempt 1 on 2026-08-27 ran the control FIRST and it passed 3 of 3 --
        # P5's prediction MET, its bar 2 of 3 cleared, `probe_target` shown to
        # discriminate between two SIBLING targets of one unit. The run then died
        # on the unit-1 generation call, and **that failure does not touch the
        # control's result**: the control runs before the units precisely so a
        # downstream failure cannot cost it.
        #
        # Re-buying it would be spending on a question already answered. A
        # skipped check that goes unmentioned is indistinguishable from one
        # nobody ran, which is what this record files as its own class of defect,
        # so it is printed here and recorded in BUILD_PROGRESS.md rather than
        # inferred from an absent section.
        control = ControlResult(runs=CONTROL_RUNS, failures=CONTROL_RUNS,
                                ranks=(None, None, None))
        print("  SKIPPED — deliberately, and the earlier result stands.")
        print(f"  Attempt 1, 2026-08-27: {CONTROL_RUNS}/{CONTROL_RUNS} refused "
              "the mis-targeted item. P5 MET.")
        print("  `probe_target` discriminates between sibling targets; that is")
        print("  banked evidence and re-buying it would spend on a settled "
              "question.")
        print("  **The ranks below are the banked result, not a fresh "
              "measurement.**")
    else:
        control = run_control(settings=settings)
        spent["control"] += CONTROL_RUNS
    if not skip_control and not control.ok:
        print(
            f"\n**RUN VOID.** The mis-targeted control was refused in only "
            f"{control.failures} of {control.runs} runs, below the "
            f"{CONTROL_MUST_FAIL}-of-{control.runs} bar.\n`probe_target` does "
            "not discriminate, so nothing it says about a real item means\n"
            "anything. Nothing was written. This is a finding: record it."
        )
        return 1
    if not skip_control:
        print(f"\ncontrol PASSED ({control.failures}/{control.runs} refused) — "
              "the check discriminates.")

    # --- the units
    #
    # Kept ONLY for `--apply`, which needs the live `BaseItem` and its
    # `ValidationReport`; every report below reads the journal instead.
    accepted_outcomes: list[Outcome] = []
    for number in numbers:
        entry = plan[number]
        print("\n" + "=" * 78)
        print(f"UNIT {number} — {entry['unit'].can_do}")
        print("=" * 78)

        payload = build_payload(number, entry["unit"].can_do, entry["slots"])
        drafts = generate_drafts(payload, settings=settings)
        spent["generate"] += 1
        outcomes = verify_cohort(
            entry["slots"], drafts, unit_number=number,
            candidates=entry["candidates"], settings=settings, calls=spent,
            reference=reference,
        )

        # **WRITTEN BEFORE THE TOP-UP RUNS, and that ordering is the fix.**
        # W10c's fourth attempt crashed inside `_top_up` and the traceback ended
        # the process before anything printed, so eight rejection codes that had
        # already been paid for were destroyed by a failure that came after them.
        journal.record(outcomes)

        # --- one top-up round, asking for exactly the shortfall
        short = [o for o in outcomes if not o.accepted]
        if short:
            print(f"\n  {len(short)} slot(s) short — one top-up round, "
                  "with the failures fed back.")
            try:
                outcomes = _top_up(
                    outcomes, short, entry, number, settings=settings, calls=spent
                )
            except Exception:  # noqa: BLE001 — a top-up is an EXTRA, not the run
                # **A top-up failing must cost the top-up and nothing else.** It
                # is a second chance at slots that already failed once; letting
                # it take down a unit whose first cohort is already on disk
                # trades something valuable for something optional. The unit
                # keeps its original outcomes, already journalled above.
                logger.exception("top-up failed for unit %s; keeping the "
                                 "cohort as first decided", number)
                print(f"\n  ** TOP-UP FAILED for unit {number} — see the log. "
                      "The unit keeps its\n     original outcomes, which were "
                      "written to the journal before this ran. **")
            else:
                journal.record([o for o in outcomes if o.topped_up])

        accepted_outcomes.extend(o for o in outcomes if o.accepted)

    # --- the report, READ BACK FROM DISK
    #
    # Not from `outcomes` in memory. The journal is the record and this is a
    # view of it, so `--report` on a later day prints the same thing without
    # re-buying a call -- and so a crash between here and the end costs the
    # printing rather than the findings.
    rows = read_journal(journal.path)
    print(f"\nreport rebuilt from {journal.path} ({len(rows)} rows)")
    _print_report(rows, numbers, control)

    print(f"\nbilled calls this run: {sum(spent.values())} "
          f"({' · '.join(f'{k} {v}' for k, v in sorted(spent.items()))})")
    print(
        "\n24 ITEMS, ONE SAMPLE EACH, of a stochastic system. A fail is "
        "decisive; a pass is\nnot proof. `probe_target` is a model checking a "
        "model, plausibly the same model\nwith correlated blind spots — a fluent "
        "item teaching a subtly wrong point can\npass every gate above. Nobody "
        "should later read this run as 'the items were\nverified'."
    )

    if not apply:
        print("\n--live — nothing was written. Re-run with --apply to write.")
        return 0
    # **`--apply` writes from memory, not from the journal**, and that is a real
    # limit rather than an oversight: `insert_item` needs a `BaseItem` and a
    # `ValidationReport`, and a journal row carries the item's VISIBLE half. It
    # cannot be rebuilt into something the validator would vouch for, and
    # inventing one from a projection would be exactly the second serialiser
    # this package refuses. So a crash before this point costs the write and
    # keeps the findings, which is the right way round.
    return _write(user_id, accepted_outcomes, settings=settings)


def _top_up(
    outcomes: list[Outcome],
    short: list[Outcome],
    entry: dict,
    unit_number: int,
    *,
    settings: Settings | None,
    calls: Counter,
) -> list[Outcome]:
    """One more round for the failed slots, with their failures fed back.

    **One round, not a loop.** An unbounded regenerate is an unbounded bill, and
    a slot that fails twice is telling you something about the prompt rather than
    about luck.

    **A unit still short after this SHIPS SHORT and the number is reported.** Six
    good items beat eight with two bad ones, and the criterion is 8: if a unit
    yields 6 the run says `6/8` loudly and writes the six. The bar is not moved
    and no filler is generated (CLAUDE.md §3 rule 7).
    """
    # **RE-INDEXED ONCE, HERE, AND USED FOR EVERYTHING THAT IS SENT (#261).**
    #
    # This read `slots = tuple(o.slot for o in short)` and handed those straight
    # to `build_payload`, so a top-up carried the ORIGINAL indices into a request
    # for `len(short)` items. After the `_shortfall_slots` fix that stopped being
    # a twelve-into-four problem and became a two-into-one problem: a fill of two
    # whose second slot fails tops up with one slot still numbered 1, addressed at
    # `drafts[1]` of a one-item response. **`_assert_indices_addressable` refuses
    # it — correctly, and loudly, which is better than the silent `missing_draft`
    # it produced before the guard existed, and still a broken run.**
    #
    # `short` keeps its ORIGINAL slots untouched: they are what
    # `merged[original.slot.index]` maps the replacements back through, and
    # re-indexing those would write the results to the wrong positions.
    sent = _reindexed_for_verifier(tuple(o.slot for o in short))
    payload = build_payload(unit_number, entry["unit"].can_do, sent)
    payload["retry"] = [
        {
            # The position IN THIS REQUEST, not in the original plan. The model
            # is being handed `len(short)` items and told which is which; a
            # number from the cohort it never saw would name nothing.
            "n": index + 1,
            "rejected_because": list(o.codes),
            "at_stage": o.stage,
        }
        for index, o in enumerate(short)
    ]
    payload["note"] = (
        "These slots were rejected. Write NEW items for them — do not resubmit "
        "the same sentences. `rejected_because` says what the gates found."
    )
    drafts = generate_drafts(payload, settings=settings)
    calls["generate"] += 1
    replacements = verify_cohort(
        sent,
        drafts,
        unit_number=unit_number,
        candidates=entry["candidates"],
        settings=settings,
        calls=calls,
        reference=coverage_reference(),
    )
    merged = list(outcomes)
    for original, replacement in zip(short, replacements, strict=True):
        if replacement.accepted:
            replacement.slot = original.slot
            replacement.topped_up = True
            merged[original.slot.index] = replacement
    return merged



def _reindexed_for_verifier(slots: tuple[Slot, ...]) -> tuple[Slot, ...]:
    """The retry plan, renumbered 0..n-1 to match the order the drafts come back.

    The slots keep their ORIGINAL indices for reporting and the outcome is mapped
    back afterwards, so only the verifier sees these numbers.

    **`dataclasses.replace` and NOT a field-by-field rebuild**, which is the fix
    for #260 rather than a tidier spelling of the same thing. The old form named
    `index`, `item_type` and `target` and silently took the default for `cohort`,
    so every topped-up item was relabelled as block 3's. `replace` copies every
    field there is, so **a field added to `Slot` later cannot be dropped here
    again** -- the defect was the enumeration, not the one field it missed.
    """
    return tuple(replace(one, index=i) for i, one in enumerate(slots))


def _measure_coverage(outcome: Outcome, reference: frozenset[str] | None) -> None:
    """Record this item's coverage. **This does not gate and must not start to.**

    `checks.deterministic_failures` enforces PRD §2.1's 90% band when handed
    `known_lemmas`, and this run hands it None -- so the number is computed here,
    beside the item, and printed.

    **Why it is measured and not enforced, and the reason is a measurement rather
    than a preference.** At the 90% floor a twelve-word sentence may carry ONE
    unknown word. Probed on 2026-08-27 against the everyday register
    `item_generate.txt` demands -- *apartments, neighbours, doctors, food,
    transport, weather* -- **4 of 8 correctly-written sentences fell below the
    floor**, on `boiler`, `sushi`, `primary` and `leak`; against a learner's
    actual ledger it was **8 of 8**, on `dentist`, `landlord`, `neighbour`,
    `umbrella` and `tram`.

    Turning the gate on would therefore reject the content CLAUDE.md §4 orders
    the generator to write, and **P1's branch rule would misread it**: `<= 11
    accepted -> the generator prompt is wrong` would fire while the prompt was
    right and the reference was too small. That is #115's shape -- the gate was
    correct and the input was wrong -- and it is the reason this is a number in
    the report rather than a verdict.

    **The bar is not lowered to make it pass** (CLAUDE.md §3 rule 7): 0.90 is
    untouched. What changes is that the floor's effect is now MEASURED on real
    generated items, by P7, instead of assumed in either direction.
    """
    if reference is None or outcome.item is None:
        return
    from core.lexicon.coverage import compute_coverage

    sentence = sentence_of(outcome.item)
    if not sentence.strip():
        return
    report = compute_coverage(sentence, reference)
    outcome.coverage_pct = report.percent
    outcome.coverage_unknown = tuple(report.unknown_lemmas)


def _print_items(rows: Sequence[dict]) -> None:
    """Every slot, accepted or not. **Nothing is summarised away before a write.**

    `rewrite_checkpoints` prints all 24 rows before it touches any of them, for
    the reason that applies here with more force: this output is the only record
    of what the model produced, and the operator reads the items from it.
    """
    print()
    for row in rows:
        accepted = row.get("state") == "accepted"
        mark = "OK " if accepted else "-- "
        extra = " (top-up)" if row.get("topped_up") else ""
        print(f"  {mark} {row['slot'] + 1}. {row['item_type']:<20} "
              f"{row['target']!r}{extra}")
        item = row.get("item")
        if item is not None:
            print(f"        prompt : {item['prompt_text']}")
            if item.get("answer") is not None:
                print(f"        answer : {item['answer']}")
            for name in ("options", "bank", "tiles", "pairs"):
                if item.get(name):
                    print(f"        {name:<7}: {item[name]}")
            if item.get("cue_text"):
                print(f"        cue    : {item['cue_text']}")
            if item.get("explanation"):
                print(f"        why    : {item['explanation']}")
        if row.get("coverage_pct") is not None:
            below = row["coverage_pct"] < COVERAGE_FLOOR * 100
            flag = "  ** BELOW THE 90% FLOOR (measured, not enforced) **" if below else ""
            unknown = (f" unknown={row['coverage_unknown']}"
                       if row.get("coverage_unknown") else "")
            print(f"        cover  : {row['coverage_pct']}%{unknown}{flag}")
        if not accepted:
            print(f"        REJECTED at {row.get('stage')}: {row.get('codes')}")
        else:
            validation = row.get("validation") or {}
            if validation.get("repair_count"):
                print(f"        repaired x{validation['repair_count']} "
                      f"({validation.get('cue_applied')})")


def _write(user_id: int, outcomes: list[Outcome], *, settings: Settings) -> int:
    """Insert every accepted item. `insert_item` refuses anything not `ok`."""
    from core.services import items as service

    written = duplicates = 0
    for outcome in outcomes:
        if not outcome.accepted or outcome.item is None or outcome.report is None:
            continue
        item_id = service.insert_item(
            user_id, outcome.item, outcome.report, model=settings.llm_model
        )
        if item_id is None:
            outcome.state = "duplicate"
            duplicates += 1
        else:
            outcome.item_id = item_id
            written += 1

    print(f"\nwritten: {written} · already present: {duplicates}")
    print(
        "Confirm the row count independently — a count this command prints about "
        "its own\nwork is not verification of it. The psql query is the deploy "
        "step in\nBUILD_PROGRESS.md."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate and validate block 3's eight items per unit. "
        "Dry by default; --live makes billed calls and writes nothing; --apply "
        "writes what passed."
    )
    parser.add_argument(
        "--user", type=int,
        help="users.id to generate for. No default, deliberately — these rows "
             "are permanent and belong to a learner.",
    )
    parser.add_argument(
        "--units", default=",".join(str(n) for n in DEFAULT_UNITS),
        help="comma-separated unit numbers (default: 1,2,3)",
    )
    parser.add_argument("--live", action="store_true",
                        help="make the calls and print the finding (billed)")
    parser.add_argument("--apply", action="store_true",
                        help="make the calls and WRITE what passed (billed)")
    parser.add_argument(
        "--journal", type=Path, default=None,
        help=f"where outcomes are written as they are decided "
             f"(default: {DEFAULT_JOURNAL}, or "
             f"{DEFAULT_CHECKPOINT_JOURNAL} with --checkpoint)",
    )
    parser.add_argument(
        "--report", type=Path, metavar="JOURNAL",
        help="rebuild the full report from a journal file. Makes NO calls.",
    )
    parser.add_argument(
        "--checkpoint", action="store_true",
        help=f"generate a CHECKPOINT cohort ({CHECKPOINT_ITEM_COUNT} items per "
             "unit, allocated by the blueprint's per_target) instead of block "
             f"3's {ITEMS_PER_UNIT} practice items. Every item is tagged "
             "`cohort: checkpoint` so block 3 will not serve it.",
    )
    parser.add_argument(
        "--retake", action="store_true",
        help="with --checkpoint: re-weight the twelve toward the targets this "
             "learner missed in their last FAILED sitting of that unit, capped "
             "at the blueprint's own maximum per target. Reads the database; "
             "makes no model call. Requires --user.",
    )
    parser.add_argument(
        "--fill", action="store_true",
        help="with --checkpoint: plan only the SHORTFALL against what this "
             "learner already holds, instead of re-buying the whole sitting. "
             "Reads the bank through the same predicate the selector uses. "
             "Requires --user.",
    )
    parser.add_argument(
        "--types",
        # The help text deliberately does not spell the syllabus content file's
        # path: `test_only_the_content_loader_reads_the_syllabus_data_files`
        # scans source text and cannot tell prose from a second parser, and it is
        # right not to try. The guard is the point; the wording yields.
        help="comma-separated item types to use for THIS RUN. May only NARROW "
             "what the unit's blueprint permits, never widen it. **A run-level "
             "parameter, not a ruling on #207** — it edits no content file, "
             "re-seeds nothing, and leaves every unit's `checkpoint.item_types` "
             "exactly as it is.",
    )
    parser.add_argument(
        "--skip-control", action="store_true",
        help="do not re-run the negative control; use the banked 3/3 result "
             "from 2026-08-27. Only valid while that result stands.",
    )
    args = parser.parse_args(argv)
    if args.journal is None:
        args.journal = (
            DEFAULT_CHECKPOINT_JOURNAL if args.checkpoint else DEFAULT_JOURNAL
        )
    if args.user is None and not args.report:
        parser.error("--user is required (no default, deliberately — these rows "
                     "are permanent and belong to a learner)")
    if args.live and args.apply:
        parser.error("--live and --apply are alternatives; --apply implies --live")
    if args.retake and not args.checkpoint:
        parser.error("--retake only means anything with --checkpoint")
    if args.fill and not args.checkpoint:
        parser.error("--fill only means anything with --checkpoint")
    if args.fill and args.retake:
        # **The error says WHY, not just no.** Both adjust the twelve and they
        # adjust it from opposite directions: `--retake` RE-WEIGHTS a fresh
        # sitting toward the targets a learner missed, and `--fill` SUBTRACTS the
        # items already banked. Combining them has a defensible meaning -- top up
        # a re-weighted sitting -- and nobody has needed it, so it is refused
        # rather than given a semantics invented at the parser.
        parser.error(
            "--fill and --retake cannot be combined. --retake re-weights a fresh "
            "sitting toward missed targets; --fill subtracts what is already "
            "banked. Both adjust the same twelve from opposite directions, and no "
            "combined meaning has been ruled. Run the retake plan, then --fill "
            "against what it leaves short."
        )
    chosen_types = None
    if args.types:
        chosen_types = tuple(t.strip() for t in args.types.split(",") if t.strip())
        if not chosen_types:
            parser.error("--types is empty")

    # #140. This module spends money, and core/llm.py's per-call token lines are
    # dropped on the floor by any script that leaves the root logger bare.
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    try:
        numbers = tuple(int(n) for n in args.units.split(",") if n.strip())
    except ValueError:
        parser.error(f"--units must be comma-separated integers, got {args.units!r}")
    if not numbers:
        parser.error("--units is empty")

    if args.report:
        return report_only(args.report)

    # **The missed targets are READ, not passed in.** A retake's re-weighting is
    # a fact about what this learner got wrong, and asking an operator to type it
    # is asking them to be the source of truth for something the database holds.
    missed: dict[int, tuple[str, ...]] | None = None
    held = None
    if args.fill:
        # **Read HERE and passed in, exactly as `--retake` reads `missed_targets`
        # below.** `unit_plan` stays pure -- no database -- which is what lets its
        # tests run without one and what keeps the planner testable.
        from core.services.items import checkpoint_held

        held = {n: checkpoint_held(args.user, unit_number=n) for n in numbers}

    if args.retake:
        from core.services.syllabus import missed_targets
        missed = {n: tuple(missed_targets(args.user, n)) for n in numbers}
        for number, targets in missed.items():
            if not targets:
                parser.error(
                    f"--retake: unit {number} has no failed sitting for user "
                    f"{args.user} to re-weight against. A retake without a "
                    "failure is a first sitting; drop --retake."
                )

    if args.live or args.apply:
        return run(args.user, numbers, apply=args.apply,
                   skip_control=args.skip_control, journal_path=args.journal,
                   checkpoint=args.checkpoint, missed=missed, types=chosen_types,
                   held=held)
    return dry_run(args.user, numbers, journal_path=args.journal,
                   checkpoint=args.checkpoint, missed=missed, types=chosen_types,
                   held=held)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
