"""W19: the progress screen — five numbers, each traced to a real ledger.

PRD §9, *gamification — the honest kind*, as the build run's rulings scope it
(2026-09-25). **Every number here is computed from a table a learner's own act
wrote, and the table is named beside it:**

    known_words     user_lexemes — `evidenced_known_count`: known/mastered rows
                    whose source is NOT `assumption` (W4's ruling). The floor
                    never inflates it.
    known_history   progress_snapshots (029) — that same count, one point per
                    day the screen was read. **The line is drawn from this or
                    not at all**; there is no reconstruction from `updated_at`.
    xp              the five activity logs, weighted by effort (`XP_WEIGHTS`),
                    held by 029's high-water mark so it never goes down on screen.
    streak_days     streaks (v2's rollover, unchanged in its rules) plus today,
                    and any day since the last rollover, when the learner
                    practised (`core.services.activity`, #259's one signal).
    freezes         streaks.freeze_tokens.
    units_passed    user_unit_state — `passed` or `mastered`.

**WHAT IS NOT HERE, REPORTED AS AN ABSENCE AND NEVER FILLED (CLAUDE.md §1a,
§3 rule 7):**

* ~~**The radar and placement history** need placement (W18, blocked on its
  item bank). Not approximated from `users.cefr_level` or the v2
  `calibration_log`: neither measures the five skills the radar draws.~~
  **TURNED ON BY W18 (2026-09-25), the old text struck above rather than
  deleted (#82's shape):** `placement` is `core.services.placement.shown_for` —
  the radar as bands per measured skill and the history as the band shown
  after each sitting, both high-water marks (drops are silent, CLAUDE.md §4),
  read from `placement_runs` (032). Still not approximated from
  `users.cefr_level` or `calibration_log`. **Two of PRD §6's five axes stay
  unmet** — reading (no reading section) and pronunciation (the Azure
  assessment was retired) — and are not drawn.
* **The six-month TARGET line.** PRD §11's target is *+1,800 lemmas over a
  baseline measured in week 1* — by placement. Without W18 there is no
  baseline, and a target drawn from the first snapshot of an evidenced-only
  count (small by design until placement) would be a target nobody measured.
  The learner's own line is drawn; the target is not.
* **Units MASTERED.** Nothing writes `mastered` (#135 — no retention metric), so
  the screen says *passed*, which is what the ledger holds.
* **The couple leaderboard** — dropped by scope ruling: a ranking between the
  two learners is a score on one of them (CLAUDE.md §4, the guilt ban).
* `sessions.xp`, `minutes`, `completed_at` are NOT read (#349): XP is computed
  from the logs, not per session, and the other two have no writer.

**NO NUMBER HERE COUNTS WHAT WAS NOT DONE.** No missed days, no remaining, no
shortfall against a target, no comparison with the partner. Zeros are returned
honestly and the SCREEN decides not to draw them (W11b's split, one place).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.rows import tuple_row

from core.db import connection
from core.items import RESPONSE_MODE
from core.services.activity import practised_dates
from core.services.lexicon import evidenced_known_count
from core.services.placement import shown_for as placement_shown

#: PRD §9: *"XP weighted by cognitive effort. Production > recognition.
#: Speaking a sentence: 10. Typing an L1→L2 production item: 6. Tapping an
#: MCQ: 2."* The three PRD numbers are kept exactly; the other two are W19's,
#: placed on the same scale:
#:
#: * ``writing`` — an English journal entry or paragraph (`writing_submissions`,
#:   `is_english`). A piece is several sentences of typed production, so it is
#:   worth two typed items. Its text is not stored (§5), so sentences cannot be
#:   counted and the piece is the unit.
#: * ``video`` — a video watched to its end (`video_assignments.completed_at`).
#:   Input, not production: above a tap, below a typed sentence.
#:
#: **What the ledger EVIDENCES is what is weighted, never what was claimed.** A
#: self-marked `speak_repeat`/`speak_answer` (``graded_by = 'self'``) recorded a
#: TAP on *I said it* — no audio exists — so it earns ``tap``. A voice turn in a
#: talk or a rung is evidenced by its transcription (`conversation_usage.
#: stt_calls`) and earns ``spoken``. A card graded with a typed answer
#: (`card_reviews.typed_response`) earns ``typed``; a card graded by a button
#: earns ``tap``.
XP_WEIGHTS: dict[str, int] = {
    "spoken": 10,
    "writing": 12,
    "typed": 6,
    "video": 4,
    "tap": 2,
}

#: The known-word line spans six months — PRD §11's horizon.
HISTORY_DAYS = 183

#: The streak's lookback when the rollover has never evaluated a day — the
#: rollover's own backfill cap (`core.services.streaks.BACKFILL_MAX_DAYS`).
_UNEVALUATED_LOOKBACK_DAYS = 30


@dataclass(frozen=True, slots=True)
class KnownPoint:
    local_date: date
    known_words: int


@dataclass(frozen=True, slots=True)
class Progress:
    """The progress screen, as numbers. **No field counts an absence.**"""

    known_words: int
    #: Ascending by date, inside the last `HISTORY_DAYS`. Today's point is
    #: always present after a read.
    known_history: tuple[KnownPoint, ...]
    xp: int
    streak_days: int
    freezes: int
    units_passed: int
    #: W18: the high-water view of finished placements, or None before the
    #: first. `core.placement.scoring.Shown`.
    placement: Any = None


def xp_counts(conn: Any, user_id: int) -> dict[str, int]:
    """How many acts of each effort class the logs hold for this learner.

    Separate from `xp_total` so a test can assert the classification against
    counts it seeded itself, never against the weighted sum it is checking.
    """
    counts = {k: 0 for k in XP_WEIGHTS}
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT i.item_type, a.graded_by, COUNT(*)
              FROM item_attempts a
              JOIN items i ON i.id = a.item_id AND i.user_id = a.user_id
             WHERE a.user_id = %s
             GROUP BY 1, 2
            """,
            (user_id,),
        )
        for item_type, graded_by, n in cur.fetchall():
            mode = RESPONSE_MODE.get(str(item_type), "tap")
            if mode == "spoken" and graded_by == "self":
                mode = "tap"
            counts[mode] += int(n)

        cur.execute(
            """
            SELECT COUNT(*) FILTER (WHERE typed_response IS NOT NULL),
                   COUNT(*) FILTER (WHERE typed_response IS NULL)
              FROM card_reviews
             WHERE user_id = %s
            """,
            (user_id,),
        )
        typed_cards, tapped_cards = cur.fetchone()
        counts["typed"] += int(typed_cards)
        counts["tap"] += int(tapped_cards)

        # A voice turn is one transcription; a transcription that never became
        # a turn (the cap, an empty result) is bounded out by LEAST.
        cur.execute(
            """
            SELECT COALESCE(SUM(turns_learner), 0),
                   COALESCE(SUM(LEAST(stt_calls, turns_learner)), 0)
              FROM conversation_usage
             WHERE user_id = %s
            """,
            (user_id,),
        )
        turns, spoken = cur.fetchone()
        counts["spoken"] += int(spoken)
        counts["typed"] += int(turns) - int(spoken)

        cur.execute(
            "SELECT COUNT(*) FROM writing_submissions WHERE user_id = %s AND is_english",
            (user_id,),
        )
        counts["writing"] += int(cur.fetchone()[0])

        cur.execute(
            "SELECT COUNT(*) FROM video_assignments "
            "WHERE user_id = %s AND completed_at IS NOT NULL",
            (user_id,),
        )
        counts["video"] += int(cur.fetchone()[0])
    return counts


