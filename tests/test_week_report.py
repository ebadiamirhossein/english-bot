"""W11b: `week_summary` — the Sunday report's one read, against a real database.

**Everything here is a READ.** The slice writes nothing, adds no table, no
column and no migration; these tests seed rows through the ordinary writers and
assert what a week of this system's data can honestly say.

**THE THREE PROPERTIES THIS FILE EXISTS FOR**, each asserted against the
mechanism that would have been WRONG as well as the one that shipped:

* **The day count must not read `sessions.completed`.** That flag is unreachable
  for a `daily` row (#259: `output` cannot self-report, so no web session has
  ever been marked complete), and `count_active_days` — the function already in
  this module's neighbour that looks like the right one — filters on exactly
  that. A report built on it would print a confident zero for a learner who
  worked every day. `test_a_day_is_counted_from_the_row_not_from_the_completed_flag`
  asserts BOTH numbers side by side so the trap is visible rather than avoided.

* **The window is the learner's local week, not the server's.** `sessions.date`
  is already a local date; `item_attempts.attempted_at`, `card_reviews.reviewed_at`,
  `user_lexemes.updated_at` and `user_unit_state.passed_at` are instants. An
  attempt at 23:30 on Sunday in Vilnius is Sunday's, and one at 00:30 on Monday
  is not — even though the two are 60 minutes apart and UTC calls both Sunday.

* **A zero is a fact here and a score on the screen.** The service returns real
  zeros; `empty` is what the surface reads, and no zero is ever rendered
  (`apps/web/components/week/report.test.tsx`).

CLAUDE.md §3 rule 6: **no assertion in this file depends on the wall clock.**
Both sides of every window comparison are computed from one injected `now`.
"""

from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg
import pytest

from core.config import load_settings
from core.services import sessions as sessions_service
from core.services import week as week_service

VILNIUS = ZoneInfo("Europe/Vilnius")

#: A Sunday, and the last day of the week under test. Every other date in this
#: file is derived from it, so nothing here can drift onto a calendar boundary.
SUNDAY = date(2026, 8, 30)
MONDAY = SUNDAY - timedelta(days=6)          # the week's first day
SATURDAY_BEFORE = MONDAY - timedelta(days=1)  # one day outside, on the early side

#: 12:00 Vilnius on the Sunday — the instant every test injects as `now`.
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=VILNIUS)


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    """A Vilnius wall-clock instant, as a learner would experience it."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=VILNIUS)


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def learner(db):
    row = db.execute(
        """
        INSERT INTO users (name, native_language, auth_email, onboarded, timezone)
        VALUES ('w11b', 'lt', %s, TRUE, 'Europe/Vilnius')
        RETURNING id
        """,
        (f"w11b-{secrets.token_hex(6)}@example.invalid",),
    ).fetchone()
    user_id = int(row[0])
    db.commit()
    try:
        yield user_id
    finally:
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.commit()


# ── seeding, through the shapes the real writers produce ────────────────────


def _session(db, learner: int, day: date, *, task_type: str = "daily",
             completed: bool = False) -> int:
    row = db.execute(
        "INSERT INTO sessions (user_id, date, task_type, completed) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (learner, day, task_type, completed),
    ).fetchone()
    db.commit()
    return int(row[0])


def _item(db, learner: int) -> int:
    from core.items.gates import ValidationReport
    from core.items.schema import parse
    from core.services import items as items_svc

    item_id = items_svc.insert_item(
        learner,
        parse({
            "item_type": "cloze_cued",
            "track": "life",
            "prompt_text": f"I ___ there twice last year. {secrets.token_hex(4)}",
            "answer": "went",
            "accepted_variants": ["went"],
            "unit_number": 1,
            "grammar_target": "past simple: regular and irregular verbs",
            "explanation": "Past simple, because the time is finished.",
            "definition": "past of go",
            "l1_gloss": "nuvykau",
        }),
        ValidationReport("passed", acceptable=("went",), canonical="went"),
        model="test-model",
    )
    db.commit()
    assert item_id is not None
    return item_id


def _attempt(db, learner: int, when: datetime, *, correct: bool = True) -> None:
    db.execute(
        "INSERT INTO item_attempts (user_id, item_id, correct, graded_by, attempted_at) "
        "VALUES (%s, %s, %s, 'deterministic', %s)",
        (learner, _item(db, learner), correct, when),
    )
    db.commit()


def _card(db, learner: int) -> int:
    """Through `cards.create_card`, the real writer — a hand INSERT would seed a
    row 013's CHECKs might never have accepted."""
    from core.cards.fsrs import CardState
    from core.services import cards as cards_svc

    card_id = cards_svc.create_card(
        db,
        learner,
        card_type="cloze",
        front=f"I _____ to the shops. {secrets.token_hex(4)}",
        back="went",
        register="neutral",
        register_source="migration_default",
        state=CardState(
            fsrs_state="review",
            fsrs_step=None,
            stability=10.0,
            difficulty=5.0,
            due=NOW,
            last_review=NOW - timedelta(days=10),
            lapses=0,
            reps=3,
        ),
        meaning="past of go",
        context_sentence="I went to the shops.",
        source_ref="himym",
    )
    db.commit()
    assert card_id is not None
    return int(card_id)


