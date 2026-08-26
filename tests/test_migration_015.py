"""Migration 015 — capture provenance, the fourth register source, and the
index that makes the duplicate guarantee reach the rows it is about.

Read from `information_schema` and `pg_constraint`, never compared against a
hand-written column list, in `tests/test_migration_014.py`'s shape.

**The load-bearing assertion is
`test_the_unique_index_is_not_scoped_to_chunkless_cards`.** The first draft of
this index carried `WHERE source_chunk_id IS NULL AND lexeme_id IS NOT NULL`, and
under that predicate it could not see a single card in the deck — `migrate_chunks`
sets `source_chunk_id` on every card and `lexeme_id` on none. The absence of that
clause IS the ruling, and an absence is exactly what a future edit restores
without noticing.
"""

from __future__ import annotations

import re

import psycopg
import pytest

from core.cards import CAPTURE_CARD_TYPES, REGISTER_SOURCES
from core.config import load_settings

MIGRATION = "015_capture.sql"


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row is not None and int(row[0] or 0) >= 15, (
            "run `python -m core.db migrate` — 015 is not applied to this database"
        )
        try:
            yield connection
        finally:
            connection.rollback()


def _check_values(conn, constraint: str) -> set[str]:
    row = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
        (constraint,),
    ).fetchone()
    assert row is not None, f"no constraint named {constraint}"
    return set(re.findall(r"'([^']+)'::text", row[0]))


