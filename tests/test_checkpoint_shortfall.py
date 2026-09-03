"""W10d commit 1: the generator is told what the bank holds, against the demand
that actually applies.

**#352 IS THE ACCEPTANCE TEST AND IT IS RUN HERE END TO END, DRY.** User 3's
shape: missed set = past continuous + the composite target; retake demand
1/5/5/1; bank 5/4/1/2. **Two targets short, five items missing** — and the bank
holds exactly twelve unattempted rows against a retake that needs exactly
twelve, so **any guard phrased as *are there twelve?* answers yes.**

**NOT ONE OF THESE TESTS MAKES A MODEL CALL.** `tests/support/netguard.py` is
armed session-wide, and the dry path is asserted to send nothing rather than
described as sending nothing.

**WHAT THESE TESTS DO NOT ESTABLISH, STATED RATHER THAN IMPLIED: that a RUN
yields five items.** They establish that five are PLANNED and that the shortfall
is reported whole. **The planner returning five and a run landing five are
different claims** — P4 in the plan is the prediction that covers the second,
and the pooled prior from the two committed journals is composite 2/4 and past
continuous 0/4. **#271's rule underneath both: a guard can refuse a bad draft
and can never show the model understood anything.**
"""

from __future__ import annotations

import secrets
from collections import Counter
from datetime import datetime, timezone

import psycopg
import pytest

from core.config import load_settings
from core.items.generate import shortfall_table, unit_plan

T1 = "past simple: regular and irregular verbs"
T2 = "past continuous for what was going on around it"
T3 = "past simple and past continuous in the same sentence"
T4 = "time linkers: then, after that, a bit later"

#: #352's measured bank, from the host on 2026-09-02.
HELD = {T1: 5, T2: 4, T3: 1, T4: 2}
#: #352's measured missed set, read from `missed_targets` and not inferred.
MISSED = (T2, T3)


def _by_target(slots) -> dict[str, int]:
    return dict(Counter(s.target for s in slots))


# ── the planner, four ways ──────────────────────────────────────────────────


def test_both_arguments_together_plan_exactly_the_five_items_352_needs() -> None:
    """**The acceptance test, and the composition is pinned, not the count.**

    A bare `len(slots) == 5` would pass for the wrong five — five past simple,
    say — which is the failure mode this whole slice is about: the right number
    in the wrong shape (#345).
    """
    plan = unit_plan([1], checkpoint=True, missed={1: MISSED}, held={1: HELD})
    assert _by_target(plan[1]["slots"]) == {T2: 1, T3: 4}


@pytest.mark.parametrize(
    "missed,held,expected",
    [
        (None, None, 12),          # first sitting: the blueprint's twelve
        ({1: MISSED}, None, 12),   # --retake alone: buys twelve to get five
        (None, {1: HELD}, 0),      # --fill alone: blueprint demand is already met
    ],
)
def test_the_three_existing_invocations_are_unchanged(missed, held, expected) -> None:
    """**The regression guard for the ruling.** Permitting a combination must not
    alter what either flag alone means — that is the whole argument for
    permitting it rather than redefining anything."""
    plan = unit_plan([1], checkpoint=True, missed=missed, held=held)
    assert len(plan[1]["slots"]) == expected


def test_fill_alone_generates_nothing_because_the_blueprint_is_already_met() -> None:
    """The 0 above is not an error state and is asserted for what it means: the
    bank meets the FIRST-SITTING demand exactly (5/4/1/2 against 5/4/1/2), which
    is why `--fill` alone could never reach #352."""
    plan = unit_plan([1], checkpoint=True, missed=None, held={1: HELD})
    assert plan[1]["slots"] == ()


# ── the shortfall table: the WHOLE shortfall, never the first ───────────────


def test_the_table_names_every_short_target_and_not_the_first() -> None:
    """**The measured failure this is written against.** `checkpoint_items`
    returns on the first target it cannot fill, so 2026-09-02's log line reported
    a shortfall of ONE against an actual shortfall of FIVE — understating it by
    80%, deterministically rather than by chance. Acting on it would have bought
    one item and left the retake blocked.

    **The selector's early return is NOT changed by this slice.** Refusing a
    cohort whole is what stops a short checkpoint reaching a learner; the defect
    was that its only reader was an `INFO` line.
    """
    rows = shortfall_table({T1: 1, T2: 5, T3: 5, T4: 1}, HELD, HELD)
    short = {r.target: r.short for r in rows if r.short}
    assert short == {T2: 1, T3: 4}, "both short targets, or the table is a log line"


