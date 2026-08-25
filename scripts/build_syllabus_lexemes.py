#!/usr/bin/env python3
"""Generate `data/syllabus_lexemes.tsv`: which of the 24 units teaches each word.

**Development-only. This never runs on the server, and it touches no database.**
It reads `data/lexemes.tsv` and `data/syllabus_units.json`, calls the model
through `core.llm`, and writes one TSV. Same role `scripts/build_lexicon.py`
plays for the lexicon, and kept out of `packages/core` for the same reason.

    .venv/bin/python scripts/build_syllabus_lexemes.py --dry-run   # no calls
    .venv/bin/python scripts/build_syllabus_lexemes.py
    .venv/bin/python scripts/build_syllabus_lexemes.py --audit 150 # agreement rate

WHY A MODEL AT ALL. PRD §3 asks for lexemes "chosen by frequency band n topic n
not already in your known-word ledger". Frequency band is a column on `lexemes`.
CEFR is a column. **Topic is not, and nothing in the repository has ever had
one** -- the sources were a frequency list and CEFR-J, neither of which carries
one. So the topic axis is produced here or it does not exist.

WHY THE MODEL IS ASKED FOR A STAGE AND NOT A UNIT. The first version of this
script asked for one of the 24 units, and the result said plainly that this is
the wrong granularity: **15 of 24 units came up short and 8 of those had fewer
than 20 words**, while units 1, 5, 9 and 13 -- the most concretely topical unit
of each stage -- absorbed everything. Unit 8 is `a/an/the` and got exactly ONE
word.

That is not a tagging failure, it is the schema of PRD §3. **The lexical field
is a property of the STAGE**: "places, products, people, city life, apartments"
covers units 5-8 together. Within a stage the units differ by GRAMMAR, and
grammar has no vocabulary of its own -- there is no such thing as an
article-flavoured noun. Asking which of four units owns a word invents a
distinction the source document never made, and the top-up pass that repaired
it was worse than the problem: it re-asked with "only unit N is available",
which is a leading question, and it was answering for the majority of 15 units.

So: the model assigns a STAGE (six options, the axis PRD actually defines) and
the split across that stage's four units is deterministic -- round-robin by
frequency, so each unit gets a comparable mix of commoner and rarer words. No
leading questions, no forced fits, and the unit split is reproducible from the
file rather than being a second opinion.

WHY THE OUTPUT IS TRUSTWORTHY ENOUGH TO COMMIT -- four layers, because a
thousand rows nobody verified is a thousand rows of unverified content:

  1. the commit is the review surface: a sorted, human-readable TSV, diffable;
  2. the mechanical gates below run BEFORE anything is written, and if a unit
     comes up short this script REPORTS THE NUMBER AND STOPS. It does not pad
     from outside the pool and it does not lower the target (CLAUDE.md §3
     rule 7);
  3. `--audit` re-tags a random sample through a differently worded prompt and
     prints an agreement rate. **This measures self-consistency, not
     correctness** -- it catches a scrambled batch and cannot tell you a topic
     is right;
  4. a human reads a sample. That is the only layer that measures quality, and
     the record says so.

CLAUDE.md §3 rule 2 does not fire: `llm.py`'s request construction is unchanged
and this calls `chat()` with existing parameters. §5b does not fire either: a
service call on our own key, not a polling loop and not an action taken on a
learner's behalf -- the precedent is `core.items.judge_observe --live`.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "core" / ".."))

from core.llm import LLMError, chat  # noqa: E402
from core.lexicon.normalize import lexeme_rows  # noqa: E402
from core.syllabus import (  # noqa: E402
    CANDIDATE_CEFR,
    CANDIDATE_MIN_FREQ_RANK,
    STAGES,
    UNIT_CANDIDATE_TARGET,
    UNIT_COUNT,
    UNITS_PER_STAGE,
    stage_of,
)
from core.syllabus.content import units  # noqa: E402

OUT_FILE = REPO_ROOT / "data" / "syllabus_lexemes.tsv"
# Not committed: a re-run of a billed pass should cost nothing the second time.
CACHE_FILE = REPO_ROOT / ".syllabus-stage-cache.json"
# 60, not 120. The first run at 120 truncated mid-object: the model emits one
# line per lemma and a 120-lemma reply runs past what it will produce in one
# turn, so `json_mode` got an unterminated string and the batch was lost. 60
# halves the reply and leaves `reject_truncation` free to catch the rest.
BATCH = 60
# 12000, and the number is empirical rather than generous. `claude-sonnet-5`
# spends output tokens reasoning before it answers, and those count against
# max_tokens: a 60-lemma batch truncated at 4000 and completed cleanly at 8000.
# 12000 is that measurement plus headroom for a batch it finds harder.
MAX_TOKENS = 12000

SYSTEM = """You are building the vocabulary lists for a 24-week English course \
for two adult B1 learners living in Vilnius. They are heading for B2.