def _column(conn, table: str, column: str):
    return conn.execute(
        """
        SELECT is_nullable, column_default, data_type
          FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    ).fetchone()


def _indexdef(conn, name: str) -> str | None:
    row = conn.execute(
        "SELECT indexdef FROM pg_indexes WHERE indexname = %s", (name,)
    ).fetchone()
    return None if row is None else row[0]


def _statements() -> str:
    """The migration's SQL with `--` commentary stripped.

    010's helper, for 010's reason: this file's comments discuss at length an
    `ALTER TABLE users` it deliberately does NOT contain, so matching the raw
    text would make these assertions pass or fail on prose.
    """
    from core.db import MIGRATIONS_DIR

    text = (MIGRATIONS_DIR / MIGRATION).read_text(encoding="utf-8")
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


# ── provenance ─────────────────────────────────────────────────────────────


def test_the_two_provenance_columns_exist_and_are_nullable(conn) -> None:
    """Nullable with no backfill: the 29 cards already in the deck came from v2
    chunks that recorded neither, and an invented capture instant would be
    indistinguishable from a real one."""
    assert _column(conn, "cards", "captured_at")[:2] == ("YES", None)
    assert _column(conn, "cards", "source_title")[:2] == ("YES", None)
    assert _column(conn, "cards", "captured_at")[2] == "timestamp with time zone"


# ── the fourth register source ─────────────────────────────────────────────


def test_the_register_source_check_mirrors_the_python_constant(conn) -> None:
    """013's move: the CHECK is asserted against the constant rather than
    maintained beside it."""
    assert _check_values(conn, "cards_register_source_check") == set(REGISTER_SOURCES)


def test_import_default_is_storable_and_a_made_up_value_is_not(conn) -> None:
    assert "import_default" in _check_values(conn, "cards_register_source_check")
    assert "guessed" not in _check_values(conn, "cards_register_source_check")


def test_register_still_has_no_default(conn) -> None:
    """013's acceptance criterion "no card exists without a register tag" is
    enforced by the ABSENCE of a default, which is checkable and cannot be
    satisfied by luck. 015 must not weaken it while widening its neighbour."""
    assert _column(conn, "cards", "register")[:2] == ("NO", None)


# ── the index ──────────────────────────────────────────────────────────────


def test_the_unique_index_exists_and_is_named(conn) -> None:
    """Named so it cannot be quietly dropped — the comment would survive it."""
    assert _indexdef(conn, "cards_one_card_per_lemma") is not None


def test_the_unique_index_keys_on_lemma_and_card_type(conn) -> None:
    definition = _indexdef(conn, "cards_one_card_per_lemma")
    assert "UNIQUE" in definition
    for column in ("user_id", "lexeme_id", "card_type"):
        assert column in definition


def test_the_unique_index_is_not_scoped_to_chunkless_cards(conn) -> None:
    """THE RULING, as a negative, because the ruling IS an absence.

    Identity is the lemma, not the provenance. With `source_chunk_id IS NULL` in
    the predicate this index would be blind to every card `migrate_chunks`
    created — which is all fourteen production cards on production — and the
    first import would have written a second `tier` card beside card 17.
    """
    definition = _indexdef(conn, "cards_one_card_per_lemma")
    assert "source_chunk_id" not in definition
    assert "lexeme_id IS NOT NULL" in definition


def test_the_index_excludes_phrase_backed_cards(conn) -> None:
    """A phrase has no lemma and never will, so those rows are outside this
    constraint permanently and correctly — not a gap to be closed later."""
    assert "WHERE (lexeme_id IS NOT NULL)" in _indexdef(
        conn, "cards_one_card_per_lemma"
    )


def test_the_index_actually_refuses_a_second_card_for_one_lemma(conn) -> None:
    """A constraint that is never exercised is a comment."""
    user_id = conn.execute(
        "INSERT INTO users (name, native_language, auth_email, onboarded) "
        "VALUES ('m015', 'fa', 'm015@example.invalid', TRUE) RETURNING id"
    ).fetchone()[0]
    lexeme_id = conn.execute("SELECT id FROM lexemes LIMIT 1").fetchone()[0]
    insert = (
        "INSERT INTO cards (user_id, card_type, front, back, register, "
        "register_source, lexeme_id, fsrs_state, due) VALUES "
        "(%s, 'production', 'f', 'b', 'neutral', 'import_default', %s, "
        "'learning', NOW())"
    )
    conn.execute(insert, (user_id, lexeme_id))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(insert, (user_id, lexeme_id))
    conn.rollback()


def test_two_cards_with_no_lexeme_coexist(conn) -> None:
    """The partial predicate's other half, stated as a positive."""
    user_id = conn.execute(
        "INSERT INTO users (name, native_language, auth_email, onboarded) "
        "VALUES ('m015b', 'fa', 'm015b@example.invalid', TRUE) RETURNING id"
    ).fetchone()[0]
    insert = (
        "INSERT INTO cards (user_id, card_type, front, back, register, "
        "register_source, fsrs_state, due) VALUES "
        "(%s, 'production', 'f', 'a b c', 'neutral', 'import_default', "
        "'learning', NOW())"
    )
    conn.execute(insert, (user_id,))
    conn.execute(insert, (user_id,))  # must not raise
    conn.rollback()


def test_every_capture_card_type_is_storable(conn) -> None:
    """013's CHECK already permits all five; this pins that the two W8f writes
    are among them, so the fan-out cannot name a type the schema refuses."""
    storable = _check_values(conn, "cards_card_type_check")
    assert set(CAPTURE_CARD_TYPES) <= storable


# ── what the file does NOT do ──────────────────────────────────────────────


def test_the_migration_touches_no_users_column(conn) -> None:
    """#48 is not triggered, and the consideration is recorded rather than
    omitted: the rule has recurred because each case looked inapplicable."""
    sql = _statements().upper()
    assert "ALTER TABLE USERS" not in sql
    assert "APPROVED_ONBOARDED_USERS" not in sql


def test_the_migration_seeds_nothing(conn) -> None:
    """010, 013 and 014's rule: a migration is not a content pipeline."""
    assert "INSERT INTO" not in _statements().upper()


def test_the_migration_writes_no_schema_version_row(conn) -> None:
    """The runner does that, and only 001 inserts one itself."""
    assert "SCHEMA_VERSION" not in _statements().upper()


def test_the_migration_adds_no_user_keyed_table(conn) -> None:
    """PRODUCT-PRINCIPLES §2 in its post-011 form: confirm the keying and say
    so. `cards.user_id` already references `users(id)`; this file adds no table
    and no user-keyed column, so it enlarges nothing."""
    assert "CREATE TABLE" not in _statements().upper()


def test_the_migration_carries_no_idempotency_guards(conn) -> None:
    """009's note, kept by 010, 012, 013 and 014: `schema_version` makes a
    re-run impossible, and a guard would only buy the impression that it is safe."""
    assert "IF NOT EXISTS" not in _statements().upper()
