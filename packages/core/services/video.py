"""Every SQL statement W12b has. Migration 019's three tables.

`core/video/` is pure and `core/video_api.py` is the HTTP door; the queries are
here, because `test_no_sql_outside_services` fails on the commit that puts one
anywhere else.

**EVERY CURSOR HERE DECLARES `row_factory=tuple_row`**, which is
`core/services/lexicon.py`'s convention and not decoration. `core.db`'s pool
opens connections with `dict_row`, so a service that read `row["id"]` would
depend on how its CALLER built the connection: correct through the pool, and
broken on the bare `psycopg.connect()` every DB test uses. The first draft of
this module did exactly that and twenty-two tests found it at once. Declaring
the factory per cursor makes each function's result shape a property of the
function rather than of the connection handed to it.

WHAT THIS MODULE WILL NOT DO:

- **It never deletes a `videos` row.** The 30-day rule is a purge of CONTENT,
  and `purge_stale` nulls columns. A `videos` row carries a learner's
  `seen_penalty` through `video_assignments`, and deleting it would silently
  re-offer a video somebody has already watched.
- **It never writes `video_assignments.completed_at`.** W12b does not define
  what "answered" means for block 2 -- no player exists, so no watch signal can
  be written. That is W13's, and a definition guessed here would be a wrong row
  in a table the record treats as the product.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Mapping, Sequence

from psycopg.rows import tuple_row

from core.lexicon.coverage import CoverageReport

logger = logging.getLogger(__name__)

#: Developer Policies §III.E.4.d for the metadata; conservative policy for the
#: transcript. Migration 019's header carries the distinction in full -- it is
#: NOT the case that §III.E.4.d licenses thirty days of scraped transcript.
RETENTION_DAYS = 30

#: How many times a retryable transcript failure is retried across runs before
#: the video is set aside. The actor is community-maintained and YouTube
#: challenges datacentre IPs, so some failures are transient and some are not;
#: three attempts distinguishes them without paying indefinitely to find out.
MAX_TRANSCRIPT_ATTEMPTS = 3

_POOL_COLUMNS = (
    "id, youtube_id, channel_id, accent, track, title, "
    "duration_s, transcript, captions_kind"
)


@dataclass(frozen=True, slots=True)
class PoolRow:
    """A candidate as the database holds it, before scoring."""

    video_id: int
    youtube_id: str
    channel_id: str
    #: **None means NOT A RELIABLE ACCENT SIGNAL (migration 020).** It is
    #: carried through as `None` and never coerced -- `str(None)` is the string
    #: `"None"`, which `accent_rotation` would bucket as a third accent (#315).
    accent: str | None
    track: str
    title: str | None
    duration_s: int | None
    transcript: str | None
    captions_kind: str | None


@dataclass(frozen=True, slots=True)
class PurgeCounts:
    scanned: int
    purged: int


# --------------------------------------------------------------------------
# The pool
# --------------------------------------------------------------------------
def upsert_video(
    conn,
    *,
    youtube_id: str,
    channel_id: str,
    accent: str,
    track: str,
    title: str | None,
    duration_s: int | None,
    published_at: datetime | None,
    now: datetime,
) -> int:
    """Create or refresh one pool row, and return its id.

    `accent` and `track` are OVERWRITTEN on every refresh, deliberately: they
    are authored on the channel entry, so re-authoring one in
    `data/video_channels.json` must reach rows already stored rather than
    applying only to new ones.

    `metadata_refreshed_at` is stamped here, which is what makes the 30-day
    clock a fact about when the metadata was last READ rather than about when
    the row was first created.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            INSERT INTO videos (youtube_id, channel_id, accent, track,
                                title, duration_s, published_at,
                                metadata_refreshed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (youtube_id) DO UPDATE
               SET channel_id            = EXCLUDED.channel_id,
                   accent                = EXCLUDED.accent,
                   track                 = EXCLUDED.track,
                   title                 = EXCLUDED.title,
                   duration_s            = EXCLUDED.duration_s,
                   published_at          = EXCLUDED.published_at,
                   metadata_refreshed_at = EXCLUDED.metadata_refreshed_at
            RETURNING id
            """,
            (
                youtube_id,
                channel_id,
                accent,
                track,
                title,
                duration_s,
                published_at,
                now,
            ),
        )
        return int(cur.fetchone()[0])


def videos_needing_transcript(
    conn, *, limit: int, max_attempts: int = MAX_TRANSCRIPT_ATTEMPTS
) -> list[PoolRow]:
    """Rows worth spending money on: never fetched, or retryably failed.

    `unavailable` is terminal and is excluded -- that is the whole point of it
    being a separate state from `failed`. Ordered fewest-attempts first so a run
    that hits the limit makes progress on the backlog instead of retrying the
    same handful.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            f"""
            SELECT {_POOL_COLUMNS}
              FROM videos
             WHERE transcript_status IN ('pending', 'failed')
               AND transcript_attempts < %s
             ORDER BY transcript_attempts ASC, published_at DESC NULLS LAST
             LIMIT %s
            """,
            (max_attempts, limit),
        )
        return [_pool_row(row) for row in cur.fetchall()]


