"""W32a — migration 036, `word_dictionary`: global, and its CHECKs driven.

**Every CHECK is driven with a row that must be refused, next to one that must
be accepted** — a constraint only read off the DDL is a constraint nobody has
seen fire (W13-ii's `capture_card_types` note). Rows use a `zqw…` lemma, which
no dictionary word begins with, and are removed after each test.

**RED BEFORE THE MIGRATION (2026-09-28):** `word_dictionary` did not exist.
"""

from __future__ import annotations

import secrets

import psycopg
import pytest
from psycopg.types.json import Jsonb

from core.config import load_settings

SENSE = {"pos": "verb", "definition": "to go somewhere", "l1": {"fa": "رفتن"}}


def _lemma() -> str:
    return "zqw" + "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(8))


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as c:
        yield c
        c.rollback()
        c.execute("DELETE FROM word_dictionary WHERE lemma LIKE 'zqw%%'")
        c.commit()


def _insert(conn, **over) -> None:
    row = {
        "lemma": _lemma(), "kind": "word", "senses": [SENSE], "register": "neutral",
        "neutral_equivalent": None, "who_says_this": None,
        "model": "test", "source": "backfill",
    }
    row.update(over)
    conn.execute(
        "INSERT INTO word_dictionary (lemma, kind, senses, register, neutral_equivalent, "
        "who_says_this, model, source) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (row["lemma"], row["kind"], Jsonb(row["senses"]), row["register"],
         row["neutral_equivalent"], row["who_says_this"], row["model"], row["source"]),
    )


def test_the_dictionary_is_global_and_has_no_user_column(conn) -> None:
    """PRODUCT-PRINCIPLES §2/§3: a meaning does not depend on the reader."""
    columns = {
        r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'word_dictionary'"
        ).fetchall()
    }
    assert columns, "word_dictionary does not exist"
    assert not any("user" in c for c in columns)


def test_a_plain_word_is_accepted(conn) -> None:
    _insert(conn)


def test_a_name_has_no_senses_and_no_register(conn) -> None:
    _insert(conn, kind="name", senses=[], register=None)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(conn, kind="name", senses=[SENSE], register=None)


@pytest.mark.parametrize(
    "over",
    [
        {"lemma": "Moving"},                       # not casefolded
        {"lemma": "t-shirt"},                      # not one token the page can tap
        {"senses": []},                            # a word with no meaning
        {"senses": [SENSE] * 4},                   # more than three senses
        {"senses": [{"pos": "verb", "l1": {}}]},   # a sense with no definition
        {"senses": {"pos": "verb"}},               # not an array
        {"register": None},                        # a word with no register
        {"register": "casual"},                    # not one of 013's five
        {"register": "slang", "neutral_equivalent": None, "who_says_this": "friends"},
        {"register": "informal", "neutral_equivalent": "to leave", "who_says_this": None},
        {"source": "tap"},                         # not one of the three sources
        {"kind": "phrase"},
    ],
)
def test_each_check_refuses_what_it_names(conn, over) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(conn, **over)


def test_informal_with_the_four_things_is_accepted(conn) -> None:
    _insert(conn, register="slang", neutral_equivalent="to leave", who_says_this="friends")


def test_one_row_per_word(conn) -> None:
    lemma = _lemma()
    _insert(conn, lemma=lemma)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert(conn, lemma=lemma)
