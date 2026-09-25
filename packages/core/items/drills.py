"""Weak-spot drills — generation. **W17. Human-run, dry by default (#196).**

    python -m core.items.drills --user N              # dry: prints, sends nothing
    python -m core.items.drills --user N --live       # BILLED, writes nothing
    python -m core.items.drills --user N --apply      # BILLED, writes what passed

**What it does.** Reads which patterns this learner's error journal EVIDENCES
(`core.services.drills.evidenced_patterns` — at least three rows of one
`error_type` inside the evidence window), and for each one whose drill bank is
short, writes one cohort of drill items through **the same pipeline and the same
gates block 3's items pass**: `generate.generate_drafts`, then
`generate.verify_cohort` — the free stages, the batched naturalness judge, the
blind solver with its repair ladder, and `gates.probe_target` against the
pattern's own target and three neighbouring patterns as decoys. Nothing about the
gates is new; only the TARGET is: a pattern's plain description instead of a
syllabus unit's grammar point.

**A pattern with no evidence is never generated for** — this command cannot be
asked to: `--codes` filters the evidenced list, it does not extend it.

**No learner text is sent.** The payload names the pattern and the learner's L1,
never a sentence from the journal. Sharper targeting from the learner's own
corrected sentences is possible and is not done here: it would send journal text
to the provider a second time for a gain nobody has measured.

**BUILD RUN RULING 0.5: THIS IS ALSO THE PROBE.** The dry run prints exactly what
`--live` would send — the model, every system prompt as substituted, every user
payload, the candidates, `max_tokens`, and the billed-call ceiling — and it is in
`BUILD_PROGRESS.md`'s `## Launch pass — probes`. No billed call has been made by
Claude Code; the response shape is the one block 3's generator has already been
run against.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.config import Settings, load_settings
from core.items import gates
from core.items import generate
from core.items.generate import Outcome, Slot

logger = logging.getLogger(__name__)

#: Gitignored, like every generator journal. **Tests always pass `journal_path`
#: (#416, #420).**
DEFAULT_JOURNAL = Path("w17-drill-journal.jsonl")

#: At most this many patterns are bought per invocation. A ceiling on spend per
#: run, not on the learner: a re-run buys the next ones.
MAX_PATTERNS_PER_RUN = 3

#: **The pattern, as a grammar target the generator and `probe_target` can read.**
#: One per written `error_types.code` — the sixteen with a `learner_label`
#: (migration 027). The three spoken codes have no entry and are never drilled.
#: **The order is the decoy order**: a pattern's decoys are its nearest
#: neighbours in this list, so the two article codes decoy each other — the
#: sibling that discriminates, `generate.target_candidates`' own reasoning.
DRILL_TARGETS: dict[str, str] = {
    # #440: a MISSING article only. The launch probe got an a/an item back from
    # the old text ("using a, an or the where English needs one"), which is
    # `article_wrong`'s error; the exclusion is written where the model reads it.
    "article_missing": "Articles: putting in the missing a or the that English needs before a noun, not choosing between a and an",
    "article_wrong": "Articles: choosing between a, an, the and no article",
    "plural_countable": "Countable and uncountable nouns, and their plurals",
    "quantifier_modifier": "Quantifiers: some, any, much, many, a few, a little, enough",
    "subject_verb_agreement": "Subject-verb agreement, including the third-person -s",
    "verb_tense_past": "The past simple for finished events",
    "present_perfect": "The present perfect for experience and unfinished time",
    "conditional": "Conditionals: the verb forms in if-sentences",
    "modal_verb": "Modal verbs: can, could, should, must, might, have to",
    "gerund_vs_infinitive": "The -ing form or to + verb after another verb",
    "preposition": "Prepositions of time and place, and after common verbs",
    "phrasal_verb": "Everyday phrasal verbs",
    "collocation": "Collocations: which words naturally go together",
    "word_order": "Word order in statements and questions",
    "false_friend": "Similar-looking English words with different meanings",
    "register_formality": "Matching the tone to the situation: casual or polite",
}

DECOYS = 3


@dataclass(frozen=True, slots=True)
class DrillPlan:
    code: str
    learner_label: str
    evidence: int
    held: int
    slots: tuple[Slot, ...]
    candidates: tuple[str, ...]
    payload: dict
    avoid: tuple[str, ...]


def drill_candidates(code: str) -> tuple[str, ...]:
    """The pattern's own target, then its `DECOYS` nearest neighbours in order."""
    codes = list(DRILL_TARGETS)
    here = codes.index(code)
    others = sorted(
        (c for c in codes if c != code),
        key=lambda c: (abs(codes.index(c) - here), codes.index(c)),
    )
    return (DRILL_TARGETS[code],) + tuple(DRILL_TARGETS[c] for c in others[:DECOYS])


