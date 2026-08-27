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
from dataclasses import dataclass, field
from pathlib import Path

from core import PROMPTS_DIR
from core.config import Settings, load_settings
from core.items import gates
from core.items.checks import COVERAGE_FLOOR, judged_sentence, sentence_of
from core.items.gates import MAX_REPAIRS, TARGET_DECOYS, TargetVerdict, ValidationReport
from core.items.grading import normalise_variants
from core.items.schema import BaseItem, parse
from core.sessions.blocks import visible_targets

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

#: The prescribed type per slot, in order. All seven types that units 1-3's
#: checkpoints permit, plus one repeat of `cloze_cued` -- the only `slot`-family
#: type here, and therefore the only one `repair.LADDER` can rescue.
#:
#: **Zero TTS and zero STT calls.** `dictation`, `listening_gap`, `speak_repeat`
#: and `speak_answer` are not permitted by units 1-3's blueprints, so
#: `gates._audio_gate` -- which bills two providers -- is never reached.
SLOT_TYPES: tuple[str, ...] = (
    "mcq",
    "cloze_cued",
    "word_bank_order",
    "error_spot",
    "match_pairs",
    "collocation_pick",
    "l1_to_l2_production",
    "cloze_cued",
)

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
    """One of the eight: which type, testing which target."""

    index: int
    item_type: str
    target: str


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
        )
        for index, item_type in enumerate(SLOT_TYPES)
    )


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


