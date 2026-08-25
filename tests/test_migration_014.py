"""W8 migration 014: the shape `syllabus_units`, `syllabus_unit_lexemes` and
`user_unit_state` leave behind.

Everything is read from `pg_constraint` / `information_schema` on a connection
this module opens itself, never compared against a hand-written column list — a
hand-written list is what drifts (CLAUDE.md §3 rule 5). The expected sets below
ARE the specification, which is why hardcoding them is correct here: they are
not derived from the code under test.

The FK assertions carry the weight they do at 012 and 013.
`tests/test_identity_boundary.py` walks `packages/core`, `apps/bot` and
`apps/api` — it does **not** scan `migrations/`, and it only parses `*.py`. A
`REFERENCES users(telegram_user_id)` in this file would pass every other test in
the suite and silently re-open #92.
"""

from __future__ import annotations

import re

import psycopg
import pytest

from core.config import load_settings
from core.syllabus import (
    CHECKPOINT_ITEM_COUNT,
    CHECKPOINT_PASS_PCT,
    MASTERY_RETENTION_DAYS,
)
from core.syllabus.states import UNIT_STATES


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row is not None and int(row[0] or 0) >= 14, (
            "run `python -m core.db migrate` — 014 is not applied to this database"
        )
        try:
            yield connection
        finally:
            connection.rollback()


FK_SQL = """
SELECT c.conname,
       (SELECT array_agg(a.attname ORDER BY k.ord)
          FROM unnest(c.conkey) WITH ORDINALITY k(attnum, ord)
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum),
       c.confrelid::regclass::text,
       (SELECT array_agg(a.attname ORDER BY k.ord)
          FROM unnest(c.confkey) WITH ORDINALITY k(attnum, ord)
          JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.attnum),
       c.confdeltype,
       c.convalidated
  FROM pg_constraint c
 WHERE c.contype = 'f' AND c.conrelid = %s::regclass
"""


def _fks(conn, table):
    return {r[0]: r[1:] for r in conn.execute(FK_SQL, (table,)).fetchall()}


def _check_values(conn, constraint: str) -> set[str]:
    row = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
        (constraint,),
    ).fetchone()
    assert row is not None, f"no constraint named {constraint}"
    return set(re.findall(r"'([^']+)'::text", row[0]))


def _checkdef(conn, constraint: str) -> str:
    row = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
        (constraint,),
    ).fetchone()
    assert row is not None, f"no constraint named {constraint}"
    return row[0]


