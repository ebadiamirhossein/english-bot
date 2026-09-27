"""W31c migration 035: pending word saves, and the gloss's L1 and source.

Read from the database this module connects to itself, never from the code
under test (CLAUDE.md §3 rule 5). Every write is rolled back.

**RED BEFORE THE MIGRATION (2026-09-27):** run against the dev database at
`schema_version` 34, every test here failed — `word_saves_pending` did not
exist, and `video_glosses` had no `l1` or `source`.
"""

from __future__ import annotations

import psycopg
import pytest

from core.config import load_settings

TEST_USER = -1_234_035


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        try:
            yield connection
        finally:
            connection.rollback()


def _user(conn) -> int:
    return conn.execute(
        "INSERT INTO users (telegram_user_id, name, native_language, onboarded) "
        "VALUES (%s, 'W31c migration fixture', 'fa', TRUE) RETURNING id",
        (TEST_USER,),
    ).fetchone()[0]


def _video(conn) -> int:
    return conn.execute(
        "INSERT INTO videos (youtube_id, channel_id, accent, track, "
        "metadata_refreshed_at) VALUES ('rt35mig0001', 'UCw31c', 'british', 'life', now()) "
        "RETURNING id"
    ).fetchone()[0]


def _pending(conn, user: int, video: int, **over) -> None:
    row = {"word": "mastodon", "context_sentence": "is that a mastodon?", "state": "pending",
           "resolved_at": None}
    row.update(over)
    conn.execute(
        "INSERT INTO word_saves_pending (user_id, video_id, word, context_sentence, state, "
        "resolved_at) VALUES (%s, %s, %s, %s, %s, %s)",
        (user, video, row["word"], row["context_sentence"], row["state"], row["resolved_at"]),
    )


def test_a_pending_save_is_keyed_to_a_learner_and_a_video(conn) -> None:
    user, video = _user(conn), _video(conn)
    _pending(conn, user, video)
    state, attempts = conn.execute(
        "SELECT state, attempts FROM word_saves_pending WHERE user_id = %s", (user,)
    ).fetchone()
    assert (state, attempts) == ("pending", 0)


def test_one_pending_row_per_learner_video_and_word(conn) -> None:
    user, video = _user(conn), _video(conn)
    _pending(conn, user, video)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _pending(conn, user, video)


def test_the_learner_is_a_real_user(conn) -> None:
    video = _video(conn)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _pending(conn, -999_999_999, video)


def test_state_is_one_of_three_and_resolution_is_stamped(conn) -> None:
    user, video = _user(conn), _video(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        _pending(conn, user, video, state="failed")


def test_a_resolved_row_carries_its_time_and_an_open_one_does_not(conn) -> None:
    user, video = _user(conn), _video(conn)
    with conn.transaction():
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                _pending(conn, user, video, state="carded", resolved_at=None)
    with pytest.raises(psycopg.errors.CheckViolation):
        _pending(conn, user, video, word="epoch", state="pending", resolved_at="2026-09-27")


def test_deleting_a_learner_deletes_their_pending_words(conn) -> None:
    user, video = _user(conn), _video(conn)
    _pending(conn, user, video)
    conn.execute("DELETE FROM users WHERE id = %s", (user,))
    assert conn.execute(
        "SELECT count(*) FROM word_saves_pending WHERE user_id = %s", (user,)
    ).fetchone()[0] == 0


def test_a_gloss_has_an_l1_object_and_a_source(conn) -> None:
    video = _video(conn)
    conn.execute(
        "INSERT INTO video_glosses (video_id, word, context_sentence, definition, register, model) "
        "VALUES (%s, 'mastodon', 'is that a mastodon?', 'an extinct elephant', 'neutral', 'm')",
        (video,),
    )
    l1, source = conn.execute(
        "SELECT l1, source FROM video_glosses WHERE video_id = %s", (video,)
    ).fetchone()
    assert (l1, source) == ({}, "manual")


def test_a_gloss_source_is_one_of_three(conn) -> None:
    video = _video(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO video_glosses (video_id, word, context_sentence, definition, register, "
            "model, source) VALUES (%s, 'epoch', 'x', 'y', 'neutral', 'm', 'batch')",
            (video,),
        )


def test_l1_must_be_an_object(conn) -> None:
    video = _video(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO video_glosses (video_id, word, context_sentence, definition, register, "
            "model, l1) VALUES (%s, 'epoch', 'x', 'y', 'neutral', 'm', '[\"fa\"]')",
            (video,),
        )