def build_payload(unit_number: int, can_do: str, slots: tuple[Slot, ...]) -> dict:
    """The user message for one unit's generation call. **No citation reaches it.**

    `can_do` and the target TEXT and nothing else. The targets arrive through
    `core.sessions.blocks.visible_targets` at the call site -- the seam #171's
    ruling is asserted at -- so `murphy_units` was never in the object this
    function is handed. **This matters more here than on any screen**: a rendered
    citation is visible and removable, and an assumption embedded in a generated
    sentence is neither.
    """
    return {
        "unit_number": unit_number,
        "can_do": can_do,
        "track": track_for(unit_number),
        "items": [
            {"n": slot.index + 1, "item_type": slot.item_type, "grammar_target": slot.target}
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
    if draft.get("answer") is not None and not draft.get("accepted_variants"):
        draft["accepted_variants"] = list(normalise_variants(draft["answer"]))
    return parse(draft)


# ── the cohort: one unit, eight slots, cheapest gate first ──────────────────


def generate_drafts(
    payload: dict, *, settings: Settings | None = None
) -> list[dict]:
    """One billed call. The raw drafts, in the order the model returned them."""
    response = gates._chat(
        [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        system=(PROMPTS_DIR / "item_generate.txt").read_text(encoding="utf-8"),
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
GENERATE_MAX_TOKENS = 8000


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
        except Exception as exc:  # pydantic ValidationError, ValueError
            outcomes.append(
                _discard(slot, unit_number, "generation", f"schema_error: {exc}"[:200])
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


# ── the accounting ──────────────────────────────────────────────────────────


@dataclass
class Tally:
    """The identity the run prints, per unit and in total.

        drafted  = accepted + discarded + duplicate
        accepted = passed + repaired
        served   = accepted, against a target of ITEMS_PER_UNIT

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

    def add(self, outcome: Outcome) -> None:
        self.drafted += 1
        if outcome.state == "accepted":
            self.accepted += 1
            if outcome.report is not None and outcome.report.repair_count:
                self.repaired += 1
        elif outcome.state == "duplicate":
            self.duplicate += 1
        else:
            self.discarded += 1
            self.by_stage[outcome.stage or "unknown"] += 1
            for code in outcome.codes:
                self.by_code[code] += 1


def tally_of(outcomes: list[Outcome]) -> Tally:
    out = Tally()
    for outcome in outcomes:
        out.add(outcome)
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


def _print_cross_tab(outcomes: list[Outcome]) -> None:
    """#168's numbers: `type x target`, never type alone.

    A type that fails only against targets it was never suited to is a different
    finding from a type that fails everywhere, and only the second is an argument
    for narrowing `checkpoint.item_types`. Printing type alone would merge them.
    """
    print("\n#168 — yield by TYPE x TARGET. n is small; see P6.")
    cells: dict[tuple[str, str], list[Outcome]] = {}
    for outcome in outcomes:
        cells.setdefault((outcome.slot.item_type, outcome.slot.target), []).append(outcome)

    by_type: dict[str, list[Outcome]] = {}
    for outcome in outcomes:
        by_type.setdefault(outcome.slot.item_type, []).append(outcome)

    for item_type in sorted(by_type):
        rows = by_type[item_type]
        accepted = sum(1 for r in rows if r.accepted)
        print(f"\n  {item_type}  —  {accepted}/{len(rows)} accepted")
        for (cell_type, target), entries in sorted(cells.items()):
            if cell_type != item_type:
                continue
            ok = sum(1 for e in entries if e.accepted)
            stages = Counter(e.stage for e in entries if not e.accepted and e.stage)
            why = ("  " + ", ".join(f"{k}:{v}" for k, v in sorted(stages.items()))) if stages else ""
            print(f"      {ok}/{len(entries)}  u{entries[0].unit_number}  {target!r}{why}")

    zero = [t for t, rows in by_type.items() if not any(r.accepted for r in rows)]
    if zero:
        print(
            f"\n  ZERO ACCEPTED: {sorted(zero)}. **This does not by itself justify "
            "removing a type\n  from `checkpoint.item_types`** — n is 3 (6 for "
            "cloze_cued) and no bar at that n\n  separates a bad type from an "
            "unlucky one. A removal needs a STRUCTURAL finding\n  beside it; today "
            "`match_pairs` is the only type that has one (its uniqueness\n  gate is "
            "unreachable — see the known issues). #168 stays open."
        )


def _print_targets(outcomes: list[Outcome]) -> None:
    """Where the claimed target ranked, and what came second.

    **The runner-up is recorded on items that PASSED** (#119). When the claimed
    target wins, second place is the distinction the item came closest to
    blurring, and it is the single most useful line for whoever rewrites the
    generator prompt. A gate that reports only pass/fail throws that away.
    """
    interesting = [o for o in outcomes if o.target is not None]
    if not interesting:
        return
    print("\nprobe_target — rank of the claimed target, and the runner-up:")
    for outcome in sorted(interesting, key=lambda o: (o.unit_number, o.slot.index)):
        verdict = outcome.target
        assert verdict is not None
        mark = "ok " if verdict.ok else "**FAIL**"
        rank = verdict.claimed_rank or "absent"
        runner = f" · runner-up {verdict.runner_up!r}" if verdict.runner_up else ""
        print(
            f"  {mark} u{outcome.unit_number} slot {outcome.slot.index + 1} "
            f"{outcome.slot.item_type:<20} rank {rank}"
            f" ({verdict.confidence or '-'}){runner}"
        )
        if not verdict.ok and verdict.first:
            print(f"        ranked first instead: {verdict.first!r}")


def _print_back_translations(outcomes: list[Outcome]) -> None:
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
    rows = [o for o in outcomes if o.back_translation]
    if not rows:
        return
    print(
        "\n#102 — READ THESE TWO LINES AGAINST EACH OTHER. Nothing in this "
        "pipeline can.\n  The gates never see both sides of an L1→L2 relation; "
        "you are the only reader who does."
    )
    for outcome in rows:
        assert outcome.item is not None
        print(f"\n  u{outcome.unit_number} slot {outcome.slot.index + 1}")
        print(f"    prompt as authored : {outcome.item.prompt_text}")
        print(f"    English answer     : {outcome.item.answer}")
        print(f"    back-translated    : {outcome.back_translation}")


# ── the pre-registered verdicts, applied by the module ──────────────────────


def _band(name: str, value: int, low: int, high: int, total: int, over: str) -> bool:
    met = low <= value <= high
    print(f"  {name}: {value} of {total} — predicted {low}-{high} — "
          f"{'MET' if met else 'NOT MET'}")
    if not met:
        print(f"      {over}")
    return met


def print_verdicts(outcomes: list[Outcome], control: "ControlResult") -> None:
    """Every branch rule, evaluated here rather than by whoever reads the output.

    W8b's finding, carried: a pre-registered prediction constrains honesty about
    the axis it names and says nothing about an axis it does not. Each of these
    is its own axis and each gets its own line.
    """
    total = len(outcomes)
    accepted = sum(1 for o in outcomes if o.accepted)
    drift = sum(1 for o in outcomes if o.stage == "target")
    unnatural = sum(1 for o in outcomes if o.stage == "judge")
    ambiguous = sum(
        1 for o in outcomes
        if o.report is not None
        and any(c in ("multi_acceptable", "not_recoverable", "under_specified",
                      "widened")
                for c in o.report.blind_solver)
    )

    print("\n" + "=" * 78)
    print("PRE-REGISTERED PREDICTIONS — written before this run, evaluated by it")
    print("=" * 78)
    _band("P1 accept rate    ", accepted, P1_LOW, P1_HIGH, total,
          "≥19 → gates may be weak at this n; P5 decides whether to believe it. "
          "≤11 → THE PROMPT IS WRONG, NOT THE GATE (rule 7): fix the prompt and "
          "re-run; do not loosen a gate.")
    _band("P2 target drift   ", drift, P2_LOW, P2_HIGH, total,
          "≥7 → the prompt is asking for grammar-flavoured sentences rather than "
          "demonstrations of a named point. Rewrite the prompt, not the check.")
    _band("P3 unnatural      ", unnatural, P3_LOW, P3_HIGH, total,
          "≥10 → read them before touching anything; #115 recorded 6/11 on "
          "hand-written fixtures and the judge is strict.")
    _band("P4 ambiguity      ", ambiguous, P4_LOW, P4_HIGH, total,
          "≥14 → grammar gaps are structurally more ambiguous than vocabulary "
          "gaps; the TYPE MIX is the fix, not the gate.")

    print(f"  P5 control        : {control.failures} of {control.runs} runs "
          f"correctly refused the mis-targeted item")
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

    measured = [o for o in outcomes if o.accepted and o.coverage_pct is not None]
    below = sum(1 for o in measured if o.coverage_pct < COVERAGE_FLOOR * 100)
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


def unit_plan(numbers: tuple[int, ...]) -> dict[int, dict]:
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
        plan[number] = {
            "unit": unit,
            "targets": targets,
            "slots": slot_plan(number, targets),
            "candidates": target_candidates(number, targets, all_targets),
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


def dry_run(user_id: int, numbers: tuple[int, ...]) -> int:
    settings = load_settings()
    plan = unit_plan(numbers)

    print("=== model ===")
    print(settings.llm_model)
    print(f"\n=== target ===\nusers.id = {user_id} · units {list(numbers)} · "
          f"{ITEMS_PER_UNIT} items each")

    print("\n=== system (item_generate.txt) ===")
    print((PROMPTS_DIR / "item_generate.txt").read_text(encoding="utf-8"))

    print("=== system (item_target.txt) ===")
    print((PROMPTS_DIR / "item_target.txt").read_text(encoding="utf-8"))

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

    print("\n=== billed calls ===")
    print(f"  ceiling {_expected_calls(numbers)} "
          f"(control {CONTROL_RUNS} + {len(numbers)} units, one top-up allowed)")
    print("  ZERO TTS and ZERO STT: no audio type is permitted by these units.")

    print("\ndry run — nothing was sent and nothing was written.")
    return 0


# ── live ────────────────────────────────────────────────────────────────────


def _confirm(prompt: str, expected: str) -> bool:
    """Type it back. There is no `--yes`, deliberately.

    The guard `seed_fixtures`, `rewrite_checkpoints` and `retire_chunk_cloze`
    all use, for the same reason: a flag that can be pasted out of a runbook is
    not a decision.
    """
    typed = input(f"{prompt} Type {expected} to continue, anything else to stop: ")
    return typed.strip() == expected


def run(
    user_id: int,
    numbers: tuple[int, ...],
    *,
    apply: bool,
    settings: Settings | None = None,
) -> int:
    settings = settings or load_settings()
    plan = unit_plan(numbers)
    spent: Counter = Counter()
    reference = coverage_reference()

    ceiling = _expected_calls(numbers)
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
    control = run_control(settings=settings)
    spent["control"] += CONTROL_RUNS
    if not control.ok:
        print(
            f"\n**RUN VOID.** The mis-targeted control was refused in only "
            f"{control.failures} of {control.runs} runs, below the "
            f"{CONTROL_MUST_FAIL}-of-{control.runs} bar.\n`probe_target` does "
            "not discriminate, so nothing it says about a real item means\n"
            "anything. Nothing was written. This is a finding: record it."
        )
        return 1
    print(f"\ncontrol PASSED ({control.failures}/{control.runs} refused) — the "
          "check discriminates.")

    # --- the units
    all_outcomes: list[Outcome] = []
    per_unit: dict[int, list[Outcome]] = {}
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

        # --- one top-up round, asking for exactly the shortfall
        short = [o for o in outcomes if not o.accepted]
        if short:
            print(f"\n  {len(short)} slot(s) short — one top-up round, "
                  "with the failures fed back.")
            outcomes = _top_up(
                outcomes, short, entry, number, settings=settings, calls=spent
            )

        per_unit[number] = outcomes
        all_outcomes.extend(outcomes)
        _print_items(outcomes)

    # --- the accounting
    print("\n" + "=" * 78)
    print("ACCOUNTING — drafted = accepted + discarded + duplicate")
    print("=" * 78)
    for number in numbers:
        _print_tally(f"unit {number}", tally_of(per_unit[number]), target=ITEMS_PER_UNIT)
    total = tally_of(all_outcomes)
    _print_tally("TOTAL", total, target=ITEMS_PER_UNIT * len(numbers))

    _print_targets(all_outcomes)
    _print_back_translations(all_outcomes)
    _print_cross_tab(all_outcomes)
    print_verdicts(all_outcomes, control)

    print(f"\nbilled calls this run: {sum(spent.values())} "
          f"({' · '.join(f'{k} {v}' for k, v in sorted(spent.items()))})")
    print(
        "\n24 ITEMS, ONE SAMPLE EACH, of a stochastic system. A fail is decisive; "
        "a pass is\nnot proof. `probe_target` is a model checking a model, "
        "plausibly the same model\nwith correlated blind spots — a fluent item "
        "teaching a subtly wrong point can\npass every gate above. Nobody should "
        "later read this run as 'the items were\nverified'."
    )

    if not apply:
        print("\n--live — nothing was written. Re-run with --apply to write.")
        return 0
    return _write(user_id, all_outcomes, settings=settings)


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
    slots = tuple(o.slot for o in short)
    payload = build_payload(unit_number, entry["unit"].can_do, slots)
    payload["retry"] = [
        {
            "n": o.slot.index + 1,
            "rejected_because": list(o.codes),
            "at_stage": o.stage,
        }
        for o in short
    ]
    payload["note"] = (
        "These slots were rejected. Write NEW items for them — do not resubmit "
        "the same sentences. `rejected_because` says what the gates found."
    )
    drafts = generate_drafts(payload, settings=settings)
    calls["generate"] += 1
    replacements = verify_cohort(
        # The slots keep their ORIGINAL indices for reporting, but the drafts
        # come back in the order asked for, so the plan handed to the verifier is
        # re-indexed to match and the outcome is mapped back afterwards.
        tuple(Slot(index=i, item_type=s.item_type, target=s.target)
              for i, s in enumerate(slots)),
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


def _print_items(outcomes: list[Outcome]) -> None:
    """Every slot, accepted or not. **Nothing is summarised away before a write.**

    `rewrite_checkpoints` prints all 24 rows before it touches any of them, for
    the reason that applies here with more force: this output is the only record
    of what the model produced, and the operator reads the items from it.
    """
    print()
    for outcome in outcomes:
        slot = outcome.slot
        mark = "OK " if outcome.accepted else "-- "
        extra = " (top-up)" if outcome.topped_up else ""
        print(f"  {mark} {slot.index + 1}. {slot.item_type:<20} {slot.target!r}{extra}")
        if outcome.item is not None:
            item = outcome.item
            print(f"        prompt : {item.prompt_text}")
            if item.answer is not None:
                print(f"        answer : {item.answer}")
            for name in ("options", "bank", "tiles", "pairs"):
                value = getattr(item, name, None)
                if value:
                    print(f"        {name:<7}: {list(value)}")
            if item.cue_text:
                print(f"        cue    : {item.cue_text}")
            if item.explanation:
                print(f"        why    : {item.explanation}")
            if outcome.coverage_pct is not None:
                below = outcome.coverage_pct < COVERAGE_FLOOR * 100
                flag = "  ** BELOW THE 90% FLOOR (measured, not enforced) **" if below else ""
                unknown = (f" unknown={list(outcome.coverage_unknown)}"
                           if outcome.coverage_unknown else "")
                print(f"        cover  : {outcome.coverage_pct}%{unknown}{flag}")
        if not outcome.accepted:
            print(f"        REJECTED at {outcome.stage}: {list(outcome.codes)}")
        elif outcome.report is not None and outcome.report.repair_count:
            print(f"        repaired x{outcome.report.repair_count} "
                  f"({outcome.report.cue_applied})")


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
        "--user", type=int, required=True,
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
    args = parser.parse_args(argv)
    if args.live and args.apply:
        parser.error("--live and --apply are alternatives; --apply implies --live")

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

    if args.live or args.apply:
        return run(args.user, numbers, apply=args.apply)
    return dry_run(args.user, numbers)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
