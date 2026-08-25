"""W7 migration 013: the shape `cards` and `card_reviews` leave behind.

Everything is read from `pg_constraint` / `information_schema` on a connection
this module opens itself, never compared against a hand-written column list —
a hand-written list is what drifts (CLAUDE.md §3 rule 5). The expected sets
below ARE the specification, which is why hardcoding them is correct here: they
are not derived from the code under test.

The FK assertions carry the same weight they do at 012. `tests/
test_identity_boundary.py` walks `packages/core`, `apps/bot` and `apps/api` — it
does **not** scan `migrations/`. A `REFERENCES users(telegram_user_id)` in this
file would pass every other test in the suite and silently re-open #92.
"""

from __future__ import annotations

import re

import psycopg
import pytest

from core.cards import (
    CARD_TYPES,
    FSRS_STATES,
    PRODUCTIVE_CARD_TYPES,
    REGISTER_SOURCES,
    REGISTERS,
)
from core.config import load_settings


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row is not None and int(row[0] or 0) >= 13, (
            "run `python -m core.db migrate` — 013 is not applied to this database"
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
    row = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
        (constraint,),
    ).fetchone()
    assert row is not None, f"{constraint} does not exist"
    return set(re.findall(r"'([^']+)'::text", row[0]))


def _column(conn, table: str, column: str) -> dict:
    row = conn.execute(
        """
        SELECT is_nullable, column_default, data_type
          FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    ).fetchone()
    assert row is not None, f"{table}.{column} does not exist"
    return {"is_nullable": row[0], "default": row[1], "data_type": row[2]}


def test_migration_013_is_applied(conn) -> None:
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    assert int(row[0]) >= 13


# ── identity ───────────────────────────────────────────────────────────────


def test_cards_user_id_references_users_id(conn) -> None:
    assert (("user_id",), "users", ("id",), "c") in _fks(conn, "cards")


def test_no_deck_table_points_at_a_telegram_id(conn) -> None:
    """Computed from the catalogue, so a renamed column cannot slip past.

    Nothing else in the suite would catch it: the identity boundary test does
    not read `migrations/`.
    """
    for table in ("cards", "card_reviews"):
        for _child, parent, parent_cols, _ondel in _fks(conn, table):
            if parent == "users":
                assert list(parent_cols) == ["id"], (
                    f"{table} points at users({parent_cols}) — #92 re-opened"
                )


def test_card_reviews_reaches_users_only_through_cards(conn) -> None:
    """The composite FK is what makes the denormalised `user_id` unforgeable."""
    fks = _fks(conn, "card_reviews")
    assert {f for f in fks if f[1] == "cards"} == {
        (("card_id", "user_id"), "cards", ("id", "user_id"), "c")
    }
    assert not [f for f in fks if f[1] == "users"]


def test_the_foreign_keys_carry_their_intended_delete_semantics(conn) -> None:
    """c=CASCADE, n=SET NULL, r=RESTRICT.

    `source_chunk_id` is SET NULL and not CASCADE on purpose: a card reviewed
    for six weeks is evidence about the learner even if the chunk it came from
    is deleted. Lexemes are never deleted, which RESTRICT makes a schema fact.
    """
    cards = {(child, parent): ondel for child, parent, _pc, ondel in _fks(conn, "cards")}
    assert cards[(("user_id",), "users")] == "c"
    assert cards[(("source_chunk_id",), "chunks")] == "n"
    assert cards[(("lexeme_id",), "lexemes")] == "r"
    assert cards[(("neutral_lexeme_id",), "lexemes")] == "r"


# ── the CHECKs agree with the Python constants ─────────────────────────────


def test_the_card_type_check_permits_exactly_prd_five(conn) -> None:
    assert _check_values(conn, "cards_card_type_check") == set(CARD_TYPES)


def test_the_register_check_permits_exactly_the_five(conn) -> None:
    assert _check_values(conn, "cards_register_check") == set(REGISTERS)


def test_the_register_source_check_permits_exactly_the_three(conn) -> None:
    assert _check_values(conn, "cards_register_source_check") == set(REGISTER_SOURCES)


def test_the_fsrs_state_check_mirrors_the_library_enum(conn) -> None:
    assert _check_values(conn, "cards_fsrs_state_check") == set(FSRS_STATES)
    assert _check_values(conn, "card_reviews_state_before_check") == set(FSRS_STATES)
    assert _check_values(conn, "card_reviews_state_after_check") == set(FSRS_STATES)


# ── "no card exists without a register tag" ────────────────────────────────


def test_register_is_not_nullable_and_has_no_default(conn) -> None:
    """**The acceptance criterion, read out of the catalogue.**

    A count of zero untagged rows would prove nothing on a small table. NOT NULL
    plus the *absence of a default* is what makes an untagged card unexpressible
    rather than merely unobserved.

    This deliberately differs from `items.register`, which carries
    `DEFAULT 'neutral'`: an item's register is set by the same call that writes
    the item, so it has no untagged moment. Cards are written by W13's capture,
    W23a's ad-hoc surface and the video pipeline, and a default would let any of
    them insert an untagged card that silently reads `neutral`.
    """
    col = _column(conn, "cards", "register")
    assert col["is_nullable"] == "NO"
    assert col["default"] is None

    source = _column(conn, "cards", "register_source")
    assert source["is_nullable"] == "NO"
    assert source["default"] is None


def test_items_register_still_has_its_default(conn) -> None:
    """The divergence above is deliberate, so it is asserted from both sides.

    Without this, someone tidying the two into agreement would delete the reason
    rather than the inconsistency.
    """
    assert _column(conn, "items", "register")["default"] is not None


# ── the receptive-first rule, PRD §8.5.2 and §8.5.4 ────────────────────────


def _named_checks(conn, table: str) -> set[str]:
    rows = conn.execute(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = %s::regclass AND contype = 'c'",
        (table,),
    ).fetchall()
    return {r[0] for r in rows}


def test_the_receptive_first_check_bars_every_productive_card_type(conn) -> None:
    """PRD §8.5.2 permits "recognition and listening cards only" for slang.

    Read out of the catalogue and compared against `core.cards`, because the
    first draft of this constraint barred `production` alone — and a cloze card
    asks the learner to produce the phrase into a gap, so a slang cloze card
    breaks the receptive-first rule through the constraint written to hold it.
    Asserting the exact set from both sides is what stops that recurring.
    """
    row = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
        ("cards_receptive_first_until_the_neutral_is_mastered",),
    ).fetchone()
    assert row is not None
    definition = row[0]
    for card_type in PRODUCTIVE_CARD_TYPES:
        assert f"'{card_type}'" in definition, card_type
    for permitted in ("recognition", "audio"):
        assert f"'{permitted}'" not in definition, permitted


def test_the_register_rules_are_schema_facts(conn) -> None:
    """All three named, so a later slice cannot drop one and keep the comment."""
    names = _named_checks(conn, "cards")
    assert "cards_taboo_is_never_productive" in names
    assert "cards_receptive_first_until_the_neutral_is_mastered" in names
    assert "cards_informal_shows_the_four_things" in names


def test_the_seeding_rules_are_schema_facts(conn) -> None:
    names = _named_checks(conn, "cards")
    assert "cards_review_state_carries_both_parameters" in names
    assert "cards_seeded_rows_carry_their_basis" in names


# ── the log is a log ───────────────────────────────────────────────────────


def test_reviewed_at_has_no_default(conn) -> None:
    """The instant that scheduled the card must be the instant logged.

    `DEFAULT NOW()` would make them two different clock reads, and the
    difference is invisible until someone replays the log and the intervals do
    not add up.
    """
    col = _column(conn, "card_reviews", "reviewed_at")
    assert col["is_nullable"] == "NO"
    assert col["default"] is None


def test_card_reviews_records_both_sides_of_a_transition(conn) -> None:
    """A log that can only say "after" cannot be replayed or re-derived."""
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'card_reviews'"
    ).fetchall()
    columns = {r[0] for r in rows}
    for column in (
        "state_before",
        "stability_before",
        "difficulty_before",
        "state_after",
        "stability_after",
        "difficulty_after",
        "due_after",
        "elapsed_days",
        "scheduled_days",
    ):
        assert column in columns, column


def test_cards_carries_no_suspended_column(conn) -> None:
    """PRD §5: a leech is rewritten with an easier cue, **not suspended**.

    Asserted rather than merely omitted: a column nobody may set is an
    invitation, and the no-guilt rule is easier to hold when hiding a card from
    a learner is not expressible.
    """
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'cards'"
    ).fetchall()
    columns = {r[0] for r in rows}
    assert "suspended" not in columns
    assert "suspended_at" not in columns
    assert "leech_at" in columns
