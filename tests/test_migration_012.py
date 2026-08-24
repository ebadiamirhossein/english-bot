"""W5 migration 012: the shape `items` and `item_attempts` leave behind.

Everything is read from `pg_constraint` / `information_schema` on a connection
this module opens itself, never compared against a hand-written column list — a
hand-written list is what drifts (CLAUDE.md §3 rule 5). The expected sets below
ARE the specification, which is why hardcoding them is correct here: they are
not derived from the code under test.

The FK assertions are the load-bearing ones. `tests/test_identity_boundary.py`
walks `packages/core`, `apps/bot` and `apps/api` — it does **not** scan
`migrations/`. A `REFERENCES users(telegram_user_id)` in `012_items.sql` would
pass every other test in this suite and silently re-open #92 two days after it
closed. Nothing else would catch it.
"""

from __future__ import annotations

import psycopg
import pytest

from core.config import load_settings
from core.items import CUE_TYPES, ITEM_TYPES, REGISTERS, TRACKS


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row is not None and int(row[0] or 0) >= 12, (
            "run `python -m core.db migrate` — 012 is not applied to this database"
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
       c.confdeltype
  FROM pg_constraint c
 WHERE c.conrelid = %s::regclass AND c.contype = 'f'
"""


def _fks(conn, table: str) -> set[tuple]:
    rows = conn.execute(FK_SQL, (table,)).fetchall()
    return {(tuple(r[1]), r[2], tuple(r[3]), r[4]) for r in rows}


def _check_values(conn, constraint: str) -> set[str]:
    """The quoted literals inside a CHECK, read back from the catalogue."""
    import re

    row = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
        (constraint,),
    ).fetchone()
    assert row is not None, f"{constraint} does not exist"
    return set(re.findall(r"'([^']+)'::text", row[0]))


def test_migration_012_is_applied(conn) -> None:
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    assert int(row[0]) >= 12


# ── identity: the assertion nothing else in the suite makes ────────────────


def test_item_attempts_user_id_references_users_id(conn) -> None:
    """#92 stays closed. `users.id`, never `users.telegram_user_id`."""
    fks = _fks(conn, "item_attempts")
    composite = {f for f in fks if f[1] == "items"}
    assert composite == {(("item_id", "user_id"), "items", ("id", "user_id"), "c")}


def test_items_user_id_references_users_id(conn) -> None:
    assert (("user_id",), "users", ("id",), "c") in _fks(conn, "items")


def test_no_item_table_points_at_a_telegram_id(conn) -> None:
    """Computed from the catalogue, so a renamed column cannot slip past."""
    for table in ("items", "item_attempts"):
        for _child, parent, parent_cols, _ondel in _fks(conn, table):
            if parent == "users":
                assert list(parent_cols) == ["id"], (
                    f"{table} points at users({parent_cols}) — #92 re-opened"
                )


def test_the_foreign_keys_carry_their_intended_delete_semantics(conn) -> None:
    """`confdeltype`: c=CASCADE, n=SET NULL, r=RESTRICT, a=NO ACTION.

    011 learned this by hand-listing seventeen of them. The reasons: an attempt
    stays valid evidence when its journal row is resolved away (SET NULL), and
    lexemes are never deleted (RESTRICT).
    """
    items = {(child, parent): ondel for child, parent, _pc, ondel in _fks(conn, "items")}
    assert items[(("user_id",), "users")] == "c"
    assert items[(("lexeme_id",), "lexemes")] == "r"
    assert items[(("error_id",), "errors")] == "n"
    assert items[(("source_chunk_id",), "chunks")] == "n"

    attempts = {
        (child, parent): ondel for child, parent, _pc, ondel in _fks(conn, "item_attempts")
    }
    assert attempts[(("item_id", "user_id"), "items")] == "c"
    assert attempts[(("session_id",), "sessions")] == "n"


# ── the CHECKs agree with the Python constants ─────────────────────────────


def test_the_item_type_check_permits_exactly_the_eleven(conn) -> None:
    assert _check_values(conn, "items_item_type_check") == set(ITEM_TYPES)


def test_the_register_check_permits_exactly_the_five(conn) -> None:
    assert _check_values(conn, "items_register_check") == set(REGISTERS)


def test_the_track_check_permits_exactly_the_three(conn) -> None:
    assert _check_values(conn, "items_track_check") == set(TRACKS)


def test_the_cue_check_permits_exactly_the_five_prd_cues(conn) -> None:
    assert _check_values(conn, "items_cue_type_check") == set(CUE_TYPES)
    assert _check_values(conn, "item_attempts_cue_shown_check") == set(CUE_TYPES)


# ── the validation record is a schema fact, not a convention ───────────────


def test_validation_is_not_nullable_and_has_no_default(conn) -> None:
    row = conn.execute(
        """
        SELECT is_nullable, column_default FROM information_schema.columns
         WHERE table_name = 'items' AND column_name = 'validation'
        """
    ).fetchone()
    assert row == ("NO", None), (
        "a DEFAULT here would let an item be written with no validation record"
    )


def test_an_item_without_a_validation_record_cannot_be_inserted(conn) -> None:
    """The three keys are the three gates."""
    conn.execute("SAVEPOINT t")
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            """
            INSERT INTO items (user_id, item_type, track, prompt_text, answer,
                               unit_number, validation, validator_version, model,
                               content_hash)
            VALUES (1, 'cloze_cued', 'life', 'I ___ home.', 'went', 3,
                    '{}'::jsonb, 1, 'test', 'deadbeef')
            """
        )
    conn.execute("ROLLBACK TO SAVEPOINT t")


