"""The reserve and the selector, against a real database.

**Two tests here would have caught defects that reached plan review three times
each**, and both are written so that they go RED against the mechanism that was
wrong rather than only green against the one that shipped:

* `test_a_later_top_up_run_does_not_move_the_reserve` -- red under a
  `created_at DESC LIMIT 12` reserve;
* `test_a_reweighted_retake_cohort_is_selected_whole` -- red under a selector
  that fills the blueprint's `per_target`.
"""

from __future__ import annotations

import psycopg
import pytest

from core.config import load_settings
from core.items.gates import ValidationReport
from core.items.grading import normalise_variants
from core.items.schema import parse
from core.services import items as svc
from core.syllabus.checkpoint import quota_map

PASSED = ValidationReport("passed")

UNIT_1 = {
    "past simple: regular and irregular verbs": 4,
    "past continuous for what was going on around it": 3,
    "past simple and past continuous in the same sentence": 3,
    "time linkers: then, after that, a bit later": 2,
}
T1, T2, T3, T4 = list(UNIT_1)


@pytest.fixture
def learner():
    with psycopg.connect(load_settings().database_url, autocommit=True) as conn:
        row = conn.execute(
            "INSERT INTO users (name, native_language, auth_email, onboarded) "
            "VALUES ('w11-selector', 'fa', 'w11-selector@example.invalid', TRUE) "
            "RETURNING id"
        ).fetchone()
        user_id = int(row[0])
        try:
            yield user_id
        finally:
            conn.execute("DELETE FROM users WHERE id = %s", (user_id,))


def _write(learner: int, *, target: str, cohort: str | None, n: int, tag: str):
    """`n` items on one target, in one cohort. Distinct stems, so no hash clash."""
    made = []
    for index in range(n):
        raw = {
            "item_type": "cloze_cued",
            "track": "life",
            "prompt_text": f"{tag}-{target[:12]}-{index} I ___ to the shops.",
            "answer": "went",
            "unit_number": 1,
            "grammar_target": target,
        }
        if cohort is not None:
            raw["cohort"] = cohort
        raw["accepted_variants"] = normalise_variants(raw["answer"])
        made.append(svc.insert_item(learner, parse(raw), PASSED, model="test-model"))
    return made


def _cohort(learner: int, cohort: str | None, tag: str):
    for target, count in UNIT_1.items():
        _write(learner, target=target, cohort=cohort, n=count, tag=tag)



def _write_stale(learner: int, *, target: str, cohort: str, n: int, tag: str):
    """Rows validated by an older gate. `_CURRENT_VALIDATOR` excludes them."""
    made = _write(learner, target=target, cohort=cohort, n=n, tag=tag)
    with psycopg.connect(load_settings().database_url, autocommit=True) as conn:
        conn.execute(
            "UPDATE items SET validator_version = validator_version - 1 "
            " WHERE id = ANY(%s)",
            (list(made),),
        )
    return made

def _attempt(learner: int, item_id: int) -> None:
    with psycopg.connect(load_settings().database_url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO item_attempts (user_id, item_id, correct, graded_by) "
            "VALUES (%s, %s, TRUE, 'deterministic')",
            (learner, item_id),
        )


# ── the reserve ─────────────────────────────────────────────────────────────


def test_block_three_does_not_serve_the_checkpoint_cohort(learner) -> None:
    """`focus_items` orders unattempted items FIRST, so without the exclusion a
    checkpoint cohort generated on Friday is exactly what block 3 reaches for."""
    _cohort(learner, "focus", "focus")
    _cohort(learner, "checkpoint", "cp")
    served = svc.focus_items(learner, unit_number=1, limit=20)
    assert len(served) == 12, "block 3 should see the focus cohort and nothing else"


