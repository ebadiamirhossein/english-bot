"""The one human-run verification. Defaults to sending nothing.

CLAUDE.md §5b bars a slice from making a billed call, and `tests/conftest.py`
makes that structural — `netguard` is autouse and session-scoped, so a test that
reached a provider would raise rather than spend money. This module is the
deliberate exception, and it is **run by the human, never by an acceptance
check**.

    python -m core.items.verify                # --dry-run, sends nothing
    python -m core.items.verify --live         # 1 probe + 1 validate + 3 controls
    python -m core.items.verify --live-audio   # ONE synthesize + ONE transcribe

**W5a: `--live` runs in BOTH directions, and the fix is not verified without
the second.** A gate that rejects everything passes the catch direction
perfectly, so the over-rejection direction is the one that establishes the probe
is *calibrated* rather than merely strict. Over-generation is this gate's
principal failure mode — a model asked to *list every acceptable answer* is being
invited to be generous — and one sample cannot tell a calibrated probe from a
generous one, which is why the control side runs several items across the three
families rather than one.

**What a `--live` pass licenses, written here because the record will carry the
result.** It shows three things and no more: the request shape is accepted by
the provider, the projection is well-formed, and the gate behaves as designed on
*these* items. It is **one sample per item of a stochastic system** and licenses
**no claim about the gate's rate** — not its false-accept rate, not its
false-reject rate. A fail is decisive; a pass is not proof. And a frontier model
resolves discourse cues a B1 learner will miss, so **even a clean probe is weaker
evidence about a learner than it looks** — the same asymmetry §4d records for
STT. Nobody should later read this result as "the gate was verified".

`--live-audio` verifies the round-trip *composition*, not request construction:
`synthesize` and `transcribe` are unmodified and `apps/bot/handlers/shadow.py`
already exercises both against the live provider daily.
"""

from __future__ import annotations

import argparse
import json
import sys

from core import PROMPTS_DIR
from core.config import load_settings
from core.items import gates
from core.items.grading import distinct_answers, normalise_variants
from core.items.projection import visible_projection
from core.items.schema import parse

# PRD §4.3's own example — the item that started the v3 rebuild.
#
#     "Head home if you want — ___ stay and push the deploy."
#
# The intended answer is `I'll`, but `I'd`, `I'm gonna`, `let me`, `I can` and
# `I might` are all grammatical and idiomatic there, so the item has no unique
# recoverable answer and cannot be marked.
#
# **W5a — the pass condition is about CLASS COUNT, not about agreement.** W5
# asserted the solver returned something other than `I'll`, and that prediction
# was simply wrong: `I'll` IS the best completion and the solver returns it on
# every run. Inverting that assertion would have left the gate exactly as
# permissive as it was. What the probe asks instead is which answers a teacher
# would have to accept, and the item is caught when that list holds more than
# one equivalence class.
#
# **`track: "work"` here is load-bearing — do not "fix" it to `life`.** On the
# Life track the mechanical jargon rule rejects the item for "deploy" before any
# model call is made, and `--live` would report a pass having never run the gate
# under test.
BROKEN_ITEM = {
    "item_type": "cloze_cued",
    "track": "work",
    "prompt_text": "Head home if you want — ___ stay and push the deploy.",
    "answer": "I'll",
    "lexeme": "will",
    "definition": "a decision made at this moment",
    "l1_gloss": "من می‌مونم",
}

# A short, digit-free, name-free sentence — everything `checks._dictation`
# requires, so the round-trip is testing audio and not the checks.
AUDIO_FIXTURE = "I forgot my keys and had to wait outside."


def _item():
    draft = dict(BROKEN_ITEM)
    draft["accepted_variants"] = normalise_variants(draft["answer"])
    return parse(draft)


def dry_run() -> int:
    """Print the exact request and send nothing."""
    item = _item()
    projection = visible_projection(item)
    settings = load_settings()
    print("=== model ===")
    print(settings.llm_model)
    print("\n=== system (cache_control: ephemeral) ===")
    print((PROMPTS_DIR / "item_probe.txt").read_text(encoding="utf-8"))
    print("=== messages ===")
    print(json.dumps(projection, ensure_ascii=False, indent=2))
    print("\n=== max_tokens ===")
    print(gates.SOLVER_MAX_TOKENS, "(reject_truncation=True)")
    print("\n=== canonical answer (NOT sent) ===")
    print(repr(item.answer), "accepted:", list(item.accepted_variants))
    print("\nNothing was sent. Re-run with --live to make one call.")
    return 0


