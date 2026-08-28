"""#235: `--apply` writes the bytes `--live` verified, and makes no model call.

**The defect this closes.** `--apply` used to generate afresh. On 2026-08-28
`--live --units 1` passed on its first attempt and `--apply --units 1`, minutes
later, produced a completely different lesson that failed three gates. **The
operator approved lesson A and lesson B would have shipped.**

**What the repair guarantees, and it is narrower than it sounds:** not that the
reading happens before the write -- it does not, and it does not need to -- but
that **the row a learner renders is the artefact the gates passed**. That is what
makes the operator's reading a reading of something real, and it is why
`core.lessons.remove` is the other half.

Every test drives the real `apply_journaled` against a real database, with the
model seam replaced by a bomb: **any model call at all fails the test.**
"""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest

from core.config import load_settings
from core.items import gates as item_gates
from core.lessons import LESSON_VERSION
from core.lessons import generate as gen
from core.lessons.schema import parse_lesson
from core.services import lessons as svc

FIXTURES = Path(__file__).parent / "fixtures" / "lessons"


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        conn.execute("DELETE FROM grammar_lessons WHERE unit_number IN (1, 9)")
        conn.commit()
        yield conn
        conn.execute("DELETE FROM grammar_lessons WHERE unit_number IN (1, 9)")
        conn.commit()


@pytest.fixture(autouse=True)
def no_model_calls(monkeypatch):
    """**Any model call fails the test.** `--apply` must make none at all.

    Stronger than counting: there is no number of calls that is acceptable here,
    so the seam raises rather than tallies.
    """
    def bomb(*args, **kwargs):
        raise AssertionError(
            "--apply made a model call. It must write the journaled lesson and "
            "never generate (#235)."
        )

    monkeypatch.setattr(item_gates, "_chat", bomb)


@pytest.fixture
def journal(tmp_path) -> Path:
    return tmp_path / "j.jsonl"


def _verified(unit: int, fixture: str) -> gen.Outcome:
    """An Outcome shaped exactly as an accepting `--live` attempt leaves it."""
    lesson = parse_lesson(json.loads((FIXTURES / fixture).read_text()))
    out = gen.Outcome(unit=unit, attempt=1, state="accepted", lesson=lesson)
    out.diagram_count = len(lesson.diagrams)
    out.section_verdicts = {
        s.target: {"ranking": [s.target], "claimed_rank": 1, "first": s.target,
                   "runner_up": None, "confidence": "high", "ok": True}
        for s in lesson.sections
    }
    out.example_verdicts = [
        {"sentence": e, "target": s.target, "ranking": [s.target],
         "claimed_rank": 1, "first": s.target, "runner_up": None,
         "confidence": "high", "ok": True}
        for s in lesson.sections for e in s.examples
    ]
    out.coverage_pct = {s.target: 94.5 for s in lesson.sections}
    out.coverage_unknown = {s.target: ("landlord",) for s in lesson.sections}
    return out


# ── the guarantee ───────────────────────────────────────────────────────────


def test_the_bytes_written_equal_the_bytes_verified(db, journal, monkeypatch) -> None:
    """**THE POINT OF #235.** What ships is what the gates passed.

    Compared as the SERIALISED PAYLOAD, not as an object: what a learner renders
    is what came back out of Postgres, so that is what is checked.
    """
    out = _verified(1, "specimen.json")
    verified_payload = out.lesson.model_dump(mode="json")

    gen.Journal(journal).record([out])
    monkeypatch.setattr("builtins.input", lambda _: "1")
    assert gen.apply_journaled((1,), journal_path=journal) == 0

    stored = svc.for_unit(1)
    assert stored is not None
    assert stored.model_dump(mode="json") == verified_payload, (
        "the row a learner renders is not the artefact the gates passed"
    )


def test_the_stored_verification_is_the_one_the_gates_produced(
    db, journal, monkeypatch
) -> None:
    """Including `coverage_unknown`, the field the journal did not used to carry."""
    out = _verified(1, "specimen.json")
    gen.Journal(journal).record([out])
    monkeypatch.setattr("builtins.input", lambda _: "1")
    gen.apply_journaled((1,), journal_path=journal)

    row = db.execute(
        "SELECT verification FROM grammar_lessons WHERE unit_number = 1"
    ).fetchone()[0]
    assert row["verdict"] == "passed"
    assert row["lesson_version"] == LESSON_VERSION
    assert row["sections"] == out.section_verdicts
    assert row["examples"] == out.example_verdicts
    assert row["coverage_pct"] == out.coverage_pct
    assert row["coverage_unknown"] == {
        k: list(v) for k, v in out.coverage_unknown.items()
    }
    # Provenance, so a reader of the column can tell where the bytes came from.
    assert row["written_by"] == "apply-from-journal"


def test_apply_writes_every_requested_unit_from_its_own_journal_row(
    db, journal, monkeypatch
) -> None:
    gen.Journal(journal).record(
        [_verified(1, "specimen.json"), _verified(9, "specimen_unit9.json")]
    )
    monkeypatch.setattr("builtins.input", lambda _: "1,9")
    assert gen.apply_journaled((1, 9), journal_path=journal) == 0
    assert svc.for_unit(1) is not None
    assert svc.for_unit(9) is not None


