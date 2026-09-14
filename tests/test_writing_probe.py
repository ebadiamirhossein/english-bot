"""W16a: the §3 rule 2 probe makes no call when dry and can write nothing when live.

**RED DEMONSTRATIONS:** `test_the_probe_holds_no_write_path` went red with
`from core.services.errors import record_errors` added to the probe;
`test_the_dry_run_sends_nothing` went red with `--live` made the default.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROBE = Path(__file__).resolve().parents[1] / "packages" / "core" / "writing" / "probe.py"


def test_the_probe_holds_no_write_path() -> None:
    """It imports no writer and contains no statement that could write a row."""
    source = PROBE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported |= {f"{node.module}.{a.name}" for a in node.names}
            imported.add(str(node.module))
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
    for forbidden in (
        "core.services.errors",
        "core.services.errors.record_errors",
        "core.services.cards",
        "core.db",
    ):
        assert forbidden not in imported, forbidden
    called = {
        getattr(n.func, "attr", getattr(n.func, "id", ""))
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
    }
    assert "correct_submission" not in called
    assert "record_errors" not in called
    upper = source.upper()
    assert "INSERT " not in upper and "UPDATE " not in upper


def test_the_dry_run_sends_nothing_and_prints_the_count(monkeypatch, capsys) -> None:
    from core.services import writing
    from core.writing import probe

    def _refuse(*args, **kwargs):
        raise AssertionError("the dry run reached the model")

    monkeypatch.setattr(writing, "chat", _refuse)
    assert probe.main([]) == 0
    out = capsys.readouterr().out
    # Hardcoded: two journal fixtures and, from W16b, one paragraph (§3 rule 5).
    assert "calls --live will make: 3" in out
    assert "request (paragraph): json_mode=True max_tokens=4000 reject_truncation=True max_corrections=8" in out
    assert "request (journal): json_mode=True max_tokens=2000 reject_truncation=True max_corrections=2" in out
    assert "DRY RUN. Nothing was sent." in out


def test_the_probes_paragraph_task_is_unit_ones_verbatim() -> None:
    """Read from `data/syllabus_units.json` independently of the probe (rule 5)."""
    import json

    from core.writing import probe

    units = json.loads((PROBE.parents[3] / "data" / "syllabus_units.json").read_text(encoding="utf-8"))
    unit1 = next(u for u in units if u["unit_number"] == 1)
    assert probe.PARAGRAPH_TASK == unit1["output_task_written"]


def test_the_live_run_makes_exactly_three_calls_and_writes_nothing(monkeypatch, capsys) -> None:
    """`--live` against a stubbed wrapper: the count, and no row anywhere."""
    from core.services import writing
    from core.writing import probe

    calls: list[str] = []

    def _stub(messages, **kwargs):
        calls.append(messages[0]["content"])
        return {"is_english": True, "corrections": [], "did_well": None}

    monkeypatch.setattr(writing, "chat", _stub)

    def _no_write(*args, **kwargs):
        raise AssertionError("the probe tried to write")

    monkeypatch.setattr("core.services.errors.record_errors", _no_write)
    monkeypatch.setattr(writing, "record_errors", _no_write)
    assert probe.main(["--live"]) == 0
    assert len(calls) == 3
    assert "3 of 3 fixtures returned a response" in capsys.readouterr().out
