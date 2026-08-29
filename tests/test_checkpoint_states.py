"""W11's seam: the two writers of `user_unit_state`, and the guards they call.

**THIS FILE IS #219's ANSWER, AND IT IS ONLY AN ANSWER IF THE GUARDS ARE REACHED
THROUGH THE FUNCTIONS THAT ACTUALLY CALL THEM.**

#219 is the eleventh recorded appearance of *a guarantee that was never once
evaluated against the thing it names*: `core.syllabus.states` had no caller
anywhere under `packages/` or `apps/`, so `ALLOWED_TRANSITIONS`, `may_move` and
`may_enter` constrained no write in this system and their tests were tests of a
pure function. Nine of `tests/test_syllabus_states.py`'s seventeen tests still
are, and that is fine -- what was missing is this file.

So every guard test here calls a SERVICE against a real database and asserts the
SERVICE refuses. A test that calls `may_move` directly proves nothing new.

**And the two guards are exercised through DIFFERENT functions**, because an
earlier draft of this slice had `record_checkpoint` call `may_enter` on a no-row
branch that `record_unit_entry` guarantees is never reached -- which would have
been #219's own family arriving inside the fix for it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from core.config import load_settings
from core.services.syllabus import record_checkpoint, record_unit_entry
from core.syllabus import CHECKPOINT_RETAKE_DAYS

NOW = datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row is not None and int(row[0] or 0) >= 18, (
            "run `python -m core.db migrate` — 018 is not applied"
        )
        try:
            yield connection
        finally:
            connection.rollback()


@pytest.fixture
def units_present(conn):
    from core.services.syllabus import upsert_units
    from core.syllabus.content import units

    upsert_units(conn, units())
    return conn


@pytest.fixture
def user_id(conn, units_present):
    row = conn.execute(
        "INSERT INTO users (name, native_language, auth_email, onboarded) "
        "VALUES (%s, %s, %s, TRUE) RETURNING id",
        ("W11 seam fixture", "fa", "w11-seam@example.test"),
    ).fetchone()
    return row[0]


def _state(conn, user_id: int, unit_number: int = 1) -> dict:
    row = conn.execute(
        "SELECT state, passed_at, last_checkpoint_score, checkpoint_attempts, "
        "       retake_due_on, entered_at "
        "  FROM user_unit_state WHERE user_id = %s AND unit_number = %s",
        (user_id, unit_number),
    ).fetchone()
    if row is None:
        return {}
    return {
        "state": row[0],
        "passed_at": row[1],
        "score": row[2],
        "attempts": row[3],
        "retake_due_on": row[4],
        "entered_at": row[5],
    }


# ── the entry write ─────────────────────────────────────────────────────────


def test_record_unit_entry_creates_one_in_progress_row(conn, user_id) -> None:
    assert record_unit_entry(conn, user_id, 1, now=NOW) is True
    assert _state(conn, user_id)["state"] == "in_progress"


def test_record_unit_entry_is_idempotent(conn, user_id) -> None:
    """A read path calls this. A refetch must change nothing.

    Idempotent **by the database** -- 014's `UNIQUE (user_id, unit_number)` plus
    `ON CONFLICT DO NOTHING` -- rather than by a read-then-write, which is the
    same instrument `_get_or_create_daily` relies on and the reason an idempotent
    create-once on a GET is a different thing from an incrementing write on a GET.
    """
    assert record_unit_entry(conn, user_id, 1, now=NOW) is True
    first = _state(conn, user_id)["entered_at"]
    assert record_unit_entry(conn, user_id, 1, now=NOW + timedelta(days=3)) is False
    assert _state(conn, user_id)["entered_at"] == first


def test_may_enter_is_reached_by_the_real_entry_path(conn, user_id, monkeypatch) -> None:
    """**RED WITHOUT THE GUARD CALL.** #219, half one.

    The service is made to attempt a state `may_enter` refuses. If
    `record_unit_entry` did not consult `may_enter` -- if the call were deleted,
    or moved to a branch the real path never reaches -- the INSERT would go
    through, because **migration 014's CHECKs would accept the row**: a first row
    in `passed` satisfies `user_unit_state_a_pass_needs_the_threshold` as long as
    `passed_at` and a score >= 80 are supplied.

    So this asserts the SERVICE refuses, and it is the only thing that can.
    """
    from core.syllabus import states

    monkeypatch.setattr(states, "may_enter", lambda incoming: incoming == "passed")
    with pytest.raises(ValueError, match="may_enter"):
        record_unit_entry(conn, user_id, 1, now=NOW)
    assert _state(conn, user_id) == {}, "no row may exist after a refusal"


# ── the checkpoint write ────────────────────────────────────────────────────


def test_a_pass_marks_the_unit_passed_and_clears_the_retake(conn, user_id) -> None:
    record_unit_entry(conn, user_id, 1, now=NOW)
    assert record_checkpoint(
        conn, user_id, 1, correct=10, item_count=12, now=NOW
    ) == "passed"
    row = _state(conn, user_id)
    assert row["state"] == "passed"
    assert row["passed_at"] is not None
    assert row["score"] == 83
    assert row["attempts"] == 1
    assert row["retake_due_on"] is None


def test_a_failure_leaves_the_unit_in_progress_with_a_retake(conn, user_id) -> None:
    """PRD §3's fail path, in full: `in_progress`, a bumped attempt, a date."""
    record_unit_entry(conn, user_id, 1, now=NOW)
    assert record_checkpoint(
        conn, user_id, 1, correct=9, item_count=12, now=NOW
    ) == "in_progress"
    row = _state(conn, user_id)
    assert row["state"] == "in_progress"
    assert row["passed_at"] is None
    assert row["score"] == 75
    assert row["attempts"] == 1
    assert row["retake_due_on"] == (NOW.date() + timedelta(days=CHECKPOINT_RETAKE_DAYS))


