"""The deck: due queue, grading, caps, leech, promotion, Anki export.

Every `cards` / `card_reviews` query lives here. No FastAPI, no Telegram, no
`import fsrs` — the scheduler is reached only through `core.cards.fsrs`, which
is the single call site (CLAUDE.md §2, and the same rule `core.llm` follows).

**The clock is always injected.** Every function below takes `now` and none of
them calls `datetime.now()`. That is what lets `tests/test_cards_service.py`
assert a due date without freezing time and without deriving its expectation
from the scheduler it is testing (CLAUDE.md §3 rules 5 and 6). The route reads
the clock once, at the edge.

**Nothing here reads `item_attempts`.** A card rating is self-reported by design
— that is what FSRS is — whereas `item_attempts.graded_by = 'self'` means
"nothing checked this answer". Turning one into the other would put a
self-assessment into a scheduler as though it were a measurement, and W19 would
inherit a progress line that silently mixes two instruments.
`tests/test_cards_service.py::test_no_path_converts_an_item_attempt_into_a_card_rating`
parses this module and fails the commit that adds one.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

from psycopg.rows import tuple_row

from core.cards import (
    DAILY_NEW_CARD_CAP,
    DAILY_REVIEW_CAP,
    LEECH_LAPSES,
    MASTERED_STATE,
    PREP_FORBIDDEN_REGISTERS,
    PREP_SOURCE_PREFIX,
    RATING_NAMES,
    RECEPTIVE_FIRST_REGISTERS,
)
from core.cards.fsrs import CardState, review
from core.db import connection, cursor
from core.items.repair import first_letter_cue

logger = logging.getLogger(__name__)


class CardWriteError(Exception):
    """A card that the deck's own rules refuse, before the database sees it."""


# ---------------------------------------------------------------------------
# rows
# ---------------------------------------------------------------------------

_CARD_COLUMNS = """
    cards.id, cards.user_id, cards.card_type, cards.source_chunk_id,
    cards.source_ref, cards.front, cards.back, cards.context_sentence,
    cards.meaning, cards.neutral_equivalent, cards.neutral_lexeme_id,
    cards.who_says_this, cards.lexeme_id, cards.cue_text, cards.register,
    cards.register_source, cards.neutral_mastered_at, cards.fsrs_state,
    cards.fsrs_step, cards.stability, cards.difficulty, cards.due,
    cards.last_review, cards.lapses, cards.reps, cards.leech_at
"""


@dataclass(frozen=True, slots=True)
class Card:
    """One card, whole. The learner-visible half is `face()`.

    Unlike `items`, a card has no hidden half worth a projection module: the
    back IS the answer and the learner asks to see it. What the reviewer must
    not do is show the back before the reveal, which is a client-side sequencing
    question, not a serialisation one — so there is no second serialiser here
    and `core.items.projection`'s contract is untouched.
    """

    id: int
    user_id: int
    card_type: str
    source_chunk_id: int | None
    source_ref: str | None
    front: str
    back: str
    context_sentence: str | None
    meaning: str | None
    neutral_equivalent: str | None
    neutral_lexeme_id: int | None
    who_says_this: str | None
    lexeme_id: int | None
    cue_text: str | None
    register: str
    register_source: str
    neutral_mastered_at: datetime | None
    state: CardState
    leech_at: datetime | None

    def face(self) -> dict:
        """What the reviewer renders. PRD §5 and §8.5.4.

        The four §8.5.4 fields are always present for an `informal`/`slang`
        card because migration 013's `cards_informal_shows_the_four_things`
        CHECK will not accept one without them. So the component has no
        "if missing" branch to get wrong.
        """
        return {
            "id": self.id,
            "card_type": self.card_type,
            "front": self.front,
            "back": self.back,
            "cue": self.cue_text or None,
            "context_sentence": self.context_sentence,
            "source_ref": self.source_ref,
            "meaning": self.meaning,
            "register": self.register,
            "neutral_equivalent": self.neutral_equivalent,
            "who_says_this": self.who_says_this,
        }