def record_transcript(
    conn, *, video_id: int, text: str, lang: str | None, kind: str | None
) -> None:
    """A successful fetch. Resets the attempt counter.

    So a video that failed twice and then worked is not one failure away from
    being set aside for good.
    """
    conn.execute(
        """
        UPDATE videos
           SET transcript            = %s,
               transcript_lang       = %s,
               captions_kind         = %s,
               transcript_status     = 'ok',
               transcript_attempts   = 0,
               transcript_last_error = NULL
         WHERE id = %s
        """,
        (text, lang, kind, video_id),
    )


def record_transcript_failure(
    conn, *, video_id: int, error: str, terminal: bool
) -> str:
    """A failed fetch. Returns the status the row now holds.

    `terminal` distinguishes "this video has no captions" from "the scraper did
    not work this time" -- the two exception classes `video_api` raises. A
    retryable failure that has exhausted its attempts becomes `unavailable` too,
    set aside rather than retried for ever, and the error text is kept so the
    reason survives the state change: an `unavailable` row with no error cannot
    be told from one that never had captions at all.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            UPDATE videos
               SET transcript_status     = CASE
                       WHEN %s THEN 'unavailable'
                       WHEN transcript_attempts + 1 >= %s THEN 'unavailable'
                       ELSE 'failed'
                   END,
                   transcript_attempts   = transcript_attempts + 1,
                   transcript_last_error = %s
             WHERE id = %s
            RETURNING transcript_status
            """,
            (terminal, MAX_TRANSCRIPT_ATTEMPTS, error[:1000], video_id),
        )
        row = cur.fetchone()
    return str(row[0]) if row else ("unavailable" if terminal else "failed")


def selectable(conn) -> list[PoolRow]:
    """Every candidate with a usable transcript. The partial index's query."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            f"""
            SELECT {_POOL_COLUMNS}
              FROM videos
             WHERE transcript_status = 'ok'
               AND transcript IS NOT NULL
             ORDER BY youtube_id
            """
        )
        return [_pool_row(row) for row in cur.fetchall()]


def purge_stale(conn, *, now: datetime, days: int = RETENTION_DAYS) -> PurgeCounts:
    """Null the metadata and transcript of every row past the retention window.

    NOT A DELETE. `youtube_id` and every `video_assignments` row survive, so a
    learner's history and `seen_penalty` are intact; what goes is the stored
    content. Migration 019's header records why the transcript is included here
    as policy and NOT as §III.E.4.d compliance -- a scraped transcript is not
    API Data, so that clause does not reach it.

    A row returns to `pending`, so the next refresh re-fetches it. **A pool that
    is not refreshed empties itself** -- there is no cron and no worker, so this
    is a real operational consequence, and `assign` refuses loudly rather than
    quietly assigning fewer than three.

    ``now`` is a parameter and not `datetime.now()` so that a test can age a row
    without waiting a month and without reading the wall clock (CLAUDE.md §3
    rule 6).
    """
    cutoff = now - timedelta(days=days)
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT count(*) FROM videos WHERE metadata_refreshed_at < %s",
            (cutoff,),
        )
        scanned = int(cur.fetchone()[0])
        cur.execute(
            """
            UPDATE videos
               SET title               = NULL,
                   duration_s          = NULL,
                   published_at        = NULL,
                   transcript          = NULL,
                   transcript_lang     = NULL,
                   captions_kind       = NULL,
                   transcript_status   = 'pending',
                   transcript_attempts = 0
             WHERE metadata_refreshed_at < %s
               AND (title IS NOT NULL OR transcript IS NOT NULL)
            RETURNING id
            """,
            (cutoff,),
        )
        purged = len(cur.fetchall())
    return PurgeCounts(scanned=scanned, purged=purged)


def pool_counts(conn) -> dict[str, int]:
    """Rows by transcript status, for the CLIs to print."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT transcript_status, count(*) FROM videos GROUP BY 1"
        )
        return {str(row[0]): int(row[1]) for row in cur.fetchall()}


