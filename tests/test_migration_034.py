"""W24d migration 034: `video_assignments.kind` and one assignment per kind per date.

Read from the database this module connects to itself, never from the code
under test (CLAUDE.md §3 rule 5). Every write is rolled back.

**RED BEFORE THE MIGRATION (2026-09-27):** run against the dev database at
`schema_version` 33, every test here failed — the `kind` column did not exist,
and a second assignment on one date was refused by 019's
`UNIQUE (user_id, assigned_for)`.
"""

from __future__ import annotations

from datetime import date

import psycopg
import pytest

from core.config import load_settings

TEST_USER = -1_234_034
ON = date(2026, 9, 29)  # a Tuesday: no video on it before W24d


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
        "VALUES (%s, 'W24d migration fixture', 'fa', TRUE) RETURNING id",
        (TEST_USER,),
    ).fetchone()[0]


def _video(conn, youtube_id: str) -> int:
    return conn.execute(
        "INSERT INTO videos (youtube_id, channel_id, accent, track, "
        "metadata_refreshed_at) VALUES (%s, 'UCw24d', 'british', 'life', now()) "
        "RETURNING id",
        (youtube_id,),
    ).fetchone()[0]


def _assign(conn, user: int, video: int, kind: str | None) -> None:
    if kind is None:
        conn.execute(
            "INSERT INTO video_assignments (user_id, video_id, assigned_for, "
            "score_breakdown) VALUES (%s, %s, %s, '{}')",
            (user, video, ON),
        )
    else:
        conn.execute(
            "INSERT INTO video_assignments (user_id, video_id, assigned_for, "
            "score_breakdown, kind) VALUES (%s, %s, %s, '{}', %s)",
            (user, video, ON, kind),
        )


def test_an_existing_shaped_insert_is_a_daily_assignment(conn) -> None:
    """Every row written before 034 — and every insert that names no kind —
    is the day's video."""
    user = _user(conn)
    _assign(conn, user, _video(conn, "w24dmig001"), None)
    assert conn.execute(
        "SELECT kind FROM video_assignments WHERE user_id = %s", (user,)
    ).fetchone()[0] == "daily"


def test_one_daily_and_one_extra_may_share_a_date(conn) -> None:
    user = _user(conn)
    _assign(conn, user, _video(conn, "w24dmig002"), "daily")
    _assign(conn, user, _video(conn, "w24dmig003"), "extra")
    assert conn.execute(
        "SELECT count(*) FROM video_assignments WHERE user_id = %s AND assigned_for = %s",
        (user, ON),
    ).fetchone()[0] == 2


@pytest.mark.parametrize("kind", ["daily", "extra"])
def test_still_only_one_of_each_kind_per_date(conn, kind) -> None:
    """019's reason is unchanged for block 2: the learner opens the day and
    finds one thing. An extra is at most one too."""
    user = _user(conn)
    _assign(conn, user, _video(conn, "w24dmig004"), kind)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _assign(conn, user, _video(conn, "w24dmig005"), kind)


def test_an_unknown_kind_is_refused(conn) -> None:
    user = _user(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        _assign(conn, user, _video(conn, "w24dmig006"), "bonus")
