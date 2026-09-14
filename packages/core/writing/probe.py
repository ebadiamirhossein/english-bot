"""W16a — the §3 rule 2 call for the writing correction, human-run and dry by default.

    python -m core.writing.probe          # prints the request; makes NO call
    python -m core.writing.probe --live   # makes exactly LIVE_CALLS calls

**WHY THIS EXISTS.** `prompts/writing_correction.txt`, `max_tokens`,
`reject_truncation`, the optional `did_well` and the two-correction contract are
NEW REQUEST CONSTRUCTION. CLAUDE.md §3 rule 2: a mocked suite cannot verify a
provider contract, so one real call is made before shipping — **and it is the
operator's, run on the Mac** (send-back S3). `load_dotenv` resolves the
repo-root `.env`, which is where the key is; the prompt build reads
`error_types` from whichever database that `.env` names, which on the Mac is the
development database. **No backup, no migration, no restart, no deploy, and
production is never contacted.**

**IT WRITES NOTHING.** No `errors` row, no `writing_submissions` row, no card.
`tests/test_writing_probe.py` reads this module's own AST and fails if it
imports a writer or contains an `INSERT` or `UPDATE`. The texts are FIXTURES —
design `1k`'s and `1m`'s entries — so no learner's writing leaves the machine.

**TWO CALLS, NOT ONE, AND THE SECOND IS NOT A RETRY.** Ruling 2 has two branches
— an opening line that survives and one that is absent — and a single fixture
can only ever show one of them. The entry with errors is expected to produce
corrections; the clean entry is expected to produce none and, quite possibly,
no opening line. **Both are read by a person** (human check HW1): the gates can
refuse a bad line; they cannot say a surviving one is true.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import time

from core.llm import LLMError
from core.services import writing
from core.services.users import User
from core.writing import gates, offers, rules

#: Design `1k`'s entry: two things worth fixing (past tense; `from` → `of`).
FIXTURE_WITH_ERRORS = (
    "Today I go to the dentist in the morning. I was very nervous because last "
    "time it hurt a lot, but this time she only clean my teeth and it was fine. "
    "After that I went to the office and we had a long meeting about the new "
    "project. My colleague Rasa explain everything twice because nobody "
    "understand the first time. In the evening I cooked soup and watched two "
    "episodes from a series. I am tired now but it was a good day."
)

#: Design `1m`'s entry: nothing to fix.
FIXTURE_CLEAN = (
    "This morning I went to the dentist and it was fine. Then I worked all day "
    "on the spreadsheet that had been broken since Friday. In the evening my "
    "sister called and we talked for a long time about her new flat. I cooked "
    "soup and went to bed early."
)

#: W16b. Unit 1's `output_task_written`, verbatim from `data/syllabus_units.json`
#: (`tests/test_writing_probe.py` pins it against the file) — both learners are on
#: unit 1 by the record's evidence, so this is the task a real Thursday serves.
PARAGRAPH_TASK = "Write six sentences about yesterday. Put them in order and join them with time words."

#: W16b. A paragraph on that task with past-tense slips and two corrections that
#: carry a phrase worth keeping (*depend of*, *waiting my friend*).
FIXTURE_PARAGRAPH = (
    "Yesterday I wake up late because my alarm didn't ring. First I drank a "
    "coffee and then I go to the office by bus. In the morning I had a meeting, "
    "and my manager said that we can't depend of the old plan any more. After "
    "lunch I was waiting my friend for a long time outside the station. Then we "
    "talked about her new flat. Finally I went to bed at midnight because I was "
    "very tired."
)

FIXTURES: tuple[tuple[str, rules.DayKind, str], ...] = (
    ("with_errors", "journal", FIXTURE_WITH_ERRORS),
    ("clean", "journal", FIXTURE_CLEAN),
    ("paragraph", "paragraph", FIXTURE_PARAGRAPH),
)

#: The number of billed calls `--live` makes. Printed by the dry run so the
#: operator confirms it before typing `--live`. **A json_mode repair or a retry
#: would add calls beyond this**, and the live run prints `usage.calls` per
#: fixture so the true figure is read rather than assumed.
LIVE_CALLS = len(FIXTURES)



def fixture_learner() -> User:
    """A B1 Farsi speaker with the explanation fallback OFF — English explanations."""
    return User(
        id=0,
        telegram_user_id=None,
        name="Probe",
        native_language="fa",
        cefr_level="B1",
        explanation_language_fallback=False,
        efset_baseline=None,
        work_domain="general",
        why_statement=None,
        track_weights={"life": 50, "curiosity": 30, "work": 20},
        morning_time=time(8, 0),
        evening_time=time(21, 0),
        onboarded=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m core.writing.probe")
    parser.add_argument(
        "--live",
        action="store_true",
        help=f"make the {LIVE_CALLS} real calls (billed). Without it, nothing is sent.",
    )
    args = parser.parse_args(argv)

    learner = fixture_learner()

    print("=== W16a/W16b writing probe ===")
    print(f"mode: {'LIVE' if args.live else 'DRY — no call is made'}")
    print(f"calls --live will make: {LIVE_CALLS}")
    for kind, task in (("journal", None), ("paragraph", PARAGRAPH_TASK)):
        print(
            f"\nrequest ({kind}): json_mode=True "
            f"max_tokens={rules.max_tokens(kind)} reject_truncation=True "
            f"max_corrections={rules.max_corrections(kind)}"
        )
        print(f"--- system prompt, {kind} (as sent) ---")
        print(writing.build_system_prompt(learner, kind, task))
    for name, kind, text in FIXTURES:
        print(f"\n--- fixture: {name} [{kind}] ({len(text)} chars) ---")
        print(text)

    if not args.live:
        print("\nDRY RUN. Nothing was sent. Re-run with --live to make the calls.")
        return 0

    labels = writing.labels()
    failures = 0
    for name, kind, text in FIXTURES:
        print(f"\n=== LIVE: {name} [{kind}] ===")
        usage: dict = {}
        task = PARAGRAPH_TASK if kind == "paragraph" else None
        try:
            raw = writing.call_model(learner, text, kind, usage_out=usage, task=task)
        except LLMError as exc:
            failures += 1
            print(f"call FAILED: {exc}")
            print(f"usage: {json.dumps(usage)}")
            continue
        print("--- raw response ---")
        print(json.dumps(raw, indent=2, ensure_ascii=False))
        print(f"--- usage --- {json.dumps(usage)}")
        shaped = gates.shape(raw, text, limit=rules.max_corrections(kind), labels=labels, kind=kind)
        print("--- after the gates ---")
        print(f"is_english: {shaped.is_english}")
        print(f"did_well: {shaped.did_well!r}  (None = absent on the wire)")
        print(f"corrections kept: {len(shaped.corrections)}")
        for c in shaped.corrections:
            print(f"  [{c['label']}] {c['you_said']!r} -> {c['correct_form']!r}  keep={c.get('keep')!r}")
            print(f"      {c['explanation']}")
        print(f"dropped by gate: {shaped.dropped or '{}'}")
        if kind == "paragraph":
            print(f"structure: {'ABSENT (refused or missing)' if shaped.structure is None else json.dumps(shaped.structure, ensure_ascii=False)}")
            chosen = offers.select(shaped.corrections)
            print(f"word offers after Q-E: {[o.phrase for o in chosen]}")

    print(f"\nDONE. {LIVE_CALLS - failures} of {LIVE_CALLS} fixtures returned a response.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