def _column(conn, table: str, column: str):
    return conn.execute(
        """
        SELECT is_nullable, column_default, data_type
          FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    ).fetchone()


def _statements(name: str = "014_syllabus.sql") -> str:
    """The migration's SQL with its `--` commentary removed.

    `tests/test_migration_010.py` established this helper for exactly this
    reason: 014's comments explain at length the `ALTER TABLE users` and the
    paired view recreate it deliberately does NOT contain, so matching against
    the raw file would make these assertions pass or fail on prose.
    """
    from core.db import MIGRATIONS_DIR

    text = (MIGRATIONS_DIR / name).read_text(encoding="utf-8")
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def _columns(conn, table: str) -> set[str]:
    return {
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        ).fetchall()
    }


# ── identity: #92 must not re-open through a migration the boundary test cannot see


def test_no_syllabus_table_points_at_a_telegram_id(conn) -> None:
    for table in ("syllabus_units", "syllabus_unit_lexemes", "user_unit_state"):
        for name, (_child, parent, parent_cols, _del, _valid) in _fks(conn, table).items():
            if parent == "users":
                assert parent_cols == ["id"], (
                    f"{name} points at users({parent_cols}) — 011 re-keyed identity "
                    "to users(id) and tests/test_identity_boundary.py does not scan "
                    "migrations/"
                )


def test_user_unit_state_is_keyed_on_the_internal_id(conn) -> None:
    fks = _fks(conn, "user_unit_state")
    assert "user_unit_state_user_id_fkey" in fks
    child, parent, parent_cols, deltype, _ = fks["user_unit_state_user_id_fkey"]
    assert (child, parent, parent_cols) == (["user_id"], "users", ["id"])
    assert deltype == "c", "a learner's unit progress goes with the learner"


# ── the 012 cross-slice contract ────────────────────────────────────────────


def test_items_unit_number_now_has_its_foreign_key(conn) -> None:
    """012 wrote the contract; 014 discharges it."""
    fks = _fks(conn, "items")
    assert "items_unit_number_fkey" in fks, (
        "migration 012 wrote: 'CROSS-SLICE CONTRACT: W8 must give "
        "syllabus_units a UNIQUE unit_number and add the foreign key in 014'"
    )
    child, parent, parent_cols, deltype, _ = fks["items_unit_number_fkey"]
    assert (child, parent, parent_cols) == (
        ["unit_number"],
        "syllabus_units",
        ["unit_number"],
    )
    assert deltype == "r", "the 24 units are fixed data; deleting one under live items is a mistake to refuse"


def test_the_unit_number_the_fk_points_at_is_the_primary_key(conn) -> None:
    """012 requires UNIQUE; a primary key is the stronger form of it."""
    row = conn.execute(
        """
        SELECT a.attname
          FROM pg_constraint c
          JOIN unnest(c.conkey) AS k(attnum) ON TRUE
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
         WHERE c.contype = 'p' AND c.conrelid = 'syllabus_units'::regclass
        """
    ).fetchall()
    assert [r[0] for r in row] == ["unit_number"]


# ── constants mirrored from core, the 013 instrument ────────────────────────


def test_the_unit_state_check_mirrors_the_constant(conn) -> None:
    assert _check_values(conn, "user_unit_state_state_check") == set(UNIT_STATES)


def test_locked_is_not_a_storable_state(conn) -> None:
    """PRD §2.3 names five states; four are storable.

    `locked` is the absence of a row, exactly as `unknown` is for
    `user_lexemes` (migration 010). Asserted rather than left implicit,
    because a later slice adding it to the CHECK would make the absence
    forgeable and nothing else in the suite would notice.
    """
    assert "locked" not in _check_values(conn, "user_unit_state_state_check")


def test_the_checkpoint_check_carries_prd_twelve_and_eighty(conn) -> None:
    definition = _checkdef(conn, "syllabus_units_checkpoint_is_twelve_at_eighty")
    assert str(CHECKPOINT_ITEM_COUNT) in definition
    assert str(CHECKPOINT_PASS_PCT) in definition


def test_the_pass_threshold_check_carries_the_same_eighty(conn) -> None:
    assert str(CHECKPOINT_PASS_PCT) in _checkdef(
        conn, "user_unit_state_a_pass_needs_the_threshold"
    )


def test_the_mastery_check_carries_three_weeks(conn) -> None:
    definition = _checkdef(
        conn, "user_unit_state_mastery_needs_a_pass_and_three_weeks"
    )
    assert f"{MASTERY_RETENTION_DAYS} days" in definition


def test_the_mastery_check_never_reads_the_clock(conn) -> None:
    """CLAUDE.md §3 rule 6, and it is load-bearing here.

    A CHECK containing now() is not immutable: the row's validity would depend
    on when it is read, and every test touching mastery would fail on a
    calendar boundary rather than on a code change. The constraint compares two
    STORED columns. This is the same rule `test_vocabulary_due_and_anki` broke
    once and that W7 answered with an injected clock.
    """
    definition = _checkdef(
        conn, "user_unit_state_mastery_needs_a_pass_and_three_weeks"
    ).lower()
    for clock in ("now()", "current_timestamp", "current_date", "localtimestamp"):
        assert clock not in definition, f"{clock} in a CHECK makes validity time-dependent"


# ── the shared/per-learner split, which is W8's central decision ────────────


def test_the_candidate_table_is_not_user_keyed(conn) -> None:
    """PRD §3's ledger clause is resolved by COMPUTING the diff, not storing it.

    A `user_id` here would be user x unit x lexeme — PRODUCT-PRINCIPLES §3's
    "materialises rows that could be computed", the same flag #93 already
    carries against W4's frequency floor.
    """
    assert "user_id" not in _columns(conn, "syllabus_unit_lexemes")


def test_the_candidate_lexeme_fk_refuses_a_deleted_lexeme(conn) -> None:
    fks = _fks(conn, "syllabus_unit_lexemes")
    _, parent, parent_cols, deltype, _ = fks["syllabus_unit_lexemes_lexeme_id_fkey"]
    assert (parent, parent_cols) == ("lexemes", ["id"])
    assert deltype == "r", "lexemes are never deleted; 013 makes the same a schema fact"


# ── negatives, stated rather than omitted ───────────────────────────────────


def test_syllabus_units_stores_nothing_for_the_three_video_items(conn) -> None:
    """PRD §3 gives each unit "3 video/audio items at 95-98% coverage".

    W12 owns them (migration 016, `videos` / `video_assignments`), and selection
    is by computed coverage against a learner's own ledger — per learner, so it
    could not sit on this shared row in any case. Asserted so the absence reads
    as a decision rather than as an oversight a later slice should "fix".
    """
    columns = _columns(conn, "syllabus_units")
    for absent in ("video_ids", "videos", "video_assignments", "coverage"):
        assert absent not in columns


def test_the_migration_touches_no_users_column(conn) -> None:
    """#48: every ALTER TABLE users is paired with a view recreate."""
    sql = _statements()
    assert "ALTER TABLE users" not in sql
    assert "CREATE OR REPLACE VIEW" not in sql


def test_the_migration_seeds_nothing(conn) -> None:
    """010's rule: data lives in data/, schema lives in migrations/.

    The 24 units arrive from `python -m core.syllabus.seed`, so that a content
    correction is a re-runnable command rather than a new migration.
    """
    sql = _statements()
    assert "INSERT INTO" not in sql.upper()


def test_the_migration_writes_no_schema_version_row(conn) -> None:
    """core/db.py's runner writes it. Only 001 inserts one itself."""
    sql = _statements()
    assert "SCHEMA_VERSION" not in sql.upper()


# ── the row-local constraints actually refuse things ────────────────────────


def test_a_unit_cannot_be_filed_under_the_wrong_stage(conn) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            """
            INSERT INTO syllabus_units (unit_number, stage, can_do,
                grammar_targets, output_task_spoken, output_task_written, checkpoint)
            VALUES (1, 6, 'x', '[{"target":"a"},{"target":"b"},{"target":"c"}]'::jsonb,
                    's', 'w', '{"item_count":12,"pass_pct":80}'::jsonb)
            """
        )


def test_a_unit_cannot_carry_two_grammar_targets(conn) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            """
            INSERT INTO syllabus_units (unit_number, stage, can_do,
                grammar_targets, output_task_spoken, output_task_written, checkpoint)
            VALUES (99, 1, 'x', '[{"target":"a"},{"target":"b"}]'::jsonb,
                    's', 'w', '{"item_count":12,"pass_pct":80}'::jsonb)
            """
        )


def test_the_named_constraints_exist_so_none_can_be_quietly_dropped(conn) -> None:
    names = {
        r[0]
        for r in conn.execute(
            """
            SELECT conname FROM pg_constraint
             WHERE conrelid IN ('syllabus_units'::regclass,
                                'user_unit_state'::regclass)
               AND contype = 'c'
            """
        ).fetchall()
    }
    for required in (
        "syllabus_units_stage_matches_unit",
        "syllabus_units_three_to_five_grammar_targets",
        "syllabus_units_checkpoint_is_twelve_at_eighty",
        "user_unit_state_a_pass_needs_the_threshold",
        "user_unit_state_mastery_needs_a_pass_and_three_weeks",
        "user_unit_state_timestamps_match_the_state",
    ):
        assert required in names, f"{required} is gone — the comment would survive it"
