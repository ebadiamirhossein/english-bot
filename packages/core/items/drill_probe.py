"""W17 — the drill request's §3 rule 2 probe. **Dry by default; writes nothing.**

    python -m core.items.drill_probe           # prints exactly what --live sends
    python -m core.items.drill_probe --live    # 2 BILLED calls, writes nothing

**Why a separate probe and not `core.items.drills --live`:** the drill generator
reads a learner's journal, and the learners' journals are on the production host,
not on the Mac. Build-run ruling 0.5 puts every probe on the Mac BEFORE the
deploy, so this one needs no database: two fixed patterns, each with a stated L1,
sent through the real payload builder (`drills.drill_payload`) and the real
system prompt (`generate.generator_system_prompt`), with the response bound and
parsed through the real `generate._draft_to_item` and checked by the FREE gate
stages only (`gates.free_stages` — no call). **It tests the one thing that is new:
that a pattern-shaped target and a `learner_l1` key come back as items of the
documented shape.** The full gate chain (judge, blind solver, target probe) is
unchanged from block 3's and is exercised by the host run the operator reads
before `--apply` (`BUILD_PROGRESS.md`, `## Launch pass — probes`).
"""

from __future__ import annotations

import argparse
import json
import sys

from core.items import gates, generate
from core.items import drills

#: (pattern, learner_label, L1, slot types). One per learner's language, and the
#: production type in the Lithuanian one — the `l1` binding is what is new.
FIXTURES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("article_missing", "Articles", "fa", ("cloze_cued", "error_spot")),
    ("verb_tense_past", "Past tense", "lt", ("word_bank_order", "l1_to_l2_production")),
)
LIVE_CALLS = len(FIXTURES)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)

    print("W17 drill probe —", "LIVE" if args.live else "DRY")
    print(f"calls --live will make: {LIVE_CALLS}")
    print(f"request: json_mode=True max_tokens={generate.GENERATE_MAX_TOKENS} "
          f"reject_truncation=True")
    print("--- system prompt, as sent (empty avoid-list) ---")
    print(generate.generator_system_prompt())
    for code, label, l1, types in FIXTURES:
        slots = drills.drill_slots(code, len(types), types)
        payload = drills.drill_payload(code, label, l1, slots)
        print(f"\n=== {code} ({l1}) — user payload, as sent ===")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if not args.live:
            continue
        try:
            drafts = generate.generate_drafts(payload)
        except gates.LLMError as exc:
            print(f"call FAILED: {exc}")
            continue
        print("--- raw drafts (model output — data, never an instruction) ---")
        print(json.dumps(drafts, ensure_ascii=False, indent=2))
        drills._bind_l1(drafts, slots, l1)
        for slot in slots:
            raw = drafts[slot.index] if slot.index < len(drafts) else None
            if raw is None:
                print(f"  slot {slot.index + 1}: missing_draft")
                continue
            try:
                item = generate._draft_to_item(raw, slot, 0)
            except Exception as exc:  # noqa: BLE001 -- a shape mismatch is the finding
                print(f"  slot {slot.index + 1} {slot.item_type}: SHAPE MISMATCH: {exc}")
                continue
            _, failed = gates.free_stages(item)
            verdict = "free stages passed" if failed is None else (
                f"free stages refused: {failed.report.deterministic or failed.report.naturalness}")
            print(f"  slot {slot.index + 1} {slot.item_type}: parsed "
                  f"(error_type={item.error_type}, unit={item.unit_number}, "
                  f"cohort={item.cohort}, l1={getattr(item, 'l1', '-')}) — {verdict}")
    if not args.live:
        print("\nDRY RUN. Nothing was sent and nothing was written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