def xp_total(conn: Any, user_id: int) -> int:
    """The weighted sum of `xp_counts`. Computed, before the high-water mark."""
    counts = xp_counts(conn, user_id)
    return sum(XP_WEIGHTS[k] * n for k, n in counts.items())


def _streak_days(conn: Any, user_id: int, today: date) -> tuple[int, int]:
    """``(streak_days, freeze_tokens)``; ``(0, 0)`` without a `streaks` row.

    The stored streak is the rollover's, evaluated through `last_evaluated_date`
    (03:00 the next morning at the earliest). **Days after it are added when the
    learner practised on them**, so practising today moves the number today
    rather than tomorrow at 03:00. Unpractised days after it are Neutral under
    v2's rule and change nothing — only the rollover can decide a Missed day,
    and it may spend a freeze on one, so this adds and never subtracts.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT current_streak, freeze_tokens, last_evaluated_date "
            "FROM streaks WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
    if row is None:
        return 0, 0
    current, tokens, last_eval = int(row[0]), int(row[1]), row[2]
    start = (
        last_eval + timedelta(days=1)
        if last_eval is not None
        else today - timedelta(days=_UNEVALUATED_LOOKBACK_DAYS - 1)
    )
    extra = len(practised_dates(conn, user_id, start=start, end=today)) if start <= today else 0
    return current + extra, tokens


def progress_summary(user_id: int, *, now: datetime) -> Progress | None:
    """This learner's progress. ``None`` for an unknown user.

    **The one function `GET /progress` calls.** It WRITES one row: today's
    `progress_snapshots` point, upserted — the known count as it is now, and
    XP as the larger of what was stored and what is computed. That write is
    the history the line is drawn from and the mark that keeps XP from
    dropping; a read that could not write it would have neither. Idempotent: a
    second read the same day changes the known count to the current one and can
    only raise XP. `GET /session/today` persists `block_breakdown` from a GET
    for the same kind of reason.

    ``now`` is injected; `datetime.now()` is called nowhere here (CLAUDE.md §3
    rule 6).
    """
    with connection() as conn:
        with conn.cursor(row_factory=tuple_row) as cur:
            cur.execute("SELECT timezone FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        if row is None:
            return None
        tz = str(row[0] or "Europe/Vilnius")
        today = now.astimezone(ZoneInfo(tz)).date()

        known = evidenced_known_count(conn, user_id)
        computed_xp = xp_total(conn, user_id)
        streak_days, freezes = _streak_days(conn, user_id, today)

        with conn.cursor(row_factory=tuple_row) as cur:
            cur.execute(
                """
                INSERT INTO progress_snapshots (user_id, local_date, known_words, xp)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, local_date) DO UPDATE
                   SET known_words = EXCLUDED.known_words,
                       xp          = GREATEST(progress_snapshots.xp, EXCLUDED.xp),
                       recorded_at = now()
                """,
                (user_id, today, known, computed_xp),
            )
            cur.execute(
                "SELECT COALESCE(MAX(xp), 0) FROM progress_snapshots WHERE user_id = %s",
                (user_id,),
            )
            shown_xp = max(int(cur.fetchone()[0]), computed_xp)
            cur.execute(
                """
                SELECT local_date, known_words
                  FROM progress_snapshots
                 WHERE user_id = %s
                   AND local_date > %s
                 ORDER BY local_date
                """,
                (user_id, today - timedelta(days=HISTORY_DAYS)),
            )
            history = tuple(KnownPoint(r[0], int(r[1])) for r in cur.fetchall())
            cur.execute(
                """
                SELECT COUNT(*) FROM user_unit_state
                 WHERE user_id = %s AND state IN ('passed', 'mastered')
                """,
                (user_id,),
            )
            units = int(cur.fetchone()[0])
        placement = placement_shown(conn, user_id)
        conn.commit()

    return Progress(
        known_words=known,
        known_history=history,
        xp=shown_xp,
        streak_days=streak_days,
        freezes=freezes,
        units_passed=units,
        placement=placement,
    )