def test_ten_of_twelve_passes_and_nine_does_not(conn, user_id) -> None:
    """The 80% boundary, from both sides, computed rather than hardcoded.

    `pass_mark(12)` is `ceil(12 * 80 / 100)` = 10. Asserted through the writer so
    that a change to either constant moves this test rather than leaving it green
    against a stale literal.
    """
    record_unit_entry(conn, user_id, 1, now=NOW)
    assert record_checkpoint(
        conn, user_id, 1, correct=9, item_count=12, now=NOW
    ) == "in_progress"
    assert record_checkpoint(
        conn, user_id, 1, correct=10, item_count=12, now=NOW
    ) == "passed"


def test_the_retake_date_is_the_learners_local_date_not_the_servers(
    conn, user_id
) -> None:
    """No wall-clock dependency (CLAUDE.md §3 rule 6).

    `now` is INJECTED and both sides of the comparison are computed the same way,
    so this cannot start failing on a calendar boundary -- which is exactly what
    broke `test_vocabulary_due_and_anki` once already. A `CURRENT_DATE + 4` in
    the writer would have made the answer depend on the server's clock instead of
    on the learner's day.
    """
    late = datetime(2026, 9, 5, 23, 30, tzinfo=timezone.utc)
    record_unit_entry(conn, user_id, 1, now=late)
    record_checkpoint(conn, user_id, 1, correct=4, item_count=12, now=late)
    assert _state(conn, user_id)["retake_due_on"] == (
        late.date() + timedelta(days=CHECKPOINT_RETAKE_DAYS)
    )


