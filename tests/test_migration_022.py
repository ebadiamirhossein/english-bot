"""W13a migration 022: the shape `subtitle_ladder` and `subtitle_reveals` leave.

Everything is read from `pg_constraint` / `information_schema` on a connection
this module opens itself, never compared against a hand-written column list — a
hand-written list is what drifts (CLAUDE.md §3 rule 5). The expected sets below
ARE the specification, which is why hardcoding them is correct here.

**THE TWO ASSERTIONS THIS FILE EXISTS FOR ARE THE TWO COPIES OF ONE FACT.**
`track_kind`'s CHECK and `core.video.ladder.TRACK_KINDS` are the same set written
twice, and `step`'s DEFAULT and `core.video.ladder.FIRST_STEP` are the same
number written twice. **Two hand-kept copies is how one of them stops matching**
(#132's family), so both are compared here rather than trusted.

**AND THE `passes_at_step` BOUND IS DRIVEN AGAINST A REAL DATABASE**, because it
is the rule itself and not a tidy range: a stored 2 means the ladder stopped
promoting, and the only way to know the CHECK refuses it is to try.
"""

from __future__ import annotations

import re
import secrets

import psycopg
import pytest

from core.config import load_settings
from core.video.ladder import FIRST_STEP, PASSES_TO_PROMOTE, STEPS, TRACK_KINDS


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        assert row is not None and int(row[0] or 0) >= 22, (
            "run `python -m core.db migrate` — 022 is not applied to this database"
        )
        yield connection


@pytest.fixture
def learner(conn):
    row = conn.execute(
        "INSERT INTO users (name, native_language, auth_email, onboarded) "
        "VALUES ('w13a-mig', 'lt', %s, TRUE) RETURNING id",
        (f"w13a-mig-{secrets.token_hex(6)}@example.invalid",),
    ).fetchone()
    user_id = int(row[0])
    conn.commit()
    try:
        yield user_id
    finally:
        conn.rollback()
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()


def _check_source(conn, name: str) -> str:
    row = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
        (name,),
    ).fetchone()
    assert row is not None, f"no constraint named {name}"
    return str(row[0])


# ── the columns ─────────────────────────────────────────────────────────────


def test_the_ladder_has_exactly_these_columns(conn) -> None:
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        " WHERE table_name = 'subtitle_ladder' ORDER BY ordinal_position"
    ).fetchall()
    assert [r[0] for r in rows] == [
        "user_id",
        "track_kind",
        "step",
        "passes_at_step",
        "entered_step_at",
        "updated_at",
    ]


def test_the_ladder_carries_no_score_column(conn) -> None:
    """*Drops are silent*, so the one moment a stored score would be shown is the
    one moment it must not be — and no rule in PRD §7.5 reads one.

    The checkpoint stores `last_checkpoint_score` only because 014's CHECK
    requires a passed row to name the score that passed. Nothing here does.
    """
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        " WHERE table_name = 'subtitle_ladder'"
    ).fetchall()
    names = {r[0] for r in rows}
    assert names.isdisjoint({"last_score", "last_check_score", "score_pct"})


def test_the_reveals_table_stores_events_and_not_a_count(conn) -> None:
    """PRD §7.5 wants *"a number that goes down over weeks"*, and **a lifetime
    counter can only ever go up.** A per-window count needs timestamps, so this
    is a log — asserted structurally, because the tempting shape is a column."""
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        " WHERE table_name = 'subtitle_reveals' ORDER BY ordinal_position"
    ).fetchall()
    assert [r[0] for r in rows] == [
        "id",
        "user_id",
        "track_kind",
        "video_id",
        "step",
        "revealed_at",
    ]


# ── the two copies of one fact ──────────────────────────────────────────────


