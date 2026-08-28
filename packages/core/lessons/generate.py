"""The lesson generator. HUMAN-RUN, DRY BY DEFAULT, and it writes nothing unasked.

    python -m core.lessons.generate [--units 1,9,20] [--live] [--apply]
                                    [--journal PATH] [--report JOURNAL]
                                    [--skip-control]

Generation is human-run by operator ruling (2026-08-27, from #196), and that
ruling is INDEPENDENT of #69: it would hold unchanged if `english-worker` were
installed tomorrow. Nothing here is scheduled, `assign_daily` is untouched, and
`tests/test_worker.py::test_assign_daily_is_registered_and_creates_no_content`
stays green without being edited.

═══════════════════════════════════════════════════════════════════════════════
WHERE THIS RUNS: **THE ENTIRE STAGED RUN HAPPENS ON THE PRODUCTION HOST.**
NOTHING BILLED IS EVER RUN ON THE MAC.
═══════════════════════════════════════════════════════════════════════════════

`--apply` writes to whatever `DATABASE_URL` points at, and on the Mac that is the
dev database at `localhost:5433`. **`grammar_lessons` rows are GLOBAL CONTENT
that must exist in production.** A local `--apply` would spend the full billed
ceiling, pass every gate, write three lessons into a database no learner reads --
and **look completely successful**. There would be nothing in its output to say
otherwise: same verdicts, same axes, same `3 lesson(s) written.`

**This record already carries that exact incident.** Running a billed command
locally and writing to the wrong database is not a hypothetical here; it is a
thing that has happened and been filed. The failure mode is silence, not an
error, which is why the instruction lives on the path that runs rather than only
in `BUILD_PROGRESS.md`.

So, in order, and ALL OF IT on the server::

    cd /home/bot/english-bot
    sudo -u bot .venv/bin/python -m core.lessons.generate --units 1,9,20   # dry
    sudo -u bot .venv/bin/python -m core.lessons.generate --live  --units 1
    sudo -u bot .venv/bin/python -m core.lessons.generate --apply --units 1
    # then READ unit 1 in block 3, on a phone. That reading authorises stage 2.
    sudo -u bot .venv/bin/python -m core.lessons.generate --live  --units 9,20 --skip-control
    sudo -u bot .venv/bin/python -m core.lessons.generate --apply --units 9,20 --skip-control

**The Mac's database is for the migration tests and the dry run's plumbing, and
for nothing else.**

**WHAT THE DRY RUN PRINTS LOCALLY VERSUS ON THE HOST, because the operator will
see both and they are not the same claim.** Everything the dry run prints is
identical in the two places -- the prompts, the payloads, the candidates, the
174 ceiling -- **except one line**::

    stored lessons below LESSON_VERSION: n of m

That line is a **read of whatever database `DATABASE_URL` names**. On the Mac it
reports the dev database and **says nothing whatever about production**: `0 of 0`
there means the Mac has no lessons, not that production has none. Only the line
printed **on the host** is a statement about the rows a learner could reach.

═══════════════════════════════════════════════════════════════════════════════
THE OPERATOR CANNOT VERIFY THE ENGLISH, and this module is built around that
rather than apologising for it at the end.
═══════════════════════════════════════════════════════════════════════════════

A wrong explanation of the present perfect reaches two B1 learners who cannot
tell it is wrong, and they will believe it. So what the operator's own reading is
for is split three ways, and the split is written here rather than left to be
assumed:

  (a) HIS READING, and nothing else, establishes: that the lesson reads as
      TEACHING rather than as a definition list; that the wrong example is a
      mistake somebody would really make; that eight sections behind four labels
      feel like an explanation rather than a form; and **whether the DIAGRAM
      READS ON A PHONE** -- a timeline that is confusing is a visual judgement,
      not an English one, and it is the one judgement in this slice he can
      actually make.
  (b) THE GATES, and not his reading, establish: the bijection, target-first on
      every section (C1), demonstration-not-decoration on every example (C2),
      internal consistency (C3), naturalness, no-guilt, diagram structure. He
      reads the stored verdicts, not the English.
  (c) NEITHER establishes whether the lesson is correct English teaching a
      correct point. That rests on C1/C2/C3, which are a model checking a model,
      plausibly the same model, with correlated blind spots. **It is not quietly
      reassigned to a reader who has said he cannot do it**, and it is the
      strongest reason the scope is 3 lessons and not 24.

═══════════════════════════════════════════════════════════════════════════════
PRE-REGISTERED AXES AND BRANCH RULES -- written before `--live` is ever executed
═══════════════════════════════════════════════════════════════════════════════

W8b's transferable finding, carried: **a pre-registered prediction constrains
honesty about the axis it names and says nothing about an axis it does not.** So
each axis gets its own number, and `--live` evaluates its own branch rules and
prints the verdict, so the reading cannot bend once the number arrives.

L1  LESSONS FAILING VERIFICATION ON THE FIRST PASS -- 0-1 of 3.
    0     -> the checks may be too weak at n=3; L6 decides whether to believe it.
    1     -> expected. Regenerate, and record which check caught it.
    2-3   -> THE GENERATOR PROMPT IS WRONG, NOT THE GATE. Fix the prompt, re-run,
             do not loosen a check (CLAUDE.md §3 rule 7).

L2  SECTIONS FAILING C1 (target-first) -- 0-2 of 12.
    >=5   -> rewrite the prompt, not C1.
    Low because the generator is GIVEN the target verbatim; not zero because
    unit 1's four targets share one tense and C1's sibling decoys are close.

L3  EXAMPLES FAILING C2 -- 0-4 of the 24-36 produced.
    >=9   -> the prompt is asking for EXAMPLES rather than for DEMONSTRATIONS.

L4  EXAMPLES REJECTED BY `judge_naturalness` -- 0-6 of the 24-36 produced.
    >=12  -> read them before touching anything. #115 recorded 6/11 on
             hand-written items and the judge is strict.

L5  DIAGRAMS FAILING THE DETERMINISTIC CHECKS -- 0-2 OF HOWEVER MANY WERE MADE.
    >=4   -> tighten the diagram schema, not the check.
    **Re-based.** An earlier draft wrote "0-1 of ~6", which came from a diagram
    cap of 3 that no longer exists. With twelve targets that all admit a kind and
    L8 predicting 2-3 per lesson the denominator is 6-9 expected and 12 possible,
    so the band is stated over what was PRODUCED and `runs.band` is given the
    real denominator. A band written over a denominator that did not happen is
    what #201 and #206 fixed.

L6  THE DRIFTED CONTROL FAILS C1 -- 3 of 3. **BAR: 2 of 3.**
    < 2   -> THE RUN IS VOID. Nothing is written, whatever the lessons did.
    The prediction and the bar are different numbers ON PURPOSE and the gap is
    stated once rather than silently reconciled: the prediction is what a working
    C1 should do, the bar is what constitutes evidence that C1 discriminates AT
    ALL. One stochastic miss on a borderline classification is not the same event
    as a gate that cannot tell two past tenses apart. 2 of 3 prints as
    `prediction NOT MET, run acceptable`, in those words.

L7  SECTION-PROSE COVERAGE against the B1 reference -- 88-96%.
    **REPORTED, NEVER ENFORCED.** No lesson is rejected for it and no
    regeneration is triggered by it. Grammar prose has to say *past participle*
    and *time linker*, and #197 measured 8 of 8 everyday sentences below the 0.90
    ITEM floor against the real ledger -- so a 95% gate on metalanguage risks an
    axis no lesson can pass, which is #213's shape. The bar is DECLINED BEFORE IT
    IS SET rather than lowered after, and the number goes in the record so the
    21-unit slice can set one on evidence.
    < 85% -> the metalanguage cost is larger than predicted and the ruling on
             #197 for prose is the operator's, owed against a number.

L8  DIAGRAMS PER LESSON -- 2-3, of a possible 4.
    0 for any lesson -> read that unit's four targets and say which kind was
             declined and why: either the closed set is short a kind, or the
             prompt is not offering them.
    4 of 4 on every lesson -> the generator is decorating rather than choosing,
             and *fewer rather than false* is not being exercised.
    **Zero is reported, never rejected** -- a lesson with no diagram is storable
    by construction, and forcing one is the "false" half of the rule.

═══════════════════════════════════════════════════════════════════════════════
WHAT VERIFICATION CANNOT DO -- recorded plainly, not as an aside
═══════════════════════════════════════════════════════════════════════════════

1. It is a MODEL CHECKING A MODEL, plausibly the same model, with correlated
   blind spots. A wrong-but-fluent explanation of a fine distinction can pass C1,
   C2 and C3 together. This is not equivalent to a human reading it.
2. ONE SAMPLE PER CHECK of a stochastic system. A fail is decisive; a pass is
   not proof.
3. NOTHING CHECKS THAT THE LESSON IS USEFUL. A section can teach its target,
   contradict nothing, sit at 96% coverage, and help nobody.
4. NOTHING CHECKS THAT THE DIAGRAM READS. That is (a), and it is the operator's.
5. A FRONTIER MODEL RESOLVES DISTINCTIONS A B1 LEARNER WILL MISS, so a clean C1
   is weaker evidence about a learner than it looks -- the same asymmetry this
   record already states for STT and for the blind solver.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from core import PROMPTS_DIR
from core.config import Settings, load_settings
from core.items import gates as item_gates
from core.items.generate import coverage_reference, target_candidates, track_for
from core.items.gates import TargetVerdict
from core.lessons import (
    DIAGRAMS_PER_LESSON,
    LESSON_VERSION,
    MAX_REGENERATIONS,
    SCOPE_UNITS,
)
from core.lessons import checks as lesson_checks
from core.lessons import gates as lesson_gates
from core.lessons.schema import (
    Lesson,
    constraint_block,
    contract_block,
    diagram_text,
    parse_lesson,
)
from core.runs import band, confirm
from core.sessions.blocks import visible_targets

logger = logging.getLogger(__name__)

DEFAULT_JOURNAL = Path("w10b-journal.jsonl")
CONTROL_FIXTURE = Path("tests") / "fixtures" / "lessons" / "drifted.json"
CONTROL_RUNS = 3
CONTROL_MUST_FAIL = 2

#: A four-section lesson with diagrams runs ~1,600-2,400 output tokens. Set with
#: headroom, and for W10c's hard-won reason: on Sonnet 5 omitting the `thinking`
#: parameter runs ADAPTIVE THINKING, and thinking tokens are billed and count
#: against `max_tokens`. Attempt 1 of W10c died at 8,000 on a response whose text
#: was a fifth of that.
LESSON_MAX_TOKENS = 16000

# Pre-registered bands. Named here so `print_verdicts` cannot quietly disagree
# with the docstring above.
L1_LOW, L1_HIGH = 0, 1
L2_LOW, L2_HIGH = 0, 2
L3_LOW, L3_HIGH = 0, 4
L4_LOW, L4_HIGH = 0, 6
L5_LOW, L5_HIGH = 0, 2
L7_LOW, L7_HIGH = 88, 96
L8_LOW, L8_HIGH = 2, 3


# ── the prompt ──────────────────────────────────────────────────────────────


def lesson_system_prompt() -> str:
    """`lesson_generate.txt` with the contract and constraints substituted in.

    **The dry run calls THIS, never the raw template**, and that is W10c's own
    caught defect rather than a precaution: its `dry_run` printed the template
    with `{contract}` unsubstituted while `--live` sent the built version, so the
    two disagreed about the system prompt on the one output that existed to be
    read before paying for it. Read the thing that changed, from the path that
    will actually run.
    """
    template = (PROMPTS_DIR / "lesson_generate.txt").read_text(encoding="utf-8")
    return (
        template
        .replace("{contract}", contract_block())
        .replace("{constraints}", constraint_block())
    )


def build_payload(unit_number: int, can_do: str, targets: Sequence[str]) -> dict:
    """What the generator is given for one unit. **No Murphy citation, ever.**

    The targets arrive through `core.sessions.blocks.visible_targets` and NOT
    through `unit.grammar_targets`, which is #171's constraint applied at the
    generation seam: that function builds the visible dict by NAMING the one
    field that may travel, so `murphy_units` is withheld by default rather than
    remembered about. `core.items.generate.unit_plan` uses the same chokepoint.
    """
    return {
        "unit_number": unit_number,
        "can_do": can_do,
        "track": track_for(unit_number),
        "grammar_targets": list(targets),
    }


def unit_plan(numbers: Sequence[int]) -> dict[int, dict]:
    """Everything the run needs about each unit. **The Murphy strip is here.**"""
    from core.syllabus.content import units

    everything = {u.unit_number: u for u in units()}
    missing = [n for n in numbers if n not in everything]
    if missing:
        raise ValueError(f"no such unit(s): {missing}")

    all_targets = {
        number: tuple(t["target"] for t in visible_targets(unit.grammar_targets))
        for number, unit in everything.items()
    }
    return {
        number: {
            "can_do": everything[number].can_do,
            "targets": all_targets[number],
            "candidates": target_candidates(
                number, all_targets[number], all_targets
            ),
        }
        for number in numbers
    }


# ── cost ────────────────────────────────────────────────────────────────────


def _calls_per_pass(sections: int, examples: int) -> int:
    return (
        1            # generation
        + sections   # C1, one per section
        + examples   # C2, one per example -- never batched, see gates.py
        + 1          # one batched naturalness call for the whole lesson
        + 1          # C3, one over the whole lesson
    )


def expected_calls(plan: dict[int, dict]) -> int:
    """The ceiling, itemised. Printed before anything is spent.

    A TRUE worst case: every lesson exhausts both regenerations. The archived
    plan's `<= 65` was the EXPECTED case labelled as a ceiling -- the same error
    W10c's `<= 110` was, stated rather than silently reconciled.
    """
    total = CONTROL_RUNS
    for info in plan.values():
        sections = len(info["targets"])
        # The ceiling assumes the upper bound on examples per section.
        total += _calls_per_pass(sections, sections * 3) * (1 + MAX_REGENERATIONS)
    return total


# ── verification ────────────────────────────────────────────────────────────


@dataclass
class Outcome:
    """One lesson's fate, and every diagnostic that decided it."""

    unit: int
    state: str = "pending"
    stage: str | None = None
    attempt: int = 1
    codes: tuple[str, ...] = ()
    details: tuple[str, ...] = ()
    lesson: Lesson | None = None
    section_verdicts: dict[str, dict] = field(default_factory=dict)
    example_verdicts: list[dict] = field(default_factory=list)
    unnatural: list[str] = field(default_factory=list)
    contradictions: tuple[str, ...] = ()
    coverage_pct: dict[str, float] = field(default_factory=dict)
    coverage_unknown: dict[str, tuple[str, ...]] = field(default_factory=dict)
    diagram_count: int = 0