def _utc(value: datetime | None) -> datetime | None:
    """Every instant leaving this module is UTC.

    psycopg hands back a `TIMESTAMPTZ` in the **connection's** timezone, which
    on this server is `Europe/Vilnius` — the correct instant, wearing a
    different offset. `core.cards.fsrs` refuses anything that is not UTC, and it
    is right to: a scheduler that silently accepted a local-offset datetime
    would give a different answer in summer and winter. Converting here rather
    than loosening the wrapper keeps the strictness where it does the work.
    """
    return None if value is None else value.astimezone(timezone.utc)


def _to_card(row: tuple) -> Card:
    return Card(
        id=int(row[0]),
        user_id=int(row[1]),
        card_type=row[2],
        source_chunk_id=int(row[3]) if row[3] is not None else None,
        source_ref=row[4],
        front=row[5],
        back=row[6],
        context_sentence=row[7],
        meaning=row[8],
        neutral_equivalent=row[9],
        neutral_lexeme_id=int(row[10]) if row[10] is not None else None,
        who_says_this=row[11],
        lexeme_id=int(row[12]) if row[12] is not None else None,
        cue_text=row[13],
        register=row[14],
        register_source=row[15],
        neutral_mastered_at=_utc(row[16]),
        state=CardState(
            fsrs_state=row[17],
            fsrs_step=int(row[18]) if row[18] is not None else None,
            stability=float(row[19]) if row[19] is not None else None,
            difficulty=float(row[20]) if row[20] is not None else None,
            due=_utc(row[21]),
            last_review=_utc(row[22]),
            lapses=int(row[23]),
            reps=int(row[24]),
        ),
        leech_at=_utc(row[25]),
    )


# ---------------------------------------------------------------------------
# writing a card
# ---------------------------------------------------------------------------


def refuse_forbidden_prep_register(source_ref: str | None, register: str) -> None:
    """PRD §8.5.2: `/prep` material never becomes a `slang` or `taboo` card.

    The prompt asks the model not to produce them; this is the half that does
    not depend on a model complying. `/prep` is a v2 Telegram surface and dies
    at W22, so the durable form of the rule is stated about the deck rather than
    about the command — "prep material never becomes a slang card" outlives
    "the prep prompt behaved".
    """
    if not source_ref or not source_ref.startswith(PREP_SOURCE_PREFIX):
        return
    if register in PREP_FORBIDDEN_REGISTERS:
        raise CardWriteError(
            f"a {register} card may not be created from a /prep source "
            f"({source_ref!r}) — PRD §8.5.2"
        )


def create_card(
    conn: Any,
    user_id: int,
    *,
    card_type: str,
    front: str,
    back: str,
    register: str,
    register_source: str,
    state: CardState,
    source_chunk_id: int | None = None,
    source_ref: str | None = None,
    context_sentence: str | None = None,
    meaning: str | None = None,
    neutral_equivalent: str | None = None,
    neutral_lexeme_id: int | None = None,
    who_says_this: str | None = None,
    lexeme_id: int | None = None,
    cue_text: str | None = None,
    seed_basis: dict | None = None,
) -> int | None:
    """Insert one card on an open connection (caller owns the transaction).

    Returns the new id, or ``None`` when the card already exists — the
    `UNIQUE (user_id, source_chunk_id, card_type)` conflict is a no-op rather
    than an error, which is the second half of the migration's idempotency
    (the first is its anti-join).

    `neutral_mastered_at` is deliberately not a parameter. It has exactly one
    writer, `promote_to_production`, and a test says so; accepting it here would
    make the receptive-first rule bypassable by any caller that passed a value.
    """
    refuse_forbidden_prep_register(source_ref, register)
    # An explicit tuple cursor: this is the one function that runs on a
    # CALLER-OWNED connection, and a caller's row factory is not ours to assume.
    # `core.db.connection()` yields dict rows; a plain `psycopg.connect` yields
    # tuples, and a test harness or a later worker job is free to use either.
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
        INSERT INTO cards (
            user_id, card_type, source_chunk_id, source_ref, front, back,
            context_sentence, meaning, neutral_equivalent, neutral_lexeme_id,
            who_says_this, lexeme_id, cue_text, register, register_source,
            fsrs_state, fsrs_step, stability, difficulty, due, last_review,
            lapses, reps, seeded_from_history, seed_basis
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s
        )
        ON CONFLICT (user_id, source_chunk_id, card_type) DO NOTHING
        RETURNING id
        """,
            (
            user_id,
            card_type,
            source_chunk_id,
            source_ref,
            front,
            back,
            context_sentence,
            meaning,
            neutral_equivalent,
            neutral_lexeme_id,
            who_says_this,
            lexeme_id,
            cue_text,
            register,
            register_source,
            state.fsrs_state,
            state.fsrs_step,
            state.stability,
            state.difficulty,
            state.due,
            state.last_review,
            state.lapses,
            state.reps,
            seed_basis is not None,
            json.dumps(seed_basis or {}, ensure_ascii=False),
            ),
        )
        row = cur.fetchone()
    return int(row[0]) if row is not None else None


# ---------------------------------------------------------------------------
# the due queue, and the caps
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeckCounts:
    """What is left today, after the caps. The reviewer's header."""

    due_now: int
    new_remaining: int
    review_remaining: int

    @property
    def total_remaining(self) -> int:
        return self.new_remaining + self.review_remaining