def test_block_three_distinguishes_legacy_from_focus_from_checkpoint(learner) -> None:
    """**The fourteen live rows carry no `cohort` key**, because they were
    written by the 8-slot block-3 run before this field existed. *Absent means
    focus* is what they ARE, not a default chosen for convenience -- so there is
    no data pass and no backfill.

    **THIS TEST ASSERTED A COUNT UNTIL 2026-08-29 AND COULD NOT SEE #260.** It
    read `_write(cohort=None, n=3)` then `assert len(focus_items(...)) == 3` --
    three in, three out -- so **three different states collapsed onto one
    assertion**: a legacy row (`None`), a real block-3 row (`"focus"`), and a
    CHECKPOINT row mislabelled `"focus"` by the top-up re-index. Production item
    id 28 was the third, and this test would have passed with it in the bank.

    **#256's family, the second sighting inside this file** -- test 14 counted
    twelve instead of naming which twelve. **A selector test must assert WHICH
    rows came back.** So this one writes all three states at once and asserts on
    ids: a count could not tell them apart even in principle, because the wrong
    answer has the same cardinality as the right one.
    """
    legacy = _write(learner, target=T1, cohort=None, n=2, tag="legacy")
    focus = _write(learner, target=T1, cohort="focus", n=2, tag="focus")
    reserved = _write(learner, target=T1, cohort="checkpoint", n=2, tag="cp")

    served = {one.id for one in svc.focus_items(learner, unit_number=1, limit=20)}
    assert served == set(legacy) | set(focus), (
        "block 3 serves the legacy rows and the declared block-3 rows"
    )
    assert served.isdisjoint(reserved), (
        "and never a checkpoint row -- the assertion id 28 needed"
    )


def test_the_reserve_yields_rather_than_leaving_block_three_empty(learner) -> None:
    """**The precedence rule: daily practice beats a weekly checkpoint.**

    A learner with an empty block 3 has lost their day; a learner with no
    checkpoint has lost a Saturday, and only one of those is recoverable. So when
    withholding would empty block 3, the reserve yields -- and the checkpoint
    then refuses LOUDLY, on a not-ready surface, rather than the session failing
    silently.
    """
    _cohort(learner, "checkpoint", "cp")
    assert len(svc.focus_items(learner, unit_number=1, limit=20)) == 12


def test_a_sat_checkpoint_becomes_ordinary_practice_stock(learner) -> None:
    """Release condition one, and nothing has to remember to apply it: the
    exclusion is over UNATTEMPTED rows, so a sat cohort simply falls out of it."""
    _write(learner, target=T1, cohort="focus", n=2, tag="focus")
    made = _write(learner, target=T1, cohort="checkpoint", n=2, tag="cp")
    assert len(svc.focus_items(learner, unit_number=1, limit=20)) == 2
    for item_id in made:
        _attempt(learner, item_id)
    assert len(svc.focus_items(learner, unit_number=1, limit=20)) == 4


def test_a_later_top_up_run_does_not_move_the_reserve(learner) -> None:
    """**RED UNDER A RECENCY RESERVE.** The test that discriminates the two
    mechanisms, and the reason the declared cohort replaced the proxy.

    A unit needs 8 + 12 = 20 unattempted items, so there are TWO generation runs.
    Run the checkpoint cohort FIRST and a block-3 top-up SECOND, and the newest
    twelve are *eight top-up items plus four of the checkpoint's twelve*.

    Under `created_at DESC LIMIT 12` the reserve then withholds items block 3 was
    generated for and hands block 3 eight of the checkpoint's -- which
    `checkpoint_items` finds on Saturday. **It does not fail loudly; it silently
    protects the wrong rows.** Under the declared cohort it cannot happen at all.
    """
    checkpoint_ids = set()
    for target, count in UNIT_1.items():
        checkpoint_ids.update(
            _write(learner, target=target, cohort="checkpoint", n=count, tag="cp")
        )
    focus_ids = set()
    for target, count in UNIT_1.items():
        focus_ids.update(
            _write(learner, target=target, cohort="focus", n=count, tag="later")
        )

    # **ASSERTED ON IDENTITY, NOT ON COUNT, and the first draft of this test got
    # that wrong in the same way the mechanism it tests did.** Counting passes
    # under recency: the selector returns the twelve TOP-UP items and block 3
    # returns the twelve CHECKPOINT ones -- twelve each, both wrong, both green.
    # A test that cannot see which rows it got cannot see this defect at all.
    chosen = svc.checkpoint_items(learner, unit_number=1, quotas=quota_map(UNIT_1))
    assert {one.id for one in chosen} == checkpoint_ids
    assert {one.id for one in svc.focus_items(learner, unit_number=1, limit=20)} == (
        focus_ids
    )


# ── the selector ────────────────────────────────────────────────────────────


def test_a_first_sitting_is_selected_in_the_blueprints_proportions(learner) -> None:
    _cohort(learner, "checkpoint", "cp")
    chosen = svc.checkpoint_items(learner, unit_number=1, quotas=quota_map(UNIT_1))
    assert len(chosen) == 12