def test_may_move_is_reached_by_the_real_write_path(conn, user_id) -> None:
    """**RED WITHOUT THE GUARD CALL.** #219, half two, and the sharper half.

    A unit that has been passed is put back through a FAILING checkpoint.
    `ALLOWED_TRANSITIONS["passed"]` is `{passed, mastered}`, so `passed ->
    in_progress` must be refused.

    **THE RED RUN WAS MEASURED RATHER THAN PREDICTED, AND IT CORRECTED THIS
    DOCSTRING AND NOTHING ELSE.** With the guard deleted, the write reached the
    database and was refused there -- by
    `user_unit_state_timestamps_match_the_state`, because THIS writer leaves
    `passed_at` set on the fail path and a row that is `in_progress` with a
    `passed_at` disagrees with itself.

    **W11's PLAN WAS RIGHT ABOUT 014 AND IS QUOTED SO THE CREDIT LANDS ON THE
    RIGHT ARTEFACT.** Its verification section says, verbatim: *"an `UPDATE` from
    `passed` to `in_progress` that nulls `passed_at` -- every CHECK is satisfied
    by the resulting row."* **The probe confirmed exactly that.** The first draft
    of THIS docstring predicted the red run would show the write land, and it was
    the prediction that was wrong -- not the plan's reading of the schema.

    **That is not 014 covering the transition, and the difference is the whole
    point.** Probed directly against the real schema:

        passed -> in_progress, passed_at KEPT   -> refused (CheckViolation)
        passed -> in_progress, passed_at NULLED -> **ACCEPTED**

    A writer that nulled `passed_at` -- which is exactly what a well-meaning
    "reset the unit" would do -- sails through every one of 014's six CHECKs,
    because all of them are ROW-LOCAL and none can see the predecessor row. See
    `test_migration_014_alone_would_permit_un_passing_a_unit` below, which holds
    that limb on its own.

    A `CHECK` cannot express a transition and only a trigger could, which this
    project does not use anywhere. So the Python seam is not the lighter option
    here; it is the only one that covers both limbs, and this test is what proves
    it is reached.
    """
    record_unit_entry(conn, user_id, 1, now=NOW)
    record_checkpoint(conn, user_id, 1, correct=12, item_count=12, now=NOW)
    with pytest.raises(ValueError, match="ALLOWED_TRANSITIONS"):
        record_checkpoint(conn, user_id, 1, correct=3, item_count=12, now=NOW)
    row = _state(conn, user_id)
    assert row["state"] == "passed", "a pass is never undone"
    assert row["passed_at"] is not None


def test_a_checkpoint_on_an_unentered_unit_raises(conn, user_id) -> None:
    """`record_checkpoint` has NO no-row branch, deliberately.

    An earlier draft had it call `may_enter` when it found no row -- a branch
    `record_unit_entry` guarantees is never reached, so #219's guard would have
    been exercised only by a code path that never runs. It raises instead: a
    checkpoint on a unit nobody entered is a bug in the caller, and inventing an
    entry would give `entered_at` a value that is a fact about a moment that
    never happened.
    """
    with pytest.raises(ValueError, match="has no user_unit_state row"):
        record_checkpoint(conn, user_id, 1, correct=10, item_count=12, now=NOW)


def test_migration_014_alone_would_permit_un_passing_a_unit(conn, user_id) -> None:
    """**The limb the service guard exists for, held on its own, in raw SQL.**

    `test_may_move_is_reached_by_the_real_write_path` shows the SERVICE refuses.
    This shows what refuses when the service is not in the way -- **nothing** --
    and it is the evidence that the Python seam is load-bearing rather than
    belt-and-braces.

    Deliberately NOT going through `record_checkpoint`: the point is what the
    database permits, so the database is asked directly. If a later slice ever
    adds a trigger or a transition constraint, this test starts failing and the
    seam decision can be revisited **on evidence** rather than on the comment
    above it.

    A pass is never undone: `passed_at` is the clock mastery is timed from
    (`MASTERY_RETENTION_DAYS`), and a unit that quietly returned to `in_progress`
    would restart that clock with nothing recording that it had.
    """
    conn.execute(
        "INSERT INTO user_unit_state "
        "  (user_id, unit_number, state, passed_at, last_checkpoint_score) "
        "VALUES (%s, 1, 'passed', %s, 90)",
        (user_id, NOW),
    )

    # Limb one: `passed_at` kept. 014 DOES catch this one -- the row would
    # disagree with itself -- and that is why the red run for the test above
    # failed the way it did rather than the way it was predicted to.
    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.transaction():
            conn.execute(
                "UPDATE user_unit_state SET state = 'in_progress' WHERE user_id = %s",
                (user_id,),
            )

    # Limb two: `passed_at` nulled. **014 ACCEPTS IT.** No CHECK is violated,
    # because none of them can see that this row used to say `passed`.
    with conn.transaction():
        conn.execute(
            "UPDATE user_unit_state SET state = 'in_progress', passed_at = NULL "
            " WHERE user_id = %s",
            (user_id,),
        )
    assert _state(conn, user_id)["state"] == "in_progress", (
        "if this now fails, the database has acquired a transition guard and "
        "#219's seam decision should be re-read against it"
    )
