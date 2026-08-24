"""W4 migration 010: `lexemes` and `user_lexemes`.

Every expectation is read from `information_schema` on a connection this module
opens itself, never compared against a hand-written column list — a hand-written
list is what drifts (CLAUDE.md §3 rule 5, known issue #48's lesson).
"""

from __future__ import annotations

import psycopg
import pytest

from core.config import load_settings
from core.lexicon.states import REGISTERS, SOURCE_RANK, STATES


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        yield connection


def _columns(conn, relation: str) -> dict[str, tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT column_name, data_type, is_nullable
          FROM information_schema.columns
         WHERE table_schema = 'public' AND table_name = %s
         ORDER BY ordinal_position
        """,
        (relation,),
    ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def _check_clauses(conn, relation: str) -> str:
    rows = conn.execute(
        """
        SELECT pg_get_constraintdef(c.oid)
          FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
         WHERE t.relname = %s AND c.contype IN ('c', 'u', 'f')
        """,
        (relation,),
    ).fetchall()
    return " ".join(r[0] for r in rows)


def _statements(name: str) -> str:
    """The migration's SQL with its `--` commentary removed.

    The comments explain, at length, the ALTER and the view recreate that this
    file deliberately does *not* contain. Matching against them would make the
    assertions below pass or fail on prose.
    """
    from core.db import MIGRATIONS_DIR

    text = (MIGRATIONS_DIR / name).read_text(encoding="utf-8")
    return "\n".join(
        line.split("--", 1)[0] for line in text.splitlines()
    )


def test_migration_010_is_applied(conn) -> None:
    """A guard for everything below: an unmigrated DB passes empty checks."""
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    assert row is not None and int(row[0] or 0) >= 10, (
        "run `python -m core.db migrate` — 010 is not applied to this database"
    )


def test_lexemes_carries_the_reference_columns(conn) -> None:
    columns = _columns(conn, "lexemes")
    assert columns["lemma"][0] == "text"
    assert columns["freq_rank"][0] == "integer"
    assert columns["cefr"][0] == "text"
    assert columns["origin"] == ("text", "NO")


def test_frequency_and_level_are_nullable_because_a_grown_row_has_neither(conn) -> None:
    """NULL rank means *rarer than the seed list's tail*, not missing."""
    columns = _columns(conn, "lexemes")
    for column in ("pos", "freq_rank", "freq_band", "cefr"):
        assert columns[column][1] == "YES", column


def test_lexemes_distinguishes_a_seeded_row_from_a_grown_one(conn) -> None:
    clauses = _check_clauses(conn, "lexemes")
    assert "origin" in clauses and "'grown'" in clauses and "'seed'" in clauses


def test_lexemes_has_no_register_column(conn) -> None:
    """PRD §8.5.1 puts register on `cards`, `items` and `user_lexemes` — not on
    the reference table. Register is a fact about how a learner met a word."""
    assert "register" not in _columns(conn, "lexemes")


def test_user_lexemes_carries_the_ledger_columns(conn) -> None:
    columns = _columns(conn, "user_lexemes")
    assert columns["user_id"] == ("bigint", "NO")
    assert columns["lexeme_id"] == ("integer", "NO")
    assert columns["state"] == ("text", "NO")
    assert columns["source"] == ("text", "NO")
    assert columns["source_rank"] == ("smallint", "NO")
    assert columns["register"][1] == "YES"
    assert columns["first_seen_at"][0] == "timestamp with time zone"


def test_the_state_check_permits_exactly_the_four_storable_states(conn) -> None:
    """`unknown` is the absence of a row. Leaving it out is what makes that
    unforgeable rather than conventional."""
    clauses = _check_clauses(conn, "user_lexemes")
    for state in STATES:
        assert f"'{state}'" in clauses
    assert "'unknown'" not in clauses


def test_every_declared_source_is_in_the_check(conn) -> None:
    clauses = _check_clauses(conn, "user_lexemes")
    for source in SOURCE_RANK:
        assert f"'{source}'" in clauses, source


def test_every_register_value_is_in_the_check(conn) -> None:
    clauses = _check_clauses(conn, "user_lexemes")
    for register in REGISTERS:
        assert f"'{register}'" in clauses, register


def test_one_row_per_learner_per_lemma(conn) -> None:
    """The UNIQUE is what makes re-running an ingestion a no-op."""
    assert "UNIQUE (user_id, lexeme_id)" in _check_clauses(conn, "user_lexemes")


def test_the_ledger_is_keyed_on_a_lexeme_id_and_never_on_a_string(conn) -> None:
    """A second tokeniser must be physically unable to write a mismatched row."""
    clauses = _check_clauses(conn, "user_lexemes")
    assert "FOREIGN KEY (lexeme_id) REFERENCES lexemes(id)" in clauses
    assert "FOREIGN KEY (user_id) REFERENCES users(telegram_user_id)" in clauses


def test_the_migration_does_not_touch_users(conn) -> None:
    """#48: every `ALTER TABLE users` must be paired with a recreate of
    `approved_onboarded_users` in the same file, because the view is
    `SELECT u.*` and freezes its column list. 010 adds nothing to `users`, so
    the pairing is not needed — recorded here so the next reader can see it was
    considered rather than forgotten."""
    sql = _statements("010_lexicon.sql")
    assert "ALTER TABLE users" not in sql
    assert "CREATE OR REPLACE VIEW" not in sql


def test_the_migration_seeds_nothing(conn) -> None:
    """15k INSERTs would be unreviewable in a diff and would couple a data
    correction to a schema version. Data lives in data/."""
    assert "INSERT INTO" not in _statements("010_lexicon.sql").upper()