def test_the_table_reports_every_target_including_the_satisfied_ones() -> None:
    """A table that listed only the shortfalls could not show that the other two
    targets were checked. The positive control is the row, not a comment."""
    rows = shortfall_table({T1: 1, T2: 5, T3: 5, T4: 1}, HELD, HELD)
    assert [r.target for r in rows] == [T1, T2, T3, T4]
    assert [(r.demand, r.servable, r.short) for r in rows] == [
        (1, 5, 0), (5, 4, 1), (5, 1, 4), (1, 2, 0)
    ]


def test_the_totals_are_the_trap_352_describes() -> None:
    """**Twelve held, twelve demanded, five missing.** The right number in the
    wrong shape — so any guard phrased as *are there twelve?* answers yes while
    the sitting cannot be filled."""
    rows = shortfall_table({T1: 1, T2: 5, T3: 5, T4: 1}, HELD, HELD)
    assert sum(r.demand for r in rows) == 12
    assert sum(r.servable for r in rows) == 12
    assert sum(r.short for r in rows) == 5


def test_a_row_hidden_by_validator_version_is_visible_in_the_table() -> None:
    """**Both counts, and this is why the query needed two columns.**

    On 2026-09-02 `servable_unattempted` equalled `unattempted_any_version` on
    every row, so nothing was hidden — **an evidenced negative, not an absence of
    a question.** A generator counting rows the code cannot serve buys the wrong
    number, and the two figures are the only way to tell a generation shortfall
    from a re-validation one. **They have completely different fixes.**
    """
    rows = shortfall_table({T3: 5}, {T3: 1}, {T3: 3})
    row = rows[0]
    assert (row.servable, row.any_version, row.short) == (1, 3, 4)
    assert row.stale == 2, "two rows exist that the selector cannot serve"


def test_the_table_never_reports_a_negative_shortfall() -> None:
    """A re-weighted retake can want FEWER of a target than a first sitting
    bought — `_shortfall_slots` clamps at zero rather than raising, and the
    report must agree with it."""
    rows = shortfall_table({T1: 1}, {T1: 5}, {T1: 5})
    assert rows[0].short == 0


# ── the worst-case exposure line (§4.2) ────────────────────────────────────


def test_the_exposure_line_names_the_class_352_generalises() -> None:
    """**#352's generalisation, printed before it is met rather than after.**

    A retake that misses a low-allocation target is unfillable from a bank built
    to the blueprint: the composite target's allocation is 1 and `quota_map`
    re-weights a missed target to 5. **Measured, reported, never enforced**
    (#197's shape) — this slice does not buy a bigger bank.
    """
    from core.items.generate import worst_case_exposure

    rows = worst_case_exposure(1)
    by = {r.target: r for r in rows}
    assert by[T3].allocation == 1
    assert by[T3].worst_case == 5
    assert by[T3].gap == 4
    # The positive control: a well-allocated target has a small gap, so the 4
    # above is this target's property and not the function's.
    assert by[T1].allocation == 5
    assert by[T1].gap == 0


# ── through the real entry point, dry ───────────────────────────────────────


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def learner(db):
    row = db.execute(
        "INSERT INTO users (name, native_language, auth_email, onboarded, timezone) "
        "VALUES ('w10d', 'lt', %s, TRUE, 'Europe/Vilnius') RETURNING id",
        (f"w10d-{secrets.token_hex(6)}@example.invalid",),
    ).fetchone()
    user_id = int(row[0])
    db.commit()
    try:
        yield user_id
    finally:
        # #340: `items`, `item_attempts` and `sessions` are all user-keyed, so
        # the convention reaches them. Nothing here writes a global table.
        db.execute("DELETE FROM item_attempts WHERE user_id = %s", (user_id,))
        db.execute("DELETE FROM items WHERE user_id = %s", (user_id,))
        db.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.commit()


def _bank(db, learner: int, per_target: dict[str, int]) -> None:
    """Checkpoint stock through the real writer, cohort-tagged."""
    from core.items.gates import ValidationReport
    from core.items.schema import parse
    from core.services import items as items_svc

    for target, count in per_target.items():
        for _ in range(count):
            item_id = items_svc.insert_item(
                learner,
                parse({
                    "item_type": "cloze_cued",
                    "track": "life",
                    "prompt_text": f"I ___ there last year. {secrets.token_hex(5)}",
                    "answer": "went",
                    "accepted_variants": ["went"],
                    "unit_number": 1,
                    "grammar_target": target,
                    "explanation": "Past simple, because the time is finished.",
                    "definition": "past of go",
                    "l1_gloss": "nuvykau",
                    "cohort": "checkpoint",
                }),
                ValidationReport("passed", acceptable=("went",), canonical="went"),
                model="test-model",
            )
            assert item_id is not None
    db.commit()


