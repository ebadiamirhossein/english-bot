"""`python -m core.placement.bank` — builds W18's placement bank. **Human-run,
dry by default (#196).**

    python -m core.placement.bank                   # dry: prints the plan and every request; sends nothing
    python -m core.placement.bank --free --apply    # writes the free sections only; NO billed call
    python -m core.placement.bank --live --sample   # BILLED, SMALL: one grammar and one listening cohort; writes nothing
    python -m core.placement.bank --live            # BILLED: generates and gates everything; writes nothing
    python -m core.placement.bank --apply           # BILLED: writes every section, and what passed
    python -m core.placement.bank --only listening:C1           # dry: one cell's cohorts and ceiling
    python -m core.placement.bank --only listening:C1 --apply   # BILLED: that cell only; no free row

**RULING 0.1 (build run 2): THE BANK IS GENERATED, NOT SOURCED, AND IT IS
UNCALIBRATED.** Every row is labelled `uncalibrated` by migration 032's column
default, and nothing here can write another value.

**What each section is, and what it costs:**

* **vocabulary** — real words drawn from `lexemes` by `freq_rank` band and CEFR
  tag (`core.services.placement.vocabulary_candidates`), and pronounceable
  pseudo-words checked absent from every lemma and every inflected form
  (`core.placement.pseudowords`). **Free.** Deterministic for `SEED`.
* **speaking** — the authored prompts in `core.placement.targets`. **Free.**
* **grammar** — `core.items.generate.generate_drafts` then
  `generate.verify_cohort`: the free stages, the batched naturalness judge, the
  blind solver with its repair ladder, and `gates.probe_target` against the
  band's own targets. **The same gates every item in the app passes**; only the
  targets are new. **Billed.**
* **listening** — the same, with `listening_gap` items, whose stage 3 is the
  audio round-trip (`gates._audio_gate`: synthesize → transcribe, the whole
  sentence and the gapped word heard). **Billed (LLM + TTS + STT).**

**What a passed item must also be, here and not in the gates:** free of an
`l1_gloss` cue. The bank is shared by a Farsi and a Lithuanian speaker, so a
gloss in one learner's language cannot be shown; such an item is reported and
not written (the payload names no L1 for the same reason).

**TOPS UP.** Each run plans only the shortfall against `targets`' sizes, so a
second `--apply` after a partial first one buys what is missing and nothing
else. **The ceiling printed is an upper bound**: every cue re-probe and every
target probe counted as if every item reached it.

**`--sample` IS THE PROBE'S LIVE HALF.** A full `--live` bills the whole bank to
look at it and then `--apply` bills it again; `--sample` keeps the first
grammar cohort and the first listening cohort (A2 — the band the generator's
B1→B2 prompt is least written for) and nothing else, so the response shape and
the gates' verdicts are seen for a few dozen calls before the full `--apply`.

**BUILD RUN RULING 0.5: THE DRY RUN IS THE PROBE.** It prints the model, every
system prompt as substituted, every payload, every candidate list, the
`max_tokens` and the ceiling — and it is in `BUILD_PROGRESS.md`'s
`## Launch pass — probes`. No billed call has been made by Claude Code.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from core.config import Settings, load_settings
from core.items import gates
from core.items import generate
from core.items.generate import Outcome, Slot
from core.placement import BANDS, CALIBRATION, readiness
from core.placement.pseudowords import pseudowords
from core.placement.scoring import BAND_SIZE, PSEUDO_PER_SITTING, REAL_PER_BAND, VOCAB_BANDS
from core.placement.targets import (
    BATCH,
    GRAMMAR_PER_BAND,
    GRAMMAR_TARGETS,
    GRAMMAR_TYPES,
    LISTENING_PER_BAND,
    LISTENING_TARGETS,
    LISTENING_TYPE,
    SITTINGS,
    CAPITALISED_IN_USE,
    NOT_A_TEST_WORD,
    SPEAKING_PROMPTS,
    all_targets,
    band_can_do,
    spelling_key,
)

logger = logging.getLogger(__name__)

#: Gitignored, like every generator journal. **Tests always pass `journal_path`
#: (#416, #420).**
DEFAULT_JOURNAL = Path("w18-placement-journal.jsonl")

#: The vocabulary draw and the pseudo-word generator are seeded, so the dry run
#: prints exactly the rows `--apply` writes.
SEED = 18

SECTIONS = ("vocabulary", "speaking", "grammar", "listening")
FREE = ("vocabulary", "speaking")


@dataclass(frozen=True, slots=True)
class Cohort:
    """One generation call's worth of slots, all in one section and band."""

    section: str
    band: str
    slots: tuple[Slot, ...]
    candidates: tuple[str, ...]
    payload: dict
    avoid: tuple[str, ...]
    item_types: tuple[str, ...]


