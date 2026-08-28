"""The journal, and the test that was missing: **a report must describe its run.**

**Nothing checked this, and a run's own evidence was destroyed by a mechanism
built to prevent a different loss.** `read_journal` kept the last write per
UNIT -- deliberately, so a stage-2 run could not clobber stage 1 -- and within a
unit it discarded every attempt but the last. On stage 1, attempt 2 reached C2
and was rejected on three named sentences; attempt 3 died at the free checks.
`--report` described attempt 3 and said C1, C2 and the negative control had never
been evaluated. **All three were false as descriptions of the run.**

The C2 rankings that would settle #228 were the casualty: never printed at the
terminal, and `run` journaled once per unit with the final Outcome, so they never
reached disk at all.

Every test here drives a journal through a REAL round trip -- written by the same
functions the live run uses, read back by `read_journal` -- and asserts the
report can still see what happened. The expected values are hand-written, never
derived from the functions under test (rule 5).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.lessons.generate import (
    ControlResult,
    Journal,
    Outcome,
    attempts_of,
    control_of,
    final_attempts,
    print_verdicts,
    read_journal,
)


def _attempt(unit: int, attempt: int, state: str, stage: str | None, **over) -> Outcome:
    out = Outcome(unit=unit, attempt=attempt, state=state, stage=stage)
    for key, value in over.items():
        setattr(out, key, value)
    return out


C2_ROW = {
    "sentence": "I was cooking dinner when the phone rang.",
    "target": "past continuous for what was going on around it",
    "ranking": [
        "past simple and past continuous in the same sentence",
        "past continuous for what was going on around it",
    ],
    "claimed_rank": 2,
    "first": "past simple and past continuous in the same sentence",
    "runner_up": "past continuous for what was going on around it",
    "confidence": "low",
    "ok": False,
}


@pytest.fixture
def journal(tmp_path: Path) -> Journal:
    return Journal(tmp_path / "j.jsonl")


# ── the defect, as a test ───────────────────────────────────────────────────


def test_an_earlier_attempt_survives_a_later_one(journal) -> None:
    """**THE DEFECT. Attempt 3 used to erase attempt 2 entirely.**

    The attempt worth keeping is the one that got FURTHEST, and it is never
    guaranteed to be the last: a regeneration can fail earlier and more cheaply
    than the attempt before it.
    """
    journal.record([_attempt(1, 2, "rejected", "structure", example_verdicts=[C2_ROW])])
    journal.record([_attempt(1, 3, "rejected", "deterministic")])

    rows = read_journal(journal.path)
    assert len(attempts_of(rows)) == 2, "an attempt was discarded"

    reached_c2 = [r for r in attempts_of(rows) if r.get("examples")]
    assert len(reached_c2) == 1
    assert reached_c2[0]["attempt"] == 2


def test_the_c2_rankings_survive_to_the_report(journal) -> None:
    """The datum #228 turns on, and the one the run destroyed.

    A rejection that names a sentence without naming what it was mistaken for
    cannot be diagnosed. The ranking, the claimed rank and the runner-up all
    have to reach disk.
    """
    journal.record([_attempt(1, 2, "rejected", "structure", example_verdicts=[C2_ROW])])
    journal.record([_attempt(1, 3, "rejected", "deterministic")])

    found = [
        v
        for r in attempts_of(read_journal(journal.path))
        for v in (r.get("examples") or [])
    ]
    assert len(found) == 1
    assert found[0]["claimed_rank"] == 2
    assert found[0]["first"] == (
        "past simple and past continuous in the same sentence"
    )
    assert found[0]["runner_up"] == (
        "past continuous for what was going on around it"
    )


def test_a_passed_control_is_not_reported_as_never_asked(journal, capsys) -> None:
    """**`--report` read `NOT EVALUATED` over a control that refused 3 of 3.**

    That is the single result which makes every other result in a run mean
    anything, and it was printed live and then lost.
    """
    control = ControlResult(
        runs=3, failures=3, ranks=(2, 2, 3),
        verdicts=({"claimed_rank": 2, "first": "past simple: regular and "
                                               "irregular verbs",
                   "runner_up": None, "ranking": [], "confidence": "high",
                   "ok": False},) * 3,
    )
    journal.record_control(control)
    journal.record([_attempt(1, 1, "rejected", "deterministic")])

    rows = read_journal(journal.path)
    recovered = control_of(rows)
    assert recovered is not None
    assert (recovered.failures, recovered.runs) == (3, 3)
    assert recovered.ok

    # And the report, built from disk alone, must say so.
    print_verdicts(rows, None)
    out = capsys.readouterr().out
    assert "L6 negative control: 3 of 3 refused" in out
    assert "NOT EVALUATED — the control was skipped" not in out


def test_a_skipped_control_still_reports_as_not_evaluated(journal, capsys) -> None:
    """The other direction. `--skip-control` must not look like a pass."""
    journal.record([_attempt(1, 1, "rejected", "deterministic")])
    print_verdicts(read_journal(journal.path), None)
    assert "NOT EVALUATED" in capsys.readouterr().out


# ── the guarantee the original design was protecting ────────────────────────


def test_stage_two_still_cannot_clobber_stage_one(journal) -> None:
    """The loss the per-unit key existed to prevent. It still cannot happen.

    Fixing one loss must not reintroduce the other -- which is the shape this
    whole row is about.
    """
    journal.record([_attempt(1, 1, "accepted", None, diagram_count=3)])
    journal.record([_attempt(9, 1, "accepted", None, diagram_count=2)])
    journal.record([_attempt(20, 1, "rejected", "structure")])

    finals = {r["unit"]: r for r in final_attempts(read_journal(journal.path))}
    assert set(finals) == {1, 9, 20}
    assert finals[1]["state"] == "accepted"
    assert finals[9]["diagram_count"] == 2


def test_a_re_run_of_one_unit_replaces_that_units_attempt(journal) -> None:
    """`(unit, attempt)` deduplicates, so a repeated run is not double-counted."""
    journal.record([_attempt(1, 1, "rejected", "structure")])
    journal.record([_attempt(1, 1, "accepted", None, diagram_count=4)])

    rows = attempts_of(read_journal(journal.path))
    assert len(rows) == 1
    assert rows[0]["state"] == "accepted"


def test_the_final_attempt_is_the_lesson_the_unit_ended_up_as(journal) -> None:
    journal.record([_attempt(1, 1, "rejected", "structure")])
    journal.record([_attempt(1, 2, "accepted", None, diagram_count=4)])
    finals = final_attempts(read_journal(journal.path))
    assert len(finals) == 1
    assert finals[0]["attempt"] == 2 and finals[0]["state"] == "accepted"


# ── the report against the run ──────────────────────────────────────────────


def test_a_gate_exercised_on_an_earlier_attempt_is_not_reported_unasked(
    journal, capsys
) -> None:
    """**The false line, as a test.** C2 ran; the report said it never did.

    Gate axes count every attempt, because a gate that ran on attempt 2 WAS
    exercised whether or not attempt 3 reached it. Per-lesson axes read the
    final attempt. Conflating the two is what made the report false.
    """
    journal.record([_attempt(1, 2, "rejected", "structure", example_verdicts=[C2_ROW])])
    journal.record([_attempt(1, 3, "rejected", "deterministic")])

    print_verdicts(read_journal(journal.path), None)
    out = capsys.readouterr().out

    c3_line = next(line for line in out.splitlines() if "L3 examples" in line)
    assert "NOT EVALUATED" not in c3_line, (
        "C2 ran on attempt 2 and the report says it was never asked"
    )
    assert "1 of 1" in c3_line


def test_the_outcome_line_still_says_the_run_produced_nothing(
    journal, capsys
) -> None:
    journal.record([_attempt(1, 3, "rejected", "deterministic")])
    print_verdicts(read_journal(journal.path), None)
    out = capsys.readouterr().out
    assert "0 of 1 lesson(s) SHIPPABLE" in out
    assert "THE RUN PRODUCED NOTHING" in out


def test_l8_prints_a_mean_and_not_a_fraction(journal, capsys) -> None:
    """`2 of 1` read as two out of one. A mean is not a fraction."""
    journal.record([_attempt(1, 1, "rejected", "deterministic", diagram_count=2)])
    print_verdicts(read_journal(journal.path), None)
    out = capsys.readouterr().out
    assert "mean 2.0 across 1 lesson(s)" in out
    assert "L8 diagrams per lesson (mean): 2 of 1" not in out


def test_every_journal_row_is_valid_json_on_one_line(journal) -> None:
    """`--report` reads it line by line; a wrapped row loses the whole run."""
    journal.record([_attempt(1, 1, "rejected", "structure", example_verdicts=[C2_ROW])])
    journal.record_control(ControlResult(runs=3, failures=3, ranks=(2, 2, 2)))
    for line in journal.path.read_text(encoding="utf-8").splitlines():
        assert json.loads(line)


def test_a_journal_from_before_the_kind_field_still_reads(tmp_path) -> None:
    """Rows written by the shipped version carry no `kind`. They are attempts.

    The stage-1 journal on the host is one of these, and it must not become
    unreadable because the format moved.
    """
    path = tmp_path / "old.jsonl"
    path.write_text(
        json.dumps({"unit": 1, "attempt": 3, "state": "rejected",
                    "stage": "deterministic", "diagram_count": 2}) + "\n",
        encoding="utf-8",
    )
    rows = read_journal(path)
    assert len(attempts_of(rows)) == 1
    assert control_of(rows) is None