def test_a_reweighted_retake_cohort_is_selected_whole(learner) -> None:
    """**RED UNDER A SELECTOR THAT FILLS `per_target`.** The fail path's own test.

    A retake cohort is built to the RE-WEIGHTED map, not the blueprint's. A
    selector demanding 4/3/3/2 cannot fill itself from a 3/3/2/4 cohort, so it
    would return nothing and **the retake would never open** -- and the retake is
    half of what W11 promises.

    Both sides call `quota_map`, so they cannot disagree about what a sitting is
    made of. That is the fix: one producer, two callers.
    """
    quotas = quota_map(UNIT_1, [T4])
    assert quotas != UNIT_1, "this test is vacuous if the retake is not re-weighted"
    for target, count in quotas.items():
        _write(learner, target=target, cohort="checkpoint", n=count, tag="retake")
    chosen = svc.checkpoint_items(learner, unit_number=1, quotas=quotas)
    assert len(chosen) == 12


def test_a_cohort_that_does_not_match_its_own_plan_is_refused(learner) -> None:
    """Refused WHOLE, never partially served.

    Without this, the test above passes on a selector that simply takes any
    twelve -- and a stale cohort would be served as if it were this week's.
    """
    quotas = quota_map(UNIT_1)
    for target, count in quotas.items():
        _write(learner, target=target, cohort="checkpoint", n=count, tag="short")
    short = dict(quotas)
    short[T4] += 1  # one more than the bank holds for that target
    short[T1] -= 1
    assert svc.checkpoint_items(learner, unit_number=1, quotas=short) == []


def test_a_short_bank_yields_no_checkpoint_rather_than_a_short_one(learner) -> None:
    """CLAUDE.md §3 rule 7: the acceptance bar is never quietly lowered.

    Eleven items is not a checkpoint with one missing; it is a different
    instrument. The number short is the generator's to report, never padded here.
    """
    _write(learner, target=T1, cohort="checkpoint", n=3, tag="cp")
    assert svc.checkpoint_items(learner, unit_number=1, quotas=quota_map(UNIT_1)) == []


def test_a_checkpoint_never_serves_an_item_this_learner_has_attempted(learner) -> None:
    _cohort(learner, "checkpoint", "cp")
    made = _write(learner, target=T1, cohort="checkpoint", n=1, tag="extra")
    _attempt(learner, made[0])
    chosen = svc.checkpoint_items(learner, unit_number=1, quotas=quota_map(UNIT_1))
    assert len(chosen) == 12
    assert made[0] not in {one.id for one in chosen}


# ── the counter and the selector must not drift apart ───────────────────────


def test_checkpoint_held_cannot_diverge_from_checkpoint_items(learner) -> None:
    """**`--fill` subtracts what `checkpoint_held` counts, so it must count
    exactly what `checkpoint_items` would serve.**

    Sharing `_COHORT` and `_UNATTEMPTED` separately was the earlier shape and it
    is the weaker one: nothing stops a clause being added to one caller and not
    the other, and the symptom would be silent — `--fill` plans against a set the
    selector refuses, so the generator reports the bank full while the checkpoint
    never becomes ready.

    So both compose from ONE constant, `_CHECKPOINT_STOCK`, and this test drives
    the property rather than the constant: **an item `checkpoint_items` would
    refuse must not be counted as held.** Three refusable rows, one of each kind
    the predicate excludes.

    Demonstrated red by giving `checkpoint_held` its own copy of the filter.
    """
    ok = _write(learner, target=T1, cohort="checkpoint", n=2, tag="ok")

    # (1) attempted -- the reserve is unattempted rows only.
    sat = _write(learner, target=T1, cohort="checkpoint", n=1, tag="sat")
    _attempt(learner, sat[0])

    # (2) the wrong cohort entirely.
    _write(learner, target=T1, cohort="focus", n=3, tag="focus")

    # (3) a stale validator version -- never servable.
    _write_stale(learner, target=T1, cohort="checkpoint", n=2, tag="stale")

    held = svc.checkpoint_held(learner, unit_number=1)
    servable = svc.checkpoint_items(learner, unit_number=1, quotas={T1: 2})

    assert held.get(T1) == 2, (
        "only the two rows the selector can actually serve are held"
    )
    assert len(servable) == 2
    assert {one.id for one in servable} == set(ok)
    # The property, stated so a future filter added to one side breaks this:
    assert held.get(T1) == len(
        svc.checkpoint_items(learner, unit_number=1, quotas={T1: held.get(T1, 0)})
    ), "held must equal what the selector will serve at that quota"