# A card is "new" when it has never been graded. `reps = 0` and not
# `fsrs_state = 'learning'`: a card that lapses re-enters relearning and would
# otherwise be counted against the NEW cap, which would let a bad day silently
# eat the day's new-card budget.
_IS_NEW_SQL = "cards.reps = 0"


def _reviewed_today(conn: Any, user_id: int, *, now: datetime) -> tuple[int, int]:
    """(new cards seen today, review cards seen today), from the log.

    Counted from `card_reviews` and never from a counter column: a counter is a
    second source of truth that drifts the first time a review is rolled back,
    and the log is append-only so the count cannot disagree with what happened.
    """
    row = conn.execute(
        """
        SELECT
            count(*) FILTER (WHERE state_before = 'learning'
                             AND stability_before IS NULL)::int AS new_seen,
            count(*) FILTER (WHERE NOT (state_before = 'learning'
                             AND stability_before IS NULL))::int AS review_seen
          FROM card_reviews
         WHERE user_id = %s
           AND reviewed_at >= %s
           AND reviewed_at < %s
        """,
        (user_id, _day_start(now), _day_start(now) + timedelta(days=1)),
    ).fetchone()
    assert row is not None
    return int(row["new_seen"]), int(row["review_seen"])


def _day_start(now: datetime) -> datetime:
    """Midnight UTC of the instant's day.

    A UTC day and not a local one, deliberately: `card_reviews.reviewed_at` is
    an instant, both learners are in one timezone, and a local-day boundary
    would make the cap depend on a `users.timezone` read that this slice does
    not need. It becomes a per-user question at multi-tenancy, alongside the
    caps themselves.
    """
    return now.astimezone(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def counts_today(user_id: int, *, now: datetime) -> DeckCounts:
    """How much of today's deck is left. Never a backlog (CLAUDE.md §4).

    `due_now` is capped the same way the queue is, so the number the learner
    sees is the number of cards they will actually be shown. Reporting the raw
    overdue count would present a backlog, which is the one thing the product is
    not allowed to do.
    """
    with connection() as conn:
        new_seen, review_seen = _reviewed_today(conn, user_id, now=now)
        row = conn.execute(
            f"""
            SELECT
                count(*) FILTER (WHERE {_IS_NEW_SQL})::int AS new_due,
                count(*) FILTER (WHERE NOT ({_IS_NEW_SQL}))::int AS review_due
              FROM cards
             WHERE user_id = %s AND due <= %s
            """,
            (user_id, now),
        ).fetchone()
    assert row is not None
    new_remaining = max(0, min(int(row["new_due"]), DAILY_NEW_CARD_CAP - new_seen))
    review_remaining = max(
        0, min(int(row["review_due"]), DAILY_REVIEW_CAP - review_seen)
    )
    return DeckCounts(
        due_now=int(row["new_due"]) + int(row["review_due"]),
        new_remaining=new_remaining,
        review_remaining=review_remaining,
    )


def due_queue(user_id: int, *, now: datetime, limit: int = 20) -> list[Card]:
    """Due cards, soonest first, **capped**.

    PRD §5's two caps are enforced here and nowhere else, as two separate
    budgets: a day of heavy reviewing must not eat the new-card allowance, and a
    pile of new captures must not crowd out the reviews that keep existing cards
    alive. Reviews are served before new cards for the same reason — a review is
    a card the learner has already invested in.
    """
    if limit <= 0:
        return []
    with connection() as conn:
        new_seen, review_seen = _reviewed_today(conn, user_id, now=now)
        new_budget = max(0, DAILY_NEW_CARD_CAP - new_seen)
        review_budget = max(0, DAILY_REVIEW_CAP - review_seen)

        selected: list[Card] = []
        for is_new, budget in ((False, review_budget), (True, new_budget)):
            room = min(budget, limit - len(selected))
            if room <= 0:
                continue
            with conn.cursor() as cur:
                cur.row_factory = tuple_row
                cur.execute(
                    f"""
                    SELECT {_CARD_COLUMNS}
                      FROM cards
                     WHERE cards.user_id = %s
                       AND cards.due <= %s
                       AND {'' if is_new else 'NOT '}({_IS_NEW_SQL})
                     ORDER BY cards.due ASC, cards.id ASC
                     LIMIT %s
                    """,
                    (user_id, now, room),
                )
                selected.extend(_to_card(r) for r in cur.fetchall())
    return selected


def get_card(user_id: int, card_id: int) -> Card | None:
    """One card, or ``None`` when it is not theirs.

    Not-yours and not-found collapse, the same as `items.presentation_for`:
    telling a caller that an id exists but belongs to someone else is a fact
    about the other learner.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            f"SELECT {_CARD_COLUMNS} FROM cards "
            "WHERE cards.id = %s AND cards.user_id = %s",
            (card_id, user_id),
        )
        row = cur.fetchone()
    return _to_card(row) if row else None


# ---------------------------------------------------------------------------
# grading
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GradeOutcome:
    """What the learner is told after a grade, and what W19 will read."""

    card_id: int
    rating: int
    due: datetime
    interval_days: int
    became_leech: bool
    counts: DeckCounts


def grade_card(
    user_id: int,
    card_id: int,
    *,
    rating: int,
    now: datetime,
    duration_ms: int | None = None,
) -> GradeOutcome | None:
    """Grade one card: schedule it, log the review, keep the ledger honest.

    Four writes in one transaction, and the order matters only in that they must
    all land or none: the card's new state, the append-only `card_reviews` row,
    the leech rewrite when the sixth lapse arrives, and the `user_lexemes` write
    when the card carries a target lemma.

    ``None`` when the card is not this learner's.
    """
    with connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.row_factory = tuple_row
                cur.execute(
                    f"SELECT {_CARD_COLUMNS} FROM cards "
                    "WHERE cards.id = %s AND cards.user_id = %s FOR UPDATE",
                    (card_id, user_id),
                )
                row = cur.fetchone()
            if row is None:
                return None
            card = _to_card(row)

            result = review(card.state, rating, now=now)
            after = result.after

            # PRD §5: a leech is rewritten with an easier cue, NOT suspended.
            # `first_letter_cue` is reused from the item repair ladder rather
            # than reimplemented — it is a pure function over a string and a
            # second copy would drift from the one the gates already trust.
            became_leech = (
                card.leech_at is None and after.lapses >= LEECH_LAPSES
            )
            cue_text = card.cue_text
            if became_leech:
                cue_text = first_letter_cue(card.back)

            conn.execute(
                """
                UPDATE cards
                   SET fsrs_state = %s, fsrs_step = %s, stability = %s,
                       difficulty = %s, due = %s, last_review = %s,
                       lapses = %s, reps = %s,
                       leech_at = CASE WHEN %s THEN %s ELSE leech_at END,
                       cue_text = %s
                 WHERE id = %s
                """,
                (
                    after.fsrs_state,
                    after.fsrs_step,
                    after.stability,
                    after.difficulty,
                    after.due,
                    after.last_review,
                    after.lapses,
                    after.reps,
                    became_leech,
                    now,
                    cue_text,
                    card_id,
                ),
            )

            conn.execute(
                """
                INSERT INTO card_reviews (
                    card_id, user_id, reviewed_at, rating,
                    state_before, stability_before, difficulty_before,
                    state_after, stability_after, difficulty_after, due_after,
                    elapsed_days, scheduled_days, review_duration_ms
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s
                )
                """,
                (
                    card_id,
                    user_id,
                    # The SAME instant that scheduled the card. Migration 013
                    # deliberately gives this column no DEFAULT NOW(), because a
                    # default would make the two different clock reads and the
                    # intervals in a replayed log would not add up.
                    now,
                    rating,
                    card.state.fsrs_state,
                    card.state.stability,
                    card.state.difficulty,
                    after.fsrs_state,
                    after.stability,
                    after.difficulty,
                    after.due,
                    result.elapsed_days,
                    result.scheduled_days,
                    _clean_duration(duration_ms),
                ),
            )

            _write_ledger(conn, card, rating=rating)

            if became_leech:
                # Never a guilt line, never a suspension. The record exists so
                # W10 can weight a leech differently; the learner is told
                # nothing except that the card now carries a hint.
                logger.info(
                    "Card became a leech user_id=%s card_id=%s lapses=%s",
                    user_id,
                    card_id,
                    after.lapses,
                )

    return GradeOutcome(
        card_id=card_id,
        rating=rating,
        due=after.due,
        interval_days=result.scheduled_days or 0,
        became_leech=became_leech,
        counts=counts_today(user_id, now=now),
    )


MAX_REVIEW_DURATION_MS = 600_000


def _clean_duration(value: int | None) -> int | None:
    """A browser-reported duration outside the range is stored as NULL.

    The same clamp `core.services.items._clean_latency` applies, and the same
    caveat (#108): ten minutes on one card is a phone that was put down. It is
    stored for W19 and **nothing in W7 schedules on it** — FSRS-6's inputs are
    exactly (state, stability, difficulty, elapsed days, rating).
    """
    if value is None or not 0 <= value <= MAX_REVIEW_DURATION_MS:
        return None
    return int(value)


def _write_ledger(conn: Any, card: Card, *, rating: int) -> None:
    """A graded card is measured retrieval — `user_lexemes` with source='review'.

    **The first `review`-sourced write in this project**, and the reason
    `core.lexicon.states.AUTHORITATIVE_SOURCES` and `MAY_LOWER` exist: W4a's
    comment says a rank gate would have made "every lapse from W7 onward"
    vanish, and that has to be proven false rather than assumed.

    Migrated v2 cards carry no `lexeme_id` — v2 chunks are phrases, not lemmas —
    so in practice this fires from W13 onward. It is built and tested now
    because the path being correct is cheaper to establish than to retrofit.
    """
    if card.lexeme_id is None:
        return
    # Lazy import: core.services.lexicon imports core.db, and a module-level
    # import here would make the two services' load order significant for no
    # gain. The same shape core.services.chunks uses for core.services.anki.
    from core.services.lexicon import LedgerEntry, record

    row = conn.execute(
        "SELECT lemma FROM lexemes WHERE id = %s", (card.lexeme_id,)
    ).fetchone()
    if row is None:
        # A card pointing at a deleted lexeme cannot happen — 013's FK is ON
        # DELETE RESTRICT — but the ledger write is not the place to assert it.
        logger.warning("Card lexeme missing card_id=%s", card.id)
        return

    # Again → the learner did not retrieve it. Hard/Good/Easy → they did.
    # `record` applies core.lexicon.states' conflict rule, which is what makes
    # `review` an AUTHORITATIVE_SOURCE that may lower a state: a lapse is
    # evidence of not-knowing, and W4a exists because rank alone discarded it.
    state = "learning" if rating == 1 else "known"
    record(
        conn,
        card.user_id,
        [
            LedgerEntry(
                lemma=str(row["lemma"]),
                state=state,
                source="review",
                register=card.register,
            )
        ],
    )


# ---------------------------------------------------------------------------
# the chunk migration's two reads
# ---------------------------------------------------------------------------
#
# They live here and not in `core.cards.migrate_chunks` because SQL lives only
# in service functions (CLAUDE.md §2) and #59 stays the only exemption in this
# project. The pass itself is pure decision-making over the rows these return.


def chunks_to_migrate(conn: Any) -> list:
    """Every chunk, oldest first per learner. **Read-only, and never filtered.**

    Not an anti-join against `cards`: the unit of work is a CARD, not a chunk,
    and a chunk that produced only a cloze card on a previous run must still be
    examined for its production card. A chunk-level anti-join would skip it
    wholesale and hide a partial migration behind an idempotent-looking second
    run.
    """
    return conn.execute(
        """
        SELECT k.id, k.user_id, k.chunk, k.full_sentence, k.meaning, k.source,
               k.track, k.next_review, k.times_right, k.times_wrong,
               k.streak_right
          FROM chunks k
         ORDER BY k.user_id, k.id
        """
    ).fetchall()


def migrated_card_keys(conn: Any, card_types: Sequence[str]) -> set[tuple[int, str]]:
    """`(chunk id, card type)` for every card this migration already created."""
    rows = conn.execute(
        """
        SELECT source_chunk_id, card_type
          FROM cards
         WHERE source_chunk_id IS NOT NULL
           AND card_type = ANY(%s)
        """,
        (list(card_types),),
    ).fetchall()
    return {(int(r["source_chunk_id"]), str(r["card_type"])) for r in rows}


# ---------------------------------------------------------------------------
# the receptive-first rule
# ---------------------------------------------------------------------------


def promote_to_production(user_id: int, card_id: int, *, now: datetime) -> bool:
    """PRD §8.5.2: promote a `slang`/`informal` card once the neutral is mastered.

    **The only writer of `cards.neutral_mastered_at`**, and
    `tests/test_cards_service.py` parses this module to say so. That column is
    what turns a cross-table rule into the row-local CHECK
    `cards_receptive_first_until_the_neutral_is_mastered`, so a guard that lived only
    here would be a guard the next card-creating slice does not know about,
    while the CHECK is one it cannot get past.

    "Mastered" is not a new notion: `core.lexicon.states.STATES` already ends at
    `mastered`, and `SOURCE_STATES['review']` already permits a review to write
    it. Returns False — without writing — when the ledger does not agree.
    """
    with connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """
                SELECT c.register, c.neutral_lexeme_id, ul.state
                  FROM cards c
                  LEFT JOIN user_lexemes ul
                         ON ul.user_id = c.user_id
                        AND ul.lexeme_id = c.neutral_lexeme_id
                 WHERE c.id = %s AND c.user_id = %s
                 FOR UPDATE OF c
                """,
                (card_id, user_id),
            ).fetchone()
            if row is None:
                return False
            if row["register"] not in RECEPTIVE_FIRST_REGISTERS:
                # A neutral or formal card was never barred, so there is nothing
                # to promote and nothing to record.
                return False
            if row["neutral_lexeme_id"] is None or row["state"] != MASTERED_STATE:
                return False
            conn.execute(
                "UPDATE cards SET neutral_mastered_at = %s WHERE id = %s",
                (now, card_id),
            )
    return True


# ---------------------------------------------------------------------------
# The cloze measurement's reader — read-only, no route behind it
# ---------------------------------------------------------------------------
#
# `export_rows(user_id)` stood here from W7 until 2026-08-25. It returned one
# learner's whole deck and its only caller was `GET /cards/export.tsv`, which
# W8a removed — a service function whose reason for existing is a deleted route
# is dead code no ban test can see, so it went with it.
#
# `cloze_cards` arriving in the same commit is not that function renamed. It is
# narrower (one card type, no faces to serialise), it is keyed on nothing (every
# learner, because the question is about the deck rather than about a person),
# and no route calls it or ever will: its one caller is
# `core.cards.probe_cloze`, a human-run measurement that writes nothing.


def cloze_cards() -> list[Card]:
    """Every `cloze` card in the database, oldest first.

    Read-only, and deliberately not scoped to a learner. W8a's finding is about
    how cloze cards are *made* — `make_sentence_with_gap` removes the phrase and
    checks nothing — so the population under measurement is the whole deck, not
    one person's share of it.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            f"SELECT {_CARD_COLUMNS} FROM cards "
            "WHERE cards.card_type = 'cloze' ORDER BY cards.id ASC"
        )
        return [_to_card(r) for r in cur.fetchall()]
