"""Every query against `grammar_lessons`. The only SQL in this slice.

`core.lessons` is pure and holds none, which is what keeps
`tests/test_core_boundary.py::test_no_sql_outside_services` unexempted and #59
the only boundary exemption in the repository.

**No `user_id` anywhere in this module, and that is the point.** Lessons are
global -- one row per unit, served to everyone -- so there is no per-learner read
to get wrong and no place for #159's L1 problem to reappear.
"""

from __future__ import annotations

import json

from psycopg.rows import tuple_row

from core.db import connection
from core.lessons import LESSON_VERSION
from core.lessons.schema import Lesson, parse_lesson


class LessonWriteError(RuntimeError):
    """A lesson that must not reach a learner."""


# Every cursor below pins `tuple_row`: the shared pool is opened with
# `dict_row`, a test connection usually is not, and a service that reads by
# position must not depend on which one it was handed.


def for_unit(unit_number: int, *, conn=None) -> Lesson | None:
    """This unit's lesson, or None. **Refuses a row below the current version.**

    **The version filter is a policy and it is stated rather than implied.**
    `grammar_lessons_only_verified_rows_exist` keeps passing on a row that was
    verified under rules that no longer exist -- the CHECK cannot see the
    version, by construction. Serving such a row would put teaching checked by
    retired checks in front of a learner with nothing saying so.

    So this refuses it, which is not a new judgement: it is
    `core.services.items.bank_for_session`'s `validator_version =
    VALIDATOR_VERSION` filter, copied, on W10's stated reason that a row
    validated by a gate that could not detect multi-acceptability may be
    ungradable. A lesson verified by checks that no longer exist is the same
    claim.

    **The cost, stated so it is not discovered:** bumping `LESSON_VERSION`
    empties every stored lesson until it is regenerated, and block 3 falls back
    to `lesson: None` and the line that says the explanation is on its way --
    which is honest, and is exactly what a unit with no lesson already shows.
    The bump is not silent: `core.lessons.generate`'s dry run prints
    `stored lessons below LESSON_VERSION: n of m` before anything is spent.
    """
    if conn is not None:
        return _read(conn, unit_number)
    with connection() as conn:
        return _read(conn, unit_number)


def _read(conn, unit_number: int) -> Lesson | None:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT unit_number, sections, diagrams
              FROM grammar_lessons
             WHERE unit_number = %s
               AND lesson_version = %s
            """,
            (unit_number, LESSON_VERSION),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return parse_lesson(
        {"unit_number": row[0], "sections": row[1], "diagrams": row[2]}
    )


def stale_count(units: tuple[int, ...] | None = None) -> tuple[int, int]:
    """`(below current version, stored at all)`, for the dry run to print.

    So a `LESSON_VERSION` bump is a number the operator reads before spending,
    rather than an emptied block 3 discovered on a phone.
    """
    with connection() as conn, conn.cursor(row_factory=tuple_row) as cur:
        if units:
            cur.execute(
                "SELECT count(*) FILTER (WHERE lesson_version < %s), count(*) "
                "FROM grammar_lessons WHERE unit_number = ANY(%s)",
                (LESSON_VERSION, list(units)),
            )
        else:
            cur.execute(
                "SELECT count(*) FILTER (WHERE lesson_version < %s), count(*) "
                "FROM grammar_lessons",
                (LESSON_VERSION,),
            )
        below, total = cur.fetchone()
    return int(below), int(total)


def delete_lesson(unit_number: int) -> bool:
    """Remove one unit's lesson. True if a row went, False if there was none.

    **The half that makes writing-before-reading safe** (#235). `--apply` writes
    the bytes `--live` verified, and the operator reads them afterwards -- so
    there has to be a NAMED COMMAND for rejecting one. *"Delete it if it is
    bad"* with nothing behind it is a rule that stops being followed the first
    time somebody is busy.

    No cascade and nothing else to clean up: `grammar_lessons` is referenced by
    no other table, and block 3 falls back to `lesson: None` and the line saying
    the explanation is on its way -- which is what a unit with no lesson already
    shows, so a learner sees a coherent screen rather than a gap.
    """
    with connection() as conn:
        cur = conn.cursor(row_factory=tuple_row)
        cur.execute(
            "DELETE FROM grammar_lessons WHERE unit_number = %s RETURNING unit_number",
            (unit_number,),
        )
        row = cur.fetchone()
        conn.commit()
    return row is not None


def insert_lesson(lesson: Lesson, verification: dict) -> bool:
    """Write a verified lesson. True if written, False if the unit already had one.

    **`verdict` is checked here as well as in the CHECK**, because a caller that
    reaches this with a failing verdict has a bug worth naming at the call site
    rather than a constraint violation worth decoding from Postgres.

    `DO NOTHING` rather than an upsert: a second `--apply` writing nothing is a
    property the operator can rely on, and replacing a lesson somebody has read
    is a different act from creating one. Regeneration deletes explicitly.
    """
    if verification.get("verdict") != "passed":
        raise LessonWriteError(
            f"refusing to write a lesson with verdict "
            f"{verification.get('verdict')!r} for unit {lesson.unit_number}"
        )
    payload = lesson.model_dump(mode="json")
    with connection() as conn:
        cur = conn.cursor(row_factory=tuple_row)
        cur.execute(
            """
            INSERT INTO grammar_lessons (
                unit_number, sections, diagrams, verification, lesson_version
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (unit_number) DO NOTHING
            RETURNING unit_number
            """,
            (
                lesson.unit_number,
                json.dumps(payload["sections"], ensure_ascii=False),
                json.dumps(payload["diagrams"], ensure_ascii=False),
                json.dumps(verification, ensure_ascii=False),
                LESSON_VERSION,
            ),
        )
        row = cur.fetchone()
        conn.commit()
    return row is not None