@dataclass
class Plan:
    #: (lemma, freq_rank, cefr)
    words: list[tuple[str, int, str]] = field(default_factory=list)
    pseudo: list[str] = field(default_factory=list)
    #: (cefr, prompt)
    speaking: list[tuple[str, str]] = field(default_factory=list)
    cohorts: list[Cohort] = field(default_factory=list)
    #: What the bank holds now, for the print.
    held: Counter = field(default_factory=Counter)


def _held(rows: Sequence[dict]) -> Counter:
    held: Counter = Counter()
    for r in rows:
        if r["section"] == "vocabulary":
            if r["is_word"]:
                held[("vocabulary", (r["freq_rank"] - 1) // BAND_SIZE)] += 1
            else:
                held[("pseudo",)] += 1
        elif r["section"] == "speaking":
            held[("speaking", r["item"]["prompt_text"])] += 1
        else:
            held[(r["section"], r["cefr"], r["error_type"])] += 1
    return held


def _cohorts(section: str, band: str, wanted: list[tuple[str, str]],
             types: tuple[str, ...], candidates: tuple[str, ...],
             avoid: tuple[str, ...]) -> list[Cohort]:
    """``wanted`` (error_type, target) slots → cohorts of at most `BATCH`, each
    re-indexed from 0 so every draft is addressable (#261)."""
    out = []
    for start in range(0, len(wanted), BATCH):
        chunk = wanted[start:start + BATCH]
        slots = tuple(
            Slot(index=i, item_type=types[(start + i) % len(types)], target=target,
                 cohort="placement", error_type=code)
            for i, (code, target) in enumerate(chunk)
        )
        generate._assert_indices_addressable(slots)
        payload = {
            "can_do": band_can_do(band, listening=section == "listening"),
            "track": "life",
            "items": [{"item_type": s.item_type, "grammar_target": s.target} for s in slots],
        }
        out.append(Cohort(section, band, slots, candidates, payload, avoid, types))
    return out


def _generated_plan(section: str, held: Counter, avoid: tuple[str, ...]) -> list[Cohort]:
    targets = GRAMMAR_TARGETS if section == "grammar" else LISTENING_TARGETS
    types = GRAMMAR_TYPES if section == "grammar" else (LISTENING_TYPE,)
    cohorts: list[Cohort] = []
    for band in BANDS:
        own = targets[band]
        per_band = GRAMMAR_PER_BAND if section == "grammar" else LISTENING_PER_BAND[band]
        each = per_band // len(own)
        # Interleaved, so a short run still spreads over the band's targets.
        short = {code: max(0, each - held[(section, band, code)]) for code, _ in own}
        wanted: list[tuple[str, str]] = []
        while any(short.values()):
            for code, target in own:
                if short[code]:
                    wanted.append((code, target))
                    short[code] -= 1
        if not wanted:
            continue
        # Grammar: the band's own targets discriminate each other. Listening: a
        # band has one or two, so every listening target is a candidate.
        candidates = (
            tuple(t for _, t in own) if section == "grammar"
            else all_targets(LISTENING_TARGETS)
        )
        cohorts.extend(_cohorts(section, band, wanted, types, candidates, avoid))
    return cohorts


def plan(sections: Sequence[str] = SECTIONS) -> Plan:
    """What a run would write and send. **Reads the database; sends nothing.**"""
    from core.db import connection
    from core.lexicon.normalize import inflections
    from core.services import placement as svc

    out = Plan()
    with connection() as conn:
        rows = svc.bank_rows(conn)
        out.held = _held(rows)
        in_bank = {r["word"] for r in rows if r["word"]}
        if "vocabulary" in sections:
            # One spelling per word across the whole bank (B4): *moustache* is
            # not drawn once *mustache* is in it, or drawn before it here.
            taken = {spelling_key(w) for w in in_bank}
            for band in range(VOCAB_BANDS):
                need = SITTINGS * REAL_PER_BAND - out.held[("vocabulary", band)]
                if need <= 0:
                    continue
                pool = [c for c in svc.vocabulary_candidates(
                    conn, band * BAND_SIZE + 1, (band + 1) * BAND_SIZE)
                    if c[0] not in in_bank and c[0] not in NOT_A_TEST_WORD
                    and c[0] not in CAPITALISED_IN_USE]
                rng = random.Random(SEED * 100 + band)
                picked: list[tuple[str, int, str]] = []
                for candidate in rng.sample(pool, len(pool)):
                    if len(picked) == need:
                        break
                    if spelling_key(candidate[0]) in taken:
                        continue
                    taken.add(spelling_key(candidate[0]))
                    picked.append(candidate)
                out.words.extend(sorted(picked, key=lambda c: c[1]))
            need = SITTINGS * PSEUDO_PER_SITTING - out.held[("pseudo",)]
            if need > 0:
                real = svc.lexeme_lemmas(conn) | frozenset(inflections())
                out.pseudo = pseudowords(need, seed=SEED, real=real, avoid=in_bank)
        if "speaking" in sections:
            out.speaking = [(c, p) for c, p in SPEAKING_PROMPTS
                            if not out.held[("speaking", p)]]
        for section in ("grammar", "listening"):
            if section in sections:
                avoid = tuple(
                    r["item"]["prompt_text"] for r in rows
                    if r["section"] == section and r["item"]
                )
                out.cohorts.extend(_generated_plan(section, out.held, avoid))
    return out


def calls_for(cohort: Cohort) -> int:
    """The billed-call ceiling for one cohort, itemised from its slots.

    generation 1 + naturalness 1 + per slot: the blind solver (probed
    families), `MAX_REPAIRS` cue re-probes (slot family), the audio round-trip
    (2: one TTS, one STT, for audio types) and one `probe_target`. W17's
    `calls_for` plus the audio term it did not need.
    """
    slots = cohort.slots
    n_probed = sum(1 for s in slots
                   if s.item_type not in gates.TYPES_WITH_AUDIO
                   and gates.ANSWER_FAMILY.get(s.item_type) in gates.PROBED_FAMILIES)
    n_slot = sum(1 for s in slots
                 if s.item_type not in gates.TYPES_WITH_AUDIO
                 and gates.ANSWER_FAMILY.get(s.item_type) == "slot")
    n_audio = sum(1 for s in slots if s.item_type in gates.TYPES_WITH_AUDIO)
    return 1 + 1 + n_probed + gates.MAX_REPAIRS * n_slot + 2 * n_audio + len(slots)


def sample(p: Plan) -> Plan:
    """The first grammar cohort and the first listening cohort; no free rows."""
    keep = []
    for section in ("grammar", "listening"):
        first = next((c for c in p.cohorts if c.section == section), None)
        if first is not None:
            keep.append(first)
    return Plan(cohorts=keep, held=p.held)


#: The cells `--only` may name: the generated sections, by band. The free
#: sections are not cells -- `--free` is their switch.
GENERATED = ("grammar", "listening")


def only_cell(value: str) -> tuple[str, str]:
    """`listening:C1` -> ("listening", "C1"), or an argparse error.

    **W24a.** Exact spelling, no case folding: a typo is refused rather than
    guessed, because the next thing this value decides is what gets billed.
    """
    section, sep, band = value.partition(":")
    if not sep or section not in GENERATED or band not in BANDS:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a generated cell: SECTION:BAND with SECTION in "
            f"{', '.join(GENERATED)} and BAND in {', '.join(BANDS)}"
        )
    return section, band


def only(p: Plan, cells: Sequence[tuple[str, str]]) -> Plan:
    """The cohorts in `cells`, and no free rows. **W24a (2026-09-27).**

    The operator's re-read printed one blocker -- *"NO — short listening C1 by
    1"* -- beside a plan of ten cohorts and 148 calls. One cell costs one
    cohort. The whole-bank readiness line still prints: it reads `held`, which
    is kept.
    """
    wanted = set(cells)
    return Plan(cohorts=[c for c in p.cohorts if (c.section, c.band) in wanted],
                held=p.held)


def first_sitting_cells(held: Counter) -> dict[tuple, int]:
    """The bank's totals keyed as `core.placement.readiness` reads them — what a
    learner who has sat nothing has unserved (launch 2026-09-26, B2)."""
    cells: Counter = Counter()
    for key, n in held.items():
        if key[0] == "vocabulary":
            cells[("vocabulary", "real", key[1])] += n
        elif key[0] == "pseudo":
            cells[("vocabulary", "pseudo")] += n
        elif key[0] == "speaking":
            cells[("speaking", "any")] += n
        else:
            cells[(key[0], key[1])] += n
    return cells


def free_rows(p: Plan) -> int:
    return len(p.words) + len(p.pseudo) + len(p.speaking)


def dry_print(p: Plan, *, settings: Settings, journal_path: Path) -> int:
    """Everything a run would write and send. Returns the billed-call ceiling."""
    print("W18 placement bank")
    print(f"calibration label on every row: {CALIBRATION}")
    print(f"model: {settings.llm_model} · TTS voice {settings.tts_voice} · "
          f"STT {settings.whisper_model}")
    print(f"max_tokens (generation): {generate.GENERATE_MAX_TOKENS} · json_mode=True · "
          f"reject_truncation=True")

    print("\n=== held now ===")
    for band in range(VOCAB_BANDS):
        print(f"  vocabulary ranks {band * BAND_SIZE + 1:>5}–{(band + 1) * BAND_SIZE:<5} "
              f"{p.held[('vocabulary', band)]:>3} of {SITTINGS * REAL_PER_BAND}")
    print(f"  pseudo-words                   {p.held[('pseudo',)]:>3} of "
          f"{SITTINGS * PSEUDO_PER_SITTING}")
    for section, targets in (("grammar", GRAMMAR_TARGETS), ("listening", LISTENING_TARGETS)):
        for band in BANDS:
            n = sum(p.held[(section, band, code)] for code, _ in targets[band])
            want = GRAMMAR_PER_BAND if section == "grammar" else LISTENING_PER_BAND[band]
            print(f"  {section:<10} {band}                   {n:>3} of {want}")
    print(f"  speaking prompts               "
          f"{sum(1 for _, t in SPEAKING_PROMPTS if p.held[('speaking', t)]):>3} of "
          f"{len(SPEAKING_PROMPTS)}")
    short = readiness.shortfall(first_sitting_cells(p.held))
    print("  a first sitting can be offered now: " + (
        "yes" if not short else "NO — short " + ", ".join(
            f"{' '.join(str(k) for k in cell)} by {n}" for cell, n in sorted(short.items(),
                                                                          key=str))))

    print(f"\n=== FREE: {len(p.words)} real words, {len(p.pseudo)} pseudo-words, "
          f"{len(p.speaking)} speaking prompts would be written ===")
    for lemma, rank, cefr in p.words:
        print(f"  word   {lemma:<16} rank {rank:>5} {cefr}")
    for word in p.pseudo:
        print(f"  pseudo {word}")
    for cefr, prompt in p.speaking:
        print(f"  speak  {cefr} {prompt}")

    total = 0
    for n, cohort in enumerate(p.cohorts, 1):
        print(f"\n=== BILLED cohort {n}: {cohort.section} {cohort.band}, "
              f"{len(cohort.slots)} slots ===")
        print("--- system prompt, as sent ---")
        print(generate.generator_system_prompt(cohort.item_types, avoid=cohort.avoid))
        print("--- user payload, as sent ---")
        print(json.dumps(cohort.payload, ensure_ascii=False, indent=2))
        print("--- probe_target candidates ---")
        for c in cohort.candidates:
            print(f"  {c}")
        calls = calls_for(cohort)
        total += calls
        print(f"--- ceiling for this cohort: {calls} calls ---")
    for name in ("item_naturalness.txt", "item_probe.txt", "item_target.txt"):
        print(f"\n=== gate prompt {name} (sent by the existing gates, unchanged) ===")
        print((generate.PROMPTS_DIR / name).read_text(encoding="utf-8"))
    print(f"\njournal: {journal_path}")
    print(f"rows the free sections would write: {free_rows(p)}")
    print(f"cohorts: {len(p.cohorts)}")
    print(f"calls --live will make, at most: {total}")
    return total


def _refused(outcome: Outcome) -> str | None:
    """A reason a PASSED item is still not written to a shared bank."""
    item = outcome.item
    if item is not None and item.cue_type == "l1_gloss":
        return "l1_gloss_cue"
    return None


def write_free(p: Plan) -> int:
    """The free sections, in one transaction. Returns the rows written."""
    from core.db import connection
    from core.services import placement as svc

    written = 0
    with connection() as conn:
        for lemma, rank, cefr in p.words:
            written += svc.insert_vocabulary(conn, lemma, is_word=True, freq_rank=rank,
                                             cefr=cefr) is not None
        for word in p.pseudo:
            written += svc.insert_vocabulary(conn, word, is_word=False, freq_rank=None,
                                             cefr=None) is not None
        for cefr, prompt in p.speaking:
            written += svc.insert_speaking(conn, prompt, cefr=cefr) is not None
        conn.commit()
    return written


def run(p: Plan, *, apply: bool, settings: Settings,
        journal_path: Path = DEFAULT_JOURNAL) -> list[tuple[Cohort, Outcome]]:
    """Generate and gate every cohort. Billed. Writes only with ``apply``."""
    from core.db import connection
    from core.items.schema import content_hash
    from core.services import placement as svc

    journal = generate.Journal(journal_path)
    spent: Counter = Counter()
    every: list[tuple[Cohort, Outcome]] = []
    for cohort in p.cohorts:
        try:
            drafts = generate.generate_drafts(
                cohort.payload, settings=settings, avoid=cohort.avoid,
                item_types=cohort.item_types,
            )
        except gates.LLMError as exc:
            print(f"{cohort.section} {cohort.band}: generation FAILED: {exc}")
            continue
        spent["generation"] += 1
        outcomes = generate.verify_cohort(
            cohort.slots, drafts, unit_number=0, candidates=cohort.candidates,
            settings=settings, calls=spent,
        )
        journal.record(outcomes)
        for one in outcomes:
            every.append((cohort, one))
            text = one.item.prompt_text if one.item is not None else "-"
            rank = one.target.claimed_rank if one.target is not None else "-"
            refused = _refused(one) if one.accepted else None
            print(f"  {cohort.section} {cohort.band} slot {one.slot.index + 1} "
                  f"{one.slot.item_type:<16} {one.state:<9} stage={one.stage} "
                  f"codes={list(one.codes)} target_rank={rank}"
                  f"{' REFUSED=' + refused if refused else ''} | {text!r}")
    print(f"\ncalls spent: {dict(spent)} · journal: {journal_path}")
    if not apply:
        print("--live: nothing was written.")
        return every
    written = 0
    with connection() as conn:
        for cohort, one in every:
            if not one.accepted or one.item is None or _refused(one):
                continue
            row = svc.insert_generated(
                conn, cohort.section,
                cefr=cohort.band, error_type=str(one.slot.error_type),
                item=one.item, validation=one.report.as_json() if one.report else {},
                model=settings.llm_model, content_hash=content_hash(one.item),
            )
            written += row is not None
        conn.commit()
    print(f"generated rows written: {written}")
    return every


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="W18 placement bank. Dry by default; --live is billed and writes "
        "nothing; --apply is billed and writes; --free limits a run to the sections "
        "that bill nothing."
    )
    parser.add_argument("--free", action="store_true",
                        help="vocabulary, pseudo-words and speaking prompts only: no billed call")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--sample", action="store_true",
                        help="only the first grammar and the first listening cohort; "
                        "free sections untouched (the probe's live half)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    parser.add_argument("--only", type=only_cell, action="append", metavar="SECTION:BAND",
                        help="only this generated cell, e.g. listening:C1 (repeatable); "
                        "no free rows")
    args = parser.parse_args(argv)
    if args.live and args.apply:
        parser.error("--live and --apply are exclusive")
    if args.free and args.live:
        parser.error("--free bills nothing, so there is nothing for --live to do")
    if args.sample and (args.free or args.apply):
        parser.error("--sample is a look, not a write: use it with --live or alone")
    if args.only and (args.free or args.sample):
        parser.error("--only names generated cells: it does not combine with --free or --sample")
    logging.basicConfig(level=logging.INFO)  # #140

    settings = load_settings()
    p = plan(FREE if args.free else SECTIONS)
    if args.sample:
        p = sample(p)
    if args.only:
        p = only(p, args.only)
    ceiling = dry_print(p, settings=settings, journal_path=args.journal)
    if args.only and not p.cohorts:
        cells = ", ".join(f"{s} {b}" for s, b in args.only)
        print(f"\nnothing is short in {cells} — nothing to send.")
        return 0
    if not (args.live or args.apply):
        print("\ndry run — nothing was sent and nothing was written.")
        return 0
    from core.runs import confirm

    if args.free:
        n = free_rows(p)
        if n == 0:
            print("\nthe free sections are full — nothing to write.")
            return 0
        if not confirm(f"This writes {n} rows and makes no billed call.", str(n)):
            print("stopped — nothing was written.")
            return 1
        print(f"written: {write_free(p)} rows")
        return 0
    if not confirm(f"This makes up to {ceiling} billed calls.", str(ceiling)):
        print("stopped — nothing was sent.")
        return 1
    if args.apply:
        print(f"free rows written: {write_free(p)}")
    run(p, apply=args.apply, settings=settings, journal_path=args.journal)
    return 0


if __name__ == "__main__":
    sys.exit(main())
