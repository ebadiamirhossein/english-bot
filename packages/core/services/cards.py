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
    RATINGS,
    RECEPTIVE_FIRST_REGISTERS,
    TYPED_ANSWER_CARD_TYPES,
)
from core.cards.fsrs import CardState, review
from core.db import connection, cursor
from core.items.grading import equivalence_key
from core.items.repair import first_letter_cue
from core.services import lexeme_images

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
    cards.last_review, cards.lapses, cards.reps, cards.leech_at,
    cards.captured_at, cards.source_title
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

    # W8f / migration 015. Defaulted, so a caller constructing a Card by hand
    # (several tests do) is not forced to supply provenance a v2 card never had.
    # NOT surfaced by `face()`: rendering the readable title is a card-face
    # change, which reaches `apps/web` and `CardFace`, and W8f does not touch
    # the frontend. The column is populated now so W13 has something to render.
    captured_at: datetime | None = None
    source_title: str | None = None

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
            # #157: whether this card asks for a typed answer before the reveal.
            # Derived from `TYPED_ANSWER_CARD_TYPES` and sent on the wire, so
            # `apps/web` holds no copy of the table -- the same rule W6 settled
            # for `response_mode`. A mirrored table is a table that drifts.
            "typed": self.card_type in TYPED_ANSWER_CARD_TYPES,
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
        captured_at=_utc(row[26]) if len(row) > 26 else None,
        source_title=row[27] if len(row) > 27 else None,
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
    captured_at: datetime | str | None = None,
    source_title: str | None = None,
) -> int | None:
    """Insert one card on an open connection (caller owns the transaction).

    Returns the new id, or ``None`` when the card already exists — the
    `UNIQUE (user_id, source_chunk_id, card_type)` conflict is a no-op rather
    than an error, which is the second half of the migration's idempotency
    (the first is its anti-join).

    `captured_at` and `source_title` (migration 015) are PRD §5's "and where it
    came from", for a card whose provenance is a capture rather than a chunk.
    Both stay NULL for a migrated card, which recorded neither, and no value is
    invented for those rows: an invented capture instant is indistinguishable
    from a real one.

    **The `ON CONFLICT` below is keyed on `source_chunk_id` and therefore CANNOT
    FIRE for a captured card**, because PostgreSQL treats every NULL as
    distinct. That is not an oversight left in place: migration 015's
    `cards_one_card_per_lemma` is the guarantee that covers those rows, and the
    caller's anti-join is the other half. Two independent guarantees on both
    paths, which is the property `migrate_chunks` has and this one needed.

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
            lapses, reps, seeded_from_history, seed_basis,
            captured_at, source_title
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s
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
            captured_at,
            source_title,
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


def cards_not_due(user_id: int, *, now: datetime, limit: int = 40) -> list[Card]:
    """This learner's cards that are NOT due, least recently seen first.

    **W31d's top-up and nothing else**: a practice drill with too few due cards
    fills from these, and **grades none of them** — reviewing early moves FSRS
    stability, which is R7's reason, kept by ruling Q8. Reads only.
    """
    if limit <= 0:
        return []
    with connection() as conn, conn.cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            f"""
            SELECT {_CARD_COLUMNS} FROM cards
             WHERE cards.user_id = %s AND cards.due > %s
             ORDER BY cards.last_review NULLS FIRST, cards.id
             LIMIT %s
            """,
            (user_id, now, limit),
        )
        return [_to_card(row) for row in cur.fetchall()]


def card_for(user_id: int, card_id: int) -> Card | None:
    """One of this learner's cards, or None. Reads only."""
    with connection() as conn, conn.cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            f"SELECT {_CARD_COLUMNS} FROM cards WHERE cards.id = %s AND cards.user_id = %s",
            (card_id, user_id),
        )
        row = cur.fetchone()
    return None if row is None else _to_card(row)


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
    session_id: int | None = None,
    typed_response: str | None = None,
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

            # #157. `None` for a `recognition` card, for `/review` used without
            # typing, and for any card type outside `TYPED_ANSWER_CARD_TYPES`.
            typed, matched = _typed_verdict(card, typed_response)

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
                    elapsed_days, scheduled_days, review_duration_ms,
                    session_id, typed_response, typed_matched
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
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
                    session_id,
                    # VERBATIM and unnormalised: "what did they actually type"
                    # cannot be recovered from "did it match". Same rule as
                    # `item_attempts.response_text`.
                    typed,
                    # RECOMPUTED HERE, never taken from the client. A verdict
                    # the browser supplies is a verdict the browser can choose
                    # (#108's shape).
                    matched,
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


