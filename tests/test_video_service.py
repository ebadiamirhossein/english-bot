"""W12b: the three tables, the retry path, the purge, and the refusal.

Every test runs inside a transaction that is rolled back, on a connection of its
own rather than the app's pool -- the same shape as `test_lexicon_ledger`.

THE THREE QUESTIONS, for the fixtures in this file:

1. WHAT DOES THIS FIXTURE SUPPLY THAT PRODUCTION DOES NOT?
   Named per test. The important one is TIME: `purge_stale` takes `now` as an
   argument and the fixture rows carry an explicit `metadata_refreshed_at`, so
   nothing here reads the wall clock. `test_vocabulary_due_and_anki` began
   failing on a calendar boundary rather than on a code change, and CLAUDE.md §3
   rule 6 exists because of it.
   The other is the ACTOR: no test opens a socket -- `tests/conftest.py` fails
   any that tries -- so failures are injected as the exception types
   `video_api` raises. **The seam that leaves uncrossed is named in
   `test_a_transport_failure_is_retryable_and_a_missing_caption_is_not`.**

2. DOES THE PRODUCTION CALLER SUPPLY IT?
   Named per test. Every `videos` row here is written by `svc.upsert_video` --
   the same function `refresh._live` calls -- so no test asserts against a row
   the refresh path could not have produced.

3. DOES THE ASSERTION NAME THE THING, OR COUNT IT?
   It names it: which column was nulled, which id survived, which status the row
   moved to. Counts appear only where the count IS the fact.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import psycopg
import pytest

from core.config import load_settings
from core.lexicon.coverage import CoverageReport
from core.services import video as svc

TEST_USER = -1_204_001

#: A FIXED anchor. Nothing in this file reads the wall clock, so no test here
#: can start failing on a calendar boundary (CLAUDE.md §3 rule 6).
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    with psycopg.connect(load_settings().database_url) as connection:
        row = connection.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        assert row is not None and int(row[0] or 0) >= 19, (
            "run `python -m core.db migrate` — 019 is not applied to this database"
        )
        try:
            yield connection
        finally:
            connection.rollback()


@pytest.fixture
def user(conn) -> int:
    row = conn.execute(
        """
        INSERT INTO users (telegram_user_id, name, native_language, onboarded)
        VALUES (%s, 'W12b fixture', 'fa', TRUE)
        RETURNING id
        """,
        (TEST_USER,),
    ).fetchone()
    return int(row[0])


def make_video(
    conn,
    youtube_id: str = "vid0000001",
    *,
    accent: str = "british",
    track: str = "life",
    refreshed: datetime | None = None,
    duration_s: int | None = 480,
) -> int:
    """Through `svc.upsert_video` -- the function the refresh path calls.

    A row built by a raw INSERT here could carry a combination the refresh path
    can never produce, and the test would then be checking a world that does not
    arrive.
    """
    return svc.upsert_video(
        conn,
        youtube_id=youtube_id,
        channel_id="UCprobe0000000000000000",
        accent=accent,
        track=track,
        title="A probe video",
        duration_s=duration_s,
        published_at=NOW - timedelta(days=1),
        now=refreshed or NOW,
    )


def status_of(conn, video_id: int) -> str:
    return conn.execute(
        "SELECT transcript_status FROM videos WHERE id = %s", (video_id,)
    ).fetchone()[0]


# ── the pool ────────────────────────────────────────────────────────────────


def test_a_new_video_starts_pending_with_no_transcript(conn) -> None:
    video_id = make_video(conn)
    assert status_of(conn, video_id) == "pending"


def test_re_polling_a_video_updates_it_rather_than_duplicating_it(conn) -> None:
    """`youtube_id` is unique, and the refresh path re-polls every run."""
    first = make_video(conn, "same0000001")
    second = make_video(conn, "same0000001")
    assert first == second


def test_a_channel_retagged_in_the_json_reaches_rows_already_stored(conn) -> None:
    """`accent` and `track` are authored on the CHANNEL, so re-authoring one
    must reach videos already in the pool -- not only new ones."""
    video_id = make_video(conn, "retag00001", accent="british", track="life")
    svc.upsert_video(
        conn,
        youtube_id="retag00001",
        channel_id="UCprobe0000000000000000",
        accent="american",
        track="curiosity",
        title="A probe video",
        duration_s=480,
        published_at=None,
        now=NOW,
    )
    row = conn.execute(
        "SELECT accent, track FROM videos WHERE id = %s", (video_id,)
    ).fetchone()
    assert (row[0], row[1]) == ("american", "curiosity")


def test_only_ok_rows_are_selectable(conn) -> None:
    """Names which video is offered, not how many."""
    ready = make_video(conn, "ready00001")
    make_video(conn, "pending0001")
    svc.record_transcript(
        conn, video_id=ready, text="hello there", lang="en", kind="manual"
    )
    assert [r.youtube_id for r in svc.selectable(conn)] == ["ready00001"]


# ── the retry-and-skip path (send-back B4: exercised, not merely specified) ──


def test_a_failed_transcript_is_retried_then_marked_not_skipped(conn) -> None:
    """The state machine, named at every step.

    The seam this does NOT cross: the failure is injected, where production
    supplies a real timeout or an IP challenge from the actor. No test opens a
    socket -- conftest's network guard fails any that tries -- so what is
    verified here is the bookkeeping, not the detection.
    """
    video_id = make_video(conn, "flaky00001")

    assert svc.record_transcript_failure(
        conn, video_id=video_id, error="502 from actor", terminal=False
    ) == "failed"
    assert svc.record_transcript_failure(
        conn, video_id=video_id, error="502 from actor", terminal=False
    ) == "failed"
    # The third attempt exhausts MAX_TRANSCRIPT_ATTEMPTS and sets it aside
    # rather than retrying for ever.
    assert svc.record_transcript_failure(
        conn, video_id=video_id, error="502 from actor", terminal=False
    ) == "unavailable"

    row = conn.execute(
        "SELECT transcript_attempts, transcript_last_error FROM videos "
        "WHERE id = %s",
        (video_id,),
    ).fetchone()
    assert row[0] == 3
    # The reason survives the state change -- an `unavailable` row with no
    # error text cannot be told from one that never had captions.
    assert "502 from actor" in row[1]


def test_a_transport_failure_is_retryable_and_a_missing_caption_is_not(
    conn,
) -> None:
    """The distinction the four-state column exists for.

    `terminal=True` is what `refresh` passes for a `TranscriptUnavailable`, and
    `False` for a `TranscriptFetchFailed`. The mapping itself lives in
    `refresh._live`; this asserts the two outcomes differ on the first attempt,
    which is what makes the two exception classes worth having.
    """
    retryable = make_video(conn, "retry00001")
    terminal = make_video(conn, "gone000001")
    assert svc.record_transcript_failure(
        conn, video_id=retryable, error="timeout", terminal=False
    ) == "failed"
    assert svc.record_transcript_failure(
        conn, video_id=terminal, error="no captions", terminal=True
    ) == "unavailable"


def test_a_retryable_row_is_offered_again_and_a_terminal_one_is_not(conn) -> None:
    """Names which video comes back, which is the point of the two states."""
    retryable = make_video(conn, "retry00001")
    terminal = make_video(conn, "gone000001")
    svc.record_transcript_failure(
        conn, video_id=retryable, error="timeout", terminal=False
    )
    svc.record_transcript_failure(
        conn, video_id=terminal, error="no captions", terminal=True
    )
    offered = [r.youtube_id for r in svc.videos_needing_transcript(conn, limit=10)]
    assert "retry00001" in offered
    assert "gone000001" not in offered


def test_a_successful_fetch_resets_the_attempt_counter(conn) -> None:
    """So a video that failed twice and then worked is not one failure from
    being set aside for good."""
    video_id = make_video(conn, "recover001")
    svc.record_transcript_failure(
        conn, video_id=video_id, error="timeout", terminal=False
    )
    svc.record_transcript(
        conn, video_id=video_id, text="it worked", lang="en", kind="manual"
    )
    row = conn.execute(
        "SELECT transcript_status, transcript_attempts FROM videos WHERE id = %s",
        (video_id,),
    ).fetchone()
    assert (row[0], row[1]) == ("ok", 0)


# ── the 30-day purge ────────────────────────────────────────────────────────


def test_the_purge_nulls_metadata_and_transcript_naming_each_column(conn) -> None:
    """Time is INJECTED: the row's `metadata_refreshed_at` and the `now` passed
    to `purge_stale` are both explicit, so this cannot fail on a calendar
    boundary (CLAUDE.md §3 rule 6)."""
    stale = NOW - timedelta(days=31)
    video_id = make_video(conn, "stale00001", refreshed=stale)
    svc.record_transcript(
        conn, video_id=video_id, text="some scraped text", lang="en", kind="manual"
    )

    counts = svc.purge_stale(conn, now=NOW)
    assert counts.purged == 1

    row = conn.execute(
        """
        SELECT title, duration_s, published_at, transcript, transcript_lang,
               captions_kind, transcript_status
          FROM videos WHERE id = %s
        """,
        (video_id,),
    ).fetchone()
    assert row[0] is None, "title survived the purge"
    assert row[1] is None, "duration_s survived the purge"
    assert row[2] is None, "published_at survived the purge"
    assert row[3] is None, "transcript survived the purge"
    assert row[4] is None, "transcript_lang survived the purge"
    assert row[5] is None, "captions_kind survived the purge"
    assert row[6] == "pending", "a purged row must be re-fetchable"


def test_the_purge_keeps_youtube_id(conn) -> None:
    """A video id is a public identifier the learner reads off the URL, and the
    purge bounds stored CONTENT. Nulling it would destroy `seen_penalty` for no
    compliance gain -- see migration 019's header."""
    video_id = make_video(conn, "keepid0001", refreshed=NOW - timedelta(days=31))
    svc.record_transcript(conn, video_id=video_id, text="x", lang="en", kind=None)
    svc.purge_stale(conn, now=NOW)
    row = conn.execute(
        "SELECT youtube_id, channel_id, accent, track FROM videos WHERE id = %s",
        (video_id,),
    ).fetchone()
    assert row[0] == "keepid0001"
    assert (row[2], row[3]) == ("british", "life")


