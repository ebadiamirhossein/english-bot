"""The run's record survives the run. **A class of defect, not a bug.**

W10c lost its diagnostics twice for two unrelated reasons. Attempt 3 was piped
through `tail -60` and the per-slot rejection codes were cut. Attempt 4 crashed
inside `_top_up`, and the traceback ended the process before `_print_items` ever
ran. **Both times the report depended on the run surviving, and both times the
cheapest information in the slice was the thing destroyed — after the model
calls that produced it had already been paid for.**

Fixing either symptom leaves the class alone. So outcomes are written to disk as
each cohort is decided, and every report is a view of that file.
"""

from __future__ import annotations

import json

import pytest

from core.items import gates
from core.items.generate import (
    ITEMS_PER_UNIT,
    Journal,
    Outcome,
    Slot,
    journal_line,
    read_journal,
    report_only,
    run,
    tally_of,
)

UNIT_1 = (
    "past simple: regular and irregular verbs",
    "past continuous for what was going on around it",
    "past simple and past continuous in the same sentence",
    "time linkers: then, after that, a bit later",
)


def _outcome(slot_index=0, state="discarded", stage="generation", codes=("schema_error: x",)):
    return Outcome(
        slot=Slot(index=slot_index, item_type="mcq", target=UNIT_1[0], cohort="focus"),
        unit_number=1, state=state, stage=stage, codes=codes,
    )


# ── the file is written as the run goes ─────────────────────────────────────


def test_a_cohort_is_on_disk_before_anything_downstream_can_fail(tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    journal.record([_outcome(i) for i in range(ITEMS_PER_UNIT)])
    assert len(read_journal(journal.path)) == ITEMS_PER_UNIT


def test_every_write_is_flushed(tmp_path):
    """A buffered journal is the same defect with a smaller window.

    The process dies and the cohort still in the buffer is the one it was
    working on — which is the interesting one.
    """
    journal = Journal(tmp_path / "j.jsonl")
    journal.record([_outcome(0)])
    # Read through a separate handle, without closing anything.
    assert (tmp_path / "j.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_a_topped_up_slot_reads_back_as_its_replacement(tmp_path):
    """Last write per (unit, slot) wins, by file position and not by clock."""
    journal = Journal(tmp_path / "j.jsonl")
    journal.record([_outcome(0, state="discarded", stage="probe")])
    replacement = _outcome(0, state="accepted", stage=None, codes=())
    replacement.topped_up = True
    journal.record([replacement])

    rows = read_journal(journal.path)
    assert len(rows) == 1, "the slot appeared twice in the rebuilt report"
    assert rows[0]["state"] == "accepted"
    assert rows[0]["topped_up"] is True


def test_the_line_carries_everything_the_report_needs(tmp_path):
    """The file is the record, not a summary beside one.

    If a field the report renders is missing here, `--report` is lossy and this
    is a log rather than a record.
    """
    line = journal_line(_outcome())
    for key in (
        "unit", "slot", "item_type", "target", "state", "stage", "codes",
        "topped_up", "item", "validation", "target_rank", "target_first",
        "target_runner_up", "target_confidence", "coverage_pct",
        "coverage_unknown", "back_translation",
    ):
        assert key in line, f"{key} would not survive to --report"
    json.dumps(line, ensure_ascii=False)  # must be serialisable as written


# ── the accounting is recomputable from disk ────────────────────────────────


def test_the_accounting_is_computed_from_rows_not_from_memory():
    """`Tally.add` takes a journal ROW.

    Taking an `Outcome` would leave a second path that only works while the
    process is alive, and the two would drift the first time one gained a field.
    """
    rows = [
        journal_line(_outcome(0, state="accepted", stage=None, codes=())),
        journal_line(_outcome(1, state="discarded", stage="judge", codes=("unnatural",))),
        journal_line(_outcome(2, state="duplicate", stage=None, codes=())),
    ]
    tally = tally_of(rows)
    assert (tally.drafted, tally.accepted, tally.discarded, tally.duplicate) == (3, 1, 1, 1)
    assert tally.balances
    assert tally.by_stage["judge"] == 1


def test_report_only_rebuilds_everything_and_makes_no_calls(tmp_path, capsys, monkeypatch):
    """The proof that the file is the record.

    `netguard` is armed session-wide, so a call would raise — and every gate seam
    is additionally booby-trapped here, so a rebuild that reached one fails
    loudly rather than passing for the wrong reason.
    """
    def _boom(*a, **k):  # pragma: no cover - must not be reached
        raise AssertionError("--report made a model call")

    for name in ("judge_naturalness", "probe_acceptable", "probe_target",
                 "back_translate", "_chat"):
        monkeypatch.setattr(gates, name, _boom)

    journal = Journal(tmp_path / "j.jsonl")
    journal.record([
        _outcome(0, state="accepted", stage=None, codes=()),
        _outcome(1, state="discarded", stage="target", codes=("ranked_2",)),
    ])
    assert report_only(journal.path) == 0
    out = capsys.readouterr().out
    assert "No calls were made" in out
    assert "ACCOUNTING" in out
    assert "PRE-REGISTERED PREDICTIONS" in out
    assert "ranked_2" in out


def test_report_only_on_a_missing_or_empty_journal_says_so(tmp_path, capsys):
    assert report_only(tmp_path / "nope.jsonl") == 1
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert report_only(empty) == 1


# ── the crash that started this ─────────────────────────────────────────────


def test_a_top_up_crash_costs_the_top_up_and_nothing_else(tmp_path, monkeypatch, capsys):
    """**Attempt 4, exactly.** `_top_up` raised and the traceback destroyed eight
    rejection codes that had already been paid for.

    Now the cohort is journalled first, the top-up is an EXTRA rather than the
    run, and its failure degrades to "no top-up" — the unit keeps what it had.
    """
    import core.items.generate as module

    monkeypatch.setattr(
        module, "generate_drafts",
        lambda payload, settings=None: [
            {"answer": "x", "explanation": "e", "definition": "d", "l1_gloss": "g"}
            for _ in payload["items"]
        ],
    )

    def _explode(*a, **k):
        raise gates.LLMError(
            "response truncated stop_reason=max_tokens output_tokens=8000 chars=0"
        )

    monkeypatch.setattr(module, "_top_up", _explode)
    monkeypatch.setattr("builtins.input", lambda _: "44")

    journal_path = tmp_path / "j.jsonl"
    code = run(3, (1,), apply=False, skip_control=True, journal_path=journal_path)

    assert code == 0, "a failed top-up took the whole run down"
    rows = read_journal(journal_path)
    assert len(rows) == ITEMS_PER_UNIT, "the codes were lost again"
    assert all(r["stage"] == "generation" for r in rows)
    assert all(r["codes"] for r in rows), "an outcome reached disk with no reason"
    assert "TOP-UP FAILED" in capsys.readouterr().out


def test_the_run_prints_where_its_journal_is(tmp_path, monkeypatch, capsys):
    """A record nobody can find is not one. The path and the rebuild command are
    printed at the top of every run, before a call is made."""
    import core.items.generate as module

    monkeypatch.setattr("builtins.input", lambda _: "no")
    run(3, (1,), apply=False, skip_control=True, journal_path=tmp_path / "j.jsonl")
    out = capsys.readouterr().out
    assert str(tmp_path / "j.jsonl") in out
    assert "--report" in out