def _review(db, learner: int, when: datetime) -> None:
    db.execute(
        """
        INSERT INTO card_reviews
            (card_id, user_id, reviewed_at, rating, state_before, state_after,
             due_after)
        VALUES (%s, %s, %s, 3, 'review', 'review', %s)
        """,
        (_card(db, learner), learner, when, when + timedelta(days=4)),
    )
    db.commit()


def _lexeme(db) -> int:
    row = db.execute("SELECT id FROM lexemes ORDER BY id LIMIT 1").fetchone()
    assert row is not None, "the lexicon seed is required — run core.lexicon.seed"
    return int(row[0])


def _known(db, learner: int, when: datetime, *, state: str = "known") -> None:
    db.execute(
        "INSERT INTO user_lexemes (user_id, lexeme_id, state, source, source_rank, updated_at) "
        "VALUES (%s, %s, %s, 'review', 5, %s)",
        (learner, _lexeme(db), state, when),
    )
    db.commit()


def _passed_unit(db, learner: int, when: datetime) -> None:
    db.execute(
        """
        INSERT INTO user_unit_state
            (user_id, unit_number, state, entered_at, passed_at, last_checkpoint_score)
        VALUES (%s, 1, 'passed', %s, %s, 92)
        """,
        (learner, when - timedelta(days=3), when),
    )
    db.commit()


def _report(learner: int, *, week_ending: date = SUNDAY, now: datetime = NOW):
    return week_service.week_summary(learner, week_ending=week_ending, now=now)


# ── the empty week — week one, and it is both learners' state ───────────────


def test_a_week_with_nothing_in_it_is_empty_and_says_so(learner) -> None:
    """Every count is a real zero and `empty` is True.

    The surface reads `empty` rather than testing six numbers itself; a screen
    that decides what a zero means is a screen that will eventually render one.
    """
    report = _report(learner)
    assert report is not None
    assert (
        report.days_with_a_session,
        report.items_answered,
        report.items_right,
        report.cards_reviewed,
        report.words_now_known,
        report.units_passed,
    ) == (0, 0, 0, 0, 0, 0)
    assert report.empty is True


def test_an_unknown_learner_is_none_rather_than_an_empty_report() -> None:
    """The route turns this into a 404, exactly as `/session/today` does.

    An empty report for a user who does not exist is a week nobody had.
    """
    assert week_service.week_summary(-1, week_ending=SUNDAY, now=NOW) is None


# ── the day count, and the flag it must not read ────────────────────────────