# ---------------------------------------------------------------------------
# the typed answer (#157)
# ---------------------------------------------------------------------------


def answer_matches(card: Card, text: str | None) -> bool:
    """Does this typed string mean the same as the card's back?

    **Through `core.items.grading.equivalence_key` and nothing else.** #157's
    ruling is explicit that this adds no second normaliser: `equivalence_key`
    already turns a string into its expanded, lowered token tuple, so
    capitalisation, edge punctuation and contractions fold — `I'll` and `I will`
    are one class — and it is the SAME function W5a's uniqueness probe counts
    with and `probe_cloze` reuses. A second fold here could accept a string the
    gate rejects, or reject one it accepts, and the learner would see a coin
    flip. That is the exact bug the v3 rebuild exists to end.

    **A card has no `accepted_variants` column**, unlike `items`, so the back is
    the whole of what can be matched against. That is a real limitation and it is
    why **this verdict never marks a card by itself**: `grade_card` still takes
    the learner's own Again/Hard/Good/Easy, and the typed attempt is what makes
    that self-grade honest rather than what replaces it. Card 17's malformed
    `_____s` hint (#147) and a one-word back would otherwise produce wrong-answer
    marks for correct English, which CLAUDE.md §4 forbids.

    An empty or whitespace-only string is not an answer and is not a match.
    """
    key = equivalence_key(text)
    if not key:
        return False
    return key == equivalence_key(card.back)


def _typed_verdict(
    card: Card, text: str | None
) -> tuple[str | None, bool | None]:
    """``(stored_response, matched)`` for `card_reviews`, or ``(None, None)``.

    Both NULL together, which is what migration 016's
    `card_reviews_a_verdict_needs_its_answer` CHECK requires: a verdict with
    nothing it was a verdict about is unreadable a month later.

    A typed string on a card type that does not take one is DISCARDED rather
    than stored. `recognition` is exempt by ruling — its answer is a meaning, and
    grading a paraphrase would fail a learner for being right in different words
    — so a client that sent one anyway is asking for a judgement this function
    is not allowed to make.
    """
    if text is None or not text.strip():
        return None, None
    if card.card_type not in TYPED_ANSWER_CARD_TYPES:
        return None, None
    return text, answer_matches(card, text)


def attempt_card(
    user_id: int, card_id: int, *, text: str
) -> bool | None:
    """Did this typed answer match? ``None`` when the card is not this learner's.

    **Read-only: it writes nothing.** The attempt is recorded by `grade_card`,
    which recomputes the verdict from the stored `typed_response` rather than
    trusting anything the client carries back.

    Two calls rather than one, and the reason is a rule this codebase already
    holds: the client HAS the back (a card has no hidden half worth a
    projection — see `Card`) but
    `tests/test_web_shell.py::test_no_answer_comparison_in_typescript` forbids it
    comparing anything, because a second definition of "the answer" is how a
    learner ends up seeing a coin flip. So the fold happens on the server, and
    the round trip is the price of there being exactly one of it.

    ``False`` on a card type that takes no typed answer, which is the honest
    answer to "did that match" for a card that was never asking.
    """
    card = get_card(user_id, card_id)
    if card is None:
        return None
    if card.card_type not in TYPED_ANSWER_CARD_TYPES:
        return False
    return answer_matches(card, text)


# ---------------------------------------------------------------------------
# the ONE card serialiser (#190)
# ---------------------------------------------------------------------------


