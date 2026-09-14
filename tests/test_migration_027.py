"""W16a migration 027: `writing_submissions` and `error_types.learner_label`.

Read from `information_schema` / `pg_constraint` on a connection this module
opens itself, never compared against a list derived from the code under test
(CLAUDE.md §3 rule 5).

**THE ASSERTION THIS FILE EXISTS FOR IS AN ABSENCE: `writing_submissions` HAS
NO COLUMN THAT COULD HOLD WHAT THE LEARNER WROTE.** CLAUDE.md §5 — the text is
held for the length of the screen and never stored. A text column added later
would be the first place a learner's writing could persist, and it would pass
every other test in the suite.

**RED DEMONSTRATIONS:** `test_the_log_has_no_column_that_could_hold_the_entry`
went red with `ALTER TABLE writing_submissions ADD COLUMN body TEXT` applied to
the dev database (reverted); `test_every_learner_label_passes_the_no_guilt_scan`
went red with `UPDATE error_types SET learner_label = 'Wrong article' WHERE code
= 'article_wrong'` (reverted).
"""

from __future__ import annotations

import re

import psycopg
import pytest

from core.config import load_settings
from core.copy_rules import BANNED


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row is not None and int(row[0] or 0) >= 27, (
            "run `python -m core.db migrate` — 027 is not applied to this database"
        )
        yield connection


def _columns(conn, table: str) -> dict[str, tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT column_name, data_type, is_nullable
          FROM information_schema.columns
         WHERE table_name = %s
        """,
        (table,),
    ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def test_the_log_has_no_column_that_could_hold_the_entry(conn) -> None:
    cols = _columns(conn, "writing_submissions")
    text_like = {
        name
        for name, (dtype, _) in cols.items()
        if dtype in ("text", "character varying", "character", "json", "jsonb", "bytea")
    }
    # `day_kind` is the only text column, and a CHECK pins it to two values.
    assert text_like == {"day_kind"}, text_like


def test_the_log_keys_on_users_id_and_links_to_sessions(conn) -> None:
    """PRODUCT-PRINCIPLES §2: `users(id)`, never a Telegram id."""
    rows = conn.execute(
        """
        SELECT kcu.column_name, ccu.table_name, ccu.column_name, rc.delete_rule
          FROM information_schema.table_constraints tc
          JOIN information_schema.key_column_usage kcu
            ON kcu.constraint_name = tc.constraint_name
          JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
          JOIN information_schema.referential_constraints rc
            ON rc.constraint_name = tc.constraint_name
         WHERE tc.table_name = 'writing_submissions'
           AND tc.constraint_type = 'FOREIGN KEY'
        """
    ).fetchall()
    fks = {r[0]: (r[1], r[2], r[3]) for r in rows}
    assert fks == {
        "user_id": ("users", "id", "CASCADE"),
        "session_id": ("sessions", "id", "SET NULL"),
    }
    cols = _columns(conn, "writing_submissions")
    assert cols["user_id"][1] == "NO"
    assert cols["session_id"][1] == "YES"
    assert cols["is_english"] == ("boolean", "NO")


def test_the_day_kind_check_admits_both_kinds_and_nothing_else(conn) -> None:
    """Migration 012's *widen once*: `paragraph` is legal so W16b needs no DDL."""
    row = conn.execute(
        """
        SELECT pg_get_constraintdef(c.oid)
          FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
         WHERE t.relname = 'writing_submissions' AND c.contype = 'c'
           AND pg_get_constraintdef(c.oid) LIKE '%%day_kind%%'
        """
    ).fetchone()
    assert row is not None
    assert set(re.findall(r"'([a-z_]+)'::text", str(row[0]))) == {"journal", "paragraph"}


def test_sixteen_written_categories_are_named_and_the_spoken_three_are_not(conn) -> None:
    rows = conn.execute("SELECT code, learner_label FROM error_types").fetchall()
    labels = dict(rows)
    assert len(labels) == 19
    spoken = {"pronunciation_vowel", "pronunciation_stress", "filler_overuse"}
    assert {code for code, label in labels.items() if label is None} == spoken
    assert sum(1 for label in labels.values() if label is not None) == 16


def test_every_learner_label_passes_the_no_guilt_scan(conn) -> None:
    """S6. `label`'s own `'Wrong article'` would fail this — which is why the
    eyebrow reads a new column and not that one."""
    rows = conn.execute(
        "SELECT code, learner_label FROM error_types WHERE learner_label IS NOT NULL"
    ).fetchall()
    offenders = [(code, label) for code, label in rows if BANNED.search(label)]
    assert offenders == []


def test_the_bots_label_column_is_untouched(conn) -> None:
    """The bot's prompt list is built from `label`; 027 must not have edited it."""
    row = conn.execute(
        "SELECT label FROM error_types WHERE code = 'article_wrong'"
    ).fetchone()
    assert row[0] == "Wrong article"


def test_a_blank_label_is_refused(conn) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "UPDATE error_types SET learner_label = '  ' WHERE code = 'word_order'"
        )
    conn.rollback()


def test_the_log_records_cached_input_tokens(conn) -> None:
    """**F3, on the first §3 rule 2 call's own numbers.** Caching is live: call 1
    reported input 140 with cache_creation 1,721. Without these two columns the
    log would record 140 where 1,861 were sent — a ~13x undercount (#321)."""
    cols = _columns(conn, "writing_submissions")
    for name in ("llm_cache_creation_input_tokens", "llm_cache_read_input_tokens"):
        assert cols[name] == ("integer", "NO"), name
