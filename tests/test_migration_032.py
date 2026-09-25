"""W18 migration 032: `placement_bank`, `placement_runs`, `placement_run_items`.

Read from `information_schema` / the tables themselves on a connection this
module opens, never compared against a list derived from the code under test
(CLAUDE.md §3 rule 5).

**THE ASSERTIONS THIS FILE EXISTS FOR:** no column in a sitting's tables could
hold what a learner typed or said (CLAUDE.md §5); the table itself refuses to
serve one learner the same item twice (the monthly re-run's rule); and no row
can claim to be calibrated (build run 2, ruling 0.1).

**RED DEMONSTRATIONS (2026-09-25), each applied to the development database
and reverted:** `ALTER TABLE placement_run_items ADD COLUMN response TEXT`
turned `test_no_column_holds_what_a_learner_typed_or_said` red;
`ALTER TABLE placement_run_items DROP CONSTRAINT placement_run_items_never_twice`
turned `test_one_learner_is_never_served_one_item_twice` red; the calibration
CHECK dropped turned `test_no_row_can_claim_calibration` red. Each was restored
from 032's own text.
**Also:** `DROP INDEX placement_runs_one_open_idx` turned
`test_one_open_sitting_per_learner` red, and the vocabulary-shape CHECK dropped
turned `test_a_pseudo_word_carries_no_band_and_a_real_word_must` red; both
restored from 032's text and re-run green.
"""

from __future__ import annotations

import secrets

import psycopg
import pytest

from core.config import load_settings
from tests.support import progress_seed as seed


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row is not None and int(row[0] or 0) >= 32, (
            "run `python -m core.db migrate` — 032 is not applied to this database"
        )
        yield connection


def _columns(conn, table):
    return {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = %s",
            (table,),
        ).fetchall()
    }


def test_no_column_holds_what_a_learner_typed_or_said(conn) -> None:
    assert _columns(conn, "placement_run_items") == {
        "run_id": "bigint",
        "user_id": "bigint",
        "bank_id": "bigint",
        "section": "text",
        "position": "smallint",
        "correct": "boolean",
        "answered_at": "timestamp with time zone",
        "served_at": "timestamp with time zone",
    }
    runs = _columns(conn, "placement_runs")
    # Every text column on a run is a CHECKed code, never free text.
    text_columns = {k for k, v in runs.items() if v == "text"}
    assert text_columns == {
        "section", "cefr", "vocabulary_band", "grammar_band", "listening_band",
        "speaking_band", "speaking_mode", "grammar_stop",
    }
    checked = {
        r[0] for r in conn.execute(
            """
            SELECT a.attname
              FROM pg_constraint c
              JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
             WHERE c.conrelid = 'placement_runs'::regclass AND c.contype = 'c'
               AND array_length(c.conkey, 1) = 1
            """
        ).fetchall()
    }
    assert text_columns <= checked


def _bank_row(conn) -> int:
    return conn.execute(
        "INSERT INTO placement_bank (section, word, is_word, content_hash) "
        "VALUES ('vocabulary', %s, FALSE, %s) RETURNING id",
        (f"w18m{secrets.token_hex(3)}", secrets.token_hex(16)),
    ).fetchone()[0]


def test_one_learner_is_never_served_one_item_twice(conn) -> None:
    learner = seed.make_learner(conn, "W18 migration", with_session=False)
    try:
        bank_id = _bank_row(conn)
        first = conn.execute(
            "INSERT INTO placement_runs (user_id, section, finished_at) "
            "VALUES (%s, 'done', now()) RETURNING id", (learner.user_id,)).fetchone()[0]
        second = conn.execute(
            "INSERT INTO placement_runs (user_id) VALUES (%s) RETURNING id",
            (learner.user_id,)).fetchone()[0]
        conn.execute(
            "INSERT INTO placement_run_items (run_id, user_id, bank_id, section, position) "
            "VALUES (%s, %s, %s, 'vocabulary', 0)", (first, learner.user_id, bank_id))
        with pytest.raises(psycopg.errors.UniqueViolation, match="placement_run_items_never_twice"):
            conn.execute(
                "INSERT INTO placement_run_items (run_id, user_id, bank_id, section, position) "
                "VALUES (%s, %s, %s, 'vocabulary', 0)", (second, learner.user_id, bank_id))
    finally:
        conn.rollback()
        seed.drop_learner(conn, learner.user_id)


def test_one_open_sitting_per_learner(conn) -> None:
    learner = seed.make_learner(conn, "W18 migration", with_session=False)
    try:
        conn.execute("INSERT INTO placement_runs (user_id) VALUES (%s)", (learner.user_id,))
        with pytest.raises(psycopg.errors.UniqueViolation, match="placement_runs_one_open_idx"):
            conn.execute("INSERT INTO placement_runs (user_id) VALUES (%s)", (learner.user_id,))
    finally:
        conn.rollback()
        seed.drop_learner(conn, learner.user_id)


def test_no_row_can_claim_calibration(conn) -> None:
    try:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "INSERT INTO placement_bank (section, word, is_word, content_hash, calibration) "
                "VALUES ('vocabulary', 'zzz', FALSE, %s, 'calibrated')", (secrets.token_hex(16),))
    finally:
        conn.rollback()
    assert conn.execute(
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_name = 'placement_bank' AND column_name = 'calibration'"
    ).fetchone()[0] == "'uncalibrated'::text"


def test_a_pseudo_word_carries_no_band_and_a_real_word_must(conn) -> None:
    try:
        with pytest.raises(psycopg.errors.CheckViolation, match="vocabulary_shape"):
            conn.execute(
                "INSERT INTO placement_bank (section, word, is_word, freq_rank, content_hash) "
                "VALUES ('vocabulary', 'house', TRUE, 12, %s)", (secrets.token_hex(16),))
    finally:
        conn.rollback()
