"""W13-ii migration 023: the shape `video_glosses` leaves behind.

Read from `pg_constraint` / `information_schema` on a connection this module
opens itself, never compared against a hand-written column list (CLAUDE.md §3
rule 5).

**THE TWO ASSERTIONS THIS FILE EXISTS FOR ARE BOTH ABOUT AGREEING WITH 013.**
`video_glosses.register`'s CHECK and `cards.register`'s CHECK are the same enum
written twice, and `video_glosses_informal_carries_the_four_things` mirrors
`cards_informal_shows_the_four_things` one layer earlier. **Both are compared
against the real thing rather than trusted**, because two hand-kept copies is
how one of them stops matching (#132's family) — and here a divergence would
mean a gloss that no card can carry, surfacing as a 500 on a learner's tap.
"""

from __future__ import annotations

import re
import secrets

import psycopg
import pytest

from core.config import load_settings


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        assert row is not None and int(row[0] or 0) >= 23, (
            "run `python -m core.db migrate` — 023 is not applied to this database"
        )
        yield connection


@pytest.fixture
def video(conn):
    row = conn.execute(
        """
        INSERT INTO videos (youtube_id, channel_id, accent, track,
                            transcript_status, metadata_refreshed_at)
        VALUES (%s, 'w13ii-chan', 'british', 'life', 'ok', now())
        RETURNING id
        """,
        (f"w13ii-{secrets.token_hex(5)}",),
    ).fetchone()
    video_id = int(row[0])
    conn.commit()
    try:
        yield video_id
    finally:
        conn.rollback()
        conn.execute("DELETE FROM videos WHERE id = %s", (video_id,))
        conn.commit()


def _enum(conn, table: str, column: str) -> set[str]:
    """The value set of one column's own CHECK, **selected by constraint NAME.**

    The first draft of this helper matched any constraint whose text contained
    the column name, and on `cards` that is
    `cards_informal_shows_the_four_things` — a four-way CHECK that also mentions
    `register` — so it compared a rule against an enum and failed for a reason
    that had nothing to do with the schema. **Found by the failure, and the
    helper is narrowed rather than the assertion loosened.**
    """
    row = conn.execute(
        """
        SELECT pg_get_constraintdef(c.oid)
          FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
         WHERE t.relname = %s AND c.contype = 'c' AND c.conname = %s
        """,
        (table, f"{table}_{column}_check"),
    ).fetchone()
    assert row is not None, f"{table}.{column} has no CHECK named {table}_{column}_check"
    return set(re.findall(r"'([a-z_]+)'::text", str(row[0])))


def _insert(conn, video_id: int, **over):
    spec = dict(
        video_id=video_id,
        word="mid",
        context_sentence="honestly that party was mid",
        definition="disappointing, not as good as expected",
        register="slang",
        neutral_equivalent="disappointing",
        who_says_this="younger speakers, to friends",
        model="test-model",
    )
    spec.update(over)
    columns = ", ".join(spec)
    holders = ", ".join(["%s"] * len(spec))
    conn.execute(
        f"INSERT INTO video_glosses ({columns}) VALUES ({holders})",
        tuple(spec.values()),
    )


# ── the columns ─────────────────────────────────────────────────────────────


def test_the_gloss_has_exactly_these_columns(conn) -> None:
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        " WHERE table_name = 'video_glosses' ORDER BY ordinal_position"
    ).fetchall()
    assert [r[0] for r in rows] == [
        "id",
        "video_id",
        "word",
        "context_sentence",
        "cue_start_s",
        "definition",
        "register",
        "neutral_equivalent",
        "who_says_this",
        "model",
        "generated_at",
        # W31c, migration 035: the learners' own languages from the same call
        # (Q7), and who asked for the gloss — `manual` / `pregen` / `tap` — so
        # the two jobs' daily ceilings are counted apart (C2). Still no `due`,
        # no fsrs field and no `user_id`: a gloss is still not a card (below).
        "l1",
        "source",
    ]


def test_a_gloss_is_not_a_card_and_carries_no_deck_state(conn) -> None:
    """**§2g's option (a), refused, asserted as a shape rather than as prose.**

    A gloss is a candidate; a card is a commitment. If this table ever grows a
    `due`, an fsrs field or a `user_id`, it has started being a deck — which is
    exactly what putting these rows in `cards` would have done, since
    `due_queue` filters on `user_id` and `due` and nothing else.
    """
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        " WHERE table_name = 'video_glosses'"
    ).fetchall()
    names = {r[0] for r in rows}
    assert names.isdisjoint({"due", "user_id", "stability", "difficulty", "fsrs_state"})


# ── agreement with 013, both directions ─────────────────────────────────────


def test_the_register_enum_is_the_one_cards_uses(conn) -> None:
    """A gloss that no card could carry is a 500 waiting for a learner's tap."""
    assert _enum(conn, "video_glosses", "register") == _enum(
        conn, "cards", "register"
    )
    # The positive control: the sets are non-empty, so equality above is two
    # real enums agreeing and not two failed greps (#345).
    assert _enum(conn, "video_glosses", "register") == {
        "formal", "neutral", "informal", "slang", "taboo"
    }


def test_an_informal_gloss_without_the_safe_alternative_is_refused(
    conn, video
) -> None:
    """PRD §8.5.4, mirrored from `cards_informal_shows_the_four_things` one layer
    earlier — so the refusal happens while the operator is watching a generation
    run, not on a learner's tap."""
    for missing in ("neutral_equivalent", "who_says_this"):
        with pytest.raises(psycopg.errors.CheckViolation):
            _insert(conn, video, **{missing: None})
        conn.rollback()
    # The positive control: the same row WITH both fields inserts, so the two
    # refusals above are the CHECK and not a malformed statement.
    _insert(conn, video)
    conn.commit()


def test_a_neutral_gloss_needs_neither(conn, video) -> None:
    """The CHECK is scoped to informal/slang, exactly as 013's is. A neutral
    word has no safe alternative to offer and none is demanded."""
    _insert(
        conn, video, register="neutral", neutral_equivalent=None, who_says_this=None
    )
    conn.commit()


# ── the third state, and the key ────────────────────────────────────────────


def test_a_gloss_may_carry_no_timestamp(conn, video) -> None:
    """**The third state, and it is not an error.** A video whose cues were
    never stored, or were refused by the identity gate, yields a gloss with the
    sentence and no offset — and the card it produces carries the sentence and
    no timestamp."""
    _insert(conn, video, cue_start_s=None)
    conn.commit()
    row = conn.execute(
        "SELECT cue_start_s FROM video_glosses WHERE video_id = %s", (video,)
    ).fetchone()
    assert row[0] is None


def test_one_gloss_per_word_per_video(conn, video) -> None:
    _insert(conn, video)
    conn.commit()
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert(conn, video)
    conn.rollback()
    # A different word on the same video is the ordinary case and must not have
    # been what the refusal above was about.
    _insert(conn, video, word="lowkey")
    conn.commit()


def test_a_gloss_goes_with_the_video_it_explains(conn, video) -> None:
    """CASCADE, unlike `cards.source_chunk_id`'s SET NULL. A card is evidence
    about the learner and outlives its source; a gloss is *about* one video's
    line and means nothing without it."""
    _insert(conn, video)
    conn.commit()
    conn.execute("DELETE FROM videos WHERE id = %s", (video,))
    conn.commit()
    left = conn.execute(
        "SELECT count(*) FROM video_glosses WHERE video_id = %s", (video,)
    ).fetchone()
    assert left[0] == 0
