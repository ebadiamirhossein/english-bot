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
- **It never deletes a `videos` row** (above), and until W13 it never wrote
  `video_assignments.completed_at` either. **THAT SECOND CLAUSE IS SPENT AND IS
  QUOTED RATHER THAN DELETED (#82's shape):** *"It never writes
  `video_assignments.completed_at`. W12b does not define what 'answered' means
  for block 2 -- no player exists, so no watch signal can be written. That is
  W13's, and a definition guessed here would be a wrong row in a table the
  record treats as the product."*

  **W13 defines it (#291), and `save_progress` is the ONE producer.** See that
  function and `core.video.watch`. `assign_video` still writes neither column,
  which is the half of the guarantee that was worth keeping.
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

    **`transcript_attempts < max_attempts` IS THE ONLY THING SETTING AN
    EXHAUSTED ROW ASIDE, AND SINCE 2026-09-01 IT IS THE ONLY THING THAT
    SHOULD BE.** `record_transcript_failure` no longer promotes an exhausted
    retryable failure to `unavailable`; such a row stays `failed` and this
    predicate excludes it. So the two facts stay separate in the column --
    *what is true of the video* in the status, *how hard we tried* in the
    counter -- and resetting the counter is the single door back in (#322).
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
    conn,
    *,
    video_id: int,
    text: str,
    lang: str | None,
    kind: str | None,
    cues: Any = None,
) -> bool:
    """A successful fetch. Resets the attempt counter.

    So a video that failed twice and then worked is not one failure away from
    being set aside for good.

    **RETURNS WHETHER THE CUES WERE STORED**, so the caller can count a refusal
    where the operator will see it. `False` never means the text was rejected --
    the transcript is always written.

    **THE IDENTITY GATE IS HERE AND NOT ONLY IN THE BACKFILL (S2).** The cues
    are stored only if joining them reproduces `text` exactly, by md5, through
    `core.video.cues.reproduces` -- the SAME function the backfill calls, so the
    two gates cannot drift into disagreeing about what identity means.

    **ON A MISMATCH: STORE THE TEXT, REFUSE THE CUES.** Not repair, not
    store-anyway, not raise. The row then holds a transcript and no cues, which
    is a **specified and survivable** state -- it renders, its words stay
    tappable, the coverage badge still shows, and there is no highlight. A row
    whose cues describe DIFFERENT text is the state that must never exist:
    coverage computed over one string and the highlight over another, **silent,
    because the highlight would still land somewhere plausible.**

    **WHY A GATE AT ALL, WHEN T5 MEASURED THE IDENTITY.** T5 measured eleven
    rows from `johnvc/YoutubeTranscripts`. That is evidence about **that actor on
    those rows**, not a property of the pipeline.
    `codepoetry/youtube-transcript-ai-scraper` is the ruled fallback, is in the
    adapter table, and **has never been measured** -- and #288 is this project
    already caught inheriting one provider's premise as a fact about all of them,
    at a cost that took a production measurement to find. **A guarantee that
    covers the rows already written and not the rows about to be written is the
    family this record keeps re-filing.**
    """
    from core.video.cues import normalise_cues, reproduces

    checked = normalise_cues(cues)
    stored = checked is not None and reproduces(checked, text)

    conn.execute(
        """
        UPDATE videos
           SET transcript            = %s,
               transcript_cues       = %s::jsonb,
               transcript_lang       = %s,
               captions_kind         = %s,
               transcript_status     = 'ok',
               transcript_attempts   = 0,
               transcript_last_error = NULL
         WHERE id = %s
        """,
        (
            text,
            json.dumps(checked) if stored else None,
            lang,
            kind,
            video_id,
        ),
    )
    return stored


def record_transcript_failure(
    conn, *, video_id: int, error: str, terminal: bool
) -> str:
    """A failed fetch. Returns the status the row now holds.

    `terminal` distinguishes "this video has no captions" from "the scraper did
    not work this time", and the error text is kept either way so the reason
    survives the state change: an `unavailable` row with no error cannot be told
    from one that never had captions at all.

    **`unavailable` NOW HAS EXACTLY ONE PRODUCER, AND THAT IS THE CHANGE
    (operator ruling, 2026-09-01, #322 and #324).** It used to have two: a
    terminal verdict, and *a retryable failure that had exhausted its
    attempts*. The second door is closed. An exhausted row stays **`failed`**.

    **WHY, AND IT IS NOT A LOOSENING.** The exhausted row is already excluded
    from the pool by `videos_needing_transcript`'s `transcript_attempts <
    max_attempts` predicate, so the status change bought no exclusion -- what it
    did was destroy the distinction between *this video has no captions* and
    *we gave up on it*, writing the first claim on the evidence for the second.
    **`unavailable` means the free listing enumerated the tracks and found
    none. Nothing else may write it.**

    **AND IT IS WHAT MAKES A RESET WORK.** Fixing the query (#324) and setting
    four rows back to `pending, attempts 0` is worth nothing if a second bad run
    walks them through the other door to the same permanent verdict. Exhaustion
    is expressed by `transcript_attempts`, which a reset clears; the status is
    reserved for what is true about the video.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            UPDATE videos
               SET transcript_status     = CASE
                       WHEN %s THEN 'unavailable'
                       ELSE 'failed'
                   END,
                   transcript_attempts   = transcript_attempts + 1,
                   transcript_last_error = %s
             WHERE id = %s
            RETURNING transcript_status
            """,
            (terminal, error[:1000], video_id),
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
    is not refreshed empties itself.** *(This read "there is no cron and no
    worker" until W24r.)* Since W24r the worker's weekly `refresh_videos` runs
    this same purge every Monday -- while `VIDEO_AUTO_REFRESH=1` is set; without
    it, the operator's `--live --apply` is still the only refresh.

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
                   -- **THE CUES JOIN THIS STATEMENT AND DO NOT GET ONE OF
                   -- THEIR OWN (migration 021).** They are a property of the
                   -- transcript -- same provenance, same lifecycle, same 30-day
                   -- policy -- so a second purge path would be a SECOND CLOCK
                   -- over one fact. Cues outliving the text they index would be
                   -- offsets into a string that is gone.
                   transcript_cues     = NULL,
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


def learner_timezones(conn) -> list[tuple[int, str]]:
    """``(users.id, timezone)`` for every approved, onboarded learner. **W24d.**

    The worker's daily assignment needs each learner's LOCAL date, so it needs
    the timezone beside the id; `approved_onboarded_users` is the same predicate
    every other scheduled pass uses (`core.scheduling.list_candidate_users`),
    with the same `Europe/Vilnius` default.
    """
    rows = conn.execute(
        "SELECT id, COALESCE(timezone, 'Europe/Vilnius') AS tz "
        "FROM approved_onboarded_users ORDER BY id"
    ).fetchall()
    out = []
    for row in rows:
        values = tuple(row.values()) if isinstance(row, dict) else tuple(row)
        out.append((int(values[0]), str(values[1])))
    return out


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


def assigned_dates(
    conn, user_id: int, dates: Sequence[date], *, kind: str = "daily"
) -> set[date]:
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
             WHERE user_id = %s AND assigned_for = ANY(%s) AND kind = %s
            """,
            (user_id, list(dates), kind),
        )
        return {row[0] for row in cur.fetchall()}


def assign_video(
    conn,
    *,
    user_id: int,
    video_id: int,
    assigned_for: date,
    score_breakdown: Mapping[str, Any],
    kind: str = "daily",
) -> int:
    """Write one assignment. **`completed_at` is deliberately not written here.**

    **W24d: `kind` is `daily` (block 2) or `extra` (keep going's watch-another,
    W24e)** -- migration 034 allows one of each per date. Whichever it is, the
    row is *seen* from then on: `seen_video_ids` reads every kind.

    Assigning a video does not complete it, and that separation is what
    `tests/test_video_service.py::test_assigning_a_video_does_not_complete_it`
    holds. The writer is `save_progress` and it is the only one (#291).
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            INSERT INTO video_assignments (user_id, video_id, assigned_for,
                                           score_breakdown, kind)
            VALUES (%s, %s, %s, %s::jsonb, %s)
            RETURNING id
            """,
            (user_id, video_id, assigned_for, json.dumps(dict(score_breakdown)), kind),
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


# --------------------------------------------------------------------------
# W13-i: the player's read, and the watch signal (#291)
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class TodayVideo:
    """One assigned video, as the player needs it. **One day, one row.**

    **NOT `assignments_for`, deliberately.** That function is a RANGE read
    (`assigned_for >= since`) returning plain dicts *"for the CLIs to print"* --
    its own docstring -- and it carries no transcript. Widening it to serve a
    learner would give one function two callers with different needs, and the
    CLI's shape would start deciding what a player receives.

    **`transcript is None` IS A STATE AND NOT AN ERROR (#335).** The 30-day
    purge nulls the transcript and returns the row to `pending`, and nothing
    coordinates that with the weekly assignment -- so a learner can open a day
    whose video is still assigned and still watchable while the interactive half
    is gone. The row is RETURNED in that state rather than filtered, because
    *no video today* and *a video whose transcript was purged* are different
    facts and the learner can only see one of them on the screen.
    """

    assignment_id: int
    video_id: int
    youtube_id: str
    title: str | None
    duration_s: int | None
    accent: str | None
    track: str
    transcript: str | None
    #: Per-cue timings (migration 021), or **None meaning the third state**:
    #: transcript present, cues absent. Specified, not a gap -- the transcript
    #: renders, its words stay tappable, the coverage badge still shows, and
    #: there is no highlight. **The normal case for every pool row the backfill
    #: did not reach**, and nothing refreshes on a schedule (#69) to drain it.
    transcript_cues: list | None
    transcript_lang: str | None
    captions_kind: str | None
    resume_position_s: int
    completed_at: datetime | None


def today_for(
    conn, user_id: int, *, on: date, kind: str = "daily"
) -> TodayVideo | None:
    """This learner's assigned video for one date, or None.

    **None is *no video today*, never a failure**, and block 2 renders it
    `empty` -- a fact computed after a successful read, which is `BLOCK_STATES`'
    own distinction. *(W24d, 2026-09-27: this read "**None is the ordinary state
    on four days in seven.** PRD §7.1 puts curated video on Monday, Wednesday and
    Friday" until operator decision 2 made video daily. None is now the state of
    a day the pool had nothing in band and unseen for -- daily when available.)*

    **`kind` (W24d, migration 034):** block 2 reads `daily`; W24e's keep-going
    reads the day's `extra`.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT a.id, a.video_id, v.youtube_id, v.title, v.duration_s,
                   v.accent, v.track, v.transcript, v.transcript_cues,
                   v.transcript_lang, v.captions_kind, a.resume_position_s,
                   a.completed_at
              FROM video_assignments a
              JOIN videos v ON v.id = a.video_id
             WHERE a.user_id = %s AND a.assigned_for = %s AND a.kind = %s
            """,
            (user_id, on, kind),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return TodayVideo(
        assignment_id=int(row[0]),
        video_id=int(row[1]),
        youtube_id=str(row[2]),
        title=row[3],
        duration_s=row[4],
        accent=None if row[5] is None else str(row[5]),
        track=str(row[6]),
        transcript=row[7],
        transcript_cues=row[8],
        transcript_lang=row[9],
        captions_kind=row[10],
        resume_position_s=int(row[11] or 0),
        completed_at=row[12],
    )


def save_progress(
    conn,
    *,
    user_id: int,
    video_id: int,
    position_s: int | None,
    now: datetime,
) -> TodayVideo | None:
    """The progress ping. **THE ONE PRODUCER OF BOTH COLUMNS (#190, #291).**

    **This function IS block 2's log**, and that is the whole of the #258
    argument. The ruling of 2026-08-29 made block completion automatic and
    deleted the manual button, its route and its service function; its per-kind
    rule turns on whether a block has a per-attempt log keyed on the session --
    `review` has `card_reviews`, `focus` has `item_attempts`, and `input` was
    *"`empty`, never `done`"* because it **served nothing and so had no log.**
    W13 makes it serve something and writes the log. **The ruling is honoured by
    supplying the evidence it asks for, not by adding a tap**, and no completion
    control exists on the player.

    **ONE STATEMENT WRITES BOTH COLUMNS**, so a position and the completion it
    implies can never disagree -- #190's *one contract, one producer* applied
    before the defect rather than after it. `core.video.watch` decides both
    values and is pure, so the rule is assertable without Postgres.

    **`completed_at` IS WRITTEN ONCE AND NEVER MOVED.** `COALESCE` keeps the
    first completion: re-watching a video the learner already finished is not a
    second completion, and overwriting the timestamp would make *when did they
    finish this* unanswerable from the row that exists to answer it.

    Returns the refreshed row, so the route serialises what was actually stored
    rather than what it hoped was -- the clamp lives in `watch.clamp_position`
    and a caller must not have to reproduce it to know the result.
    """
    from core.video.watch import clamp_position, is_complete

    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT duration_s FROM videos WHERE id = %s", (video_id,)
        )
        row = cur.fetchone()
    if row is None:
        return None
    duration_s = row[0]

    position = clamp_position(position_s, duration_s)
    complete = is_complete(position, duration_s)

    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            UPDATE video_assignments
               SET resume_position_s = %s,
                   completed_at      = CASE
                       WHEN %s THEN COALESCE(completed_at, %s)
                       ELSE completed_at
                   END
             WHERE user_id = %s AND video_id = %s
            RETURNING assigned_for, kind
            """,
            (position, complete, now, user_id, video_id),
        )
        updated = cur.fetchone()
    if updated is None:
        # Not this learner's video, or not assigned at all. The route turns this
        # into a 404 rather than a silent success -- a ping that wrote nothing
        # and said it wrote something is the shape #298 spent a whole row on.
        return None
    return today_for(conn, user_id, on=updated[0], kind=updated[1])


def watched_video_ids(conn, user_id: int) -> frozenset[int]:
    """Videos this learner has finished. Block 2's `_derive_done` reads this."""
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT video_id FROM video_assignments "
            "WHERE user_id = %s AND completed_at IS NOT NULL",
            (user_id,),
        )
        return frozenset(int(row[0]) for row in cur.fetchall())


def today_for_user(user_id: int, *, now: datetime) -> TodayVideo | None:
    """`today_for`, for a caller that has no connection and no date.

    **THE ONE FUNCTION `GET /video/today` CALLS** (CLAUDE.md §2: a route parses,
    authorises, calls one service function, serialises). Without it the route
    would have to open a connection, read the learner's timezone, compute their
    local date and then call `today_for` -- four steps, three of them business
    logic, in a layer that is not allowed any.

    **WHOSE DATE: THE LEARNER'S.** `local_today(users.timezone, now)`, the same
    resolution `core.services.sessions` uses for every `sessions.date` in the
    table, reached through the same helper rather than restated -- two answers to
    *what day is it for this learner* is how one of them goes stale. `now` is
    injected, like every other clock in this module, so a date boundary is
    assertable without freezing the wall clock (CLAUDE.md §3 rule 6).

    None when the learner is unknown OR when nothing is assigned for their date,
    and the route turns both into a 404. **They are different facts and the
    route does not need to tell them apart**: neither is an error and neither
    changes what the client shows.
    """
    from core.db import connection
    from core.services.sessions import local_today

    with connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(timezone, 'Europe/Vilnius') AS tz FROM users"
            " WHERE id = %s",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return today_for(conn, user_id, on=local_today(row["tz"], now))


def save_progress_for_user(
    user_id: int, video_id: int, *, position_s: int | None, now: datetime
) -> TodayVideo | None:
    """`save_progress`, for a caller that has no connection.

    **THE ONE FUNCTION `POST /video/{id}/progress` CALLS**, for the same reason
    `today_for_user` exists: the route must not hold a connection or decide when
    to commit. The write and the read-back happen in ONE transaction, so the row
    the client is handed is the row that was stored -- not a second read that
    could see someone else's write between them.
    """
    from core.db import connection

    with connection() as conn:
        updated = save_progress(
            conn,
            user_id=user_id,
            video_id=video_id,
            position_s=position_s,
            now=now,
        )
        conn.commit()
    return updated


def rows_needing_cues(conn) -> list[tuple[int, str, str]]:
    """`(video_id, youtube_id, transcript)` for every row the backfill could fill.

    **This is the third state's population, and it is a QUERY rather than an
    estimate** (#268). A row with a transcript and no cues renders, stays
    tappable and keeps its badge -- it simply has no highlight -- and nothing
    drains it on a schedule, because there is no cron and no worker (#69).
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT id, youtube_id, transcript
              FROM videos
             WHERE transcript IS NOT NULL
               AND transcript_cues IS NULL
             ORDER BY youtube_id
            """
        )
        return [(int(r[0]), str(r[1]), str(r[2])) for r in cur.fetchall()]


def record_cues(conn, *, video_id: int, cues: Any, text: str) -> bool:
    """The backfill's write. **Gated on the same identity check as the fetch.**

    Returns whether it wrote. `False` means the join did not reproduce the
    stored transcript, and the caller **reports and skips** -- never repairs. A
    mismatch means the stored text came from a different fetch than the cues,
    and writing anyway is the two-instruments-on-one-screen failure T5's fifth
    question existed to prevent.

    **REFUSES TO OVERWRITE A NON-NULL `transcript_cues`.** The `WHERE` clause
    carries it, so a second run is a no-op at the database rather than by the
    caller's good manners -- the same reasoning 015's partial UNIQUE uses for
    putting an idempotency guarantee in the schema rather than in today's
    creator.
    """
    from core.video.cues import normalise_cues, reproduces

    checked = normalise_cues(cues)
    if checked is None or not reproduces(checked, text):
        return False
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            UPDATE videos
               SET transcript_cues = %s::jsonb
             WHERE id = %s
               AND transcript_cues IS NULL
               AND transcript = %s
            RETURNING id
            """,
            (json.dumps(checked), video_id, text),
        )
        return cur.fetchone() is not None
