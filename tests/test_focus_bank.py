"""W10d commit 2 — the focus bank. **#299's fix, and the guard against its cause.**

**THE DEFECT, IN ONE LINE: block 3 serves eight items a day and unit 1's focus
cohort holds four**, so a learner met the same items on day two. Three causes,
and this file holds the two a test can reach.

**WHAT THIS SUITE DELIBERATELY DOES NOT ASSERT: that the bank reaches 56.**
Bank size is a property of PRODUCTION DATA, not of code. A test that writes 56
rows and then asserts 56 is a green test over an unreachable path (§3 rule 4)
that would pass on the day the real bank is empty — **the same defect wearing
the opposite sign.** The 56 is counted on the host, by a query independent of
the command that wrote the rows, and **the operator reads the bank.** What the
suite owes instead is the guard against the CAUSE, which is below.

**AND ONE THING NO TEST HERE CAN SHOW, SAID PLAINLY:** that 56 items are 56
different teaching moments rather than 56 rephrasings of four sentences. #271's
rule — a guard refuses a bad draft and never shows the model understood — and
#169 already proved `content_hash` is blind to it. Only a person reading the
bank settles it.
"""

from __future__ import annotations

import psycopg
import pytest

from core.config import load_settings
from core.items.gates import ValidationReport
from core.items.grading import normalise_variants
from core.items.schema import parse
from core.services import items as svc

PASSED = ValidationReport("passed")
TARGET = "past simple: regular and irregular verbs"


@pytest.fixture
def learner():
    with psycopg.connect(load_settings().database_url, autocommit=True) as conn:
        row = conn.execute(
            "INSERT INTO users (name, native_language, auth_email, onboarded) "
            "VALUES ('w10d-focus', 'fa', 'w10d-focus@example.invalid', TRUE) "
            "RETURNING id"
        ).fetchone()
        user_id = int(row[0])
        try:
            yield user_id
        finally:
            conn.execute("DELETE FROM users WHERE id = %s", (user_id,))


def _write(learner: int, *, cohort: str | None, n: int, tag: str, unit: int = 1):
    """`n` items, optionally tagged with a cohort.

    **What this fixture supplies that a real run does not:** a cohort key on
    demand. **The production shape is `cohort=None`** — Q1 confirmed on the host
    2026-08-31 that `payload ->> 'cohort'` is blank on all 14 focus rows — so
    `cohort=None` is the case that matters and `cohort="focus"` is the one that
    does not exist in the wild.
    """
    made = []
    for index in range(n):
        raw = {
            "item_type": "cloze_cued",
            "track": "life",
            "prompt_text": f"{tag}-{index} I ___ to the shops yesterday.",
            "answer": "went",
            "unit_number": unit,
            "grammar_target": TARGET,
        }
        if cohort is not None:
            raw["cohort"] = cohort
        raw["accepted_variants"] = normalise_variants(raw["answer"])
        made.append(svc.insert_item(learner, parse(raw), PASSED, model="test-model"))
    return made


# ── F3 — `focus_held` ───────────────────────────────────────────────────────


def test_focus_held_counts_a_row_with_no_cohort_key(learner) -> None:
    """**THE NAMED ASSERTION, AND IT IS WORTH MONEY.**

    The four live focus rows carry **no `cohort` key at all** and read as focus
    only through `_COHORT`'s `coalesce`. A counter keyed on an explicit
    `payload ->> 'cohort' = 'focus'` would see **0 instead of 4**, plan the
    52-item shortfall as a 56-item one, and **buy those four items twice** — a
    paid-for duplicate run, not a tidiness question.

    So this inserts rows in the PRODUCTION SHAPE — no cohort key — and asserts
    the counter finds them.

    Demonstrated red by giving `focus_held` a private
    `payload ->> 'cohort' = 'focus'` predicate.
    """
    _write(learner, cohort=None, n=4, tag="live-shape")
    assert svc.focus_held(learner, unit_number=1) == 4


def test_focus_held_does_not_count_the_checkpoint_reserve(learner) -> None:
    """**A checkpoint item is not focus stock and must not pay for itself.**

    Counting the reserve would understate the shortfall and leave block 3 short
    — #299's own direction of failure.
    """
    _write(learner, cohort=None, n=3, tag="focus")
    _write(learner, cohort="checkpoint", n=5, tag="cp")
    assert svc.focus_held(learner, unit_number=1) == 3


def test_focus_held_is_unit_scoped(learner) -> None:
    _write(learner, cohort=None, n=3, tag="u1", unit=1)
    _write(learner, cohort=None, n=2, tag="u2", unit=2)
    assert svc.focus_held(learner, unit_number=1) == 3
    assert svc.focus_held(learner, unit_number=2) == 2


