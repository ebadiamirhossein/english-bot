"""Turning a v2 chunk's review history into an FSRS state.

**There is no v2 review *history* in the sense the slice row implies.** Nothing
in this schema logs an individual chunk review: `migrations/004_chunk_review.sql`
added four aggregate columns to `chunks` — `next_review`, `times_right`,
`times_wrong`, `streak_right` — written by
`core.services.chunks.mark_chunk_result` through the shared
`core.services.errors.spacing_step` ladder, and `sessions` records a quiz
session, not a card outcome. So "seed stability from v2 review history" can only
mean *seed from four aggregates*, and this module is the whole of that mapping,
in one place, versioned.

**Two branches, and the split is the point.**

*No history* (`times_right + times_wrong == 0`) is a real and probably common
case — a chunk presented but never graded, or captured and never surfaced. It
produces a genuinely new FSRS card with `stability = None` and
`difficulty = None`. **Nothing is invented.** A fabricated stability would be a
wrong schedule the learner then lives inside, and it would be indistinguishable
from a measured one a month later.

*Real history* seeds `State.Review` from the four numbers, and every seeded card
carries `seed_basis` — the inputs, verbatim, plus this mapping's version.
Together with the fact that the migration never modifies `chunks`, that is what
makes the slice reversible: if this mapping turns out wrong, a re-seed is an
UPDATE with a stated formula rather than a reconstruction from nothing.

**What was rejected, and why it matters.** The obvious alternative is to
synthesise a `ReviewLog` and replay it through `Scheduler.review_card` to
"derive" a stability. It produces a better-looking number out of review
datetimes that never happened — a fabricated stability wearing a derivation's
clothes. No review event is invented anywhere in this slice, which is why
`card_reviews` is empty immediately after the migration and an acceptance
criterion says so.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from core.cards.fsrs import CardState, initial_state

# The v2 ladder, imported and never re-declared. It is the seed's only interval
# input, and two hand-maintained copies of an ordering is precisely how a
# conflict rule quietly stops meaning what its docstring says
# (`core.lexicon.states`' own argument, one package over).
from core.services.errors import SPACING_DAYS

#: Bumped if the mapping below changes. Stored in `cards.seed_basis` so a row
#: seeded under an old mapping is identifiable — the same argument
#: `items.validator_version` makes, and it cannot be retrofitted either.
SEED_MAPPING = "v2_ladder"
SEED_MAPPING_VERSION = 1

# FSRS' own difficulty bounds (`MIN_DIFFICULTY` / `MAX_DIFFICULTY` in
# fsrs/scheduler.py). Mirrored so the clamp is not a magic pair of numbers.
MIN_DIFFICULTY = 1.0
MAX_DIFFICULTY = 10.0


def ladder_interval(streak_right: int) -> int:
    """The interval v2 would next have chosen. 1 → 3 → 7 → 21 → 60."""
    return SPACING_DAYS[min(max(int(streak_right), 0), 4)]


def _at_utc_midnight(value: date) -> datetime:
    """A DATE column becomes an instant. Midnight UTC, never the local day.

    `chunks.next_review` is a DATE and `cards.due` is TIMESTAMPTZ, so a
    conversion has to happen somewhere. Doing it at midnight UTC keeps it
    reproducible: any other choice makes the migrated due date depend on the
    server's timezone at the moment the pass happened to run.
    """
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def seed_from_v2(
    *,
    times_right: int,
    times_wrong: int,
    streak_right: int,
    next_review: date | None,
    today: date,
) -> tuple[CardState, dict | None]:
    """Map one chunk's v2 aggregates to an FSRS state.

    Returns the state and, when it was seeded from history, the `seed_basis`
    that migration 013's CHECK requires. `None` means the card is genuinely new
    and `seeded_from_history` stays FALSE.
    """
    right = max(0, int(times_right))
    wrong = max(0, int(times_wrong))
    reviews = right + wrong
    due_date = next_review or today

    if reviews == 0:
        # Branch (a): nothing was ever measured, so nothing is asserted.
        return initial_state(due=_at_utc_midnight(due_date)), None

    # Branch (b). stability = the interval the learner has been surviving.
    #
    # FSRS defines stability as the interval at which retrievability falls to
    # the target retention. The v2 ladder interval is the interval this phrase
    # has actually been coming back at and being recalled. That is an estimate
    # at an unknown retention — but it is derived from a measurement, it is
    # monotone in the thing it should be monotone in (more consecutive recalls →
    # longer stability), and it is recorded as a mapping WITH A VERSION rather
    # than as a fact.
    interval = ladder_interval(streak_right)
    stability = float(interval)

    # difficulty from the error rate, clamped to FSRS' own [1, 10]. A
    # never-missed phrase seeds at 1.0, an always-missed one at 10.0.
    difficulty = MIN_DIFFICULTY + (MAX_DIFFICULTY - MIN_DIFFICULTY) * (wrong / reviews)
    difficulty = min(MAX_DIFFICULTY, max(MIN_DIFFICULTY, difficulty))

    due = _at_utc_midnight(due_date)

    # `last_review` is ARITHMETIC OVER STORED VALUES, not an invented event. v2
    # set `next_review = review_date + interval`, so `next_review - interval` is
    # the date of the review that produced it. It is needed because py-fsrs'
    # State.Review branch reads `days_since_last_review`, and it is deliberately
    # NOT written into `card_reviews`: the log starts empty and its first row is
    # a real one.
    last_review = due - timedelta(days=interval)

    state = CardState(
        fsrs_state="review",
        fsrs_step=None,
        stability=stability,
        difficulty=difficulty,
        due=due,
        last_review=last_review,
        lapses=wrong,
        reps=reviews,
    )
    basis = {
        "mapping": SEED_MAPPING,
        "mapping_version": SEED_MAPPING_VERSION,
        "times_right": right,
        "times_wrong": wrong,
        "streak_right": max(0, int(streak_right)),
        "next_review": next_review.isoformat() if next_review else None,
        "ladder_interval_days": interval,
    }
    return state, basis