# --------------------------------------------------------------------------
# Coverage -- an audit record, never read back
# --------------------------------------------------------------------------
def record_coverage(
    conn,
    *,
    user_id: int,
    video_id: int,
    report: CoverageReport,
    lexicon_digest: str,
    now: datetime | None = None,
) -> None:
    """Write what was computed, and on what basis.

    Every field of the basis is stored -- `proper_nouns_detected`, `casing`, the
    digest -- because a stored 94% and a real 94% are otherwise
    indistinguishable, and #288 is precisely a case where they differ.

    This row is NEVER READ BACK to decide anything. `assign` recomputes coverage
    on every run, so there is no cache here and no invalidation rule; the row is
    an audit record. See migration 019's PRODUCT-PRINCIPLES §3 note.
    """
    conn.execute(
        """
        INSERT INTO video_coverage (user_id, video_id, coverage,
                                    counted_tokens, excluded_tokens,
                                    proper_nouns_detected, casing,
                                    lexicon_digest, computed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, now()))
        ON CONFLICT (user_id, video_id) DO UPDATE
           SET coverage              = EXCLUDED.coverage,
               counted_tokens        = EXCLUDED.counted_tokens,
               excluded_tokens       = EXCLUDED.excluded_tokens,
               proper_nouns_detected = EXCLUDED.proper_nouns_detected,
               casing                = EXCLUDED.casing,
               lexicon_digest        = EXCLUDED.lexicon_digest,
               computed_at           = EXCLUDED.computed_at
        """,
        (
            user_id,
            video_id,
            round(report.coverage, 4),
            report.counted_tokens,
            report.excluded_tokens,
            report.proper_nouns_detected,
            report.casing,
            lexicon_digest,
            now,
        ),
    )


def degraded_coverage_count(conn) -> int:
    """Coverage rows computed with the proper-noun rule switched off (#288).

    Printed by both CLIs. Pool starvation must not present itself as "no videos
    to assign" with no visible cause.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT count(*) FROM video_coverage "
            "WHERE proper_nouns_detected = FALSE"
        )
        return int(cur.fetchone()[0])


# --------------------------------------------------------------------------
# The learner
# --------------------------------------------------------------------------
def track_weights(conn, user_id: int) -> dict[str, int] | None:
    """This learner's track weights, or None if the user id is unknown.

    `core.services.users.get_user` returns the same value but opens its OWN
    connection, so calling it from inside an open transaction would nest a
    second one and read outside it. This takes the caller's `conn`, which also
    means `assign`'s dry run reads the same row its `--apply` would write
    against.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT track_weights FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    if row is None:
        return None
    return {str(k): int(v) for k, v in (row[0] or {}).items()}


