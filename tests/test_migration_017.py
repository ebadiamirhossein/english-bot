"""W10b migration 017: the shape `grammar_lessons` leaves behind.

Everything is read from `pg_constraint` / `information_schema` on a connection
this module opens itself, never compared against a hand-written column list — a
hand-written list is what drifts (CLAUDE.md §3 rule 5). The expected sets below
ARE the specification, which is why hardcoding them is correct here.

**Both diagram-count edges are driven against a real database rather than read
off the DDL**, because the two states this constraint got wrong in successive
drafts both failed as an INSERT error, not as a check result. Zero was
unstorable under the approved plan's floor of 1; four was unstorable under the
first revision's cap of 3 — and four is the natural output for every unit in this
slice's scope.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import psycopg
import pytest

from core.config import load_settings
from core.lessons import DIAGRAMS_PER_LESSON, LESSON_VERSION, SECTIONS_PER_LESSON

FIXTURES = Path(__file__).parent / "fixtures" / "lessons"


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        assert row is not None and int(row[0] or 0) >= 17, (
            "run `python -m core.db migrate` — 017 is not applied to this database"
        )
        connection.execute("DELETE FROM grammar_lessons WHERE unit_number = 1")
        connection.commit()
        yield connection
        connection.execute("DELETE FROM grammar_lessons WHERE unit_number = 1")
        connection.commit()


def _sections() -> str:
    raw = json.loads((FIXTURES / "specimen.json").read_text())
    return json.dumps(raw["sections"])


def _diagrams(n: int) -> str:
    raw = json.loads((FIXTURES / "specimen.json").read_text())
    return json.dumps(raw["diagrams"][:n])


def _insert(conn, *, sections=None, diagrams=None, verdict="passed", version=None):
    conn.execute(
        "INSERT INTO grammar_lessons (unit_number, sections, diagrams, "
        "verification, lesson_version) VALUES (1, %s, %s, %s, %s)",
        (
            sections if sections is not None else _sections(),
            diagrams if diagrams is not None else _diagrams(4),
            json.dumps({"verdict": verdict}),
            version if version is not None else LESSON_VERSION,
        ),
    )
    conn.commit()


def test_the_columns_are_what_the_slice_declares(conn) -> None:
    rows = conn.execute(
        "SELECT column_name, is_nullable FROM information_schema.columns "
        "WHERE table_name = 'grammar_lessons'"
    ).fetchall()
    assert {r[0] for r in rows} == {
        "unit_number", "sections", "diagrams", "verification",
        "lesson_version", "generated_at",
    }
    assert all(r[1] == "NO" for r in rows), "every column is NOT NULL"


def test_there_is_no_user_column(conn) -> None:
    """PRODUCT-PRINCIPLES §2 and §3: lessons are global, asserted in the schema."""
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'grammar_lessons'"
    ).fetchall()
    assert not [r[0] for r in rows if "user" in r[0]]


def test_the_unit_is_the_primary_key_and_references_the_syllabus(conn) -> None:
    rows = conn.execute(
        "SELECT conname, contype, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'grammar_lessons'::regclass"
    ).fetchall()
    kinds = {r[1] for r in rows}
    assert "p" in kinds and "f" in kinds
    fk = next(r[2] for r in rows if r[1] == "f")
    assert "syllabus_units(unit_number)" in fk
    assert "ON DELETE RESTRICT" in fk


def test_the_check_names_match_the_constants(conn) -> None:
    """A bound stated in SQL and in Python is two places to change one number."""
    rows = conn.execute(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'grammar_lessons'::regclass AND contype = 'c'"
    ).fetchall()
    defs = {name: definition for name, definition in rows}

    # Postgres normalises `BETWEEN a AND b` to `>= a AND <= b`, so the bounds are
    # parsed out of what the DATABASE reports rather than matched against the
    # text this repository wrote. Comparing the file to itself would prove
    # nothing about the applied schema.
    def bounds(definition: str) -> tuple[int, int]:
        found = [int(n) for n in re.findall(r"<?>?=\s*(\d+)", definition)]
        assert len(found) == 2, f"could not read bounds from {definition!r}"
        return min(found), max(found)

    assert bounds(defs["grammar_lessons_sections_three_to_five"]) == SECTIONS_PER_LESSON
    assert bounds(defs["grammar_lessons_zero_to_five_diagrams"]) == DIAGRAMS_PER_LESSON
    assert "grammar_lessons_only_verified_rows_exist" in defs


def test_a_zero_diagram_lesson_inserts(conn) -> None:
    """**Unstorable under the approved plan's floor of 1.**

    "Fewer rather than false" declares zero legitimate, so a schema that forbids
    it makes the design's own outcome an INSERT error. #213's shape.
    """
    _insert(conn, diagrams=json.dumps([]))
    assert conn.execute(
        "SELECT jsonb_array_length(diagrams) FROM grammar_lessons WHERE unit_number = 1"
    ).fetchone()[0] == 0


def test_a_four_diagram_lesson_inserts(conn) -> None:
    """**Unstorable under the first revision's cap of 3.**

    Every unit in scope has four targets and all twelve admit a kind, so four is
    the natural first-pass output — the floor's defect at the other end.
    """
    _insert(conn, diagrams=_diagrams(4))
    assert conn.execute(
        "SELECT jsonb_array_length(diagrams) FROM grammar_lessons WHERE unit_number = 1"
    ).fetchone()[0] == 4


def test_a_six_diagram_lesson_is_refused(conn) -> None:
    """The ceiling still bites above the syllabus's own maximum target count."""
    raw = json.loads((FIXTURES / "specimen.json").read_text())
    six = raw["diagrams"] + raw["diagrams"][:2]
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(conn, diagrams=json.dumps(six))
    conn.rollback()


def test_a_two_section_lesson_is_refused(conn) -> None:
    raw = json.loads((FIXTURES / "specimen.json").read_text())
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(conn, sections=json.dumps(raw["sections"][:2]))
    conn.rollback()


def test_a_row_that_failed_verification_cannot_exist(conn) -> None:
    """"Regenerated, never shipped with a warning" — made unforgeable."""
    for verdict in ("rejected", "unshippable", "pending"):
        with pytest.raises(psycopg.errors.CheckViolation):
            _insert(conn, verdict=verdict)
        conn.rollback()


def test_the_check_cannot_see_the_version_which_is_why_the_service_filters(conn) -> None:
    """The gap the read policy exists to close, demonstrated rather than asserted.

    A row at a retired `lesson_version` still satisfies every CHECK. Nothing in
    the schema can refuse it, so `core.services.lessons.for_unit` does.
    """
    _insert(conn, version=LESSON_VERSION - 1)
    stored = conn.execute(
        "SELECT lesson_version FROM grammar_lessons WHERE unit_number = 1"
    ).fetchone()
    assert stored[0] == LESSON_VERSION - 1, "the CHECK accepted a retired version"

    from core.services import lessons as svc

    assert svc.for_unit(1) is None, "but the service refuses to serve it"


def test_a_second_row_for_one_unit_is_impossible(conn) -> None:
    _insert(conn)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert(conn)
    conn.rollback()