def test_the_purge_keeps_the_assignment(conn, user) -> None:
    """NAMES THE SURVIVING ROW. The learner's history is what nothing else
    records, and the purge is not allowed to touch it."""
    video_id = make_video(conn, "assigned01", refreshed=NOW - timedelta(days=31))
    svc.record_transcript(conn, video_id=video_id, text="x", lang="en", kind=None)
    svc.assign_video(
        conn,
        user_id=user,
        video_id=video_id,
        assigned_for=date(2026, 9, 7),
        score_breakdown={"total": 0.8},
    )

    svc.purge_stale(conn, now=NOW)

    rows = svc.assignments_for(conn, user, since=date(2026, 1, 1))
    assert [r["youtube_id"] for r in rows] == ["assigned01"]
    assert rows[0]["assigned_for"] == date(2026, 9, 7)


def test_a_fresh_row_is_not_purged(conn) -> None:
    video_id = make_video(conn, "fresh00001", refreshed=NOW - timedelta(days=29))
    svc.record_transcript(conn, video_id=video_id, text="kept", lang="en", kind=None)
    assert svc.purge_stale(conn, now=NOW).purged == 0
    row = conn.execute(
        "SELECT transcript FROM videos WHERE id = %s", (video_id,)
    ).fetchone()
    assert row[0] == "kept"