def test_the_track_kind_check_is_the_constants_own_set(conn) -> None:
    for table in ("subtitle_ladder", "subtitle_reveals"):
        row = conn.execute(
            """
            SELECT pg_get_constraintdef(c.oid)
              FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
             WHERE t.relname = %s AND c.contype = 'c'
               AND pg_get_constraintdef(c.oid) LIKE '%%track_kind%%'
            """,
            (table,),
        ).fetchone()
        assert row is not None, f"{table} has no track_kind CHECK"
        found = set(re.findall(r"'([a-z_]+)'::text", str(row[0])))
        assert found == set(TRACK_KINDS), (table, found)


def test_the_step_default_is_the_constants_first_step(conn) -> None:
    """A learner with no row is on step 1, and the DEFAULT says so too."""
    row = conn.execute(
        "SELECT column_default FROM information_schema.columns "
        " WHERE table_name = 'subtitle_ladder' AND column_name = 'step'"
    ).fetchone()
    assert row is not None
    assert str(row[0]).startswith(str(FIRST_STEP))


# ── the bounds, driven against the database ─────────────────────────────────


def test_a_step_off_the_ladder_is_refused(conn, learner) -> None:
    for bad in (0, len(STEPS) + 1):
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "INSERT INTO subtitle_ladder (user_id, track_kind, step) "
                "VALUES (%s, 'youtube_curated', %s)",
                (learner, bad),
            )
        conn.rollback()


def test_a_second_pass_can_never_persist(conn, learner) -> None:
    """**The rule, as a constraint.** Two passes promote and the promotion clears
    the counter, so a stored `2` means the promotion did not happen."""
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO subtitle_ladder (user_id, track_kind, passes_at_step) "
            "VALUES (%s, 'youtube_curated', %s)",
            (learner, PASSES_TO_PROMOTE),
        )
    conn.rollback()
    # The positive control: one pass IS storable, so the refusal above is the
    # bound doing its job and not the INSERT being malformed (#345).
    conn.execute(
        "INSERT INTO subtitle_ladder (user_id, track_kind, passes_at_step) "
        "VALUES (%s, 'youtube_curated', 1)",
        (learner,),
    )
    conn.commit()


def test_one_ladder_per_learner_per_track_kind(conn, learner) -> None:
    conn.execute(
        "INSERT INTO subtitle_ladder (user_id, track_kind) "
        "VALUES (%s, 'youtube_curated')",
        (learner,),
    )
    conn.commit()
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            "INSERT INTO subtitle_ladder (user_id, track_kind) "
            "VALUES (%s, 'youtube_curated')",
            (learner,),
        )
    conn.rollback()
    # Two ladders for one learner is the point of the table, so the row above
    # must not be what made the second INSERT fail.
    conn.execute(
        "INSERT INTO subtitle_ladder (user_id, track_kind) "
        "VALUES (%s, 'native_series')",
        (learner,),
    )
    conn.commit()


def test_a_reveal_survives_the_video_it_was_made_on(conn, learner) -> None:
    """`ON DELETE SET NULL`, not CASCADE. A reveal is evidence about the
    learner's listening; deleting it with the video would make the weekly number
    drop for a reason that has nothing to do with them."""
    row = conn.execute(
        """
        INSERT INTO videos (youtube_id, channel_id, accent, track,
                            transcript_status, metadata_refreshed_at)
        VALUES (%s, 'w13a-chan', 'british', 'life', 'ok', now())
        RETURNING id
        """,
        (f"w13a-{secrets.token_hex(5)}",),
    ).fetchone()
    video_id = int(row[0])
    conn.execute(
        "INSERT INTO subtitle_reveals (user_id, track_kind, step, video_id) "
        "VALUES (%s, 'youtube_curated', 4, %s)",
        (learner, video_id),
    )
    conn.commit()
    conn.execute("DELETE FROM videos WHERE id = %s", (video_id,))
    conn.commit()
    left = conn.execute(
        "SELECT video_id FROM subtitle_reveals WHERE user_id = %s", (learner,)
    ).fetchall()
    assert [r[0] for r in left] == [None], "the reveal went with the video"
    conn.execute("DELETE FROM subtitle_reveals WHERE user_id = %s", (learner,))
    conn.commit()