def grade_intervals(card: Card, *, now: datetime) -> dict[str, int]:
    """What each of the four buttons would schedule, in days. Computed, never guessed.

    Four scheduler calls on frozen state — `core.cards.fsrs.review` copies the
    card before touching it, so asking "what would Easy do" cannot advance
    anything.

    **This lived in `apps/api/routers/cards.py` until W10a.** It was arithmetic
    over the scheduler sitting in a route, which CLAUDE.md §2 forbids ("a route
    contains no business logic"), and it was tolerable only while the route was
    the single consumer. W10 added a second — the daily session — and the
    tolerable version became the defect below.
    """
    return {
        name: review(card.state, rating, now=now).scheduled_days or 0
        for name, rating in RATINGS.items()
    }


def card_face(card: Card, *, now: datetime) -> dict:
    """**The only place a card is turned into what a learner's browser receives.**

    `Card.face()` plus `intervals`, and every producer goes through here.

    **This function exists because there were two producers and only one of them
    was complete (#190).** W7's route built `CardFace(**card.face(),
    intervals=...)`; W10's session block returned `card.face()` alone. The
    TypeScript type declared `intervals: Record<Rating, number>` — not optional —
    so `GradeButtons` read `card.intervals[rating]` unguarded and **the session
    crashed on the first card a learner graded.**

    Nothing caught it. `BlockOut.payload` is `dict[str, Any]`, so pydantic
    validated an envelope it had no shape for; Vitest hand-wrote its card
    fixtures, so the client's *expectation* and the server's *output* were never
    compared. Both suites were green and the two halves had never met.

    **The rule this establishes: one contract, one producer.** A second call site
    that assembles a card face by hand is the defect returning, and
    `tests/test_cards_service.py::test_only_one_function_builds_a_card_face`
    fails the commit that adds one.

    `now` is injected, like every other clock in this module, so a due-date
    preview is assertable without freezing time (CLAUDE.md §3 rule 6).

    **`image` (W13d) is added HERE and not in `Card.face()`, for the same
    reason:** a picture is read from `lexeme_images`, and the one producer is
    the one place that read can live without a second caller forgetting it. It
    is None for a phrase card, a collocation card and every word without an
    operator-approved picture — which is PRD §2.6.3's *"demonstrably
    unchanged"*: those faces are what they were, plus `"image": null`.
    """
    return {
        **card.face(),
        "intervals": grade_intervals(card, now=now),
        "image": lexeme_images.face_for(card.card_type, card.lexeme_id),
    }


# ---------------------------------------------------------------------------
# what one request needs (#159)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReviewQueue:
    """The queue, the counts, and the learner's L1 — one service call.

    **`l1_language` rides on the ENVELOPE and not on every card** (#159). It is a
    per-user fact read from `users.native_language`, and eighty copies of it is
    eighty chances for two of them to disagree.

    Why it exists at all: `cards.user_id` references `users(id)` and nothing
    walked the join, so `card-face.tsx` guessed the language from the SCRIPT —
    which tags every Latin-script line `en` and is therefore **silently wrong for
    Lithuanian**. No tofu, no direction symptom, nothing on screen and nothing in
    a log; a screen reader and a hyphenation engine are simply told the wrong
    language. There is no migration in this: `users.native_language TEXT NOT
    NULL` has existed since `001_init_postgres.sql:19`.

    It also makes `/review/queue` a route that calls ONE service function, where
    it used to call two (CLAUDE.md §2).
    """

    cards: list[Card]
    counts: DeckCounts
    l1_language: str


def native_language(conn: Any, user_id: int) -> str:
    """`users.native_language` for this learner. 'en' when the row is unknown.

    Defaulting rather than raising: a missing user is not this function's problem
    to report, and `en` is the one value that makes the renderer do nothing
    special — no `font-l1`, no `lang` override. Failing open to "treat it as
    English" is the harmless direction.
    """
    row = conn.execute(
        "SELECT native_language FROM users WHERE id = %s", (user_id,)
    ).fetchone()
    if row is None or not row["native_language"]:
        return "en"
    return str(row["native_language"])