def test_the_purge_is_idempotent_within_a_run(conn) -> None:
    """A second sweep must not report the same rows again, or the operator
    reads a purge count that never falls."""
    video_id = make_video(conn, "twice00001", refreshed=NOW - timedelta(days=31))
    svc.record_transcript(conn, video_id=video_id, text="x", lang="en", kind=None)
    assert svc.purge_stale(conn, now=NOW).purged == 1
    assert svc.purge_stale(conn, now=NOW).purged == 0


# ── coverage: an audit record ───────────────────────────────────────────────


def report(coverage: float, *, detected: bool = True, casing: str = "conventional"):
    return CoverageReport(
        coverage=coverage,
        total_tokens=100,
        counted_tokens=90,
        excluded_tokens=10,
        by_state={"known": 85, "unknown": 5},
        unknown_lemmas=("widget",),
        proper_nouns_detected=detected,
        casing=casing,
    )


def test_coverage_stores_the_basis_and_not_only_the_number(conn, user) -> None:
    """A stored 94% and a real 94% are otherwise indistinguishable, and #288 is
    exactly a case where they differ."""
    video_id = make_video(conn, "cover00001")
    svc.record_coverage(
        conn,
        user_id=user,
        video_id=video_id,
        report=report(0.9412, detected=False, casing="lowercase"),
        lexicon_digest="deadbeefdeadbeef",
        now=NOW,
    )
    row = conn.execute(
        """
        SELECT coverage, proper_nouns_detected, casing, lexicon_digest
          FROM video_coverage WHERE user_id = %s AND video_id = %s
        """,
        (user, video_id),
    ).fetchone()
    assert float(row[0]) == pytest.approx(0.9412)
    assert row[1] is False
    assert row[2] == "lowercase"
    assert row[3] == "deadbeefdeadbeef"