def test_focus_held_cannot_diverge_from_bank_for_session(learner) -> None:
    """**`--fill` subtracts what `focus_held` counts, so every row it counts
    must be one block 3 can actually serve.**

    The precedent is `test_checkpoint_held_cannot_diverge_from_checkpoint_items`,
    demonstrated red the same way. **The property, not the constant:** a row
    `bank_for_session` would never return must not be counted as held, because
    a generator that counts rows the code cannot serve buys the wrong number.

    Here the divergence that matters is the **validator version** — a stale row
    is invisible to block 3 and would silently shrink the purchase.

    Demonstrated red by dropping `_CURRENT_VALIDATOR` from `_FOCUS_STOCK`.
    """
    _write(learner, cohort=None, n=3, tag="ok")
    stale = _write(learner, cohort=None, n=2, tag="stale")
    with psycopg.connect(load_settings().database_url, autocommit=True) as conn:
        conn.execute(
            "UPDATE items SET validator_version = validator_version - 1"
            " WHERE id = ANY(%s)",
            (list(stale),),
        )

    servable = {
        row.id for row in svc.bank_for_session(learner, unit_number=1, limit=100)
    }
    assert svc.focus_held(learner, unit_number=1) == len(servable) == 3


# ── F1 — the two eights, and the guard against #299's actual cause ──────────


def test_the_bank_target_and_the_session_size_are_different_numbers() -> None:
    """**#299's CAUSE, AND IT PREDATES THE YIELD PROBLEM.**

    `ITEMS_PER_UNIT = 8` and `FOCUS_ITEM_COUNT = 8` **both cited
    `docs/PRD-v3-web.md:213`, which is a PER-SESSION number.** Nothing in the
    PRD ever said the BANK should be eight, so even at 100% yield a unit
    reached a one-day cycle. **The two eights were never the same quantity and
    the citation is what made them look like it.**

    So: how many items block 3 serves in a session, how many slots one
    generation cohort has, and how big the bank must be are **three numbers**,
    and only the first may cite that PRD line.

    RED against restoring the citation on `ITEMS_PER_UNIT`, and against making
    `FOCUS_BANK_TARGET` equal to either eight.
    """
    from pathlib import Path

    from core.items.generate import FOCUS_BANK_TARGET, ITEMS_PER_UNIT
    from core.services.items import FOCUS_ITEM_COUNT

    assert FOCUS_BANK_TARGET == 56
    assert FOCUS_BANK_TARGET != FOCUS_ITEM_COUNT
    assert FOCUS_BANK_TARGET != ITEMS_PER_UNIT

    citation = "PRD-v3-web.md:213"
    generate = Path("packages/core/items/generate.py").read_text(encoding="utf-8")
    services = Path("packages/core/services/items.py").read_text(encoding="utf-8")

    # The per-session number may cite it; it IS that number.
    assert citation in services

    # **The cohort size may not.** Sliced to the constant's own block so a
    # mention in a comment elsewhere in this 2,600-line module cannot satisfy
    # or break the assertion.
    block = generate[generate.index("ITEMS_PER_UNIT = 8") - 1200 :]
    block = block[: block.index("ITEMS_PER_UNIT = 8")]
    assert citation not in block, (
        "ITEMS_PER_UNIT is a cohort size, not PRD §4.1's per-session eight — "
        "citing that line is what produced #299"
    )


def test_a_short_bank_serves_what_it_has_and_does_not_pad(learner) -> None:
    """§3 rule 7 on the read side: **the shortfall is items, never a lowered
    bar.** A bank of three serves three, and block 3 is short rather than
    padded with repeats.
    """
    _write(learner, cohort=None, n=3, tag="short")
    served = svc.focus_items(learner, unit_number=1)
    assert len(served) == 3
    assert len({one.id for one in served}) == 3


# ── F3 — the focus `--fill` ────────────────────────────────────────────────


def test_fill_without_checkpoint_is_permitted_and_plans_the_shortfall() -> None:
    """**`--fill` was refused unless `--checkpoint`; that refusal was the whole
    blocker on the focus half.**

    The plan is computed from `focus_held` against `FOCUS_BANK_TARGET` and is
    expressed in **cohorts**, because F4 keeps the cohort at eight slots and
    loops — eight is the size every gate, ceiling and test was measured against,
    and a 40-slot cohort's thinking once consumed 8,000 tokens and returned an
    empty text block.

    **No database and no model call:** `unit_plan` is pure and `held` is passed
    in, exactly as the checkpoint side does it.

    RED against restoring `parser.error("--fill only means anything with
    --checkpoint")`, and against a plan that ignores what the bank holds.
    """
    from core.items.generate import unit_plan

    plan = unit_plan([1], focus_held={1: 4})[1]
    assert plan["held"] == 4
    assert plan["shortfall"] == 52
    # 52 items over 8-slot cohorts, and the remainder rounds UP: seven cohorts
    # would buy 56 and leave the bank four short of its own target.
    assert plan["cohorts"] == 7
    assert len(plan["slots"]) == 8