def test_a_failed_sitting_plus_a_bank_plans_five_through_main(
    db, learner, capsys
) -> None:
    """**#352, end to end, through `main` with no `--live` and no `--apply`.**

    Two flags the parser refused until this commit, on a real database, with a
    real failed sitting and a real bank. **Nothing is sent and nothing is
    written** — the netguard is armed and this asserts the exit code of a dry
    run, not a description of one.

    **THE FIXTURE IS TWENTY-FOUR ROWS, NOT TWELVE, AND THE FIRST DRAFT OF IT WAS
    WRONG IN A WAY WORTH KEEPING.** It seeded twelve and then attempted two of
    them to build the failed sitting — which CONSUMED two of the twelve, because
    `checkpoint_held` counts UNATTEMPTED rows. The report then correctly said
    *7 short* against a bank of 10. **The code was right and the fixture modelled
    a state that has never existed.**

    #352's real shape is the one this now builds: **a sat sitting of twelve
    (attempted, and therefore invisible to `checkpoint_held`) plus twelve
    unattempted rows in the 5/4/1/2 shape** — 24 rows in unit 1, which is what
    the host reported. **The sitting's twelve are what makes the remainder
    5/4/1/2 rather than the blueprint's own allocation.**
    """
    from core.items.generate import main

    # The SAT sitting: twelve items in the blueprint's shape, all attempted.
    sat = {T1: 5, T2: 4, T3: 1, T4: 2}
    _bank(db, learner, sat)
    row = db.execute(
        "INSERT INTO sessions (user_id, date, task_type, completed, payload) "
        "VALUES (%s, CURRENT_DATE, 'checkpoint', TRUE, "
        "        '{\"unit_number\": 1, \"passed\": \"false\"}'::jsonb) RETURNING id",
        (learner,),
    ).fetchone()
    session_id = int(row[0])
    for item in db.execute(
        "SELECT id, payload ->> 'grammar_target' FROM items WHERE user_id = %s",
        (learner,),
    ).fetchall():
        db.execute(
            "INSERT INTO item_attempts (user_id, item_id, session_id, correct, "
            "graded_by) VALUES (%s, %s, %s, %s, 'deterministic')",
            (learner, int(item[0]), session_id, item[1] not in MISSED),
        )
    db.commit()

    # The REMAINDER: twelve unattempted rows, which is what the host read.
    _bank(db, learner, HELD)

    from core.services.items import checkpoint_held
    assert checkpoint_held(learner, unit_number=1) == HELD, (
        "the fixture does not reproduce #352's measured bank"
    )

    code = main([
        "--user", str(learner), "--units", "1", "--checkpoint", "--retake", "--fill",
    ])
    assert code == 0
    out = capsys.readouterr().out

    # The positive control first: the dry run really ran and reached the plan.
    assert "dry run — nothing was sent and nothing was written." in out
    # **Both short targets, with their own numbers — never just the first.**
    assert "2  past continuous" not in out, "past continuous is short by ONE"
    assert "1  past continuous for what was going on around it  <-- SHORT" in out
    assert "4  past simple and past continuous in the same sentence  <-- SHORT" in out
    assert "** 5 items short across 2 target(s). Held 12, demanded 12. **" in out
    # #352's trap, printed: the right number in the wrong shape.
    assert "the right NUMBER in the wrong SHAPE" in out
    # §4.2's exposure line, reported and never enforced.
    assert "worst-case retake exposure (reported, never enforced)" in out


def test_retake_without_a_failed_sitting_is_still_refused_with_fill(
    db, learner
) -> None:
    """**The refusal that must NOT be deleted alongside the one that was.**

    `--retake` on a unit with no failed sitting is a first sitting, and that
    error has to keep firing when `--fill` is present — deleting one
    `parser.error` next to another is exactly how the second one goes with it.
    """
    from core.items.generate import main

    with pytest.raises(SystemExit):
        main([
            "--user", str(learner), "--units", "1", "--checkpoint",
            "--retake", "--fill",
        ])


def test_fill_without_checkpoint_is_still_refused(db, learner) -> None:
    from core.items.generate import main

    with pytest.raises(SystemExit):
        main(["--user", str(learner), "--units", "1", "--fill"])