def test_a_day_is_counted_from_the_row_not_from_the_completed_flag(
    db, learner
) -> None:
    """**#259 in one assertion.** `sessions.completed` is FALSE on every `daily`
    row that has ever existed — `output` cannot self-report, so nothing sets it —
    and `count_active_days` filters on exactly that.

    Both numbers are asserted here, side by side. The trap is not "remember not
    to use `count_active_days`"; it is that the wrong function returns a
    plausible number for a learner who worked all week.
    """
    _session(db, learner, MONDAY, completed=False)
    _session(db, learner, SUNDAY, completed=False)

    assert _report(learner).days_with_a_session == 2
    assert sessions_service.count_active_days(learner, start=MONDAY, end=SUNDAY) == 0


def test_a_learner_cannot_have_two_daily_rows_on_one_day(db, learner) -> None:
    """`COUNT(DISTINCT date)` is belt to migration 016's braces, and the braces
    are asserted here rather than assumed.

    `sessions_one_daily_per_user_per_date` makes a second `daily` row on one
    date impossible, so the DISTINCT can never be the thing that saves this
    number — which is worth knowing, because a DISTINCT that never fires is a
    defence nobody has tested. The report and the index agree, and the test says
    which one is doing the work.
    """
    _session(db, learner, SUNDAY)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _session(db, learner, SUNDAY)
    db.rollback()
    assert _report(learner).days_with_a_session == 1


def test_only_the_daily_session_counts_a_day(db, learner) -> None:
    """`sessions` holds twelve task types, eleven of them the Telegram bot's.

    A `quiz` row from v2 is not a day of this app's week, and counting it would
    make the report describe a product the learner is no longer using.
    """
    _session(db, learner, SUNDAY, task_type="quiz")
    assert _report(learner).days_with_a_session == 0


def test_a_day_outside_the_week_is_not_in_it(db, learner) -> None:
    """The window has TWO ends. A missing lower bound counts the whole history
    and quietly turns a weekly report into a lifetime one."""
    _session(db, learner, SATURDAY_BEFORE)
    _session(db, learner, MONDAY)
    assert _report(learner).days_with_a_session == 1


# ── the window is the learner's local week ──────────────────────────────────


def test_the_window_is_the_learners_local_week_and_not_utc(db, learner) -> None:
    """23:30 Sunday in Vilnius is Sunday's; 00:30 Monday is not.

    Both instants are 20:30 and 21:30 **UTC on the Sunday**, so a window built
    from UTC dates counts both and a window built from the learner's dates
    counts one. Sixty minutes apart, and only one of them is in this week.
    """
    _attempt(db, learner, _at(SUNDAY, 23, 30))
    _attempt(db, learner, _at(SUNDAY + timedelta(days=1), 0, 30))
    assert _report(learner).items_answered == 1


def test_the_first_minute_of_the_week_is_inside_it(db, learner) -> None:
    """00:00 Monday, local. An exclusive lower bound loses the first session of
    every week and does it silently."""
    _attempt(db, learner, _at(MONDAY, 0, 0))
    assert _report(learner).items_answered == 1


# ── what the five tables say ────────────────────────────────────────────────


def test_items_answered_and_how_many_were_right(db, learner) -> None:
    _attempt(db, learner, _at(MONDAY, 9), correct=True)
    _attempt(db, learner, _at(MONDAY, 9, 5), correct=True)
    _attempt(db, learner, _at(MONDAY, 9, 10), correct=False)
    report = _report(learner)
    assert (report.items_answered, report.items_right) == (3, 2)


def test_a_week_where_nothing_was_right_still_counts_the_answering(
    db, learner
) -> None:
    """`items_right` is 0 and `items_answered` is 2 — the service reports both.

    **The surface is where the zero stops**, not here: a service that refused to
    return the number would leave the screen deriving it, and the no-zero rule
    would then live in two places.
    """
    _attempt(db, learner, _at(MONDAY, 9), correct=False)
    _attempt(db, learner, _at(MONDAY, 10), correct=False)
    report = _report(learner)
    assert (report.items_answered, report.items_right) == (2, 0)
    assert report.empty is False