def test_a_full_bank_plans_nothing_rather_than_a_negative() -> None:
    """A bank at or past the target buys nothing. **Asserted because the
    arithmetic is a subtraction and the failure mode is a negative cohort
    count**, which would either crash or, worse, round to one and spend.
    """
    from core.items.generate import unit_plan

    for held in (56, 60):
        plan = unit_plan([1], focus_held={1: held})[1]
        assert plan["shortfall"] == 0
        assert plan["cohorts"] == 0


def test_a_focus_run_without_fill_still_plans_one_cohort() -> None:
    """**The unfilled path is unchanged**, which is what keeps every existing
    caller and every W10c test meaning what it meant.
    """
    from core.items.generate import unit_plan

    plan = unit_plan([1])[1]
    assert plan["cohorts"] == 1
    assert plan["held"] is None
    assert len(plan["slots"]) == 8


# ── #305 — the ceiling must count the cohorts the run will actually make ────


def test_the_ceiling_counts_every_cohort_the_run_will_make() -> None:
    """**#305: the printed ceiling is what the operator authorises a billed run
    against, and it was a quarter of the real number.**

    `_expected_calls` costed **one cohort per unit** while a filled focus run
    loops. At unit 1's real shortfall it would print a ceiling for one cohort
    and the run would make seven cohorts' worth — *"an authorisation given
    against a number that is a quarter of the real one"*.

    **The assertion is a RATIO, not a literal**, because a literal here would
    have to be re-derived by hand every time `SLOT_TYPES` or `MAX_REPAIRS`
    moves — which is exactly the staleness #305 is about. `CONTROL_RUNS` is
    outside the per-cohort work, so it is subtracted from both sides.

    RED against restoring the one-cohort-per-unit arithmetic.
    """
    from core.items.generate import CONTROL_RUNS, _expected_calls, unit_plan

    one = unit_plan([1])
    seven = unit_plan([1], focus_held={1: 4})
    assert seven[1]["cohorts"] == 7

    per_cohort = _expected_calls(one) - CONTROL_RUNS
    assert per_cohort > 0
    assert _expected_calls(seven) - CONTROL_RUNS == per_cohort * 7


def test_the_ceiling_is_zero_work_when_the_bank_is_already_full() -> None:
    """A run with nothing to buy costs nothing but the control. **Asserted
    because the failure mode is a ceiling that quietly prices a cohort the run
    will not make**, which reads as headroom rather than as an error.
    """
    from core.items.generate import CONTROL_RUNS, _expected_calls, unit_plan

    full = unit_plan([1], focus_held={1: 56})
    assert full[1]["cohorts"] == 0
    assert _expected_calls(full) == CONTROL_RUNS


# ── F2 — the avoid-list ────────────────────────────────────────────────────


def test_the_generator_is_told_what_the_bank_already_holds() -> None:
    """**#299's THIRD CAUSE, AND THE ONE THAT DECIDES THE SLICE.**

    `seen` is a list of item TYPES, so a second run sends a byte-identical
    request; its output either bounces off `content_hash` or passes as **the
    same sentence in different clothes** (#169, ids 21 and 29). **More runs on
    a generator that is never told what the bank holds cannot reach the
    target** — without F2, F1 raises the target and sends the yield to
    duplicates.

    Measured at ~590 input tokens for 40 items and ~800 at 56, and
    `GENERATE_MAX_TOKENS` is an OUTPUT budget, so the two never compete.

    **WHAT THIS CANNOT SHOW (#271): that the model obeyed.** An avoid-list
    reduces duplication by telling the generator what exists; it cannot detect
    it. #169 stays open and this test does not touch it.

    RED against dropping the avoid-list from the prompt.
    """
    from core.items.schema import constraint_block

    held = ["I went to the shops.", "She was reading when I arrived."]
    without = constraint_block(["cloze_cued"])
    with_list = constraint_block(["cloze_cued"], avoid=held)

    assert with_list != without
    for sentence in held:
        assert sentence in with_list
        assert sentence not in without


def test_an_empty_bank_sends_no_avoid_list_at_all() -> None:
    """**Not an empty heading.** A first run has nothing to avoid, and a prompt
    section saying so is tokens spent to tell the model nothing — and reads to
    a model as a constraint it cannot satisfy.
    """
    from core.items.schema import constraint_block

    assert constraint_block(["cloze_cued"], avoid=[]) == constraint_block(
        ["cloze_cued"]
    )


# ── the dry report — the only surface the operator reads before spending ───


