"""The one human-run verification. Defaults to sending nothing.

CLAUDE.md §5b bars a slice from making a billed call, and `tests/conftest.py`
makes that structural — `netguard` is autouse and session-scoped, so a test that
reached a provider would raise rather than spend money. This module is the
deliberate exception, and it is **run by the human, never by an acceptance
check**.

    python -m core.items.verify                # --dry-run, sends nothing
    python -m core.items.verify --live         # ONE blind-solver call
    python -m core.items.verify --live-audio   # ONE synthesize + ONE transcribe

**What a `--live` pass licenses, written here because the record will carry the
result.** It shows three things and no more: the request shape is accepted by
the provider, the projection is well-formed, and the gate *can* reject a
genuinely ambiguous item. It is **one sample of a stochastic system** and
licenses **no claim about the gate's rate** — not its false-accept rate, not its
false-reject rate. A fail is decisive; a pass is not proof. Nobody should later
read this result as "the gate was verified".

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
from core.items.grading import fold_answer, normalise_variants
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
# THE PASS CONDITION IS INVERTED, deliberately: the gate is working when the
# solver returns something OTHER than the canonical answer, because that is the
# gate correctly detecting the ambiguity.
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
    print((PROMPTS_DIR / "item_blind_solver.txt").read_text(encoding="utf-8"))
    print("=== messages ===")
    print(json.dumps(projection, ensure_ascii=False, indent=2))
    print("\n=== max_tokens ===")
    print(gates.SOLVER_MAX_TOKENS, "(reject_truncation=True)")
    print("\n=== canonical answer (NOT sent) ===")
    print(repr(item.answer), "accepted:", list(item.accepted_variants))
    print("\nNothing was sent. Re-run with --live to make one call.")
    return 0


def live() -> int:
    item = _item()
    result = gates.blind_solve(item)
    answer = str(result.get("answer", ""))
    agreed = fold_answer(answer) in {fold_answer(v) for v in item.accepted_variants}
    print("solver answered:", repr(answer), "confidence:", result.get("confidence"))
    print("canonical:", repr(item.answer))
    if agreed:
        print(
            "\nFAIL — the solver recovered the canonical answer, so this gate "
            "would have let the PRD's own broken item through."
        )
        return 1
    print(
        "\nPASS — the solver did not recover the canonical answer, so the gate "
        "rejects the item that started this rebuild."
    )
    print(
        "This is ONE sample of a stochastic system. It licenses no claim about "
        "the gate's rate; a fail is decisive, a pass is not proof."
    )
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
    parser.add_argument("--live", action="store_true", help="one blind-solver call")
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
