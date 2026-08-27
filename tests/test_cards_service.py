"""`core.services.cards` against a real database: caps, leech, promotion, ledger.

**The clock is injected everywhere**, so nothing here freezes time and no
assertion compares against a calendar date (CLAUDE.md §3 rule 6). Every
expectation is a delta from an instant the test chose.

**The FSRS arithmetic is not re-asserted here.** `tests/test_cards_fsrs.py`
pins it against py-fsrs' own published vectors; this file asserts what the
*service* does with the result — that it persists it, logs both sides of it,
counts a lapse, and stops at the caps.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from core.cards import (
    DAILY_NEW_CARD_CAP,
    DAILY_REVIEW_CAP,
    LEECH_LAPSES,
    PRODUCTIVE_CARD_TYPES,
    RATINGS,
)
from core.cards.fsrs import CardState, initial_state
from core.config import load_settings
from core.services import cards as svc

T0 = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)
AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def learner(db):
    row = db.execute(
        "INSERT INTO users (name, native_language, auth_email, onboarded) "
        "VALUES ('w7-svc', 'fa', %s, TRUE) RETURNING id",
        (f"w7-svc-{secrets.token_hex(6)}@example.invalid",),
    ).fetchone()
    user_id = int(row[0])
    db.commit()
    try:
        yield user_id
    finally:
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.commit()


def _mature(due: datetime) -> CardState:
    return CardState(
        fsrs_state="review",
        fsrs_step=None,
        stability=10.0,
        difficulty=5.0,
        due=due,
        last_review=due - timedelta(days=10),
        lapses=0,
        reps=4,
    )


def _card(db, user_id: int, **over) -> int:
    spec = dict(
        card_type="cloze",
        front="I _____ to the shops.",
        back="went",
        register="neutral",
        register_source="migration_default",
        state=_mature(T0 - timedelta(days=1)),
        meaning="past of go",
        context_sentence="I went to the shops.",
        source_ref="himym",
    )
    spec.update(over)
    card_id = svc.create_card(db, user_id, **spec)
    db.commit()
    assert card_id is not None
    return card_id


# ── the caps, PRD §5 ───────────────────────────────────────────────────────


def test_the_caps_are_prds_numbers() -> None:
    """Stated here so a change to them is a change to a test, not a constant."""
    assert DAILY_NEW_CARD_CAP == 12
    assert DAILY_REVIEW_CAP == 80


def test_the_new_card_cap_stops_the_queue(db, learner) -> None:
    """Thirteen new cards due; twelve are served. The real constant, not a stub."""
    for i in range(DAILY_NEW_CARD_CAP + 1):
        _card(db, learner, front=f"new {i}", state=initial_state(due=T0 - timedelta(days=1)))
    queue = svc.due_queue(learner, now=T0, limit=50)
    assert len(queue) == DAILY_NEW_CARD_CAP


def test_the_review_cap_stops_the_queue(db, learner) -> None:
    """Eighty-five review cards due; eighty are served."""
    for i in range(DAILY_REVIEW_CAP + 5):
        _card(db, learner, front=f"review {i}")
    queue = svc.due_queue(learner, now=T0, limit=200)
    assert len(queue) == DAILY_REVIEW_CAP


def test_the_two_budgets_do_not_borrow_from_each_other(db, learner) -> None:
    """A heavy reviewing day must not eat the new-card allowance, or the reverse.

    Two separate budgets rather than one total: a review is a card the learner
    has already invested in, and a pile of new captures must not crowd it out.
    """
    for i in range(20):
        _card(db, learner, front=f"new {i}", state=initial_state(due=T0 - timedelta(days=1)))
    for i in range(20):
        _card(db, learner, front=f"review {i}")
    queue = svc.due_queue(learner, now=T0, limit=200)
    assert len(queue) == 20 + DAILY_NEW_CARD_CAP  # all reviews, capped new


def test_reviews_are_served_before_new_cards(db, learner) -> None:
    new_id = _card(db, learner, front="new", state=initial_state(due=T0 - timedelta(days=1)))
    review_id = _card(db, learner, front="review")
    queue = svc.due_queue(learner, now=T0, limit=2)
    assert [c.id for c in queue] == [review_id, new_id]


def test_grading_counts_against_the_cap_for_the_rest_of_the_day(db, learner) -> None:
    ids = [
        _card(db, learner, front=f"new {i}", state=initial_state(due=T0 - timedelta(days=1)))
        for i in range(DAILY_NEW_CARD_CAP + 1)
    ]
    for card_id in ids[:DAILY_NEW_CARD_CAP]:
        svc.grade_card(learner, card_id, rating=EASY, now=T0)
    assert svc.due_queue(learner, now=T0, limit=50) == []
    # …and the budget returns tomorrow, without the skipped card piling up.
    assert svc.counts_today(learner, now=T0 + timedelta(days=1)).new_remaining >= 1


def test_the_counts_never_report_a_backlog(db, learner) -> None:
    """CLAUDE.md §4: missed days shrink the task; they never pile up."""
    for i in range(40):
        _card(db, learner, front=f"new {i}", state=initial_state(due=T0 - timedelta(days=30)))
    counts = svc.counts_today(learner, now=T0)
    assert counts.new_remaining == DAILY_NEW_CARD_CAP
    assert counts.total_remaining == DAILY_NEW_CARD_CAP


# ── grading ────────────────────────────────────────────────────────────────


def test_grading_moves_the_due_date_and_persists_it(db, learner) -> None:
    card_id = _card(db, learner)
    outcome = svc.grade_card(learner, card_id, rating=GOOD, now=T0)
    assert outcome is not None
    stored = svc.get_card(learner, card_id)
    assert stored.state.due == outcome.due
    assert stored.state.due > T0
    assert stored.state.last_review == T0


def test_the_four_grades_schedule_in_order_through_the_service(db, learner) -> None:
    dues = []
    for rating in (AGAIN, HARD, GOOD, EASY):
        card_id = _card(db, learner, front=f"card {rating}")
        outcome = svc.grade_card(learner, card_id, rating=rating, now=T0)
        dues.append(outcome.due)
    assert dues == sorted(dues)
    assert len(set(dues)) == 4


def test_every_grade_appends_exactly_one_review_row_with_both_sides(
    db, learner
) -> None:
    """The log is the half that cannot be recovered later."""
    card_id = _card(db, learner)
    svc.grade_card(learner, card_id, rating=GOOD, now=T0, duration_ms=4200)
    row = db.execute(
        "SELECT rating, reviewed_at, state_before, stability_before, "
        "state_after, stability_after, due_after, elapsed_days, "
        "scheduled_days, review_duration_ms "
        "FROM card_reviews WHERE card_id = %s",
        (card_id,),
    ).fetchall()
    assert len(row) == 1
    (rating, reviewed_at, sb, stab_b, sa, stab_a, due_after, elapsed,
     scheduled, duration) = row[0]
    assert rating == GOOD
    assert reviewed_at == T0
    assert sb == "review" and stab_b == pytest.approx(10.0)
    assert sa == "review" and stab_a != pytest.approx(10.0)
    assert due_after == svc.get_card(learner, card_id).state.due
    assert elapsed == 11  # due was T0-1d, last_review 10 days before that
    assert scheduled == (due_after - T0).days
    assert duration == 4200


def test_the_logged_instant_is_the_instant_that_scheduled_the_card(
    db, learner
) -> None:
    """Migration 013 gives `reviewed_at` no default precisely so this holds.

    A `DEFAULT NOW()` would make them two different clock reads, and the
    difference is invisible until someone replays the log.
    """
    card_id = _card(db, learner)
    svc.grade_card(learner, card_id, rating=GOOD, now=T0)
    reviewed_at = db.execute(
        "SELECT reviewed_at FROM card_reviews WHERE card_id = %s", (card_id,)
    ).fetchone()[0]
    assert reviewed_at == T0
    assert svc.get_card(learner, card_id).state.last_review == reviewed_at


def test_a_meaningless_duration_is_stored_as_null_rather_than_a_lie(
    db, learner
) -> None:
    """A learner who puts the phone down for an hour reports a real number.

    Nothing schedules on it either way — FSRS-6's inputs are state, stability,
    difficulty, elapsed days and the rating (#108).
    """
    card_id = _card(db, learner)
    svc.grade_card(learner, card_id, rating=GOOD, now=T0, duration_ms=99_999_999)
    stored = db.execute(
        "SELECT review_duration_ms FROM card_reviews WHERE card_id = %s", (card_id,)
    ).fetchone()[0]
    assert stored is None


def test_another_learners_card_is_not_gradeable(db, learner) -> None:
    card_id = _card(db, learner)
    row = db.execute(
        "INSERT INTO users (name, native_language, auth_email, onboarded) "
        "VALUES ('w7-other', 'fa', %s, TRUE) RETURNING id",
        (f"w7-other-{secrets.token_hex(6)}@example.invalid",),
    ).fetchone()
    other = int(row[0])
    db.commit()
    try:
        assert svc.grade_card(other, card_id, rating=GOOD, now=T0) is None
    finally:
        db.execute("DELETE FROM users WHERE id = %s", (other,))
        db.commit()


# ── the leech rule, PRD §5 ─────────────────────────────────────────────────


def _lapse(learner: int, card_id: int, moment: datetime) -> datetime:
    """One full lapse cycle: fall out of Review, then climb back into it.

    **A lapse is falling out of the Review state, not answering Again.** A card
    already in relearning that is answered Again stays in relearning and counts
    nothing further — otherwise a single bad minute would spend the whole leech
    budget, and PRD §5's "6 lapses" would mean six taps rather than six times
    the phrase was genuinely forgotten. So the loop grades Again (Review →
    relearning, one lapse) and then Good (relearning → Review), which is what a
    real card's history looks like.
    """
    outcome = svc.grade_card(learner, card_id, rating=AGAIN, now=moment)
    moment = outcome.due + timedelta(minutes=30)
    outcome = svc.grade_card(learner, card_id, rating=GOOD, now=moment)
    return outcome.due + timedelta(minutes=30)


def test_a_leech_is_rewritten_with_a_cue_and_never_suspended(db, learner) -> None:
    """PRD §5: "leech at 6 lapses → card is rewritten with an easier cue, not
    suspended". Migration 013 has no `suspended` column, so the second half is
    a schema fact; this asserts the first."""
    card_id = _card(db, learner)
    moment = T0
    for _ in range(LEECH_LAPSES):
        moment = _lapse(learner, card_id, moment)
    stored = svc.get_card(learner, card_id)
    assert stored.state.lapses == LEECH_LAPSES
    assert stored.leech_at is not None
    # `first_letter_cue`, reused from the item repair ladder.
    assert stored.cue_text and stored.cue_text.startswith("w")
    assert stored.cue_text != "went"
    # The card is still in the deck. Nothing hides it.
    assert svc.get_card(learner, card_id) is not None


def test_answering_again_twice_in_a_row_counts_one_lapse(db, learner) -> None:
    """Falling out of Review is the lapse; flailing inside relearning is not.

    Without this rule a single bad minute spends the whole leech budget and
    PRD §5's "6 lapses" would mean six taps rather than six forgettings.
    """
    card_id = _card(db, learner)
    first = svc.grade_card(learner, card_id, rating=AGAIN, now=T0)
    svc.grade_card(learner, card_id, rating=AGAIN, now=first.due + timedelta(minutes=30))
    assert svc.get_card(learner, card_id).state.lapses == 1


def test_a_card_below_the_threshold_is_not_a_leech(db, learner) -> None:
    card_id = _card(db, learner)
    moment = T0
    for _ in range(LEECH_LAPSES - 1):
        moment = _lapse(learner, card_id, moment)
    stored = svc.get_card(learner, card_id)
    assert stored.state.lapses == LEECH_LAPSES - 1
    assert stored.leech_at is None
    assert stored.cue_text is None


def test_the_leech_mark_is_set_once(db, learner) -> None:
    card_id = _card(db, learner)
    moment = T0
    marked_at = None
    for _ in range(LEECH_LAPSES + 3):
        moment = _lapse(learner, card_id, moment)
        if marked_at is None:
            stored = svc.get_card(learner, card_id)
            if stored.leech_at is not None:
                marked_at = stored.leech_at
    assert marked_at is not None
    assert svc.get_card(learner, card_id).leech_at == marked_at


# ── the receptive-first rule, PRD §8.5.2 ───────────────────────────────────


SLANG = dict(
    register="slang",
    register_source="detected",
    front="That's a hard pass.",
    back="hard pass",
    meaning="a firm refusal",
    context_sentence="That's a hard pass from me.",
    neutral_equivalent="I'd rather not, thanks",
    who_says_this="Friends and casual colleagues. Not in a client email.",
)


def test_a_slang_recognition_card_is_always_allowed(db, learner) -> None:
    """`recognition` and `audio` are the two PRD §8.5.2 permits for slang."""
    assert _card(db, learner, card_type="recognition", **SLANG)


@pytest.mark.parametrize("card_type", sorted(PRODUCTIVE_CARD_TYPES))
def test_no_productive_slang_card_can_be_created_directly(
    db, learner, card_type: str
) -> None:
    """**The ordering criterion, and the CHECK is what makes it survive W10.**

    All THREE productive types, not just `production`. PRD §8.5.2 permits
    "recognition and listening cards only" for slang, and **a cloze card asks
    the learner to produce the phrase into a gap** — it is a production card
    with a sentence around it, not a milder form of one. An earlier draft of
    this constraint barred `production` alone, which would have let the entire
    migrated deck for two learners consist of slang cloze cards.

    A guard living only in today's card-creating code is a guard the next
    card-creating slice does not know about. This is the database refusing.
    """
    with pytest.raises(psycopg.errors.CheckViolation):
        _card(db, learner, card_type=card_type, **SLANG)
    db.rollback()


def test_a_slang_card_missing_any_of_prds_four_things_is_refused(db, learner) -> None:
    """PRD §8.5.4. A slang card without the safe alternative is the card the
    PRD calls "useless and slightly dangerous"."""
    for missing in ("neutral_equivalent", "who_says_this", "meaning", "context_sentence"):
        spec = dict(SLANG)
        spec[missing] = None
        with pytest.raises(psycopg.errors.CheckViolation):
            _card(db, learner, card_type="recognition", **spec)
        db.rollback()


def test_a_taboo_production_card_can_never_exist(db, learner) -> None:
    """PRD §8.5.1: taboo is receptive only. Row-local, so no promotion path."""
    with pytest.raises(psycopg.errors.CheckViolation):
        _card(
            db,
            learner,
            card_type="production",
            register="taboo",
            register_source="detected",
            neutral_equivalent="not now",
            who_says_this="nobody, professionally",
            meaning="an expletive",
            context_sentence="…",
        )
    db.rollback()


def _lexeme(db) -> int:
    row = db.execute("SELECT id FROM lexemes ORDER BY id LIMIT 1").fetchone()
    assert row is not None, "the lexicon seed is required — run core.lexicon.seed"
    return int(row[0])


def test_promotion_refuses_until_the_neutral_equivalent_is_mastered(
    db, learner
) -> None:
    lexeme_id = _lexeme(db)
    card_id = _card(
        db, learner, card_type="recognition", neutral_lexeme_id=lexeme_id, **SLANG
    )

    # No ledger row at all.
    assert svc.promote_to_production(learner, card_id, now=T0) is False

    # Known is not mastered. `core.lexicon.states.STATES` already defines the
    # ladder; W7 does not invent a second notion of mastery beside it.
    db.execute(
        "INSERT INTO user_lexemes (user_id, lexeme_id, state, source, source_rank) "
        "VALUES (%s, %s, 'known', 'review', 5)",
        (learner, lexeme_id),
    )
    db.commit()
    assert svc.promote_to_production(learner, card_id, now=T0) is False

    db.execute(
        "UPDATE user_lexemes SET state = 'mastered' "
        "WHERE user_id = %s AND lexeme_id = %s",
        (learner, lexeme_id),
    )
    db.commit()
    assert svc.promote_to_production(learner, card_id, now=T0) is True
    assert svc.get_card(learner, card_id).neutral_mastered_at is not None


def test_promotion_does_nothing_to_a_neutral_card(db, learner) -> None:
    """A neutral card was never barred, so there is nothing to record."""
    card_id = _card(db, learner)
    assert svc.promote_to_production(learner, card_id, now=T0) is False
    assert svc.get_card(learner, card_id).neutral_mastered_at is None


def test_a_promoted_slang_production_card_is_accepted(db, learner) -> None:
    """The other side of the CHECK: once the evidence is recorded, it passes."""
    card_id = svc.create_card(
        db,
        learner,
        card_type="recognition",
        state=_mature(T0),
        register_source="detected",
        **{k: v for k, v in SLANG.items() if k != "register_source"},
    )
    db.commit()
    db.execute(
        "UPDATE cards SET card_type = 'production', neutral_mastered_at = %s "
        "WHERE id = %s",
        (T0, card_id),
    )
    db.commit()  # no CheckViolation


# ── /prep never becomes a slang card, PRD §8.5.2 ───────────────────────────


def test_a_prep_sourced_slang_card_is_refused(db, learner) -> None:
    """The half that does not depend on a model complying with a prompt.

    `/prep` is a v2 Telegram surface and dies at W22; the deck does not, so the
    durable rule is stated about the deck rather than about the command.
    """
    for register in ("slang", "taboo"):
        with pytest.raises(svc.CardWriteError, match="prep"):
            svc.refuse_forbidden_prep_register("prep_client_call", register)


def test_a_prep_sourced_neutral_card_is_fine(db, learner) -> None:
    assert _card(db, learner, source_ref="prep_client_call") is not None


def test_a_non_prep_source_is_not_constrained_by_the_prep_rule() -> None:
    svc.refuse_forbidden_prep_register("himym_s2e4", "slang")
    svc.refuse_forbidden_prep_register(None, "slang")


# ── the ledger, and the honesty of the instrument ─────────────────────────


def test_a_graded_card_writes_the_ledger_as_measured_retrieval(db, learner) -> None:
    """The first `review`-sourced write in this project.

    `review` is an AUTHORITATIVE_SOURCE and is in `MAY_LOWER`, which is why W4a
    exists: gating on rank alone would have made every lapse from W7 onward
    vanish. That has to be proven false rather than assumed.
    """
    lexeme_id = _lexeme(db)
    card_id = _card(db, learner, lexeme_id=lexeme_id)
    svc.grade_card(learner, card_id, rating=GOOD, now=T0)
    row = db.execute(
        "SELECT state, source FROM user_lexemes WHERE user_id = %s AND lexeme_id = %s",
        (learner, lexeme_id),
    ).fetchone()
    assert row == ("known", "review")


def test_a_lapse_lowers_the_ledger_state(db, learner) -> None:
    """The assertion W4a's comment says would otherwise have been silently lost."""
    lexeme_id = _lexeme(db)
    card_id = _card(db, learner, lexeme_id=lexeme_id)
    svc.grade_card(learner, card_id, rating=GOOD, now=T0)
    svc.grade_card(learner, card_id, rating=AGAIN, now=T0 + timedelta(days=1))
    row = db.execute(
        "SELECT state FROM user_lexemes WHERE user_id = %s AND lexeme_id = %s",
        (learner, lexeme_id),
    ).fetchone()
    assert row[0] == "learning"


def test_a_card_with_no_target_lemma_writes_no_ledger_row(db, learner) -> None:
    """Migrated v2 cards are phrases, not lemmas. The path exists for W13."""
    before = db.execute(
        "SELECT count(*) FROM user_lexemes WHERE user_id = %s", (learner,)
    ).fetchone()[0]
    card_id = _card(db, learner)
    svc.grade_card(learner, card_id, rating=GOOD, now=T0)
    after = db.execute(
        "SELECT count(*) FROM user_lexemes WHERE user_id = %s", (learner,)
    ).fetchone()[0]
    assert before == after


def test_no_path_converts_an_item_attempt_into_a_card_rating() -> None:
    """**A card rating is self-reported by design; a `self` item mark is not.**

    `item_attempts.graded_by = 'self'` means "nothing checked this answer" —
    W6's spoken types. A card rating is the learner telling the scheduler how
    retrieval felt, which is what FSRS *is*. Turning one into the other would
    put a self-assessment into a scheduler as though it were a measurement, and
    W19 would inherit a progress line that silently mixes two instruments.

    Parsed rather than reasoned about, so the commit that adds such a path
    fails here.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(svc))

    # Docstrings are excluded on purpose: this module's own docstring explains
    # *why* the path does not exist, and a naive substring scan would fail on
    # the explanation. What is checked is executable code — every string
    # literal that is not a docstring (which is where a query would live) and
    # every import.
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node in docstrings:
                continue
            assert "item_attempts" not in node.value, node.value
        # `core.services.items` specifically — NOT `core.items`. The pure
        # half is legitimately reused: `first_letter_cue` is a function over a
        # string, and a second copy of it here would drift from the one the
        # item gates already trust. What must not happen is this module reading
        # an item's ATTEMPTS.
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") != "core.services.items", node.module
            if (node.module or "") == "core.services":
                assert all(a.name != "items" for a in node.names)
        if isinstance(node, ast.Import):
            assert all(a.name != "core.services.items" for a in node.names)


def test_promote_to_production_is_the_only_writer_of_the_promotion_column() -> None:
    """`neutral_mastered_at` is what turns a cross-table rule into a row-local
    CHECK. A second writer would make the CHECK a formality."""
    import inspect
    import re

    source = inspect.getsource(svc)
    # SQL assignments only. `neutral_mastered_at=row[16]` in `_to_card` is a
    # READ, and matching it would make this test fail for the one construction
    # that is unavoidable.
    writes = [
        line
        for line in source.splitlines()
        if re.search(r"neutral_mastered_at\s*=\s*%s", line)
    ]
    assert len(writes) == 1, writes
    body = inspect.getsource(svc.promote_to_production)
    assert "neutral_mastered_at = %s" in body


# ── the cloze reader, W8a's measurement ────────────────────────────────────
#
# `export_rows` and its four tests stood here from W7 until 2026-08-25. The
# route they served is gone, so they are gone. `cloze_cards` replaces neither
# the function nor the tests: it answers a different question, for a human-run
# measurement rather than for a route.


def test_the_cloze_reader_returns_only_cloze_cards(db, learner) -> None:
    """The population under measurement is the gapped cards and nothing else.

    W8a's finding is about how a cloze card is *made* — `make_sentence_with_gap`
    removes the phrase and checks nothing. A `recognition` or `production` card
    is not gapped and cannot have the defect, so probing one would be
    money spent on a question that cannot come back interesting.
    """
    _card(db, learner, card_type="cloze", front="I _____ to the shops.")
    _card(db, learner, card_type="recognition", **SLANG)
    got = svc.cloze_cards()
    mine = [c for c in got if c.user_id == learner]
    assert [c.card_type for c in mine] == ["cloze"]


def test_the_cloze_reader_is_not_scoped_to_one_learner(db, learner) -> None:
    """Deliberately unkeyed. The question is about the deck, not about a person.

    `export_rows` took a `user_id` because a backup belongs to whoever downloads
    it. This does not, and the difference is why one replaced the other rather
    than being renamed into it.
    """
    import inspect

    assert inspect.signature(svc.cloze_cards).parameters == {}
    _card(db, learner, card_type="cloze", front="She _____ it anyway.")
    assert any(c.user_id == learner for c in svc.cloze_cards())


def test_the_cloze_reader_preserves_the_five_underscore_gap(db, learner) -> None:
    """The front is read back byte-identical, gap and all.

    `core.services.anki.GAP` is five underscores and `core.items.schema.GAP` is
    three. The probe is handed the card's own front unmodified, because five is
    what the learner sees — rewriting it would send the model a sentence nobody
    is looking at, which is the defect W5b found and W5c fixed.
    """
    front = '"I wish someone had warned me to ask about _____ upfront," she said.'
    card_id = _card(db, learner, card_type="cloze", front=front)
    got = {c.id: c for c in svc.cloze_cards()}[card_id]
    assert got.front == front
    assert "_____" in got.front


def test_the_cloze_reader_writes_nothing(db, learner) -> None:
    """Read twice, identical both times, and the row is untouched."""
    card_id = _card(db, learner, card_type="cloze")
    before = db.execute(
        "SELECT front, back, due, reps, lapses FROM cards WHERE id = %s", (card_id,)
    ).fetchone()
    svc.cloze_cards()
    svc.cloze_cards()
    after = db.execute(
        "SELECT front, back, due, reps, lapses FROM cards WHERE id = %s", (card_id,)
    ).fetchone()
    assert before == after


# ── the ratings map to the library's integers ─────────────────────────────


def test_the_rating_names_are_the_four_fsrs_grades() -> None:
    assert set(RATINGS) == {"again", "hard", "good", "easy"}
    assert sorted(RATINGS.values()) == [1, 2, 3, 4]


# --------------------------------------------------------------------------
# #190: one contract, one producer
# --------------------------------------------------------------------------


def test_only_one_module_builds_a_card_face() -> None:
    """**The rule that stops #190 coming back, and it is a rule about producers.**

    W10 shipped a session whose block 1 crashed on the first card a learner
    graded. The cause was not a typo: `Card.face()` returns the card's own
    columns, `intervals` is computed from the scheduler, and the client's
    `CardFace` type declares both — so a caller who reaches for `face()` gets an
    object TypeScript believes is complete and which is not.
    `apps/api/routers/cards.py` added the missing field; W10's
    `core.services.sessions._review_block` did not, and nothing compared them.

    So `Card.face()` may be called from exactly ONE module —
    `core.services.cards`, where `card_face` completes it — and every producer
    goes through that. **A second hand-assembled face is the defect returning.**

    Asserted by MODULE rather than by line, because the rule is about who
    produces a card face and not about where the call sits. Parsed and never
    grepped: prose about the rule is not the rule being broken (#150).
    """
    import ast
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    roots = ("packages/core", "apps/api", "apps/worker", "apps/bot")

    callers: set[str] = set()
    for name in roots:
        for path in sorted((repo_root / name).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "face"
                ):
                    callers.add(str(path.relative_to(repo_root)))

    assert callers == {"packages/core/services/cards.py"}, (
        "`Card.face()` may be called only inside `core.services.cards`, where "
        "`card_face` completes it with `intervals`. Callers found: "
        + ", ".join(sorted(callers))
    )


def test_a_card_face_always_carries_all_four_intervals() -> None:
    """The field the client reads unguarded, asserted where it is produced.

    `GradeButtons` maps over `RATINGS` and reads `card.intervals[rating]` for
    every one of the four. A face carrying three of them crashes exactly as a
    face carrying none does.
    """
    from datetime import datetime, timezone

    from core.cards import RATINGS
    from core.cards.fsrs import initial_state
    from core.services.cards import Card, card_face

    now = datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc)
    card = Card(
        id=1,
        user_id=1,
        card_type="production",
        source_chunk_id=None,
        source_ref=None,
        front="to eat quickly",
        back="devour",
        context_sentence=None,
        meaning=None,
        neutral_equivalent=None,
        neutral_lexeme_id=None,
        who_says_this=None,
        lexeme_id=None,
        cue_text=None,
        register="neutral",
        register_source="import_default",
        neutral_mastered_at=None,
        state=initial_state(due=now),
        leech_at=None,
    )
    face = card_face(card, now=now)
    assert set(face["intervals"]) == set(RATINGS)
    assert all(isinstance(v, int) for v in face["intervals"].values())
