"""W11b: the Sunday weekly report. **One read, and it writes nothing.**

PRD §4.2 gives Sunday four words — *"No tasks. Weekly report. Free extensive
input, tracked but never required."* — and this module is the second of them.
It adds no table, no column and no migration; every table it reads already
exists and nothing here is an INSERT or an UPDATE.

────────────────────────────────────────────────────────────────────────────────
WHAT A WEEK OF THIS SYSTEM'S DATA CAN HONESTLY SAY

Enumerated in W11's plan §7.1 **from the data and not from the schema**, which
is the correction that section had to make to itself:

    sessions        task_type='daily', date   -> how many days had a session
    item_attempts   attempted_at, correct     -> items answered, and how many
                                                 were right
    card_reviews    reviewed_at               -> cards reviewed
    user_lexemes    state, updated_at         -> words that reached `known`
    user_unit_state passed_at                 -> a unit passed this week

**AND WHAT IT CANNOT, WHICH IS REPORTED AS AN ABSENCE AND NEVER FILLED WITH A
SUBSTITUTE** (CLAUDE.md §3 rule 7): XP (W19 — `sessions.xp` is NULL on every row
that exists), input minutes and videos watched (W12/W13), speaking (W14–W16),
mastery (#135 — there is no metric and nothing can write `mastered`), coverage
trend (#197, unruled), and **free extensive input, which §4.2 says is tracked
and which nothing tracks** (#253).

────────────────────────────────────────────────────────────────────────────────
THE TRAP THIS MODULE IS BUILT AROUND: `sessions.completed`

`core.services.sessions.count_active_days` counts `COUNT(DISTINCT date)` over
`sessions` **filtered on `completed = TRUE`**. It is the function that looks
like the right one, and using it here would print a confident **zero** for a
learner who worked every day: `completed` is set for a `daily` row only when all
five blocks report done, and block 4 (`output`) **cannot self-report** — `POST
/correct` records no `session_id`, so nothing links a correction to the sitting
it happened in. That is #259, narrowed by W11's #258 ruling and still open, and
it is why the day count here reads the ROW and not the flag.

**So `sessions` says one thing on this surface: how many days had a session.**
`block_breakdown` is written again since W11 (`_derive_done`, on every
hydration), but `minutes` and `completed_at` have had **no writer at all** since
`complete_block` was removed with the button nobody tapped — and a column with
no writer is a column that reports zero forever.

────────────────────────────────────────────────────────────────────────────────
THE WINDOW IS THE LEARNER'S, AND THE CLOCK IS INJECTED

PRD §4.2's week runs **Mon → Sun**, so `week_ending` is a Sunday and the window
is the seven local dates ending on it. `sessions.date` is already a local date;
the other four tables carry instants, so their bounds are the learner's local
midnights converted through `users.timezone` — an attempt at 23:30 on Sunday in
Vilnius is Sunday's, and one at 00:30 on Monday is not, though UTC calls both
Sunday.

`now` is INJECTED and `datetime.now()` is called nowhere in this module, which
is what lets a test walk the week boundary without freezing the clock
(CLAUDE.md §3 rule 6) and what makes `sunday` a fact the SERVER owns rather than
a `new Date().getDay()` in a browser somewhere — the reasoning
`components/checkpoint/saturday-link.tsx` already records.

────────────────────────────────────────────────────────────────────────────────
ZEROS: HONEST HERE, NEVER ON THE SCREEN

Every count returned is a real number, including zero, and `empty` is the one
question the surface asks. **The no-zero rule lives on the surface, in one
place** (`apps/web/components/week/report.tsx`): a zero on a report is a score,
and a score of zero on a week nobody promised anything about is guilt with no
banned word in it. A service that refused to return the number would push that
judgement into the screen, and then the rule would live in two places and one of
them would drift.

**And nothing here counts what was NOT done.** No missed days, no shortfall
against a target, no comparison with last week — *drops are silent, raises are
announced*, and CLAUDE.md §4's *never present a backlog* is the reason a
report that says what did not happen is a backlog with a date on it (#160).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from core.db import connection

#: PRD §4.2's week ends on Sunday. `date.weekday()` is Monday-0, so Sunday is 6.
SUNDAY = 6

#: Mon → Sun inclusive.
WEEK_DAYS = 7

#: `user_lexemes.state` values that mean the learner knows the word. `mastered`
#: is included because it is BEYOND `known` on `core.lexicon.states.STATES`, and
#: a ladder read as an equality test loses its own top rung.
KNOWN_STATES = ("known", "mastered")


@dataclass(frozen=True, slots=True)
class WeekReport:
    """One week, as six numbers and the two facts that frame them.

    **There is deliberately no field here for `minutes`, `xp`, `completed` or a
    block breakdown.** Each is a column nothing writes, so each would be a zero
    that never moves; `tests/test_week_report.py` asserts their absence on this
    class's own field names, so adding one is a failing test rather than a quiet
    regression.
    """

    #: The Sunday this week ends on, in the learner's local calendar.
    week_ending: date
    #: Whether the learner's today IS that Sunday. Sunday's home reads this.
    sunday: bool

    days_with_a_session: int
    items_answered: int
    items_right: int
    cards_reviewed: int
    words_now_known: int
    units_passed: int

    @property
    def empty(self) -> bool:
        """Nothing happened this week — the one question the surface asks.

        Computed from every count rather than from one of them, so a week with
        a single graded card is not reported as empty because no session row
        was created.
        """
        return not any(
            (
                self.days_with_a_session,
                self.items_answered,
                self.items_right,
                self.cards_reviewed,
                self.words_now_known,
                self.units_passed,
            )
        )


def week_ending_for(local_date: date) -> date:
    """The Sunday of the Mon–Sun week that contains ``local_date``.

    Sunday returns itself: Sunday is the week's LAST day (PRD §4.2), so the
    report a learner reads on Sunday is about the week they have just had,
    including that morning.
    """
    return local_date + timedelta(days=SUNDAY - local_date.weekday())


def _bounds(week_ending: date, tz: str) -> tuple[date, date, datetime, datetime]:
    """`(first local date, last local date, first instant, first instant after)`.

    The instants are the learner's local midnights. Half-open on the upper end
    so 23:59:59.999 on the Sunday is inside and 00:00 on the Monday is not —
    a closed upper bound written as `<= end of day` has to pick a precision, and
    every choice of precision is a bug at some resolution.
    """
    zone = ZoneInfo(tz)
    first = week_ending - timedelta(days=WEEK_DAYS - 1)
    return (
        first,
        week_ending,
        datetime.combine(first, time.min, tzinfo=zone),
        datetime.combine(week_ending + timedelta(days=1), time.min, tzinfo=zone),
    )


def week_summary(
    user_id: int,
    *,
    week_ending: date | None = None,
    now: datetime,
) -> WeekReport | None:
    """This learner's week. ``None`` when the user is unknown.

    **The one function `GET /week` calls.** The route parses, authorises, calls
    this and serialises; there is no business logic above it and no SQL below it
    anywhere else (CLAUDE.md §2).

    ``week_ending`` defaults to the Sunday of the week containing the learner's
    today. **The route never passes one** — the parameter exists so a test can
    assert the window's two ends without freezing the clock (CLAUDE.md §3
    rule 6), which is the same shape `now` already has throughout this codebase.

    ``None`` rather than an empty report for an unknown user: an empty week is a
    fact about a week, and a week nobody had is not one.
    """
    with connection() as conn:
        row = conn.execute(
            "SELECT timezone FROM users WHERE id = %s", (user_id,)
        ).fetchone()
        if row is None:
            return None
        tz = row["timezone"]
        local_today = now.astimezone(ZoneInfo(tz)).date()
        ending = week_ending or week_ending_for(local_today)
        first_date, last_date, first_at, next_at = _bounds(ending, tz)

        # **THE DAY COUNT READS THE ROW, NEVER `completed`.** See this module's
        # banner: `count_active_days` filters on a flag no `daily` row has ever
        # carried (#259), so the obvious reuse returns zero for a full week.
        #
        # `task_type = 'daily'` because `sessions` holds twelve types, eleven of
        # them the Telegram bot's. A `quiz` row from v2 is not a day of this
        # app's week.
        days = conn.execute(
            """
            SELECT COUNT(DISTINCT date) AS n
              FROM sessions
             WHERE user_id = %s
               AND task_type = 'daily'
               AND date BETWEEN %s AND %s
            """,
            (user_id, first_date, last_date),
        ).fetchone()["n"]

        # `correct` is NOT NULL, so `COUNT(*) FILTER` and a SUM agree; the
        # filter is used because it says what it counts. No `graded_by` filter:
        # "items answered" is every attempt, and 012 makes `graded_by` NOT NULL
        # with three values precisely so the number is not silently mixed.
        attempts = conn.execute(
            """
            SELECT COUNT(*) AS answered,
                   COUNT(*) FILTER (WHERE correct) AS right_
              FROM item_attempts
             WHERE user_id = %s
               AND attempted_at >= %s
               AND attempted_at < %s
            """,
            (user_id, first_at, next_at),
        ).fetchone()

        reviews = conn.execute(
            """
            SELECT COUNT(*) AS n
              FROM card_reviews
             WHERE user_id = %s
               AND reviewed_at >= %s
               AND reviewed_at < %s
            """,
            (user_id, first_at, next_at),
        ).fetchone()["n"]

        # **A PROXY, AND IT IS NAMED AS ONE.** There is no `became_known_at`.
        # `core.services.lexicon.record`'s upsert moves `updated_at` only when
        # the row's state, source or register actually changes, so a `known` row
        # touched inside the window is one that changed inside the window — but
        # a row that was already `known` and had its SOURCE upgraded is counted
        # too. That over-counts a positive by at most a word or two and never
        # invents a shortfall, which is the direction this surface can afford to
        # be wrong in.
        words = conn.execute(
            """
            SELECT COUNT(*) AS n
              FROM user_lexemes
             WHERE user_id = %s
               AND state = ANY(%s)
               AND updated_at >= %s
               AND updated_at < %s
            """,
            (user_id, list(KNOWN_STATES), first_at, next_at),
        ).fetchone()["n"]

        # 014's `user_unit_state_a_pass_needs_the_threshold` means a non-NULL
        # `passed_at` cannot exist on a row that did not pass, so the timestamp
        # alone is the whole predicate and no `state` filter is owed.
        units = conn.execute(
            """
            SELECT COUNT(*) AS n
              FROM user_unit_state
             WHERE user_id = %s
               AND passed_at >= %s
               AND passed_at < %s
            """,
            (user_id, first_at, next_at),
        ).fetchone()["n"]

    return WeekReport(
        week_ending=ending,
        sunday=local_today.weekday() == SUNDAY,
        days_with_a_session=int(days),
        items_answered=int(attempts["answered"]),
        items_right=int(attempts["right_"]),
        cards_reviewed=int(reviews),
        words_now_known=int(words),
        units_passed=int(units),
    )
