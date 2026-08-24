"""The `errors.source` widening, classified against W4's harvest allow-list.

**The error journal is the product.** Migration 012 added six values to the
CHECK and every one is classified in the same slice, not left for whichever
later slice first writes one. The axis is W4's: did the learner TYPE it, or did
a recogniser GUESS it? A mishearing promoted to `known` is permanent damage; a
missing harvest is recoverable.
"""

from __future__ import annotations

import re

import psycopg
import pytest

from core.config import load_settings
from core.lexicon.states import HARVESTED_SOURCES, NOT_HARVESTED_SOURCES
from core.services.lexicon import PRODUCED_ERROR_SOURCES


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        try:
            yield connection
        finally:
            connection.rollback()


def _check_values(conn, constraint: str) -> set[str]:
    row = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
        (constraint,),
    ).fetchone()
    assert row is not None
    return set(re.findall(r"'([^']+)'::text", row[0]))


def test_every_permitted_source_is_classified_exactly_once(conn) -> None:
    """A seventh value cannot be added without someone making the decision."""
    permitted = _check_values(conn, "errors_source_check")
    assert HARVESTED_SOURCES | NOT_HARVESTED_SOURCES == permitted
    assert HARVESTED_SOURCES & NOT_HARVESTED_SOURCES == set()


def test_the_harvest_query_reads_the_frozenset(conn) -> None:
    """Two hand-kept copies of an allow-list is how one stops matching."""
    assert set(PRODUCED_ERROR_SOURCES) == HARVESTED_SOURCES


def test_asr_sources_are_never_harvested() -> None:
    """`voice` and `diary` from W4; `shadow` is the same class, added at W5."""
    for source in ("voice", "diary", "shadow"):
        assert source in NOT_HARVESTED_SOURCES


def test_item_is_not_harvested() -> None:
    """It covers typed AND spoken responses under one value.

    Harvesting it would let a `speak_answer` mishearing promote a word to
    `known`. `core.items.RESPONSE_MODE` is shipped so W6/W7 can split the two
    honestly rather than widening this set and hoping.
    """
    assert "item" in NOT_HARVESTED_SOURCES
    assert "item" not in HARVESTED_SOURCES


def test_placement_is_not_harvested() -> None:
    """PRD §6: the instrument must not change.

    Harvesting from it feeds the measurement back into the thing measured.
    """
    assert "placement" in NOT_HARVESTED_SOURCES


def test_someone_elses_english_is_never_harvested() -> None:
    """`capture` from W4; `video` is the same class, added at W5."""
    assert {"capture", "video"} <= NOT_HARVESTED_SOURCES


def test_the_keyboard_authored_v5_sources_are_harvested() -> None:
    """`answer` and `retell` are `text`'s class: the learner typed them."""
    assert {"answer", "retell"} <= HARVESTED_SOURCES


def test_w4s_original_four_are_unchanged() -> None:
    """W5 widened the CHECK. It did not widen the behaviour."""
    assert {"quiz", "text", "reading", "conversation"} <= HARVESTED_SOURCES