def review_queue(user_id: int, *, now: datetime, limit: int = 20) -> ReviewQueue:
    """Everything `GET /review/queue` needs, in one call."""
    with connection() as conn:
        language = native_language(conn, user_id)
    return ReviewQueue(
        cards=due_queue(user_id, now=now, limit=limit),
        counts=counts_today(user_id, now=now),
        l1_language=language,
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


# ---------------------------------------------------------------------------
# W8b's retirement — the two halves of `core.cards.retire_chunk_cloze`
# ---------------------------------------------------------------------------
#
# **The predicate is `card_type = 'cloze' AND source_chunk_id IS NOT NULL`, in
# both functions, and it is never a date range and never a list of ids.** That
# is `delete_items_by_hash`' reasoning one module over: a date range sweeps rows
# nobody looked at, and an id list typed into a file is a claim about the
# database that stops being true the moment the database changes. A cloze card
# W13 creates from a video line carries no `source_chunk_id`, so it is outside
# this command **by construction rather than by timing** — it cannot be reached
# by running the command at the wrong moment.

#: The one predicate, written once. Both functions below interpolate it, so the
#: set that is counted and the set that is deleted cannot drift apart into two
#: WHERE clauses that merely happen to agree today.
_CHUNK_CLOZE_SQL = "cards.card_type = 'cloze' AND cards.source_chunk_id IS NOT NULL"


def chunk_cloze_cards_with_review_counts() -> list[tuple[Card, int]]:
    """Every chunk-derived cloze card with how many times it has been graded.

    Read-only. The count travels with the card because the decision that needs
    it — *may this row be deleted at all?* — is per-card: `card_reviews` is
    append-only by design and cascades from `cards`, so deleting a graded card
    discards a real learner event and says nothing about it.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            f"""
            SELECT {_CARD_COLUMNS}, count(r.id) AS review_count
              FROM cards
              LEFT JOIN card_reviews r ON r.card_id = cards.id
             WHERE {_CHUNK_CLOZE_SQL}
             GROUP BY cards.id
             ORDER BY cards.id ASC
            """
        )
        return [(_to_card(row[:-1]), int(row[-1])) for row in cur.fetchall()]


def delete_chunk_cloze_cards() -> list[int]:
    """Delete the chunk-derived cloze cards W8b retired. Returns the ids.

    **A card that has ever been graded is not deleted**, and that guard lives
    here as well as in the caller on purpose. `core.cards.retire_chunk_cloze`
    reads the review counts, prints them and refuses if any is non-zero — but a
    learner can grade a card between that read and this DELETE, and
    `card_reviews`' composite foreign key is `ON DELETE CASCADE`, so the review
    would go with the card and nothing would say so. Two independent guarantees,
    the shape `migrate_chunks` uses for idempotency, and for the same reason:
    the guarantee you can demonstrate on the Mac is not always the one that
    holds on production.

    The caller compares this list against what it previewed and reports a
    difference as a finding rather than as a success.
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            f"""
            DELETE FROM cards
             WHERE {_CHUNK_CLOZE_SQL}
               AND NOT EXISTS (
                   SELECT 1 FROM card_reviews r WHERE r.card_id = cards.id
               )
            RETURNING cards.id
            """
        )
        deleted = [int(row[0]) for row in cur.fetchall()]
    logger.info("chunk cloze cards deleted count=%s", len(deleted))
    return deleted


# ---------------------------------------------------------------------------
# W8f: captured vocabulary — resolution, the anti-join, and the backfill
# ---------------------------------------------------------------------------
#
# SQL lives here and not in `core.cards.capture` / `.import_vocab` /
# `.backfill_lexemes`, so `test_core_boundary.py::test_cards_package_is_pure`
# stays unexempted and #59 remains this project's only boundary exemption.