def _verdict_row(verdict: TargetVerdict) -> dict:
    """Everything `TargetVerdict` knows, kept. #119's lesson, and #194's.

    The RUNNER-UP is the sharp one: on a section that PASSED, second place is the
    distinction the prose came closest to blurring. #194 is that W10c printed it
    and then lost it; here it is stored on the lesson's own verification blob, so
    the evidence survives the run that produced it.
    """
    return {
        "ranking": list(verdict.ranking),
        "claimed_rank": verdict.claimed_rank,
        "first": verdict.first,
        "runner_up": verdict.runner_up,
        "confidence": verdict.confidence,
        "ok": verdict.ok,
    }


def verify_lesson(
    lesson: Lesson,
    info: dict,
    *,
    reference: frozenset[str],
    settings: Settings | None = None,
) -> Outcome:
    """Every gate, cheapest first. **Free checks before a single billed call.**"""
    from core.lexicon.coverage import compute_coverage

    out = Outcome(unit=lesson.unit_number, lesson=lesson)
    targets = info["targets"]
    candidates = info["candidates"]
    out.diagram_count = len(lesson.diagrams)

    # ── free ────────────────────────────────────────────────────────────────
    failures = lesson_checks.deterministic_failures(lesson, targets)
    if failures:
        out.state = "rejected"
        out.stage = "deterministic"
        out.codes = tuple(f.code for f in failures)
        out.details = tuple(str(f) for f in failures)
        return out

    # Coverage is MEASURED AND REPORTED, never enforced (L7, #197). Computed
    # here so it is on the record even for a lesson that later fails a gate.
    for section in lesson.sections:
        report = compute_coverage(lesson_checks.section_prose(section), reference)
        out.coverage_pct[section.target] = report.percent
        out.coverage_unknown[section.target] = tuple(report.unknown_lemmas)

    # ── C1, one call per section ────────────────────────────────────────────
    by_target = {spec.target: diagram_text(spec) for spec in lesson.diagrams}
    drifted: list[str] = []
    for section in lesson.sections:
        verdict = lesson_gates.on_target(
            section,
            candidates=candidates,
            diagram=by_target.get(section.target),
            settings=settings,
        )
        out.section_verdicts[section.target] = _verdict_row(verdict)
        if not verdict.ok:
            drifted.append(section.target)
    if drifted:
        out.state = "rejected"
        out.stage = "on_target"
        out.codes = ("section_off_target",) * len(drifted)
        out.details = tuple(
            f"{t!r} ranked "
            f"{out.section_verdicts[t]['claimed_rank']}, behind "
            f"{out.section_verdicts[t]['first']!r}"
            for t in drifted
        )
        return out

    # ── C2, one call per example ────────────────────────────────────────────
    off: list[str] = []
    for section in lesson.sections:
        for sentence in section.examples:
            verdict = lesson_gates.example_demonstrates(
                sentence,
                claimed=section.target,
                candidates=candidates,
                settings=settings,
            )
            row = _verdict_row(verdict)
            row["sentence"] = sentence
            row["target"] = section.target
            out.example_verdicts.append(row)
            if not verdict.ok:
                off.append(sentence)
    if off:
        out.state = "rejected"
        out.stage = "structure"
        out.codes = ("example_does_not_demonstrate",) * len(off)
        out.details = tuple(f"{s!r}" for s in off)
        return out

    # ── naturalness, ONE batched call ───────────────────────────────────────
    # **The judge sees the examples and never the explanation.** Its prompt asks
    # "would a real person say this to a friend?" -- a correct question for an
    # example sentence and a meaningless one for a paragraph of teaching.
    # Handing it the explanation is #115's mistake with the polarity flipped.
    #
    # 12 sentences is inside `JUDGE_BATCH` (20), so this is the FIRST CALLER
    # EVER to actually use the batch path -- every existing call site passes a
    # list of one. It does NOT close #120, which is about `gates.validate`'s
    # per-item call; it demonstrates the path works.
    sentences = [s for section in lesson.sections for s in section.examples]
    verdicts = item_gates.judge_naturalness(sentences, settings=settings)
    for sentence, verdict in zip(sentences, verdicts, strict=True):
        if not verdict.natural:
            out.unnatural.append(f"{sentence!r}: {verdict.reason}")
    if out.unnatural:
        out.state = "rejected"
        out.stage = "naturalness"
        out.codes = ("unnatural",) * len(out.unnatural)
        out.details = tuple(out.unnatural)
        return out

    # ── C3, one call over the whole lesson ──────────────────────────────────
    out.contradictions = lesson_gates.contradictions(lesson, settings=settings)
    if out.contradictions:
        out.state = "rejected"
        out.stage = "contradiction"
        out.codes = ("contradiction",) * len(out.contradictions)
        out.details = out.contradictions
        return out

    out.state = "accepted"
    return out


