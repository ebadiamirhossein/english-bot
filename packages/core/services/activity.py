"""W19: *did this learner practise on this day?* — one answer, read from the logs.

**#259's fix, and the reason it lives in its own module.** Until W19 every
consumer of "an active day" asked `sessions.completed = TRUE`, and **no `daily`
row has ever carried that flag**: block 4 cannot self-report (#258), and W11
removed the button that set it. So a learner who did the web session every day
read as inactive to the streak rollover, to `count_active_days` (the v2 stats
and the operator panel) and to the nudge ladder, which could nudge them to
practise on a day they had practised. #259's own row names the constraint on
the fix: **whichever signal is chosen for *this learner did the work* should
feed every consumer**, because choosing two is how two surfaces start to
disagree about the same day. This is that one signal; `streaks`, `sessions` and
`motivation` all read it.

**WHAT COUNTS — AN ACT THE LEARNER PERFORMED, RECORDED IN A LOG, ON THAT LOCAL
DAY.** Never *opened the app*: a `daily` `sessions` row is created by a GET, so
counting it would make hydration practice (#259's warning, and the refusal
`day_in_unit`'s docstring makes one column over). The five logs:

    item_attempts        attempted_at     an item answered (block 3, checkpoint, drill)
    card_reviews         reviewed_at      a card graded
    conversation_usage   local_date       a turn the learner sent (talk, answer, retell)
                                          — `turns_learner > 0`
    writing_submissions  local_date       an entry written IN ENGLISH (`is_english`);
                                          a non-English one spent a call and is not
                                          the learner's English (W16a's S2 ruling)
    video_assignments    completed_at     a video watched to its end

**Local dates, never UTC.** The instants are converted through
`users.timezone`, so a review at 23:30 in Vilnius is that day's, as
`core.services.week` does. `conversation_usage` and `writing_submissions`
already store the learner's local date and are read as they are.

**What this does NOT decide:** what a *missed* day is. v2's rule (an
incomplete `quiz`) is kept unchanged in `core.services.streaks`; the web has no
missed state because nothing is delivered to a learner unasked until W20's
push. That is filed (#431) rather than invented here.

SQL lives here and nowhere above it (CLAUDE.md §2). No FastAPI, no HTTP.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from psycopg.rows import tuple_row

#: The five logs, as one UNION. Each arm yields local dates for one user inside
#: [start, end]. `%(tz)s` is the learner's timezone; timestamps are converted
#: with `AT TIME ZONE` so the date is the learner's calendar day.
_PRACTISED_DATES_SQL = """
    SELECT (attempted_at AT TIME ZONE %(tz)s)::date AS d
      FROM item_attempts
     WHERE user_id = %(uid)s
       AND (attempted_at AT TIME ZONE %(tz)s)::date BETWEEN %(start)s AND %(end)s
    UNION
    SELECT (reviewed_at AT TIME ZONE %(tz)s)::date
      FROM card_reviews
     WHERE user_id = %(uid)s
       AND (reviewed_at AT TIME ZONE %(tz)s)::date BETWEEN %(start)s AND %(end)s
    UNION
    SELECT local_date
      FROM conversation_usage
     WHERE user_id = %(uid)s
       AND turns_learner > 0
       AND local_date BETWEEN %(start)s AND %(end)s
    UNION
    SELECT local_date
      FROM writing_submissions
     WHERE user_id = %(uid)s
       AND is_english
       AND local_date BETWEEN %(start)s AND %(end)s
    UNION
    SELECT (completed_at AT TIME ZONE %(tz)s)::date
      FROM video_assignments
     WHERE user_id = %(uid)s
       AND completed_at IS NOT NULL
       AND (completed_at AT TIME ZONE %(tz)s)::date BETWEEN %(start)s AND %(end)s
"""


def practised_dates(conn: Any, user_id: int, *, start: date, end: date) -> set[date]:
    """Local dates in ``[start, end]`` on which this learner practised.

    Empty for an unknown user. Takes an open connection so a caller already
    inside a transaction (the streak rollover holds `FOR UPDATE`) reads through
    it rather than checking a second one out of the pool.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT timezone FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if row is None:
            return set()
        tz = str(row[0] or "Europe/Vilnius")
        cur.execute(
            _PRACTISED_DATES_SQL,
            {"uid": user_id, "tz": tz, "start": start, "end": end},
        )
        return {r[0] for r in cur.fetchall()}


def practised_on(conn: Any, user_id: int, day: date) -> bool:
    """True when this learner practised on local ``day``."""
    return day in practised_dates(conn, user_id, start=day, end=day)