def resolve_capture_lemma(
    conn: Any, word: str, *, grow: bool = True
) -> tuple[int | None, str]:
    """A captured word → its `lexemes` row. Returns `(id, path)`.

    `path` is one of `identity` | `grown` | `would_grow` | `unresolved`, and it
    is returned rather than logged because the dry run prints it: "9 resolved"
    is not the check, "7 identity + 2 grown" is. If `tier` ever reports
    `identity`, the suffix step is live and has written `ti`.

    **`grow=False` makes this read-only**, which is what a dry run needs:
    `ensure_lexeme` INSERTs, so a dry run that resolved the ordinary way would
    silently add rows to `lexemes` while reporting that it wrote nothing. The
    dry path reports `would_grow` for a word it could add, so the operator sees
    the same two-way split before and after.

    **`lemmatize` IS DELIBERATELY NOT CALLED, and that is the whole function.**

    `core.lexicon.normalize.lemmatize` has three steps, and the third proposes
    suffix-stripped candidates and accepts one **if it is already a known
    lemma**. Its docstring promises it "can fail to resolve, but it cannot
    invent" — which is true literally and false in effect:

        lemmatize("tier") -> "ti"

    `tier` is absent from the 15,000-lemma seed list, so step 3 strips `-er`,
    proposes `['ti', 'tie']`, and `ti` IS in the list at rank 9,856 — an
    artefact of an OpenSubtitles-derived frequency file. Nothing was invented
    and the answer is still wrong.

    That step exists to fold INFLECTIONS onto a lemma. A captured word arrives
    in dictionary form already, so the step buys nothing on this path and costs
    a mislabelled card. And a mislabel here is not cosmetic: migration 013 says
    of `lexeme_id` that it "is what `grade_card` writes the ledger from, with
    source='review'", so a card pointing at `ti` would write ledger evidence for
    the wrong word every time the learner graded it — into the one structure
    CLAUDE.md §5 calls unrebuildable.

    Worse, it would have READ GREEN: the importer would make the identical error
    on the identical input, so `tier` would still deduplicate correctly, because
    both sides of the comparison were wrong in the same direction.

    `ensure_lexeme`'s own docstring assumes the composition this function
    refuses — "called after `lemmatize` has returned None" — and that assumption
    is exactly what `tier` breaks. Filed against W4 (`lemmatize`'s suffix step
    reaches anything absent from the seed list) and NOT fixed here: coverage
    calls `lemmatize` on every transcript token, so changing it moves every
    coverage figure this project has recorded, and that is its own slice with
    its own before-and-after.

    **The importer and the backfill both call this**, which is the point. An
    earlier draft had the importer growing lexemes while the backfill refused
    to, so the same word was a lemma on one path and not on the other.
    """
    normalised = word.strip().lower()
    if not normalised:
        return None, "unresolved"

    from core.services import lexicon as lexicon_service

    found = lexicon_service.lexeme_ids(conn, [normalised])
    if normalised in found:
        return int(found[normalised]), "identity"

    if not grow:
        # Read-only: say what WOULD happen, write nothing. `GROWABLE` is the
        # same regex `ensure_lexeme` applies, imported rather than restated so
        # the dry run and the apply cannot disagree about which words are addable.
        addable = lexicon_service.GROWABLE.match(normalised) is not None
        return None, ("would_grow" if addable else "unresolved")

    # Absent from the dictionary. Grow it — `origin='grown'`, NULL `freq_rank`,
    # which migration 010's frequency floor (`WHERE freq_rank IS NOT NULL`)
    # already refuses to assume known. The dictionary gains exactly what a tap
    # would have added. A multi-word back fails GROWABLE on the space and comes
    # back None, which is how phrase-backed cards stay out of this by themselves.
    grown = lexicon_service.ensure_lexeme(conn, normalised)
    return (int(grown), "grown") if grown is not None else (None, "unresolved")


def lemmas_with_a_card(conn: Any, user_id: int) -> frozenset[str]:
    """Every lemma this learner already has ANY card for.

    The importer's anti-join, and it is **row-level on purpose**: one existing
    card of any type skips the whole row, so a word with a production card does
    not quietly gain a recognition one. The alternative turns the S24a
    verification run into a nine-card write.

    Reads `lexemes.lemma` through the join rather than `cards.back`, because
    `back` is display text and this is an identity question — the same reason
    013 gives `neutral_lexeme_id` for preferring a join to a text match.

    An EXPLICIT tuple cursor, for `create_card`'s reason one page up: this runs
    on a CALLER-OWNED connection and a caller's row factory is not ours to
    assume. `core.db.connection()` yields dict rows and a plain `psycopg.connect`
    yields tuples, and both reach here — the command through the pool, W13's
    route and the tests through their own connection.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT l.lemma
              FROM cards c
              JOIN lexemes l ON l.id = c.lexeme_id
             WHERE c.user_id = %s
            """,
            (user_id,),
        )
        return frozenset(str(row[0]) for row in cur.fetchall())