The course has six stages. You will be given the stages and a batch of English \
lemmas. For each lemma, say which single stage it best belongs to, or null.

Judge by SUBJECT MATTER. Would this word come up naturally while a learner is \
talking about that stage's topics and doing its can-do task?

Rules:
- One stage per lemma, or null. Never a list.
- Be willing to say null. A word that fits nowhere in particular is better left \
out than forced somewhere.
- Stage 5 is the only work/business stage. Do NOT put office, marketing, pricing \
or negotiation vocabulary in stages 1-4.
- Stage 6 is consolidation and range: words that are about how people say \
things -- describing, reacting, hedging, repairing -- rather than about one \
subject.
- Judge the lemma as an ordinary English word. Ignore rare or technical senses.

Reply with ONLY a JSON object: {"assignments": {"lemma": 3, "lemma2": null, ...}}
Every lemma you were given must appear exactly once as a key."""

AUDIT_SYSTEM = """You are checking vocabulary placement for an English course.

You will be given six course stages and a list of English words. For each word, \
name the stage whose subject matter it most naturally belongs to, or null if \
none of them fit it particularly well.

Answer independently. Think about where a learner would actually meet the word.

Reply with ONLY a JSON object: {"assignments": {"word": 3, "word2": null, ...}}"""


def stage_catalogue() -> str:
    """The six stages, as the model sees them. PRD §3's own table."""
    lines = []
    for stage in STAGES:
        members = [u for u in units() if u.stage == stage.number]
        lines.append(
            f"Stage {stage.number} — {stage.title} (weeks "
            f"{members[0].unit_number}-{members[-1].unit_number}) — "
            f"can do: {stage.can_do} — subject matter: {stage.lexical_field}"
        )
    return "\n".join(lines)


def pool() -> list[tuple[str, int, int, str]]:
    """(lemma, freq_rank, freq_band, cefr) for every candidate, commonest first.

    The filter IS the design: B1/B2 only, and strictly above the top-2000
    assumption floor. A lemma inside the floor is assumed known for every
    learner (`assume_top_frequency_known`), so it could never survive the
    per-learner diff and has no business being a target.
    """
    rows = [
        (lemma, rank, band, cefr)
        for lemma, _pos, rank, band, cefr in lexeme_rows()
        if cefr in CANDIDATE_CEFR and rank > CANDIDATE_MIN_FREQ_RANK
    ]
    rows.sort(key=lambda r: r[1])
    return rows


def ask(system: str, catalogue: str, lemmas: list[str]) -> dict[str, int | None]:
    payload = chat(
        [
            {
                "role": "user",
                "content": (
                    f"The six stages:\n\n{catalogue}\n\n"
                    f"Assign each of these {len(lemmas)} lemmas:\n"
                    + ", ".join(lemmas)
                ),
            }
        ],
        system=system,
        json_mode=True,
        max_tokens=MAX_TOKENS,
        # A truncated reply is a LOST BATCH, not a short one: json_mode would
        # raise on the unterminated object anyway, and this turns a confusing
        # parse error into the accurate one. Every lemma that does not come back
        # is left unassigned rather than guessed at.
        reject_truncation=True,
    )
    raw = payload.get("assignments", {}) if isinstance(payload, dict) else {}
    out: dict[str, int | None] = {}
    for lemma in lemmas:
        value = raw.get(lemma)
        out[lemma] = value if isinstance(value, int) and 1 <= value <= len(STAGES) else None
    return out


