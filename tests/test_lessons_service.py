"""`core.services.lessons` — the only SQL in this slice, against a real database."""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest

from core.config import load_settings
from core.lessons import LESSON_VERSION
from core.lessons.schema import parse_lesson
from core.services import lessons as svc

FIXTURES = Path(__file__).parent / "fixtures" / "lessons"
PASSED = {"verdict": "passed", "lesson_version": LESSON_VERSION}


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        conn.execute("DELETE FROM grammar_lessons WHERE unit_number = 1")
        conn.commit()
        yield conn
        conn.execute("DELETE FROM grammar_lessons WHERE unit_number = 1")
        conn.commit()


def _lesson():
    return parse_lesson(json.loads((FIXTURES / "specimen.json").read_text()))


def test_a_lesson_round_trips(db) -> None:
    assert svc.insert_lesson(_lesson(), PASSED) is True
    stored = svc.for_unit(1)
    assert stored is not None
    assert [s.target for s in stored.sections] == [
        s.target for s in _lesson().sections
    ]
    assert len(stored.diagrams) == len(_lesson().diagrams)


def test_a_second_apply_writes_nothing(db) -> None:
    """A property the operator can rely on when re-running a billed command."""
    assert svc.insert_lesson(_lesson(), PASSED) is True
    assert svc.insert_lesson(_lesson(), PASSED) is False


def test_a_failing_verdict_is_refused_at_the_call_site(db) -> None:
    """Named where the bug is, not decoded from a constraint violation."""
    with pytest.raises(svc.LessonWriteError):
        svc.insert_lesson(_lesson(), {"verdict": "rejected"})
    assert svc.for_unit(1) is None


def test_a_lesson_below_the_current_version_is_not_served(db) -> None:
    """**The read policy, and it is `bank_for_session`'s, copied.**

    `grammar_lessons_only_verified_rows_exist` keeps passing on a row verified
    under rules that no longer exist -- the CHECK cannot see the version. Serving
    it would put teaching checked by retired checks in front of a learner with
    nothing saying so.
    """
    svc.insert_lesson(_lesson(), PASSED)
    assert svc.for_unit(1) is not None
    db.execute(
        "UPDATE grammar_lessons SET lesson_version = %s WHERE unit_number = 1",
        (LESSON_VERSION - 1,),
    )
    db.commit()
    assert svc.for_unit(1) is None, (
        "a lesson verified under retired checks was served"
    )


def test_the_stale_count_is_what_the_dry_run_prints(db) -> None:
    """So a LESSON_VERSION bump is a number read before spending, not a surprise."""
    svc.insert_lesson(_lesson(), PASSED)
    assert svc.stale_count((1,)) == (0, 1)
    db.execute(
        "UPDATE grammar_lessons SET lesson_version = %s WHERE unit_number = 1",
        (LESSON_VERSION - 1,),
    )
    db.commit()
    assert svc.stale_count((1,)) == (1, 1)


def test_a_unit_with_no_lesson_returns_none(db) -> None:
    assert svc.for_unit(7) is None


def test_a_zero_diagram_lesson_is_storable(db) -> None:
    """**The state the approved plan's floor made unstorable.**

    Driven against a real database rather than read off the DDL, because the
    failure it guards against was an INSERT error, not a check result.
    """
    raw = json.loads((FIXTURES / "specimen.json").read_text())
    raw["diagrams"] = []
    assert svc.insert_lesson(parse_lesson(raw), PASSED) is True
    stored = svc.for_unit(1)
    assert stored is not None and stored.diagrams == ()


def test_a_four_diagram_lesson_is_storable(db) -> None:
    """**The state the first revision's cap of 3 made unstorable.**

    All four of unit 1's targets admit a kind, so four diagrams is the natural
    first-pass output -- and under `BETWEEN 0 AND 3` it would have died on the
    INSERT with a diagnostic naming Postgres.
    """
    lesson = _lesson()
    assert len(lesson.diagrams) == 4
    assert svc.insert_lesson(lesson, PASSED) is True
    stored = svc.for_unit(1)
    assert stored is not None and len(stored.diagrams) == 4