# ── the refusal ─────────────────────────────────────────────────────────────


def test_apply_with_no_journaled_lesson_makes_no_model_call_and_refuses(
    db, journal, capsys
) -> None:
    """**It must never fall back to generating.**

    A silent fallback would reinstate exactly the divergence #235 closes, on the
    path nobody is watching. The autouse fixture makes any model call an error,
    so this asserts the refusal AND the absence of the call in one.
    """
    journal.write_text("", encoding="utf-8")
    assert gen.apply_journaled((1,), journal_path=journal) == 1

    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert "never generates" in out.lower()
    # The exact command to run, named rather than described.
    assert "--live --units 1" in out
    assert svc.for_unit(1) is None, "a row was written with nothing verified"


def test_apply_refuses_a_unit_whose_journal_row_was_rejected(
    db, journal, capsys
) -> None:
    """Only an ACCEPTED attempt counts. A rejected one is not a lesson."""
    out = _verified(1, "specimen.json")
    out.state = "rejected"
    out.stage = "structure"
    gen.Journal(journal).record([out])

    assert gen.apply_journaled((1,), journal_path=journal) == 1
    assert "REFUSED" in capsys.readouterr().out
    assert svc.for_unit(1) is None


def test_apply_refuses_a_journaled_lesson_that_no_longer_passes_the_free_checks(
    db, journal, capsys, monkeypatch
) -> None:
    """A hand-edited journal, or a syllabus reworded since the lesson was verified.

    The deterministic checks cost nothing, so re-running them on the loaded bytes
    is free insurance against the journal and the syllabus having drifted apart.
    """
    out = _verified(1, "specimen.json")
    tampered = out.lesson.model_dump(mode="json")
    tampered["sections"] = tampered["sections"][:3]      # bijection now broken
    tampered["diagrams"] = [
        d for d in tampered["diagrams"]
        if d["target"] != out.lesson.sections[3].target
    ]
    out.lesson = parse_lesson(tampered)
    gen.Journal(journal).record([out])

    monkeypatch.setattr("builtins.input", lambda _: "1")
    gen.apply_journaled((1,), journal_path=journal)
    printed = capsys.readouterr().out
    assert "no longer passes the free checks" in printed
    assert "target_missing" in printed
    assert svc.for_unit(1) is None


def test_a_declined_confirmation_writes_nothing(db, journal, monkeypatch) -> None:
    gen.Journal(journal).record([_verified(1, "specimen.json")])
    monkeypatch.setattr("builtins.input", lambda _: "yes")
    assert gen.apply_journaled((1,), journal_path=journal) == 1
    assert svc.for_unit(1) is None


def test_live_never_writes_a_row(db, journal, monkeypatch) -> None:
    """The other half of the split: `--live` verifies and journals, nothing more.

    `run` still accepts `apply=` so an old call site cannot silently write.
    """
    monkeypatch.setattr(gen, "generate_lesson",
                        lambda *a, **k: parse_lesson(
                            json.loads((FIXTURES / "specimen.json").read_text())))
    monkeypatch.setattr(gen, "verify_lesson",
                        lambda lesson, info, **k: _verified(1, "specimen.json"))
    monkeypatch.setattr(gen, "coverage_reference", lambda: frozenset({"a"}))
    monkeypatch.setattr(gen, "confirm", lambda *a, **k: True)

    assert gen.run((1,), apply=True, journal_path=journal, skip_control=True) == 0
    assert svc.for_unit(1) is None, "--live wrote a row"
    assert gen.verified_lessons(gen.read_journal(journal)), "nothing was journaled"


# ── the other half: removal ─────────────────────────────────────────────────


def test_a_rejected_lesson_can_be_removed_by_name(db, journal, monkeypatch) -> None:
    """**"Delete it if it's bad" needs a command, or it stops being followed.**"""
    from core.lessons import remove

    gen.Journal(journal).record([_verified(1, "specimen.json")])
    monkeypatch.setattr("builtins.input", lambda _: "1")
    gen.apply_journaled((1,), journal_path=journal)
    assert svc.for_unit(1) is not None

    assert remove.main(["--unit", "1"]) == 0
    assert svc.for_unit(1) is None


def test_removal_requires_the_unit_number_typed_back(db, journal, monkeypatch) -> None:
    """No `--yes`. A flag pasted out of a runbook is not a decision."""
    from core.lessons import remove

    gen.Journal(journal).record([_verified(1, "specimen.json")])
    monkeypatch.setattr("builtins.input", lambda _: "1")
    gen.apply_journaled((1,), journal_path=journal)

    monkeypatch.setattr("builtins.input", lambda _: "yes")
    assert remove.main(["--unit", "1"]) == 1
    assert svc.for_unit(1) is not None, "a declined confirmation removed the row"


def test_removing_a_unit_with_no_lesson_is_not_an_error(db) -> None:
    from core.lessons import remove

    assert remove.main(["--unit", "9"]) == 0


def test_removal_refuses_a_unit_outside_the_syllabus(db) -> None:
    from core.lessons import remove

    with pytest.raises(SystemExit):
        remove.main(["--unit", "99"])