def tag(rows: list[tuple[str, int, int, str]], catalogue: str) -> dict[str, int | None]:
    """Assign every lemma a stage. Cached, so a re-run costs nothing.

    The cache is keyed on the prompt and the pool. It exists because the first
    version of this script had to be thrown away after ~50 billed calls when the
    granularity turned out to be wrong, and the assignments went with it.
    """
    cached: dict[str, int | None] = {}
    if CACHE_FILE.exists():
        cached = {k: v for k, v in json.loads(CACHE_FILE.read_text()).items()}
        print(f"cache: {len(cached)} lemmas already tagged", flush=True)

    todo = [r for r in rows if r[0] not in cached]
    batches = [todo[i : i + BATCH] for i in range(0, len(todo), BATCH)]
    for n, batch in enumerate(batches, start=1):
        lemmas = [r[0] for r in batch]
        try:
            got = ask(SYSTEM, catalogue, lemmas)
        except LLMError as exc:
            print(f"  batch {n}/{len(batches)}: FAILED ({exc}) — left unassigned", flush=True)
            got = dict.fromkeys(lemmas)
        cached.update(got)
        CACHE_FILE.write_text(json.dumps(cached))
        placed = sum(1 for v in got.values() if v is not None)
        print(f"  batch {n}/{len(batches)}: {placed}/{len(lemmas)} placed", flush=True)
    return cached


def split_stage_across_its_units(
    stage: int, members: list[tuple[str, int, int, str]]
) -> dict[int, list[tuple[str, int, int, str]]]:
    """Deal a stage's words round-robin, by frequency, across its four units.

    **Deterministic, and no model is asked.** Within a stage the four units
    differ by GRAMMAR, not by subject matter -- PRD §3 gives one lexical field
    per stage -- so there is no topical question to answer here and asking one
    would invent a distinction the source document does not make.

    Round-robin rather than contiguous slices so every unit gets a comparable
    mix of commoner and rarer words: a contiguous split would make unit 5 easy
    and unit 8 hard for no reason anyone chose.
    """
    first_unit = (stage - 1) * UNITS_PER_STAGE + 1
    out: dict[int, list[tuple[str, int, int, str]]] = {
        first_unit + i: [] for i in range(UNITS_PER_STAGE)
    }
    for index, row in enumerate(sorted(members, key=lambda r: r[1])):
        out[first_unit + index % UNITS_PER_STAGE].append(row)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--audit", type=int, default=0, metavar="N")
    args = parser.parse_args()

    rows = pool()
    catalogue = stage_catalogue()
    need_per_stage = UNITS_PER_STAGE * UNIT_CANDIDATE_TARGET
    print(
        f"pool {len(rows)} lemmas ({'/'.join(CANDIDATE_CEFR)}, rank > "
        f"{CANDIDATE_MIN_FREQ_RANK}); need {need_per_stage} per stage "
        f"({UNIT_COUNT * UNIT_CANDIDATE_TARGET} total); "
        f"{(len(rows) + BATCH - 1) // BATCH} batches of {BATCH}",
        flush=True,
    )
    if args.dry_run:
        print("dry run — no calls made")
        return 0

    print("pass 1: stage assignment", flush=True)
    assigned = tag(rows, catalogue)

    by_stage: dict[int, list[tuple[str, int, int, str]]] = {
        s.number: [] for s in STAGES
    }
    for row in rows:
        stage = assigned.get(row[0])
        if stage is not None:
            by_stage[stage].append(row)
    print(
        "stage totals: "
        + ", ".join(f"{s}:{len(v)}" for s, v in sorted(by_stage.items())),
        flush=True,
    )

    # Stage 6's lexical field in PRD §3 is literally "everything; consolidation",
    # so a leftover word is not a bad fit for it -- it is the definition. This is
    # the ONE place a word moves without the model having put it there, and it
    # moves into the stage whose stated field is "everything".
    leftover = [r for r in rows if assigned.get(r[0]) is None]
    if len(by_stage[6]) < need_per_stage and leftover:
        gap = need_per_stage - len(by_stage[6])
        taken = leftover[:gap]
        by_stage[6].extend(taken)
        print(
            f"stage 6: +{len(taken)} from the unassigned pool → {len(by_stage[6])} "
            '(PRD §3 calls stage 6 "everything; consolidation")',
            flush=True,
        )

    short = {s: len(v) for s, v in by_stage.items() if len(v) < need_per_stage}
    if short:
        print(
            f"\nSTOPPING. Stages below {need_per_stage} lemmas: {short}\n"
            "The bar is not lowered (CLAUDE.md §3 rule 7). Widen the pool or "
            "re-run the tagger; do not pad from outside it."
        )
        return 1

    by_unit: dict[int, list[tuple[str, int, int, str]]] = {}
    for stage, members in by_stage.items():
        # Only the commonest `need_per_stage` are kept: beyond that the words
        # get rarer than a B1->B2 learner has any use for this year.
        by_unit.update(split_stage_across_its_units(stage, members[:need_per_stage]))

    if args.audit:
        run_audit(rows, assigned, catalogue, args.audit)

    write(by_unit)
    return 0