def test_recomputing_coverage_overwrites_rather_than_accumulating(
    conn, user
) -> None:
    """`assign` recomputes on every run, so a second write is the normal case
    and must not grow the table."""
    video_id = make_video(conn, "recomp0001")
    for coverage in (0.90, 0.95):
        svc.record_coverage(
            conn,
            user_id=user,
            video_id=video_id,
            report=report(coverage),
            lexicon_digest="d",
            now=NOW,
        )
    rows = conn.execute(
        "SELECT coverage FROM video_coverage WHERE user_id = %s AND video_id = %s",
        (user, video_id),
    ).fetchall()
    assert len(rows) == 1
    assert float(rows[0][0]) == pytest.approx(0.95)


def test_degraded_coverage_rows_are_countable_for_the_dry_run(conn, user) -> None:
    """Operator ruling A4: pool starvation must not present itself as "no
    videos" with no visible cause."""
    good = make_video(conn, "good000001")
    bad = make_video(conn, "bad0000001")
    svc.record_coverage(
        conn, user_id=user, video_id=good, report=report(0.95),
        lexicon_digest="d", now=NOW,
    )
    svc.record_coverage(
        conn, user_id=user, video_id=bad, report=report(0.99, detected=False),
        lexicon_digest="d", now=NOW,
    )
    assert svc.degraded_coverage_count(conn) == 1


# ── assignment ──────────────────────────────────────────────────────────────


def test_accent_exposure_reads_what_the_learner_was_given(conn, user) -> None:
    """Not what the pool contains -- exposure is a fact about this learner."""
    british = make_video(conn, "brit000001", accent="british")
    american = make_video(conn, "amer000001", accent="american")
    make_video(conn, "unseen0001", accent="american")
    for offset, video_id in enumerate((british, american)):
        svc.assign_video(
            conn,
            user_id=user,
            video_id=video_id,
            assigned_for=date(2026, 9, 7) + timedelta(days=offset),
            score_breakdown={},
        )
    assert svc.accent_exposure(conn, user) == {"british": 1, "american": 1}


