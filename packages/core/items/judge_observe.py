"""What the naturalness judge was actually asked, and what it actually said.

**Human-run. Never an acceptance check.** CLAUDE.md §5b bars a slice from making
a billed call, and `tests/conftest.py` makes that structural — `netguard` is
autouse and session-scoped. This module is the deliberate exception, the same
category as `verify.py` and `seed_fixtures.py`:

    python -m core.items.judge_observe            # dry run, sends nothing
    python -m core.items.judge_observe --live     # ~76 calls, confirmed first
    python -m core.items.judge_observe --live --runs 3

**Why this exists.** The W6 seeding run rejected five of the eleven committed
fixtures (#115) and kept no reasons, so it could not distinguish the two
explanations that need opposite fixes: the judge over-rejects, or `valid.json`
holds items the gate refuses. `judge_naturalness` asks the model for a one-word
`reason` and `gates.py:327-335` parses it away, so nothing downstream ever saw
it. This module sees it.

**A separate module, not a `verify.py` flag.** `verify.py`'s contract is "both
directions pass, exit 0 is the acceptance criterion". This one produces a
*finding*, and folding it in would let a later reader take exit 0 as "the gate
was verified".

**The judge is not modified to observe it.** `gates._chat` is an existing seam;
`_recording` wraps it, delegates to the real callable, captures the raw response
and restores the seam — including on the exception path. So the harness calls the
**real** `judge_naturalness`, and the verdict it reports and the reason it prints
come from *the same call*. Rebuilding the request by hand would have let the two
drift, which is the W5a `--live` bug one level up: **the thing that verifies must
measure the thing it reports on.**

────────────────────────────────────────────────────────────────────────────────
THE THREE ARMS

  A — as shipped.  Exactly what `gates.validate` sends. At W5b that was
      `checks.sentence_of(item)` — the **gapped stem** for `mcq`, `cloze_cued`
      and `collocation_pick`, and for `error_spot` the sentence **with the
      deliberate error still in it**. **W5c acted on the finding**: the gate now
      sends `checks.judged_sentence(item)` and so does this arm, which means A
      and B are the same string and the comparison below is spent. The module is
      kept as the standing instrument for "what is the judge actually asked?" —
      re-running it now measures whether prose is accepted, nothing more.
  B — filled.  The same sentence with the gap closed / the error tile corrected.
      Deterministic and in-process — a second model call here would add a second
      source of ambiguity to an experiment about ambiguity. Only the four
      gapped/error types differ between A and B, and that asymmetry IS the
      hypothesis.
  C — the `listening_gap` probe.  Two public `probe_acceptable` calls per run,
      bare and `first_letter_length`-cued, reproducing the sequence the W6 run
      made. No audio gate: `_audio_gate` already passed on production, and
      re-running it would bill TTS and STT to re-learn that.
      **Opt-in since W5c (`--probe-arm`).** It returned `classes=0` on all six
      attempts, and on that evidence ruling R1 removed the probe from this type
      altogether — so the arm now observes a path production does not take.

────────────────────────────────────────────────────────────────────────────────
PRE-REGISTERED PREDICTIONS AND BRANCH RULES

Written before the numbers, following the #57 precedent, precisely so a
near-miss result cannot pull the action after the fact. `--live` evaluates them
itself and prints the verdict, so the answer is not adjusted by hand afterwards.

  P1  arm A rejects mcq, cloze_cued, collocation_pick, error_spot at >=80% each
  P2  arm B accepts those same four at >=80% each
  P3  the six clean-prose strings accept at >=80% each on arm A
  P4  listening_gap passes naturalness and fails only at the probe

  P1 and P2      -> the judge is right, THE INPUT IS WRONG. Fix what
                    `sentence_of` hands the judge. Do NOT touch the prompt, and
                    there is no threshold to touch (the verdict is a raw bool).
  P1, not P2     -> the fixtures are genuinely unnatural. `valid.json` is wrong
                    and ~1,340 tests assert over items that could never ship.
  not P1         -> the gate is unstable run to run. The worst outcome for W10,
                    because yield is then not a property of the item at all.

**What this licenses.** Five samples of eleven items of a stochastic system. It
distinguishes a deterministic cause from a stochastic one and **nothing more**.
No claim about the gate's rate, in either direction. It is not a yield number for
W10 and must not be read as one: these fixtures were hand-written to be good and
generated items will not be.

Nothing is written to any database. This module imports no `core.services`
module, opens no connection, and never contacts the production host — it runs on
the Mac against the committed fixtures and needs only `ANTHROPIC_API_KEY`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from core import PROMPTS_DIR
from core.config import load_settings
from core.items import gates
from core.items.checks import judged_sentence, sentence_of
from core.items.grading import distinct_answers, equivalence_key, normalise_variants
from core.items.repair import apply_cue
from core.items.schema import GAP, ErrorSpotItem, parse
from core.services.paths import repo_root

#: The same committed file `seed_fixtures`, `test_items_projection` and the
#: TypeScript renderer tests read. `tests/test_items_judge_observe.py` pins this
#: loader against `seed_fixtures.load_fixtures` rather than importing it, so the
#: two cannot drift and this module stays free of `core.services`.
FIXTURES = Path("tests") / "fixtures" / "items" / "valid.json"

#: Sample count. One sample is what produced #115's uncertainty in the first
#: place. Five per arm makes the primary question decisive — under "it is just
#: noise at p=0.5", A rejecting 5/5 while B accepts 5/5 on all four items is
#: ~1e-12 — and buys a stability number for the six that passed at the same
#: time. If `dictation` accepts 3/5 rather than 5/5, the run-to-run variance is
#: far wider than anyone assumed and that alone changes W10.
DEFAULT_RUNS = 5

#: Arm C is cheap and its question is coarser (is the canonical ever offered at
#: all?), so it runs fewer times.
PROBE_RUNS = 3

#: ">=80% each" in both directions, for the pre-registered predictions.
HIGH = 0.8
LOW = 0.2


def _fixture_path() -> Path:
    return repo_root() / FIXTURES


def load_fixtures() -> list[dict]:
    """The eleven drafts, parsed and variant-normalised, in file order."""
    rows = json.loads(_fixture_path().read_text(encoding="utf-8"))
    out = []
    for row in rows:
        draft = dict(row["item"])
        if draft.get("answer") is not None and "accepted_variants" not in draft:
            draft["accepted_variants"] = normalise_variants(draft["answer"])
        out.append({"name": row["name"], "item": parse(draft)})
    return out


# ── the arms ────────────────────────────────────────────────────────────────


def arm_as_shipped(item) -> str:
    """Exactly the string `gates.validate` hands the judge.

    Deliberately a one-line delegation rather than a copy.
    `tests/test_items_judge_observe.py` asserts it is byte-identical to what
    the gate sends for all eleven fixtures, so if that ever changes this
    harness follows it or the suite fails.

    **W5c re-pointed this from `sentence_of` to `judged_sentence`**, because
    that is what `gates.validate` now sends. The contract is "what production
    sends", not "what production sent in W5b" — a harness pinned to a string
    the gate stopped making would report on a request nobody makes, which is
    the W5a `--live` bug this module was built to avoid repeating.
    """
    return judged_sentence(item)


def arm_filled(item) -> str:
    """The same sentence with the gap closed, or the wrong tile corrected.

    Deterministic, no model call.

    **Independently written, and it stays that way.** Since W5c fixed the input,
    this is what `judged_sentence` produces — so it would be tempting to
    delegate. It must not: `test_arm_b_is_what_the_gate_now_sends` asserts the
    two agree over all eleven fixtures, and that assertion is evidence only
    while the two are separate implementations. Delegating would turn it into a
    tautology that passes no matter what either function does.
    """
    if isinstance(item, ErrorSpotItem):
        tiles = list(item.tiles)
        tiles[item.wrong_index] = item.correction
        return " ".join(tiles)
    sentence = sentence_of(item)
    if GAP in sentence and item.answer:
        return sentence.replace(GAP, item.answer)
    return sentence


# ── the seam ────────────────────────────────────────────────────────────────


@contextmanager
def _recording():
    """Wrap `gates._chat`, capture raw responses, restore on the way out.

    Read-only: the same request goes out and the same verdict comes back. The
    judge, the prompt and the fixtures are untouched by this slice — assertable
    by `git diff`.
    """
    calls: list[dict] = []
    original = gates._chat

    def recorder(*args, **kwargs):
        response = original(*args, **kwargs)
        calls.append(
            {
                "messages": args[0] if args else kwargs.get("messages"),
                "response": response,
            }
        )
        return response

    gates._chat = recorder
    try:
        yield calls
    finally:
        gates._chat = original


def _reason_of(calls: list[dict]) -> str:
    """The one-word reason for sentence 1, which `judge_naturalness` discards."""
    if not calls:
        return "?"
    response = calls[-1]["response"]
    if not isinstance(response, dict):
        return "-"
    for row in response.get("verdicts") or []:
        if not isinstance(row, dict):
            continue
        try:
            n = int(row.get("n", 0))
        except (TypeError, ValueError):
            continue
        if n == 1:
            return str(row.get("reason", "-"))
    return "missing-row"  # the fail-open default fired: gates.py:335


def judge_once(sentence: str, *, settings) -> tuple[bool, str]:
    """One real `judge_naturalness` call. Verdict and reason from the SAME call."""
    with _recording() as calls:
        verdict = gates.judge_naturalness([sentence], settings=settings)[0]
    # `.natural`: since W5c the gate returns a `NaturalnessVerdict`, which is
    # always truthy as an object. The reason still comes from `_reason_of`,
    # read off the raw response at the seam — so the harness derives it
    # independently of the gate rather than trusting the thing it observes.
    return verdict.natural, _reason_of(calls)


# ── reporting ───────────────────────────────────────────────────────────────


def _summarise(results: list[tuple[bool, str]]) -> str:
    natural = sum(1 for ok, _ in results if ok)
    reasons = Counter(reason for _, reason in results)
    tally = ", ".join(f"{r}x{n}" for r, n in reasons.most_common())
    return f"{natural}/{len(results)} natural   reasons: {tally}"


def _mostly_natural(results: list[tuple[bool, str]]) -> bool:
    return sum(1 for ok, _ in results if ok) >= HIGH * len(results)


def _mostly_rejected(results: list[tuple[bool, str]]) -> bool:
    return sum(1 for ok, _ in results if ok) <= LOW * len(results)


def _partition(fixtures: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """judged / gapped-or-errored / clean-prose.

    `match_pairs` is not judged at all: it has no sentence, so `judged_sentence`
    returns "" and `gates.validate` skips the call (`if sentence.strip()`).

    Since W5c `gapped` is empty by construction — that is the fix, visible here.
    """
    judged = [r for r in fixtures if arm_as_shipped(r["item"]).strip()]
    gapped = [r for r in judged if arm_filled(r["item"]) != arm_as_shipped(r["item"])]
    names = {r["name"] for r in gapped}
    clean = [r for r in judged if r["name"] not in names]
    return judged, gapped, clean


# ── dry run ─────────────────────────────────────────────────────────────────


def dry_run(runs: int) -> int:
    """Print both arms for every fixture. Send nothing.

    Most of the finding is visible here at zero cost: the four `___` strings are
    the ones the judge was asked to call natural English.
    """
    settings = load_settings()
    fixtures = load_fixtures()
    judged, gapped, clean = _partition(fixtures)

    print(f"model:  {settings.llm_model}")
    print(f"runs:   {runs} per arm")
    print(f"source: {_fixture_path()}")
    print("\n=== system prompt sent for every arm-A and arm-B call ===")
    print((PROMPTS_DIR / "item_naturalness.txt").read_text(encoding="utf-8"))

    print("=== what each fixture puts in front of the judge ===\n")
    for row in fixtures:
        item = row["item"]
        shipped, filled = arm_as_shipped(item), arm_filled(item)
        if not shipped.strip():
            print(
                f"{row['name']:22} (not judged — no sentence to judge)"
            )
            continue
        flag = "  <-- GAPPED/ERRORED" if filled != shipped else ""
        print(f"{row['name']:22} A: {shipped!r}{flag}")
        if filled != shipped:
            print(f"{'':22} B: {filled!r}")
    print(
        f"\n{len(judged)} judged, {len(gapped)} of them gapped or errored, "
        f"{len(clean)} already prose."
    )
    print(
        f"\n--live would make {len(judged) * runs} arm-A calls + "
        f"{len(gapped) * runs} arm-B calls "
        f"= {len(judged) * runs + len(gapped) * runs}, "
        f"plus {2 * PROBE_RUNS} more with --probe-arm."
    )
    print("Nothing was sent and nothing was written.")
    return 0


# ── live ────────────────────────────────────────────────────────────────────


def _confirm(calls: int) -> bool:
    print(f"\nAbout to make {calls} billed model calls. Nothing is written to")
    print("any database and the production host is not contacted.")
    return input("Type y to continue, anything else to stop: ").strip().lower() == "y"


def _run_judge_arms(judged, gapped, runs, settings):
    arm_a: dict[str, list[tuple[bool, str]]] = {}
    arm_b: dict[str, list[tuple[bool, str]]] = {}

    print("\n=== ARM A — AS SHIPPED: exactly what gates.validate sends ===")
    for row in judged:
        sentence = arm_as_shipped(row["item"])
        print(f"\n{row['name']:22} {sentence!r}")
        results = []
        for run in range(1, runs + 1):
            ok, reason = judge_once(sentence, settings=settings)
            results.append((ok, reason))
            print(f"  run {run}  {'natural  ' if ok else 'UNNATURAL'}  {reason}")
        arm_a[row["name"]] = results
        print(f"  -> {_summarise(results)}")

    print("\n=== ARM B — FILLED: the same sentence, gap closed / error corrected ===")
    for row in gapped:
        sentence = arm_filled(row["item"])
        print(f"\n{row['name']:22} {sentence!r}")
        results = []
        for run in range(1, runs + 1):
            ok, reason = judge_once(sentence, settings=settings)
            results.append((ok, reason))
            print(f"  run {run}  {'natural  ' if ok else 'UNNATURAL'}  {reason}")
        arm_b[row["name"]] = results
        print(f"  -> {_summarise(results)}")

    return arm_a, arm_b


def _run_probe_arm(fixtures, settings) -> list[dict]:
    """Arm C. Reproduces the W6 sequence with public calls and no audio.

    **Opt-in since W5c (`--probe-arm`), because production no longer takes this
    path.** Ruling R1 exempted `listening_gap` from the text-only probe on the
    evidence this arm produced: `classes=0` on all six attempts. Billing for it
    by default would be a harness charging to observe a dead branch. It stays
    runnable because W14 may give the probe the audio and make the question
    live again (#121).
    """
    row = next((r for r in fixtures if r["name"] == "listening_gap"), None)
    if row is None:
        return []
    item = row["item"]
    cued = apply_cue(item, "first_letter_length")
    canonical = equivalence_key(item.answer)

    print("\n=== ARM C — the listening_gap probe (no audio gate; it passed at W6) ===")
    print("  NOTE: `gates.validate` no longer takes this path. W5c ruling R1")
    print("  exempted the type on this arm's own evidence; re-run it only to")
    print("  re-open the question, not to check production.")
    print(f"  canonical: {item.answer!r}   key={canonical}")
    print(f"  the probe sees only: {item.prompt_text!r}")
    print("  ...and NEVER the audio the learner hears. PRD §4.3 says the blind")
    print("  solver sees 'only what the learner will see'; here it sees less.\n")

    out = []
    for run in range(1, PROBE_RUNS + 1):
        for label, target in (("bare", item), ("first_letter_length", cued)):
            response = gates.probe_acceptable(target, settings=settings)
            offers = gates._candidates(response)
            classes = distinct_answers(offers)
            offered = canonical in classes
            out.append({"run": run, "cue": label, "offers": offers, "offered": offered})
            print(
                f"  run {run} [{label:18}] classes={len(classes)} {offers} "
                f"canonical_offered={offered}"
            )
    return out


def _verdict(arm_a, arm_b, gapped, clean, probe) -> None:
    """Evaluate the pre-registered branch rules. Nothing is adjusted by hand."""
    print("\n=== PRE-REGISTERED PREDICTIONS ===")

    if not gapped:
        # After W5c the two arms are the same string by construction, so
        # `gapped` is empty and P1/P2 quantify over nothing — and `all()` over
        # an empty set is True. Printing "HELD" there would be a green result
        # over an unreachable path, which is exactly what CLAUDE.md §3 rule 4
        # forbids. Say so instead of scoring it.
        print(
            "  P1/P2  VACUOUS   no fixture differs between the arms any more.\n"
            "         W5c fixed the input, so arm A IS arm B and the W5b\n"
            "         comparison has nothing left to compare. The finding of\n"
            "         this run is the arm-A column alone: every judged string\n"
            "         is prose, and the question is whether it is accepted."
        )
        p3 = all(_mostly_natural(arm_a[r["name"]]) for r in clean)
        print(
            f"  P3  {'HELD    ' if p3 else 'FAILED  '}  "
            "the judged strings accept at >=80% each"
        )
        if probe:
            offered = sum(1 for pr in probe if pr["offered"])
            print(
                f"  ARM C   {offered}/{len(probe)} calls offered the canonical. "
                "Not scored:\n"
                "         ruling R1 removed this path from production, so the\n"
                "         arm reports on a branch `gates.validate` no longer\n"
                "         reaches. It is re-openable evidence, not a verdict."
            )

        print("\n=== VERDICT ===")
        print(
            "  THE FIX HOLDS."
            if p3
            else "  THE FIX DOES NOT HOLD — prose is still being rejected."
        )
        return

    p1 = all(_mostly_rejected(arm_a[r["name"]]) for r in gapped)
    p2 = all(_mostly_natural(arm_b[r["name"]]) for r in gapped)
    p3 = all(_mostly_natural(arm_a[r["name"]]) for r in clean)
    lg = arm_a.get("listening_gap", [])
    p4 = bool(lg) and _mostly_natural(lg) and any(not p["offered"] for p in probe)

    for name, held, text in (
        ("P1", p1, "arm A rejects the four gapped/errored at >=80% each"),
        ("P2", p2, "arm B accepts those same four at >=80% each"),
        ("P3", p3, "the clean-prose strings accept at >=80% each"),
        ("P4", p4, "listening_gap passes naturalness, fails only at the probe"),
    ):
        print(f"  {name}  {'HELD    ' if held else 'FAILED  '}  {text}")

    print("\n=== VERDICT, PER THE BRANCH RULES AS WRITTEN BEFORE THE RUN ===")
    if p1 and p2:
        print(
            "  THE JUDGE IS RIGHT AND THE INPUT IS WRONG.\n"
            "  The same sentence is rejected gapped and accepted filled, so the\n"
            "  rejection is caused by what `sentence_of` hands the judge, not by\n"
            "  the item and not by the judge's strictness. Fix the input. Do NOT\n"
            "  touch the prompt; there is no threshold to touch."
        )
    elif p1 and not p2:
        print(
            "  THE FIXTURES ARE GENUINELY UNNATURAL.\n"
            "  Filling the gap did not rescue them, so `valid.json` holds items\n"
            "  the gate refuses and the suite has been asserting over items that\n"
            "  could never ship."
        )
    else:
        print(
            "  THE GATE IS UNSTABLE RUN TO RUN.\n"
            "  Arm A did not reproduce the W6 rejections, so yield is not a\n"
            "  property of the item. This is the worst outcome for W10."
        )


def live(runs: int, *, probe_arm: bool) -> int:
    settings = load_settings()
    fixtures = load_fixtures()
    judged, gapped, clean = _partition(fixtures)
    total = len(judged) * runs + len(gapped) * runs
    if probe_arm:
        total += 2 * PROBE_RUNS

    if not _confirm(total):
        print("Stopped. Nothing was sent.")
        return 1

    print(f"\nmodel: {settings.llm_model}   runs: {runs}   calls: {total}")
    arm_a, arm_b = _run_judge_arms(judged, gapped, runs, settings)
    probe = _run_probe_arm(fixtures, settings) if probe_arm else []

    print("\n=== SUMMARY ===")
    print(f"{'item':22} {'arm A':16} {'arm B':16}")
    for row in judged:
        name = row["name"]
        a = arm_a[name]
        b = arm_b.get(name)
        a_txt = f"{sum(1 for ok, _ in a if ok)}/{len(a)} natural"
        b_txt = (
            f"{sum(1 for ok, _ in b if ok)}/{len(b)} natural" if b else "(same as A)"
        )
        print(f"{name:22} {a_txt:16} {b_txt:16}")

    _verdict(arm_a, arm_b, gapped, clean, probe)

    print(
        f"\n{len(judged)} ITEMS, {runs} SAMPLES EACH, of a stochastic system. This "
        "distinguishes a\ndeterministic cause from a stochastic one and NOTHING "
        "MORE. It licenses no claim\nabout the gate's rate in either direction, "
        "and it is NOT a yield number for W10:\nthese fixtures were hand-written "
        "to be good and generated items will not be.\n"
        "\nNothing was written to any database and the production host was not "
        "contacted."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="make the calls and print the finding"
    )
    parser.add_argument(
        "--runs", type=int, default=DEFAULT_RUNS,
        help=f"samples per fixture per arm (default {DEFAULT_RUNS})")
    parser.add_argument(
        "--probe-arm",
        action="store_true",
        help="also run arm C, which W5c ruling R1 removed from production",
    )
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if args.live:
        return live(args.runs, probe_arm=args.probe_arm)
    return dry_run(args.runs)


if __name__ == "__main__":
    sys.exit(main())