def current_unit(conn, user_id: int) -> int | None:
    """The unit this learner is working through, for `target_hit`.

    None when nothing is in progress, which is not an error: `target_hit` is
    then 0 for every candidate and drops out of the ranking rather than
    distorting it.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT unit_number FROM user_unit_state
             WHERE user_id = %s AND state = 'in_progress'
             ORDER BY unit_number
             LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
    return int(row[0]) if row else None


def onboarded_user_ids(conn) -> list[int]:
    """The learners coverage is computed for.

    Reuses `core.services.lexicon`'s definition rather than restating a
    predicate for who counts as a learner -- two answers to that question is how
    one of them goes stale.
    """
    from core.services.lexicon import onboarded_user_ids as _ids

    return _ids(conn)


# --------------------------------------------------------------------------
# Assignment
# --------------------------------------------------------------------------
def accent_exposure(conn, user_id: int) -> dict[str, int]:
    """How many videos of each accent this learner has been assigned.

    Reads `video_assignments`, not `videos.accent` alone, so exposure is a fact
    about what this learner was given and not about what the pool contains.

    **A NULL ACCENT IS EXCLUDED, AND THIS IS THE MORE SERIOUS HALF OF #315.**
    The comprehension read `{str(row[0]): int(row[1]) ...}`, so a null became a
    `"None"` KEY WITH A REAL COUNT BEHIND IT, and the damage was not confined to
    the unknown channel. `accent_rotation` computes
    ``total = sum(exposure.values())`` and ``1.0 - exposure.get(accent, 0) /
    total``, so a `"None"` bucket **inflates `total` and thereby LOWERS
    `american` and `british`** -- the corruption reaches the two real accents --
    while a `"None"` candidate whose bucket is still empty scores
    ``1.0 - 0/total = 1.0``, **the maximum the term returns.** The unknown video
    wins BECAUSE it is unknown, and the known ones are pushed down to make room.

    **The filter is in the SQL rather than in the comprehension** so that a
    later edit to the mapping cannot undo it: a null never enters the result at
    all, instead of entering and being removed. A null accent is not exposure to
    an accent, so it is not exposure.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT v.accent, count(*)
              FROM video_assignments a
              JOIN videos v ON v.id = a.video_id
             WHERE a.user_id = %s
               AND v.accent IS NOT NULL
             GROUP BY 1
            """,
            (user_id,),
        )
        return {str(row[0]): int(row[1]) for row in cur.fetchall()}


def seen_video_ids(conn, user_id: int) -> frozenset[int]:
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT DISTINCT video_id FROM video_assignments WHERE user_id = %s",
            (user_id,),
        )
        return frozenset(int(row[0]) for row in cur.fetchall())


def assigned_dates(conn, user_id: int, dates: Sequence[date]) -> set[date]:
    """Which of these dates already hold an assignment, so a re-run is a no-op.

    The unique index would refuse a duplicate anyway; asking first is what lets
    the CLI say "already assigned" instead of showing the operator a constraint
    violation.
    """
    if not dates:
        return set()
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT assigned_for FROM video_assignments
             WHERE user_id = %s AND assigned_for = ANY(%s)
            """,
            (user_id, list(dates)),
        )
        return {row[0] for row in cur.fetchall()}


def assign_video(
    conn,
    *,
    user_id: int,
    video_id: int,
    assigned_for: date,
    score_breakdown: Mapping[str, Any],
) -> int:
    """Write one assignment. `completed_at` is deliberately not written."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            INSERT INTO video_assignments (user_id, video_id, assigned_for,
                                           score_breakdown)
            VALUES (%s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (user_id, video_id, assigned_for, json.dumps(dict(score_breakdown))),
        )
        return int(cur.fetchone()[0])


def assignments_for(conn, user_id: int, *, since: date) -> list[dict]:
    """What this learner has been given, newest first. For the CLIs to print."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT a.assigned_for, a.video_id, v.youtube_id, v.title,
                   v.accent, v.track, a.resume_position_s, a.completed_at
              FROM video_assignments a
              JOIN videos v ON v.id = a.video_id
             WHERE a.user_id = %s AND a.assigned_for >= %s
             ORDER BY a.assigned_for DESC
            """,
            (user_id, since),
        )
        columns = (
            "assigned_for",
            "video_id",
            "youtube_id",
            "title",
            "accent",
            "track",
            "resume_position_s",
            "completed_at",
        )
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def _pool_row(row: tuple) -> PoolRow:
    return PoolRow(
        video_id=int(row[0]),
        youtube_id=str(row[1]),
        channel_id=str(row[2]),
        # **NOT `str(row[3])` -- #315 site (a).** A NULL accent coerced here
        # becomes the string `"None"`, which is a perfectly valid dict key and
        # a perfectly valid accent as far as every reader downstream is
        # concerned. `accent_rotation` would bucket it and score it 1.0 on its
        # first appearance, so the unknown-accent video wins BECAUSE it is
        # unknown. The null is carried, not converted.
        accent=None if row[3] is None else str(row[3]),
        track=str(row[4]),
        title=row[5],
        duration_s=row[6],
        transcript=row[7],
        captions_kind=row[8],
    )
