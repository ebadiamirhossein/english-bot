"""PRD §7.5's subtitle ladder: the only place it is read or written. W13a.

`core.video.ladder` decides what a comprehension check DOES; this module is
where a learner's position lives. **One producer (#190)**, and
`tests/test_subtitle_ladder_service.py::test_exactly_one_module_writes_the_ladder`
holds it structurally — a ladder written from two places is the defect this
record has filed nine times.

────────────────────────────────────────────────────────────────────────────────
WHAT W13a SHIPS, AND WHAT IT REPORTS UNMET

**SHIPPED: the state and the rules.** Which step a learner is on, per ladder;
promotion after two checks at >=85%, announced; demotion below 60%, silent;
reveal events, counted per window.

**REPORTED UNMET, NOT APPROXIMATED, NOT STUBBED, NOT PUT BEHIND A FLAG**
(CLAUDE.md §3 rule 7):

* **The comprehension check itself** (PRD §7.3) — the instrument every movement
  rule is defined over. It is generated content, so it is gated on the §1a
  ruling, which is unruled and is **not** to be answered before T1. **Nothing
  calls `record_check` today**, and that is asserted rather than left to be
  discovered.
* **Step 1's L1 subtitle track.** PRD §2.5: generated from the English
  transcript and cached, **never fetched from YouTube**. Generated means a model
  call, which is the same gate. **This is the bottom rung — the one every
  learner starts on — so the ladder cannot render its own first step.**
* **Step 3's per-line reveal** (*"tap any line to reveal it"*). **R12's
  measurement, inherited from W13-i so it is not rediscovered:** a generated
  track is a rolling window with no line boundaries — overlapping consecutive
  pairs at 1405/1527, 655/714, 958/1038, 897/1034, 1471/1705, 272/317, roughly
  **92% on every generated track measured** — and **all three assigned videos
  are generated**. Two workarounds stay refused on the record: merging cues into
  synthetic sentences (a generated artefact presented as the transcript's own
  structure) and shipping for manual tracks only (behaviour that appears and
  disappears on a property no learner can see).
* **Connected-speech drills from failed lines** (PRD §7.5's last paragraph) —
  generated, same gate, and they need the failed line the comprehension check
  would identify.

**AND THEREFORE: NO SURFACE.** W13a changes nothing a learner sees, and that is
a decision with a reason rather than an omission. A display switch driven by
this state would have exactly one reachable branch — every learner is on step 1,
nothing can move them, and step 1 cannot be drawn — so rendering it would mean
**silently drawing step 2 in step 1's place**, which is the approximation rule 7
forbids, on the rung that matters most. `apps/web` is untouched and **no Vercel
rebuild is owed.**

────────────────────────────────────────────────────────────────────────────────
THE TWO LADDERS, AND WHY ONE OF THEM CANNOT MOVE

PRD §7.5 keeps `youtube_curated` and `native_series` apart because the skills
are different. **Every `videos` row is a YouTube one today** — the series import
path is Language Reactor / Trancy (#172-#174) and does not exist — so
`native_series` has no producer and no row will carry it yet. **The mapping
lives in this sentence and nowhere in code**: no `videos.source_type` column was
added, because `track_kind` is a property of the ladder and a column on the
shared `videos` row would be a change to a table migration 022's row does not
name (019's ruling, from the other side).

────────────────────────────────────────────────────────────────────────────────
THE CLOCK IS INJECTED

`now` is a parameter and `datetime.now()` is called nowhere here, so a test can
walk a reveal window without freezing time (CLAUDE.md §3 rule 6) — the shape
`core.services.week` and `core.services.sessions` already use.
"""

from __future__ import annotations

from datetime import datetime

from core.db import connection
from core.video.ladder import (
    FIRST_STEP,
    STEPS,
    TRACK_KINDS,
    LadderState,
    Movement,
    apply_check,
)


def _kind(track_kind: str) -> str:
    """Refuse an unknown ladder **before** it reaches SQL.

    Migration 022's CHECK would refuse it too, and that is the point of having
    both: this one names the caller's mistake, the CHECK survives a hand
    `UPDATE`. Neither is redundant with the other.
    """
    if track_kind not in TRACK_KINDS:
        raise ValueError(
            f"track_kind must be one of {TRACK_KINDS}, got {track_kind!r}"
        )
    return track_kind


def ladder_for(user_id: int, *, track_kind: str) -> LadderState:
    """Where this learner is. **A learner with no row is on the first step.**

    **This read writes nothing.** `GET /session/today` earns its create-once
    write because block 3 cannot be paced without the row existing; nothing
    needs a ladder row to exist, and a read path that writes is how a refetch
    becomes a state change. The first INSERT is the first movement.
    """
    kind = _kind(track_kind)
    with connection() as conn:
        row = conn.execute(
            "SELECT step, passes_at_step FROM subtitle_ladder "
            " WHERE user_id = %s AND track_kind = %s",
            (user_id, kind),
        ).fetchone()
    if row is None:
        return LadderState(step=FIRST_STEP, passes_at_step=0)
    return LadderState(step=int(row["step"]), passes_at_step=int(row["passes_at_step"]))