def drill_types(l1: str | None) -> tuple[str, ...]:
    """Block 3's slot types. **Without the production slot if the learner's L1
    is one the schema cannot carry** (`L1ToL2ProductionItem.l1` is `fa | lt`)."""
    if l1 in ("fa", "lt"):
        return generate.SLOT_TYPES
    return tuple(t for t in generate.SLOT_TYPES if t != "l1_to_l2_production")


def drill_slots(code: str, n: int, types: Sequence[str]) -> tuple[Slot, ...]:
    """`n` drill slots for one pattern, indexed 0..n-1 so every draft is
    addressable (`generate._assert_indices_addressable`, #261)."""
    target = DRILL_TARGETS[code]
    return tuple(
        Slot(index=i, item_type=types[i % len(types)], target=target, cohort="drill",
             error_type=code)
        for i in range(n)
    )


def drill_payload(code: str, learner_label: str, l1: str | None,
                  slots: tuple[Slot, ...]) -> dict:
    """The user message. **The pattern and the learner's L1; no journal text.**"""
    generate._assert_indices_addressable(slots)
    payload = {
        "can_do": f"Practise {DRILL_TARGETS[code][0].lower()}{DRILL_TARGETS[code][1:]}",
        "track": "life",
        "items": [
            {"item_type": slot.item_type, "grammar_target": slot.target}
            for slot in slots
        ],
    }
    if l1:
        # **A NAME, NOT THE CODE (W15, #424's sweep).** W17 sent `"fa"`/`"lt"`
        # raw, which is F5's defect: the model is told a language's name, and an
        # unmapped code raises rather than being sent as-is. The unit generator
        # and this one now say the learner's language the same way.
        from core.writing.rules import language_name

        payload["learner_l1"] = language_name(l1)
    return payload


def plan_for(user_id: int, *, now: datetime,
             codes: Sequence[str] | None = None) -> list[DrillPlan]:
    """What a run would buy. **Reads the database; sends nothing.**"""
    from core.services import drills as drills_service
    from core.services import items as items_service

    l1 = drills_service.learner_l1(user_id)
    types = drill_types(l1)
    wanted = set(codes) if codes else None
    entries = []
    for pattern in drills_service.evidenced_patterns(user_id, now=now):
        if pattern.code not in DRILL_TARGETS:
            continue
        if wanted is not None and pattern.code not in wanted:
            continue
        held = items_service.drills_held(user_id, error_type=pattern.code)
        short = max(0, items_service.DRILL_BANK_TARGET - held)
        if short == 0:
            continue
        slots = drill_slots(pattern.code, short, types)
        entries.append(
            DrillPlan(
                code=pattern.code,
                learner_label=pattern.learner_label,
                evidence=pattern.evidence,
                held=held,
                slots=slots,
                candidates=drill_candidates(pattern.code),
                payload=drill_payload(pattern.code, pattern.learner_label, l1, slots),
                avoid=items_service.drill_sentences(user_id, error_type=pattern.code),
            )
        )
    # The least-stocked patterns first, then by code: a spend cap per run, and
    # never a rank of the learner's errors (#412).
    entries.sort(key=lambda e: (e.held, e.code))
    return entries[:MAX_PATTERNS_PER_RUN]


def calls_for(entry: DrillPlan) -> int:
    """The billed-call ceiling for one pattern, itemised from its slots.

    generation 1 + naturalness 1 + probes (probed families only) + cue re-probes
    (slot family, `MAX_REPAIRS` each) + one `probe_target` per slot + one
    back-translation per production slot. **No top-up round and no negative
    control** (decisions log, W17).
    """
    slots = entry.slots
    n_probed = sum(1 for s in slots
                   if gates.ANSWER_FAMILY.get(s.item_type) in gates.PROBED_FAMILIES)
    n_slot = sum(1 for s in slots if gates.ANSWER_FAMILY.get(s.item_type) == "slot")
    n_l1 = sum(1 for s in slots if s.item_type == "l1_to_l2_production")
    return 1 + 1 + n_probed + gates.MAX_REPAIRS * n_slot + len(slots) + n_l1