# The over-rejection control. One item per probed family, because a gate that
# rejects everything passes the catch direction perfectly. Each must come back
# with exactly ONE equivalence class.
#
# The `cloze_cued` control carries its cue, and that is the whole reason it is
# unique: the cue supplies the lemma and `yesterday` forces the tense, so
# morphology decides the filler rather than meaning. Without it the slot admits
# walked, drove, ran and got — which is what the W5 fixture did, and a correct
# probe would have looked over-generous against it.
CONTROLS = [
    ("slot", {
        "item_type": "cloze_cued", "track": "life", "lexeme": "go",
        "prompt_text": "I ___ to the shops yesterday.", "answer": "went",
        "cue_type": "definition", "cue_text": "(past of go)"}),
    ("message", {
        "item_type": "l1_to_l2_production", "track": "life", "lexeme": "go",
        "prompt_text": "من دیروز به مغازه رفتم", "answer": "I went to the shops",
        "accepted_variants": ["i went to the shops", "i went to the shop"]}),
    ("fixed_option", {
        "item_type": "mcq", "track": "life", "lexeme": "go",
        "prompt_text": "I ___ to the shops yesterday.", "answer": "went",
        "options": ["went", "goed", "gone", "going"]}),
]


def _classes(item) -> tuple[list[str], tuple]:
    response = gates.probe_acceptable(item)
    candidates = gates._candidates(response)
    return candidates, distinct_answers(candidates)


def live() -> int:
    """Both directions. Exit non-zero if either fails."""
    failures = 0

    print("=== CATCH DIRECTION — PRD §4.3's own broken item ===")
    item = _item()
    candidates, classes = _classes(item)
    print("  probe accepted:", candidates)
    print("  distinct classes:", len(classes), [" ".join(c) for c in classes])
    if len(classes) > 1:
        print("  PASS — the probe sees the ambiguity the gate exists for.")
    else:
        print(
            "  FAIL — one class. The gate still cannot see the ambiguity, and\n"
            "         a single-answer solve is what it has effectively become."
        )
        failures += 1

    verdict = gates.validate(item, judge=False).report
    print(f"  full verdict: {verdict.verdict} (repairs={verdict.repair_count}, "
          f"cue={verdict.cue_applied}, calls={verdict.solver_calls})")
    print("  NOTE: `repaired` is a correct outcome — PRD §4.3 offers a "
          "first-letter cue\n        for this very item, and TASKS says "
          "'rejected OR repaired'.")
    if verdict.verdict == "passed" and verdict.repair_count == 0:
        print("  FAIL — accepted unrepaired.")
        failures += 1

    print("\n=== OVER-REJECTION DIRECTION — one control per probed family ===")
    print("  A gate that rejects everything passes the catch direction "
          "perfectly.\n  This is the half that shows the probe is calibrated.")
    for family, draft in CONTROLS:
        control = parse(
            {**draft, "accepted_variants": draft.get("accepted_variants")
             or normalise_variants(draft["answer"])}
        )
        candidates, classes = _classes(control)
        ok = len(classes) == 1
        print(f"  [{family:12}] classes={len(classes)} {candidates} "
              f"{'PASS' if ok else 'FAIL — over-rejecting'}")
        if not ok:
            failures += 1

    print(
        "\nONE SAMPLE PER ITEM of a stochastic system. No claim about the "
        "gate's rate.\nA fail is decisive; a pass is not proof. A model also "
        "resolves cues a B1\nlearner will miss, so a clean probe is weaker "
        "evidence about a learner than\nit looks."
    )
    if failures:
        print(f"\n{failures} check(s) failed.")
        return 1
    print("\nBoth directions pass.")
    return 0


def live_audio() -> int:
    ok, heard = gates.audio_round_trip(AUDIO_FIXTURE)
    print("sent:  ", repr(AUDIO_FIXTURE))
    print("heard: ", repr(heard))
    print("round-trip:", "PASS" if ok else "FAIL")
    print(
        "\nSTT hears better than a B1 learner: a pass is necessary but not "
        "sufficient, a fail is decisive."
    )
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true",
        help="the probe, in both directions (catch + over-rejection)")
    parser.add_argument(
        "--live-audio", action="store_true", help="one synthesize + one transcribe"
    )
    args = parser.parse_args(argv)
    if args.live:
        return live()
    if args.live_audio:
        return live_audio()
    return dry_run()


if __name__ == "__main__":
    sys.exit(main())