def cards_needing_a_lexeme(conn: Any) -> list[tuple[int, int, str, str]]:
    """Cards with no `lexeme_id` **whose source chunk is a vocabulary import**.

    `lexeme_id IS NULL AND chunks.source = 'vocabulary'`, and the second half was
    added after a production dry run, not designed in. **It is a predicate about
    WHAT THE CARD TEACHES, not a date range and not an id list** — so
    `retire_chunk_cloze`'s rule is satisfied rather than bent: the population is
    defined by a property of the row that stays true as the database changes.

    **WHY THE SCOPE NARROWED.** `resolve_capture_lemma` refuses `lemmatize`'s
    suffix step because `tier` resolved to `ti` (#177). The dry run found the
    same corruption arriving through the OTHER door:

        mid  →  identity match  →  `mid` ADJ, rank 8,955  ("middle")

    The card teaches the slang sense. The lexeme means *middle*. Nothing
    resolved wrongly, nothing was invented, and no guard fired — **the identity
    match is exactly right about the string and exactly wrong about the word**,
    because `lexemes` carries `pos` and no SENSE distinction at all. Migration
    013 says `lexeme_id` is what `grade_card` writes the ledger from, so that
    card would have written evidence for *middle* every time a learner graded
    the slang meaning. Filed as **#180**.

    A second reason, and it is a product decision rather than a defect:
    `delulu` and `low-key` are absent from the seed list, so an unscoped
    backfill would **grow the shared dictionary** with slang lemmas. `lexemes`
    is global — one row serves every learner — and whether slang belongs in it
    is nobody's call to make inside a backfill.

    **What a `vocabulary` chunk is, and why the lemma is safe there:** a Trancy
    row is a single dictionary word the learner looked up, with its gloss. One
    word, one sense, no register question. That is the population where lemma
    identity means what `cards.lexeme_id` says it means.

    Everything else stays NULL, and that is filed rather than deferred:
    the phrase backs **permanently** (a phrase has no lemma — already ruled),
    and the single-word slang backs until **W13** gives capture a sense-aware
    identity, which `lexemes` cannot express today.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT c.id, c.user_id, c.card_type, c.back
              FROM cards c
              JOIN chunks k ON k.id = c.source_chunk_id
             WHERE c.lexeme_id IS NULL
               AND k.source = 'vocabulary'
             ORDER BY c.id
            """
        )
        return [
            (int(r[0]), int(r[1]), str(r[2]), str(r[3])) for r in cur.fetchall()
        ]