def dry_print(user_id: int, plan: list[DrillPlan], *, settings: Settings,
              journal_path: Path) -> int:
    """Everything `--live` would send. Returns the call ceiling."""
    print(f"W17 drills — user {user_id}")
    print(f"model: {settings.llm_model}")
    print(f"max_tokens (generation): {generate.GENERATE_MAX_TOKENS} · json_mode=True · "
          f"reject_truncation=True")
    if not plan:
        print("\nno evidenced pattern needs drills — nothing would be sent.")
        return 0
    print("\n=== patterns (operator view: the count is never shown to a learner) ===")
    for entry in plan:
        print(f"  {entry.code:<24} label={entry.learner_label!r} evidence={entry.evidence} "
              f"held={entry.held} buys={len(entry.slots)}")
    total = 0
    for entry in plan:
        print(f"\n=== {entry.code} ===")
        print("--- system prompt, as sent ---")
        print(generate.generator_system_prompt(avoid=entry.avoid))
        print("--- user payload, as sent ---")
        print(json.dumps(entry.payload, ensure_ascii=False, indent=2))
        print("--- probe_target candidates (own first, then decoys) ---")
        for c in entry.candidates:
            print(f"  {c}")
        n = calls_for(entry)
        total += n
        print(f"--- ceiling for this pattern: {n} calls ---")
    for name in ("item_naturalness.txt", "item_probe.txt", "item_target.txt",
                 "item_backtranslate.txt"):
        print(f"\n=== gate prompt {name} (sent by the existing gates, unchanged) ===")
        print((generate.PROMPTS_DIR / name).read_text(encoding="utf-8"))
    print(f"\njournal: {journal_path}")
    print(f"calls --live will make, at most: {total}")
    return total


#: Moved to `generate.bind_l1` by W15 (#424) so both generators share one
#: binding; the name stays for the probe and the tests that import it.
_bind_l1 = generate.bind_l1


def run(user_id: int, plan: list[DrillPlan], *, apply: bool, settings: Settings,
        journal_path: Path = DEFAULT_JOURNAL) -> list[Outcome]:
    """One cohort per pattern. Billed. Writes only with `apply`."""
    from core.services import drills as drills_service

    l1 = drills_service.learner_l1(user_id)
    journal = generate.Journal(journal_path)
    spent: Counter = Counter()
    every: list[Outcome] = []
    for entry in plan:
        try:
            drafts = generate.generate_drafts(entry.payload, settings=settings,
                                              avoid=entry.avoid)
        except gates.LLMError as exc:
            print(f"{entry.code}: generation FAILED: {exc}")
            continue
        spent["generation"] += 1
        _bind_l1(drafts, entry.slots, l1)
        # `unit_number=0` marks "no unit" in the journal line; the ITEM carries
        # no unit (`generate._draft_to_item`'s drill branch).
        outcomes = generate.verify_cohort(
            entry.slots, drafts, unit_number=0, candidates=entry.candidates,
            settings=settings, calls=spent,
        )
        journal.record(outcomes)
        every.extend(outcomes)
        for one in outcomes:
            text = one.item.prompt_text if one.item is not None else "-"
            rank = one.target.claimed_rank if one.target is not None else "-"
            print(f"  {entry.code} slot {one.slot.index + 1} {one.slot.item_type:<20} "
                  f"{one.state:<9} stage={one.stage} codes={list(one.codes)} "
                  f"target_rank={rank} | {text!r}")
    print(f"\ncalls spent: {dict(spent)} · journal: {journal_path}")
    if apply:
        generate._write(user_id, every, settings=settings)
    else:
        print("--live: nothing was written.")
    return every


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="W17 weak-spot drills. Dry by default; --live is billed and "
        "writes nothing; --apply is billed and writes what passed."
    )
    parser.add_argument("--user", type=int, required=True)
    parser.add_argument("--codes", default="", help="comma-separated evidenced codes")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    args = parser.parse_args(argv)
    if args.live and args.apply:
        parser.error("--live and --apply are exclusive")
    logging.basicConfig(level=logging.INFO)  # #140

    settings = load_settings()
    codes = [c.strip() for c in args.codes.split(",") if c.strip()] or None
    plan = plan_for(args.user, now=datetime.now(timezone.utc), codes=codes)
    ceiling = dry_print(args.user, plan, settings=settings, journal_path=args.journal)
    if not (args.live or args.apply):
        print("\ndry run — nothing was sent and nothing was written.")
        return 0
    if not plan:
        return 0
    from core.runs import confirm

    expected = str(args.user) if args.apply else str(ceiling)
    if not confirm(f"This makes up to {ceiling} billed calls.", expected):
        print("stopped — nothing was sent.")
        return 1
    run(args.user, plan, apply=args.apply, settings=settings, journal_path=args.journal)
    return 0


if __name__ == "__main__":
    sys.exit(main())