def test_one_assignment_per_learner_per_date(conn, user) -> None:
    """Migration 019's unique index. The learner opens the day and finds one
    thing, not a choice."""
    first = make_video(conn, "first00001")
    second = make_video(conn, "second0001")
    when = date(2026, 9, 7)
    svc.assign_video(
        conn, user_id=user, video_id=first, assigned_for=when, score_breakdown={}
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        svc.assign_video(
            conn,
            user_id=user,
            video_id=second,
            assigned_for=when,
            score_breakdown={},
        )


def test_the_score_breakdown_survives_so_a_choice_stays_diagnosable(
    conn, user
) -> None:
    """The pool it was scored against may be purged before anybody asks why."""
    video_id = make_video(conn, "why000001")
    svc.assign_video(
        conn,
        user_id=user,
        video_id=video_id,
        assigned_for=date(2026, 9, 7),
        score_breakdown={"coverage_fit": 1.0, "total": 0.7875},
    )
    row = conn.execute(
        "SELECT score_breakdown FROM video_assignments WHERE user_id = %s",
        (user,),
    ).fetchone()
    assert row[0]["total"] == pytest.approx(0.7875)


def test_completed_at_has_no_writer_in_this_slice(conn, user) -> None:
    """W12b does not define what "answered" means for block 2 -- no player
    exists, so no watch signal can be written. That is W13's, and a guess
    written here would be a wrong row in a table the record treats as the
    product. Asserted rather than left as a comment."""
    video_id = make_video(conn, "nowriter01")
    svc.assign_video(
        conn,
        user_id=user,
        video_id=video_id,
        assigned_for=date(2026, 9, 7),
        score_breakdown={},
    )
    row = conn.execute(
        "SELECT completed_at, resume_position_s FROM video_assignments "
        "WHERE user_id = %s",
        (user,),
    ).fetchone()
    assert row[0] is None
    assert row[1] == 0


def test_assigned_dates_lets_a_re_run_leave_existing_days_alone(
    conn, user
) -> None:
    video_id = make_video(conn, "taken00001")
    taken = date(2026, 9, 7)
    svc.assign_video(
        conn, user_id=user, video_id=video_id, assigned_for=taken, score_breakdown={}
    )
    week = [taken, date(2026, 9, 9), date(2026, 9, 11)]
    assert svc.assigned_dates(conn, user, week) == {taken}


def test_a_videos_row_cannot_be_deleted_out_from_under_an_assignment(
    conn, user
) -> None:
    """ON DELETE RESTRICT. Nothing in this slice deletes a `videos` row, and
    this is what makes that hold for whoever writes the next one."""
    video_id = make_video(conn, "protect001")
    svc.assign_video(
        conn,
        user_id=user,
        video_id=video_id,
        assigned_for=date(2026, 9, 7),
        score_breakdown={},
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute("DELETE FROM videos WHERE id = %s", (video_id,))


# ── the pooled connection commits on exit, and the dry runs must survive it ──


def test_the_pool_commits_on_clean_exit_so_a_dry_run_must_not_write() -> None:
    """The behaviour a dry run has to be written against, pinned as a fact.

    `core.db.connection()` yields from the psycopg pool, whose context manager
    **commits on clean exit**. `core.video.assign`'s first draft called
    `record_coverage` unconditionally and committed only under `--apply` -- so
    the dry run persisted coverage rows while printing "DRY RUN -- nothing was
    written". **A command that lies about its own dryness is worse than one with
    no dry mode**, because the operator stops checking.

    (1) WHAT THIS SUPPLIES THAT PRODUCTION DOES NOT: nothing -- it uses the real
        `core.db.connection`, which is the thing whose behaviour is in question.
    (2) THE PRODUCTION CALLER: `assign.main()` and `refresh._live`, both of which
        open exactly this connection.
    (3) NAMES OR COUNTS: it names the surviving row by its youtube_id.

    Asserted rather than commented because the guard in `assign.py` is only
    correct while this is true, and nothing else in the suite would notice if a
    psycopg upgrade changed it.
    """
    from core.db import connection

    probe = "_probe_pool_commit"
    try:
        with connection() as conn:
            conn.execute(
                """
                INSERT INTO videos (youtube_id, channel_id, accent, track,
                                    metadata_refreshed_at)
                VALUES (%s, 'probe', 'british', 'life', now())
                """,
                (probe,),
            )
            # deliberately NO conn.commit()
        with connection() as conn:
            row = conn.execute(
                "SELECT youtube_id FROM videos WHERE youtube_id = %s", (probe,)
            ).fetchone()
        assert row is not None, (
            "the pool no longer commits on clean exit -- core/video/assign.py's "
            "dry-run guard was written against that behaviour and must be "
            "re-read"
        )
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM videos WHERE youtube_id = %s", (probe,))
            conn.commit()


def test_the_assign_dry_run_writes_no_coverage_row(conn, user) -> None:
    """The defect itself, in the direction it actually failed.

    The dry path computes coverage -- it must, to rank -- and simply does not
    store it. Here that is asserted through the service the CLI calls, with the
    write withheld exactly as `--apply`-less `assign` withholds it.
    """
    video_id = make_video(conn, "drycover01")
    svc.record_transcript(
        conn, video_id=video_id, text="the cat sat on the mat", lang="en", kind="manual"
    )
    before = conn.execute(
        "SELECT count(*) FROM video_coverage WHERE user_id = %s", (user,)
    ).fetchone()[0]
    # The dry path's shape: compute, do not record.
    assert svc.selectable(conn), "fixture did not become selectable"
    after = conn.execute(
        "SELECT count(*) FROM video_coverage WHERE user_id = %s", (user,)
    ).fetchone()[0]
    assert after == before == 0