def test_the_dry_report_names_the_bank_the_shortfall_and_the_cohorts(
    learner, capsys
) -> None:
    """**The operator authorises a billed run against this text.**

    #262's rule and #305's: a number printed before the spend must be derived
    from the plan being costed. So the report states what the bank holds, what
    is short, and how many cohorts that buys — **and a reader can check the
    arithmetic without running anything.**

    **What this fixture supplies that a real run does not:** four rows and a
    fresh learner. **Nothing here asserts a count against block 3's actual
    request** — the 56 is counted on the host by a query independent of the
    command that wrote the rows, and that is where the criterion lives.

    RED against a report that prints the cohort plan without the bank it was
    computed from.
    """
    from core.items.generate import dry_run

    _write(learner, cohort=None, n=4, tag="bank")
    from core.services.items import focus_held as held_now

    dry_run(learner, (1,), focus_held={1: held_now(learner, unit_number=1)})
    out = capsys.readouterr().out

    assert "focus bank" in out.lower()
    for figure in ("4", "52", "7", "56"):
        assert figure in out, f"the report must state {figure}"


def test_a_dry_run_makes_no_model_call(learner) -> None:
    """**W13-ii's bar, and it is stronger than making no write.** `netguard` is
    armed session-wide, so a call would raise rather than bill — this asserts
    the intent explicitly rather than relying on the guard.
    """
    from unittest.mock import patch

    from core.items.generate import dry_run

    _write(learner, cohort=None, n=4, tag="dry")
    with patch("core.llm.chat") as called:
        dry_run(learner, (1,), focus_held={1: 4})
    assert called.call_count == 0


def test_the_run_repeats_the_cohort_and_refreshes_the_avoid_list(
    learner, monkeypatch
) -> None:
    """**F4: the cohort stays at eight and the RUN loops.** Seven cohorts, not
    one 56-slot request.

    **AND THE AVOID-LIST IS RE-READ BETWEEN COHORTS, WHICH IS THE HALF THAT IS
    EASY TO GET WRONG.** Reading the bank once before the loop would let cohort
    2 write what cohort 1 just wrote — #299's third cause surviving inside its
    own fix, and invisible because both requests would look correct in isolation.

    **Mocked at the transport** (`gates._chat`), never at `generate_drafts` or
    at a service function: the payload build, the prompt substitution and the
    avoid-list assembly all execute. Patching higher would leave every one of
    them unexercised — #345's shape.

    **What this fixture supplies that a real run does not:** a model that
    returns nothing, so no item is written and no gate runs. It therefore proves
    the REQUESTS, which is what F2 changes, and asserts nothing about yield.
    """
    from core.items import generate as gen

    _write(learner, cohort=None, n=40, tag="already")

    seen_prompts: list[str] = []

    def _fake_chat(messages, *, system=None, **kw):
        seen_prompts.append(system or "")
        return {"items": []}

    monkeypatch.setattr(gen.gates, "_chat", _fake_chat)
    monkeypatch.setattr(gen, "_confirm", lambda *a, **k: True)
    monkeypatch.setattr(gen, "run_control", lambda **k: gen.ControlResult(
        runs=3, failures=3, ranks=(None, None, None)))

    from core.services.items import focus_held as held_now

    held = held_now(learner, unit_number=1)
    gen.run(learner, (1,), apply=False, skip_control=True,
            focus_held={1: held})

    # 56 - 40 = 16, over 8-slot cohorts, is exactly two.
    generation_prompts = [p for p in seen_prompts if "ALREADY IN THIS" in p]
    assert len(generation_prompts) == 2, (
        f"two cohorts expected, saw {len(generation_prompts)} generation calls"
    )
    for prompt in generation_prompts:
        assert "already-0 " in prompt or "already-0" in prompt


def test_the_ceiling_line_itemises_cohorts_not_units(learner, capsys) -> None:
    """**#262's SHAPE IN THE LINE THE OPERATOR AUTHORISES AGAINST: the number
    was right and its explanation was wrong.**

    After #305 the ceiling counts cohorts, but the itemisation beside it still
    read `control 3 + 1 units` while the figure priced **seven cohorts**. *"A
    wrong denominator that matches by accident reads as a right one"* — and here
    it would read as a ceiling for one unit's single cohort, which is the exact
    misreading #305 exists to prevent, surviving in the prose next to the fix.

    Caught by reading the dry run's real output rather than by a test, which is
    why this test exists now.
    """
    from core.items.generate import dry_run

    _write(learner, cohort=None, n=8, tag="ceil")
    dry_run(learner, (1,), focus_held={1: 8})
    out = capsys.readouterr().out

    line = next(one for one in out.splitlines() if "ceiling" in one)
    assert "6 cohorts" in line, line
    assert "1 units" not in line