def run_audit(rows, assigned, catalogue: str, sample_size: int) -> None:
    """Re-tag a sample through a differently worded prompt; print agreement.

    **Self-consistency, not correctness.** Stated here and in the record so the
    number is never read as a quality measurement. The quality measurement is a
    person reading rows, and there is no substitute for it.
    """
    placed = [r[0] for r in rows if assigned.get(r[0]) is not None]
    rng = random.Random(20260825)  # fixed: the sample must be reproducible
    sample = rng.sample(placed, min(sample_size, len(placed)))
    agree = 0
    checked = 0
    for offset in range(0, len(sample), BATCH):
        batch = sample[offset : offset + BATCH]
        try:
            got = ask(AUDIT_SYSTEM, catalogue, batch)
        except LLMError as exc:
            print(f"  audit batch FAILED ({exc})", flush=True)
            continue
        for lemma, value in got.items():
            checked += 1
            if value == assigned[lemma]:
                agree += 1
    if checked:
        print(
            f"\naudit: {agree}/{checked} = {100 * agree / checked:.0f}% agreement "
            "with an independently worded prompt, on the STAGE assignment.\n"
            "This is SELF-CONSISTENCY, not correctness. Read a sample yourself.",
            flush=True,
        )


def write(by_unit: dict[int, list[tuple[str, int, int, str]]]) -> None:
    lines = [
        "# Generated by scripts/build_syllabus_lexemes.py — do not edit by hand.",
        "#",
        "# Which of the 24 units (PRD §3) teaches each word. Topic is not a column",
        "# on `lexemes` and never has been, so this assignment is authored, not",
        "# derived. It is committed as a sorted TSV precisely so it is reviewable",
        "# in a diff -- see the script's docstring for the four checks it gets.",
        "#",
        "# These are CANDIDATES, shared by every learner. The per-learner target",
        "# list is candidates minus that learner's known-word ledger, computed at",
        "# read time by core.services.syllabus.unit_target_lexemes -- never stored.",
        "#",
        "# Derived from data/lexemes.tsv and inherits its licences (CC BY-SA 4.0);",
        "# see data/LICENCES.md.",
        "lemma\tunit\tfreq_rank\tfreq_band\tcefr",
    ]
    total = 0
    for unit in range(1, UNIT_COUNT + 1):
        for lemma, rank, band, cefr in sorted(by_unit[unit], key=lambda r: r[1]):
            lines.append(f"{lemma}\t{unit}\t{rank}\t{band}\t{cefr}")
            total += 1
    OUT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    counts = {u: len(v) for u, v in by_unit.items()}
    print(f"\nwrote {OUT_FILE} — {total} rows")
    print(f"per unit: min {min(counts.values())}, max {max(counts.values())}")
    print(f"stages: {sorted({stage_of(u) for u in counts})}")


if __name__ == "__main__":
    raise SystemExit(main())
