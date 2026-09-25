"""#424 — the unit generator's §3 rule 2 probe. **Dry by default; writes nothing.**

    python -m core.items.l1_probe           # prints exactly what --live sends
    python -m core.items.l1_probe --live    # 2 BILLED calls, writes nothing

**What changed in the request, and so what this probes:** `build_payload` now
sends `"learner_l1"` as a language NAME, and `item_generate.txt` now says what
the key governs (`l1_gloss` and the `l1_to_l2_production` prompt). A mocked
suite cannot show the model writes a Lithuanian production prompt when told
*Lithuanian* (CLAUDE.md §3 rule 2), so one call per learner's language is made,
on the Mac, by the operator, before the deploy (build-run ruling 0.5).

**No database, no learner, no journal.** Unit 1's real can-do and first target,
two slots each (`cloze_cued`, `l1_to_l2_production`), through the real
`generate.build_payload`, the real system prompt, `generate.bind_l1` and
`generate._draft_to_item`, then the FREE gate stages only (`gates.free_stages`,
no call). The full chain is unchanged from block 3's and is exercised by the
operator's next real unit run.
"""

from __future__ import annotations

import argparse
import json
import sys

from core.items import gates, generate

#: Unit 1's can-do and first target, verbatim from `data/syllabus_units.json`
#: (`tests/test_unit_generator_l1.py` pins the target; the can-do is read here).
CAN_DO = "I can tell a friend what I did yesterday, in order, without stopping to think."
TARGET = "past simple: regular and irregular verbs"
TYPES = ("cloze_cued", "l1_to_l2_production")
#: One per learner's language.
LANGUAGES = ("fa", "lt")
LIVE_CALLS = len(LANGUAGES)


def _slots() -> tuple[generate.Slot, ...]:
    return tuple(
        generate.Slot(index=i, item_type=t, target=TARGET, cohort="focus")
        for i, t in enumerate(TYPES)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)

    print("#424 unit-generator L1 probe —", "LIVE" if args.live else "DRY")
    print(f"calls --live will make: {LIVE_CALLS}")
    print(f"request: json_mode=True max_tokens={generate.GENERATE_MAX_TOKENS} "
          f"reject_truncation=True")
    print("--- system prompt, as sent (empty avoid-list, these two types) ---")
    print(generate.generator_system_prompt(TYPES))
    slots = _slots()
    for l1 in LANGUAGES:
        payload = generate.build_payload(1, CAN_DO, slots, l1=l1)
        print(f"\n=== unit 1 ({l1}) — user payload, as sent ===")
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
        generate.bind_l1(drafts, slots, l1)
        for slot in slots:
            raw = drafts[slot.index] if slot.index < len(drafts) else None
            if raw is None:
                print(f"  slot {slot.index + 1}: missing_draft")
                continue
            try:
                item = generate._draft_to_item(raw, slot, 1)
            except Exception as exc:  # noqa: BLE001 -- a shape mismatch is the finding
                print(f"  slot {slot.index + 1} {slot.item_type}: SHAPE MISMATCH: {exc}")
                continue
            _, failed = gates.free_stages(item)
            verdict = "free stages passed" if failed is None else (
                f"free stages refused: {failed.report.deterministic or failed.report.naturalness}")
            print(f"  slot {slot.index + 1} {slot.item_type}: parsed "
                  f"(l1={getattr(item, 'l1', '-')}, l1_gloss={getattr(item, 'l1_gloss', None)!r}, "
                  f"prompt={getattr(item, 'prompt_text', '')!r}) — {verdict}")
    if not args.live:
        print("\nDRY RUN. Nothing was sent and nothing was written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