def record_check(
    user_id: int, *, track_kind: str, score_pct: int, now: datetime
) -> Movement:
    """Apply one comprehension check and store the result. Returns what moved.

    **THE MOVEMENT IS RETURNED RATHER THAN LEFT TO BE RE-DERIVED**, because the
    caller has to know whether to announce — and a caller that recomputed
    "did I go up?" from the before and after states would be a second copy of
    the rule (#132's family). `Movement.announce` is true only for a promotion:
    *raises announced, drops silent*, and a demotion message would be a guilt
    message with no banned word in it (CLAUDE.md §4, and #348 is that exact
    mistake shipping today).

    **`entered_step_at` moves only when the step does.** A clock that restarted
    on every check could not tell a long step from a new one, which is the only
    thing it is for.

    **NOTHING CALLS THIS YET.** Its caller is the comprehension check, which is
    generated content gated on §1a — see this module's banner. The absence is
    asserted by a test so that acquiring a caller is a deliberate act.
    """
    kind = _kind(track_kind)
    before = ladder_for(user_id, track_kind=kind)
    movement = apply_check(before, score_pct)
    after = movement.state
    moved = after.step != before.step

    with connection() as conn:
        conn.execute(
            """
            INSERT INTO subtitle_ladder
                (user_id, track_kind, step, passes_at_step, entered_step_at,
                 updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, track_kind) DO UPDATE
               SET step = EXCLUDED.step,
                   passes_at_step = EXCLUDED.passes_at_step,
                   -- The arrival clock survives a check that moved nothing.
                   entered_step_at = CASE
                       WHEN subtitle_ladder.step = EXCLUDED.step
                       THEN subtitle_ladder.entered_step_at
                       ELSE EXCLUDED.entered_step_at
                   END,
                   updated_at = EXCLUDED.updated_at
            """,
            (user_id, kind, after.step, after.passes_at_step, now, now),
        )
        conn.commit()
    return movement


def record_reveal(
    user_id: int,
    *,
    track_kind: str,
    step: int,
    video_id: int | None,
    now: datetime,
) -> None:
    """Log one reveal. **An event, not a counter, and it carries its step.**

    PRD §7.5 wants *"a number that goes down over weeks"*, and a lifetime
    counter can only ever go up. The window count is computed from these rows,
    so any window can be asked for after the fact — which a column could never
    have given back.

    **THE STEP IS STORED BECAUSE PRD §7.5 COUNTS STEP 4's REVEALS**, not every
    reveal: step 3's *tap any line* is the safety net and is explicitly not the
    measure. An undifferentiated log could never be separated out again — the
    same history-you-did-not-keep argument that made this a table.

    **NOTHING CALLS THIS YET** either: the reveal control belongs to steps 3 and
    4, and step 3's *tap any line* has no line to tap on a generated track (R12).
    """
    kind = _kind(track_kind)
    if step not in STEPS:
        raise ValueError(f"step must be one of {STEPS}, got {step!r}")
    with connection() as conn:
        conn.execute(
            "INSERT INTO subtitle_reveals (user_id, track_kind, step, video_id, "
            "revealed_at) VALUES (%s, %s, %s, %s, %s)",
            (user_id, kind, step, video_id, now),
        )
        conn.commit()


def reveals_between(
    user_id: int,
    *,
    track_kind: str,
    start: datetime,
    end: datetime,
    step: int | None = None,
) -> int:
    """Reveals in `[start, end)`. Half-open, so two adjacent windows cannot both
    claim the same reveal — the same boundary rule `core.services.week` uses.

    `step` narrows to one rung. **PRD §7.5's headline number is `step=4`** —
    *"reveals in step 4 are counted and shown as a number that goes down over
    weeks"* — and the default of `None` counts every reveal, which is a
    different and also true number. **The caller says which it means**; a
    function that silently returned one of them under a name that reads like the
    other is how a figure ends up meaning something nobody chose.
    """
    kind = _kind(track_kind)
    if step is not None and step not in STEPS:
        raise ValueError(f"step must be one of {STEPS} or None, got {step!r}")
    with connection() as conn:
        row = conn.execute(
            """
            SELECT count(*) AS n FROM subtitle_reveals
             WHERE user_id = %s AND track_kind = %s
               AND revealed_at >= %s AND revealed_at < %s
               AND (%s::smallint IS NULL OR step = %s)
            """,
            (user_id, kind, start, end, step, step),
        ).fetchone()
    return int(row["n"])