def verification_blob(out: Outcome) -> dict:
    """What goes in `grammar_lessons.verification`. Mirrors `items.validation`.

    **#194 is answered here rather than repeated.** W10c printed its
    `TargetVerdict`s and stored none, so the evidence for *this item tests its
    target* survived only in stdout. Every C1 and C2 verdict, runner-up included,
    is stored on the row.
    """
    return {
        "verdict": "passed" if out.state == "accepted" else out.state,
        "lesson_version": LESSON_VERSION,
        "attempt": out.attempt,
        "sections": out.section_verdicts,
        "examples": out.example_verdicts,
        "contradictions": list(out.contradictions),
        "coverage_pct": out.coverage_pct,
        "coverage_unknown": {k: list(v) for k, v in out.coverage_unknown.items()},
        "diagram_count": out.diagram_count,
    }


# ── the negative control ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ControlResult:
    runs: int
    failures: int
    ranks: tuple[int | None, ...]

    @property
    def ok(self) -> bool:
        return self.failures >= CONTROL_MUST_FAIL


def run_control(*, settings: Settings | None = None) -> ControlResult:
    """The drifted section through C1, three times, BEFORE any lesson.

    `verify.py`'s central lesson: **a check that rejects nothing passes the catch
    direction perfectly.** C1 is the one gate here that could be inert and still
    look like it is working -- every section would rank its claimed target first
    and every lesson would pass.

    It runs first so a dead C1 costs three calls rather than a hundred and
    seventy-four.
    """
    from core.lessons.schema import Section

    fixture = json.loads(CONTROL_FIXTURE.read_text(encoding="utf-8"))
    section = Section.model_validate(fixture["section"])
    ranks: list[int | None] = []
    for _ in range(CONTROL_RUNS):
        verdict = lesson_gates.on_target(
            section, candidates=fixture["candidates"], settings=settings
        )
        ranks.append(verdict.claimed_rank)
    return ControlResult(
        runs=CONTROL_RUNS,
        failures=sum(1 for r in ranks if r != 1),
        ranks=tuple(ranks),
    )