def test_the_repair_cap_is_a_schema_fact(conn) -> None:
    """If a later slice loosens the Python loop, the INSERT fails."""
    definition = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'items_repair_count_check'"
    ).fetchone()
    assert definition is not None and "2" in definition[0]


def test_the_answer_present_iff_rule_names_both_exceptions(conn) -> None:
    definition = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'items_answer_present_iff_type_has_one'"
    ).fetchone()
    assert definition is not None
    assert "speak_answer" in definition[0]
    assert "match_pairs" in definition[0]


def test_an_item_with_no_target_cannot_be_inserted(conn) -> None:
    """PRD §4.3 gate 3 in DDL."""
    conn.execute("SAVEPOINT t")
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            """
            INSERT INTO items (user_id, item_type, track, prompt_text, answer,
                               validation, validator_version, model, content_hash)
            VALUES (1, 'cloze_cued', 'life', 'I ___ home.', 'went',
                    '{"deterministic":[],"naturalness":[],"blind_solver":[]}'::jsonb,
                    1, 'test', 'deadbeef2')
            """
        )
    conn.execute("ROLLBACK TO SAVEPOINT t")


# ── the rest of 012's declared scope ───────────────────────────────────────


def test_the_errors_source_check_carries_the_full_v3_set(conn) -> None:
    assert _check_values(conn, "errors_source_check") == {
        "quiz", "voice", "text", "reading", "diary", "capture", "conversation",
        "shadow", "retell", "answer", "item", "placement", "video",
    }


def test_track_weights_defaults_to_the_v3_mix(conn) -> None:
    """PRD §4.6: Life 50 / Curiosity 30 / Work 20."""
    row = conn.execute(
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_name = 'users' AND column_name = 'track_weights'"
    ).fetchone()
    assert row is not None
    for fragment in ('"life": 50', '"curiosity": 30', '"work": 20'):
        assert fragment in row[0]


def test_the_view_was_recreated_alongside_the_users_alter(conn) -> None:
    """#48: every ALTER TABLE users is paired with a view recreate."""
    row = conn.execute(
        "SELECT definition FROM pg_views WHERE viewname = 'approved_onboarded_users'"
    ).fetchone()
    assert row is not None
    assert "ar.user_id = u.id" in row[0].replace("\n", " ")