def set_card_lexeme(conn: Any, card_id: int, lexeme_id: int) -> bool:
    """Point one card at its lemma. Returns whether a row changed.

    `AND lexeme_id IS NULL` is in the WHERE and is not decoration: it makes the
    write idempotent and makes a second run report zero instead of rewriting
    rows a later slice may have corrected. This is the only column it touches.
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "UPDATE cards SET lexeme_id = %s WHERE id = %s AND lexeme_id IS NULL",
            (lexeme_id, card_id),
        )
        return cur.rowcount == 1


def captured_cards(user_id: int) -> list[Card]:
    """This learner's imported cards, for the independent read-back.

    Matches on `register_source` — the fourth value migration 015 added — which
    is what makes an import findable in one WHERE. That is the same move
    `user_lexemes.source = 'assumption'` makes for the frequency floor (#93).
    """
    with cursor() as cur:
        cur.row_factory = tuple_row
        cur.execute(
            f"SELECT {_CARD_COLUMNS} FROM cards "
            "WHERE cards.user_id = %s AND cards.register_source = 'import_default' "
            "ORDER BY cards.id ASC",
            (user_id,),
        )
        return [_to_card(r) for r in cur.fetchall()]


# ═══════════════════════════════════════════════════════════════════════════
# W13-ii — the capture path: one tap on a transcript word, two cards.
# ═══════════════════════════════════════════════════════════════════════════

#: Which two card types a capture writes, per register. **MEASURED AGAINST 013's
#: CHECKS ON A REAL DATABASE, all twenty (card_type, register) combinations,
#: before this mapping was written** -- not read off the DDL, because two of the
#: three refusals come from constraints whose names do not mention `card_type`.
#:
#: **THE W13 PLAN's §2e SAID `cloze + production` UNCONDITIONALLY AND THAT PAIR
#: CANNOT BE INSERTED FOR HALF THE REGISTERS.**
#: `cards_receptive_first_until_the_neutral_is_mastered` refuses `production`,
#: `cloze` and `collocation` for `informal` and `slang` until
#: `neutral_mastered_at` is set, and `cards_taboo_is_never_productive` refuses
#: `production` for `taboo`.
#:
#: **This is not a workaround for a constraint; it is CLAUDE.md §4 and 013
#: saying the same thing.** *Slang and informal items are receptive-only until
#: the neutral equivalent is mastered.* A cloze card for a slang word is
#: teaching production of slang, which is the rule's whole subject. So the pair
#: is productive for `neutral`/`formal` and receptive otherwise, and the
#: acceptance criterion -- **two cards of different `card_type`** -- is met in
#: both branches.
_CAPTURE_PAIRS: dict[str, tuple[str, str]] = {
    "formal": ("cloze", "production"),
    "neutral": ("cloze", "production"),
    "informal": ("recognition", "audio"),
    "slang": ("recognition", "audio"),
    "taboo": ("recognition", "audio"),
}


def capture_card_types(register: str) -> tuple[str, str]:
    """The two card types a capture of this register writes.

    Raises on an unknown register rather than defaulting: a register this
    mapping has not been measured against is a register whose CHECKs nobody has
    driven, and guessing would move the failure to a learner's tap.
    """
    try:
        return _CAPTURE_PAIRS[register]
    except KeyError:
        raise ValueError(
            f"no capture pair measured for register {register!r}; "
            f"known: {sorted(_CAPTURE_PAIRS)}"
        ) from None


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """What one tap did. **Three states, and none of them is an exception.**

    `saved` -- two cards written, ids returned.
    `already_saved` -- **#178.** This learner already has this word from this
        line. Distinct from success *and* from failure: a learner who taps twice
        did a normal thing, and a 500 (which is what the raw `UniqueViolation`
        would be through a route) tells them they broke something.
    `no_gloss` -- nothing has been generated for this word. **§1a is ruled
        PRE-GENERATE, so this is a fact rather than a prompt**: the request path
        never generates, and an ungiossed word stays ungiossed until the
        operator runs the command.
    """

    state: str
    card_ids: tuple[int, ...] = ()


def _capture_source_ref(video_id: int, cue_start_s: float | None) -> str:
    """`video:<id>@<seconds>`, or `video:<id>` when there is no offset.

    **The third state is an absent suffix and never a zero** (#330's shape): a
    video whose cues were never stored yields a card carrying the sentence and
    no timestamp, and `@0.000` would be a claim that the line is at the start.
    """
    if cue_start_s is None:
        return f"video:{video_id}"
    return f"video:{video_id}@{cue_start_s:.3f}"


def save_captured_word(
    user_id: int, *, video_id: int, word: str, now: datetime
) -> CaptureResult:
    """One tap on a transcript word. **The one function `POST /video/{id}/save-word`
    calls.**

    **IT REACHES NO MODEL AND CANNOT.** §1a is ruled pre-generate: the
    definition, register, neutral equivalent and who-says-this are already a
    `video_glosses` row, written by `python -m core.video.explain --apply` while
    the operator was watching. This function reads that row. The standing ruling
    of 2026-08-27 -- *the app never generates while a learner waits, and never
    while nobody is watching* -- is held here by construction.

    **THE ALREADY-SAVED PRE-CHECK IS BY `(user_id, context_sentence, front)`
    AND NOT BY LEMMA, AND THAT IS #181's DEFERRAL.** A slang or informal card is
    written with `lexeme_id NULL` -- outside `cards_one_card_per_lemma`, exactly
    as the fifteen migrated recognition cards already are -- so neither that
    index nor `lemmas_with_a_card` can see it. **The stated cost: two captures
    of the same phrase from two DIFFERENT lines are both written**, because the
    line is part of the key. #181's identity question stays open and this does
    not answer it.

    `now` is injected, as everywhere else in this module.
    """
    from core.services import glosses as glosses_service

    with connection() as conn:
        gloss = glosses_service.gloss_for(conn, video_id, word)
        if gloss is None:
            return CaptureResult(state="no_gloss")
        result = capture_from_gloss(
            conn, user_id, video_id=video_id, gloss=gloss,
            context_sentence=gloss.context_sentence, cue_start_s=gloss.cue_start_s,
            now=now,
        )
        conn.commit()
    return result


def capture_from_gloss(
    conn: Any,
    user_id: int,
    *,
    video_id: int,
    gloss: Any,
    context_sentence: str,
    cue_start_s: float | None,
    now: datetime,
) -> CaptureResult:
    """Two cards from one gloss, on the CALLER's connection (no commit).

    **W31c extracted this from `save_captured_word`** so a tap and the
    pending-word job write cards through ONE function — two writers of one card
    shape would be #190's defect. Two changes ride with it:

    * **the sentence is the caller's** — the line the learner tapped (W31c's
      `core.services.words.save`, or a pending row's copy of it), not only the
      line `explain` happened to find first. *"The exact sentence plus
      timestamp"* is the one the learner was looking at;
    * **`lexeme_id` is set for a neutral or formal capture whose gloss key is a
      lexeme (#469)**, through `resolve_capture_lemma(..., grow=False)` — the
      read-only path, identity only, no suffix guessing (#162). Without it no
      picture could ever reach a card saved from a video (`lexeme_images` is
      keyed on it). **Slang, informal and taboo stay NULL**, as W13-ii wrote
      them: their phrase is not the dictionary word.

    **SETTING `lexeme_id` RE-ARMS #178's CONSTRAINT**: `cards_one_card_per_lemma`
    is live for these rows now, so a learner who already has a card for this
    lexeme — from a video, a lesson or the placement import — gets
    `already_saved`, never a `UniqueViolation` (a 500 for a normal tap).
    """
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute("SELECT title FROM videos WHERE id = %s", (video_id,))
        title_row = cur.fetchone()
    title = title_row[0] if title_row else None

    front = gloss.word
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            """
            SELECT 1 FROM cards
             WHERE user_id = %s AND context_sentence = %s AND front = %s
             LIMIT 1
            """,
            (user_id, context_sentence, front),
        )
        seen = cur.fetchone()
    if seen is not None:
        return CaptureResult(state="already_saved")

    lexeme_id: int | None = None
    if gloss.register in ("neutral", "formal"):
        lexeme_id, _path = resolve_capture_lemma(conn, front, grow=False)
    if lexeme_id is not None:
        with conn.cursor(row_factory=tuple_row) as cur:
            cur.execute(
                "SELECT 1 FROM cards WHERE user_id = %s AND lexeme_id = %s LIMIT 1",
                (user_id, lexeme_id),
            )
            if cur.fetchone() is not None:
                return CaptureResult(state="already_saved")

    state = CardState(
        fsrs_state="learning",
        fsrs_step=0,
        stability=None,
        difficulty=None,
        due=now,
        last_review=None,
        lapses=0,
        reps=0,
    )
    written: list[int] = []
    for card_type in capture_card_types(gloss.register):
        card_id = create_card(
            conn,
            user_id,
            card_type=card_type,
            front=front,
            back=gloss.definition,
            register=gloss.register,
            # 013 declared `detected` and NOTHING HAS EVER WRITTEN IT but this
            # path -- which is what makes #126's re-tagging pass a
            # `WHERE register_source = 'migration_default'` away.
            register_source="detected",
            state=state,
            source_ref=_capture_source_ref(video_id, cue_start_s),
            context_sentence=context_sentence,
            # `meaning` only where 013's CHECK requires it (#158, #356): see the
            # W13-ii note this replaced, kept in `save_captured_word`'s history.
            meaning=(
                gloss.definition
                if gloss.register in ("informal", "slang")
                else None
            ),
            neutral_equivalent=gloss.neutral_equivalent,
            who_says_this=gloss.who_says_this,
            lexeme_id=lexeme_id,
            captured_at=now,
            source_title=title,
        )
        if card_id is not None:
            written.append(card_id)
    return CaptureResult(state="saved", card_ids=tuple(written))