# ── the journal ─────────────────────────────────────────────────────────────


def journal_line(out: Outcome) -> dict:
    return {
        "unit": out.unit,
        "attempt": out.attempt,
        "state": out.state,
        "stage": out.stage,
        "codes": list(out.codes),
        "details": list(out.details),
        "diagram_count": out.diagram_count,
        "coverage_pct": out.coverage_pct,
        "sections": out.section_verdicts,
        "examples": out.example_verdicts,
        "contradictions": list(out.contradictions),
        "lesson": out.lesson.model_dump(mode="json") if out.lesson else None,
    }


class Journal:
    """Outcomes on disk as they are decided, flushed every time.

    **This is what stopped W10c's five failed attempts being re-bought.**
    `--report` rebuilds the whole reading from it with zero calls.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, outcomes: Sequence[Outcome]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            for out in outcomes:
                handle.write(json.dumps(journal_line(out), ensure_ascii=False) + "\n")
            handle.flush()


def read_journal(path: Path) -> list[dict]:
    """Last write per unit wins, ordered by file position."""
    rows: dict[int, dict] = {}
    if not path.exists():
        return []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows[row["unit"]] = row
    return list(rows.values())


# ── the verdicts ────────────────────────────────────────────────────────────


def print_verdicts(rows: Sequence[dict], control: ControlResult | None) -> None:
    """Every branch rule, evaluated here rather than by whoever reads the output.

    Each axis gets **its own denominator** through `runs.band`'s `exercised`, so
    an axis nothing reached prints NOT EVALUATED rather than MET. That is #201
    and its sequel, and reusing the one implementation is why `band` was promoted
    to `core.runs` instead of copied.
    """
    print("\n── pre-registered axes ─────────────────────────────────────────")
    lessons = len(rows)
    stages = [r.get("stage") for r in rows]

    failed_first = sum(1 for r in rows if r.get("attempt", 1) > 1 or r["state"] != "accepted")
    band("L1 lessons failing first pass", failed_first, L1_LOW, L1_HIGH, lessons,
         "2-3 means the GENERATOR PROMPT is wrong, not the gate. Fix the "
         "prompt, re-run, do not loosen a check.")

    reached_c1 = sum(1 for st in stages if st not in ("deterministic", "runner"))
    sections_seen = sum(len(r.get("sections") or {}) for r in rows)
    drifted = sum(1 for st in stages if st == "on_target")
    band("L2 sections failing C1", drifted, L2_LOW, L2_HIGH, sections_seen,
         ">=5 means rewrite the prompt, not C1.",
         exercised=sections_seen if reached_c1 else 0)

    examples_seen = sum(len(r.get("examples") or []) for r in rows)
    off = sum(1 for st in stages if st == "structure")
    band("L3 examples failing C2", off, L3_LOW, L3_HIGH, examples_seen,
         ">=9 means the prompt is asking for examples rather than for "
         "demonstrations.",
         exercised=examples_seen)

    judged = sum(1 for st in stages
                 if st not in ("deterministic", "runner", "on_target", "structure"))
    unnatural = sum(1 for st in stages if st == "naturalness")
    band("L4 examples judged unnatural", unnatural, L4_LOW, L4_HIGH, examples_seen,
         ">=12 means read them before touching anything.",
         exercised=examples_seen if judged else 0)

    diagrams = sum(r.get("diagram_count", 0) for r in rows)
    diagram_fails = sum(
        1 for r in rows for c in (r.get("codes") or []) if c.startswith("diagram_")
        or c in ("timeline_now", "timeline_points", "timeline_not_ordered",
                 "branch_count", "branches_not_distinct", "callout_count",
                 "callout_not_in_sentence", "form_slots", "contrast_identical")
    )
    band("L5 diagrams failing the deterministic checks", diagram_fails,
         L5_LOW, L5_HIGH, diagrams,
         ">=4 means tighten the diagram schema, not the check.",
         exercised=diagrams)

    if control is None:
        print("  L6 negative control: NOT EVALUATED — the control was skipped. "
              "**Not met, not unmet: never asked.**")
    elif control.failures == control.runs:
        print(f"  L6 negative control: {control.failures} of {control.runs} "
              f"refused — predicted {CONTROL_RUNS} of {CONTROL_RUNS} — MET")
    elif control.ok:
        # The exact words, asserted by a test so neither reading can be quietly
        # preferred after the fact.
        print(f"  L6 negative control: {control.failures} of {control.runs} "
              f"refused — bar is {CONTROL_MUST_FAIL} of {control.runs} — "
              f"**prediction NOT MET, run acceptable**")
    else:
        print(f"  L6 negative control: {control.failures} of {control.runs} "
              f"refused — below the {CONTROL_MUST_FAIL}-of-{control.runs} bar — "
              f"**RUN VOID**")

    measured = [
        pct for r in rows for pct in (r.get("coverage_pct") or {}).values()
    ]
    if measured:
        low = min(measured)
        avg = round(sum(measured) / len(measured), 2)
        inside = L7_LOW <= avg <= L7_HIGH
        print(f"  L7 section coverage: mean {avg}%, lowest {low}% — "
              f"predicted {L7_LOW}-{L7_HIGH}% — {'MET' if inside else 'NOT MET'}")
        print("      **REPORTED, NEVER ENFORCED.** No lesson was rejected for "
              "this and no regeneration was triggered by it (#197, L7).")
        if avg < 85:
            print("      Below 85%: the metalanguage cost is larger than "
                  "predicted, and the ruling on #197 for prose is the "
                  "operator's — now owed against a number.")
    else:
        print("  L7 section coverage: NOT EVALUATED — no lesson reached the "
              "coverage measurement. **Not met, not unmet: never asked.**")

    per_lesson = [r.get("diagram_count", 0) for r in rows]
    if per_lesson:
        band("L8 diagrams per lesson (mean)",
             round(sum(per_lesson) / len(per_lesson)),
             L8_LOW, L8_HIGH, len(per_lesson),
             "0 on any lesson: read that unit's targets and say which kind was "
             "declined. 4 of 4 everywhere: the generator is decorating.")
        for r in rows:
            if r.get("diagram_count", 0) == 0:
                print(f"      unit {r['unit']}: ZERO diagrams — reported, not "
                      "rejected. Read its targets.")


# ── dry ─────────────────────────────────────────────────────────────────────


def dry_run(numbers: tuple[int, ...], journal_path: Path = DEFAULT_JOURNAL) -> int:
    settings = load_settings()
    plan = unit_plan(numbers)
    ceiling = expected_calls(plan)

    print(f"model: {settings.llm_model}")
    print(f"units: {', '.join(str(n) for n in numbers)}")
    print(f"lesson_version: {LESSON_VERSION}")
    print(f"max_tokens: generate {LESSON_MAX_TOKENS}")
    print()
    print("=== system (lesson_generate.txt, SUBSTITUTED — this is what --live "
          "sends) ===")
    print(lesson_system_prompt())
    for name in ("lesson_on_target.txt", "lesson_structure.txt",
                 "lesson_contradiction.txt"):
        print(f"\n=== system ({name}) ===")
        print((PROMPTS_DIR / name).read_text(encoding="utf-8"))

    for number, info in plan.items():
        print(f"\n=== user payload (unit {number}) ===")
        print(json.dumps(
            build_payload(number, info["can_do"], info["targets"]),
            ensure_ascii=False, indent=2,
        ))
        print(f"--- C1/C2 candidates (unit {number}) ---")
        for candidate in sorted(set(info["candidates"])):
            mark = "own" if candidate in info["targets"] else "decoy"
            print(f"  [{mark}] {candidate}")

    reference = coverage_reference()
    print(f"\ncoverage reference: {len(reference)} lemmas "
          f"(CEFR A1/A2/B1 + top 2000). "
          f"**MEASURED AND REPORTED, NEVER ENFORCED** — L7, #197.")

    control = json.loads(CONTROL_FIXTURE.read_text(encoding="utf-8"))
    print(f"\nnegative control: claims {control['claims']!r}, actually teaches "
          f"{control['actually']!r}")
    print(f"  {CONTROL_RUNS} runs, bar {CONTROL_MUST_FAIL} of {CONTROL_RUNS}. "
          f"Runs FIRST — a dead C1 costs {CONTROL_RUNS} calls, not {ceiling}.")

    try:
        from core.services import lessons as lessons_service

        below, total = lessons_service.stale_count(numbers)
        print(f"\nstored lessons below LESSON_VERSION: {below} of {total}")
        if below:
            print("  Those units serve NO lesson until regenerated — block 3 "
                  "falls back to the line saying the explanation is on its way.")
    except Exception as exc:  # pragma: no cover - a dry run must not need a DB
        print(f"\nstored lessons: could not read ({exc.__class__.__name__})")

    print(f"\njournal: {journal_path}")
    if journal_path.exists():
        print(f"  ** {journal_path} ALREADY EXISTS — a --live run APPENDS. **")

    print(f"\nbilled call ceiling: {ceiling}")
    print("  Itemised per lesson per pass: 1 generation + one C1 per section + "
          "one C2 per example + 1 naturalness batch + 1 C3.")
    print(f"  True worst case: every lesson exhausts both regenerations "
          f"({MAX_REGENERATIONS}).")
    print(f"\n  --live would ask you to type: {ceiling}")
    print(f"  --apply would ask you to type: "
          f"{','.join(str(n) for n in numbers)}")
    print("\ndry run — nothing was sent and nothing was written.")
    return 0


# ── live ────────────────────────────────────────────────────────────────────


def generate_lesson(
    number: int,
    info: dict,
    *,
    feedback: str | None = None,
    settings: Settings | None = None,
) -> Lesson:
    payload = build_payload(number, info["can_do"], info["targets"])
    if feedback:
        payload["previous_attempt_failed_because"] = feedback
    response = item_gates._chat(
        [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        system=lesson_system_prompt(),
        json_mode=True,
        max_tokens=LESSON_MAX_TOKENS,
        reject_truncation=True,
        settings=settings,
    )
    if not isinstance(response, dict):
        raise item_gates.LLMError("generator did not return an object")
    return parse_lesson({**response, "unit_number": number})


def run(
    numbers: tuple[int, ...],
    *,
    apply: bool,
    journal_path: Path = DEFAULT_JOURNAL,
    skip_control: bool = False,
    settings: Settings | None = None,
) -> int:
    settings = settings or load_settings()
    plan = unit_plan(numbers)
    ceiling = expected_calls(plan)
    journal = Journal(journal_path)

    print(f"units {', '.join(str(n) for n in numbers)} · ceiling {ceiling} "
          f"billed calls · {'APPLY (writes rows)' if apply else 'LIVE (writes nothing)'}")
    expected = ",".join(str(n) for n in numbers) if apply else str(ceiling)
    if not confirm("", expected):
        print("Stopped. Nothing was sent.")
        return 1

    control: ControlResult | None = None
    if not skip_control:
        control = run_control(settings=settings)
        print(f"\ncontrol: refused in {control.failures} of {control.runs} "
              f"(ranks {control.ranks})")
        if not control.ok:
            print(
                f"\n**RUN VOID.** The drifted control was refused in only "
                f"{control.failures} of {control.runs} runs, below the "
                f"{CONTROL_MUST_FAIL}-of-{control.runs} bar.\nC1 does not "
                "discriminate, so nothing it says about a real lesson means\n"
                "anything. Nothing was written. This is a finding: record it."
            )
            return 1
    else:
        print("\ncontrol: SKIPPED on the banked result. L6 prints NOT EVALUATED.")

    reference = coverage_reference()
    outcomes: list[Outcome] = []

    for number, info in plan.items():
        feedback: str | None = None
        out: Outcome | None = None
        for attempt in range(1, MAX_REGENERATIONS + 2):
            print(f"\n── unit {number}, attempt {attempt} ──")
            try:
                lesson = generate_lesson(
                    number, info, feedback=feedback, settings=settings
                )
            except ValidationError as exc:
                out = Outcome(unit=number, state="rejected", stage="generation",
                              attempt=attempt, codes=("schema",),
                              details=(str(exc)[:400],))
                feedback = f"The previous attempt did not match the contract: {exc}"
                print(f"  rejected at generation: {str(exc)[:200]}")
                continue
            out = verify_lesson(lesson, info, reference=reference, settings=settings)
            out.attempt = attempt
            if out.state == "accepted":
                print(f"  accepted · {out.diagram_count} diagrams")
                break
            print(f"  rejected at {out.stage}: {'; '.join(out.details)[:300]}")
            feedback = (
                f"The previous attempt was rejected at the {out.stage} check: "
                + "; ".join(out.details)
            )
        assert out is not None
        if out.state != "accepted":
            print(f"\n  ** UNIT {number} IS UNSHIPPABLE after "
                  f"{MAX_REGENERATIONS} regenerations. **")
            print("  Reported, not shipped with a warning, and no bar is "
                  "adjusted (CLAUDE.md §3 rule 7).")
        outcomes.append(out)

    journal.record(outcomes)
    print_verdicts([journal_line(o) for o in outcomes], control)

    if not apply:
        print("\n--live — verified and printed. NOTHING WAS WRITTEN.")
        return 0

    from core.services import lessons as lessons_service

    written = 0
    for out in outcomes:
        if out.state != "accepted" or out.lesson is None:
            print(f"  unit {out.unit}: not written ({out.state})")
            continue
        if lessons_service.insert_lesson(out.lesson, verification_blob(out)):
            written += 1
            print(f"  unit {out.unit}: WRITTEN")
        else:
            print(f"  unit {out.unit}: already had a lesson; nothing written")
    print(f"\n{written} lesson(s) written.")
    return 0


def report_only(journal_path: Path) -> int:
    """Rebuild the reading from the journal. **Makes no calls.**"""
    rows = read_journal(journal_path)
    if not rows:
        print(f"no rows in {journal_path}")
        return 1
    print(f"{len(rows)} unit(s) from {journal_path}")
    for row in rows:
        print(f"  unit {row['unit']}: {row['state']}"
              + (f" at {row['stage']}" if row.get("stage") else "")
              + f" · attempt {row.get('attempt', 1)}"
              + f" · {row.get('diagram_count', 0)} diagrams")
    print_verdicts(rows, None)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate grammar lessons. Dry by default."
    )
    parser.add_argument(
        "--units", default=",".join(str(n) for n in SCOPE_UNITS),
        help=f"comma-separated unit numbers (default: "
             f"{','.join(str(n) for n in SCOPE_UNITS)})",
    )
    parser.add_argument("--live", action="store_true",
                        help="make the calls and print the finding (billed)")
    parser.add_argument("--apply", action="store_true",
                        help="make the calls and WRITE what passed (billed)")
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL,
                        help=f"outcomes as they are decided "
                             f"(default: {DEFAULT_JOURNAL})")
    parser.add_argument("--report", type=Path, metavar="JOURNAL",
                        help="rebuild the report from a journal. Makes NO calls.")
    parser.add_argument(
        "--skip-control", action="store_true",
        help="do not re-run the negative control; use the banked result. Only "
             "valid while that result stands, and NOT valid if the banked run "
             "landed at the bar rather than at the prediction.",
    )
    args = parser.parse_args(argv)

    # #140. This module spends money, and core/llm.py's per-call token lines are
    # dropped on the floor by any script that leaves the root logger bare. That
    # is how W8's tagger had 138 calls and $6.60 reconstructed after the fact
    # against a $1-2 estimate. **#140 STAYS OPEN** and still names
    # `judge_observe.py` and `verify.py`.
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    if args.report:
        return report_only(args.report)

    numbers = tuple(int(n) for n in args.units.split(",") if n.strip())
    if args.live or args.apply:
        return run(numbers, apply=args.apply, journal_path=args.journal,
                   skip_control=args.skip_control)
    return dry_run(numbers, args.journal)


if __name__ == "__main__":
    sys.exit(main())