def test_cards_reviewed_this_week(db, learner) -> None:
    _review(db, learner, _at(MONDAY, 8))
    _review(db, learner, _at(SUNDAY, 8))
    _review(db, learner, _at(SATURDAY_BEFORE, 8))
    assert _report(learner).cards_reviewed == 2


def test_words_that_reached_known_this_week(db, learner) -> None:
    _known(db, learner, _at(MONDAY, 8))
    assert _report(learner).words_now_known == 1


def test_a_word_known_before_this_week_is_not_counted_again(db, learner) -> None:
    """`updated_at` moves only when the ledger row actually changes, so a row
    last touched before Monday is last week's news and belongs to no report."""
    _known(db, learner, _at(SATURDAY_BEFORE, 8))
    assert _report(learner).words_now_known == 0


def test_a_word_still_only_seen_is_not_a_word_you_know(db, learner) -> None:
    _known(db, learner, _at(MONDAY, 8), state="seen")
    assert _report(learner).words_now_known == 0


def test_a_unit_passed_this_week_is_the_one_raise_this_report_can_announce(
    db, learner
) -> None:
    """The first thing in this product that was ever worth announcing, and after
    W11 it is reachable for the first time."""
    _passed_unit(db, learner, _at(SUNDAY, 11))
    assert _report(learner).units_passed == 1


def test_a_unit_passed_last_week_is_not_announced_again(db, learner) -> None:
    _passed_unit(db, learner, _at(SATURDAY_BEFORE, 11))
    assert _report(learner).units_passed == 0


# ── the week the report names ───────────────────────────────────────────────


def test_the_week_ends_on_the_sunday_of_the_week_that_contains_today() -> None:
    """PRD §4.2's week runs Mon → Sun, so Sunday is the last day and not the
    first. Asserted for all seven weekdays from one fixed Sunday, so this cannot
    pass because the day the suite ran happened to be convenient."""
    for offset in range(7):
        day = MONDAY + timedelta(days=offset)
        assert week_service.week_ending_for(day) == SUNDAY, day


def test_today_being_sunday_is_a_fact_the_server_owns(learner) -> None:
    """A `new Date().getDay()` in the browser puts a learner in Vilnius on the
    browser's idea of Sunday — the reasoning `saturday-link.tsx` already
    records. The flag comes from `users.timezone` and the injected instant."""
    assert _report(learner, now=NOW).sunday is True
    assert _report(
        learner, week_ending=SUNDAY, now=_at(MONDAY, 12)
    ).sunday is False


def test_a_report_asked_for_without_a_week_uses_the_learners_own_today(
    db, learner
) -> None:
    """The route passes no `week_ending`; the parameter exists so the window is
    assertable without freezing the clock (CLAUDE.md §3 rule 6)."""
    _session(db, learner, SUNDAY)
    report = week_service.week_summary(learner, now=NOW)
    assert report is not None
    assert report.week_ending == SUNDAY
    assert report.days_with_a_session == 1


# ── what this report cannot say, held open ──────────────────────────────────


def test_the_report_carries_none_of_the_four_columns_nothing_writes(
    learner,
) -> None:
    """**#258 / #259, as an assertion rather than as a paragraph.**

    `sessions.minutes` and `sessions.completed_at` have no writer at all —
    `complete_block` was the only one and W11 removed it — and `sessions.xp` is
    NULL on every row that exists (W19 owns the weighting). A field for any of
    them here would be a number that is always zero, and a zero on a report is a
    score.

    Asserted on the dataclass's own field names, so adding one is a failing test
    rather than a quiet regression.
    """
    fields = set(week_service.WeekReport.__dataclass_fields__)
    assert fields.isdisjoint({"minutes", "xp", "completed", "blocks_completed"})
