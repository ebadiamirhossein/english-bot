"""`core.cards.migrate_chunks` — the fan-out table, and idempotency proved twice.

The fan-out tests are pure (`plan_for_chunk` takes a row and returns a plan), so
the whole decision table is asserted without Postgres. The idempotency tests are
not, because the property being asserted is about what a second run writes to a
real table.

**The accounting identity is the load-bearing assertion.** Every chunk lands in
exactly one bucket, so "nothing was silently lost" is checkable rather than
asserted. The runbook's independent `psql` query computes the same sum from the
other side, without importing anything from this module.

**W8b: no `cloze` card is created from a chunk, and that is asserted rather than
merely no longer exercised.** A pass that stopped producing a card type would
otherwise be indistinguishable from a test file that stopped looking for one —
which is how a defect survives a rewrite. `test_the_pass_never_plans_a_cloze_card`
walks the whole decision table and is the criterion.
"""

from __future__ import annotations

from datetime import date

import psycopg
import pytest

from core.cards import CHUNK_CARD_TYPES, MIGRATION_CARD_TYPES
from core.cards.migrate_chunks import plan_for_chunk, run
from core.cards.slang_glosses import SlangGloss
from core.config import load_settings

TODAY = date(2026, 8, 25)


def _row(**over):
    row = {
        "id": 1,
        "user_id": 9,
        "chunk": "hard pass",
        "full_sentence": "That's a hard pass from me.",
        "meaning": "a firm refusal",
        "source": "himym_s2e4",
        "track": "life",
        "next_review": None,
        "times_right": 0,
        "times_wrong": 0,
        "streak_right": 0,
    }
    row.update(over)
    return row


# ── the fan-out table, pure ────────────────────────────────────────────────


def test_a_complete_chunk_becomes_ONE_production_card_and_never_a_cloze() -> None:
    plan = plan_for_chunk(_row(), today=TODAY)
    assert plan.bucket == "production_with_hint"
    assert [c["card_type"] for c in plan.cards] == ["production"]


@pytest.mark.parametrize(
    "row",
    [
        _row(),
        _row(meaning=None),
        _row(full_sentence=None),
        _row(full_sentence="Something else entirely."),
        _row(meaning=None, full_sentence=None),
        _row(source="slang"),
        _row(times_right=9, times_wrong=1, streak_right=4),
    ],
    ids=[
        "complete", "no_meaning", "no_sentence", "phrase_not_in_sentence",
        "neither", "slang", "with_history",
    ],
)
def test_the_pass_never_plans_a_cloze_card(row) -> None:
    """**W8b's criterion, over the whole decision table.**

    Every shape a v2 chunk can take, including the glossed-slang route, asserted
    against a hardcoded card type rather than against whatever `plan_for_chunk`
    returns (CLAUDE.md §3 rule 5). The constants are checked in the same test
    because the pass and the anti-join read them, and a creator that no longer
    writes a card type while `MIGRATION_CARD_TYPES` still claims it would leave
    the idempotency set describing rows nobody writes.

    The ruling, its three causes and its cost are in the module's docstring.
    """
    plan = plan_for_chunk(row, today=TODAY, glosses=GLOSSES)
    assert all(spec["card_type"] != "cloze" for spec in plan.cards)
    assert "cloze" not in CHUNK_CARD_TYPES
    assert "cloze" not in MIGRATION_CARD_TYPES
    assert CHUNK_CARD_TYPES == ("production",)


def test_the_production_front_carries_the_gloss_and_the_context_hint() -> None:
    """The gapped sentence is now a HINT and never a question.

    It is built by `core.services.anki.make_sentence_with_gap`, the same
    function `due_chunks` uses to decide a chunk is reviewable at all — so a
    chunk v2 could gap is a chunk this migration can hint with, by construction.
    The exact string is asserted here because this is the only card that carries
    it since W8b retired the cloze card that used to.
    """
    (production,) = plan_for_chunk(_row(), today=TODAY).cards
    assert production["front"] == "a firm refusal\nThat's a _____ from me."
    assert production["back"] == "hard pass"
    assert production["context_sentence"] == "That's a hard pass from me."


def test_a_chunk_whose_phrase_is_not_in_its_sentence_still_makes_a_production_card() -> None:
    plan = plan_for_chunk(
        _row(full_sentence="Something else entirely."), today=TODAY
    )
    assert plan.bucket == "production_no_hint"
    assert [c["card_type"] for c in plan.cards] == ["production"]
    assert plan.cards[0]["front"] == "a firm refusal"


def test_a_chunk_with_no_sentence_still_makes_a_production_card() -> None:
    plan = plan_for_chunk(_row(full_sentence=None), today=TODAY)
    assert plan.bucket == "production_no_hint"
    assert [c["card_type"] for c in plan.cards] == ["production"]


def test_a_chunk_with_no_meaning_now_makes_no_card_at_all() -> None:
    """**The cost of W8b, made falsifiable.** This chunk used to get a cloze card.

    It is `skipped_no_meaning` rather than `skipped_no_face` because the two are
    worth telling apart in a run's output: this one had a gappable sentence and
    was served until 2026-08-25. The bucket was empty on production the day the
    ruling shipped, and #148 records the constraint every future import inherits
    — a chunk with no gloss now yields nothing.
    """
    plan = plan_for_chunk(_row(meaning=None), today=TODAY)
    assert plan.bucket == "skipped_no_meaning"
    assert plan.cards == ()


def test_a_chunk_that_can_produce_neither_produces_nothing() -> None:
    plan = plan_for_chunk(
        _row(meaning=None, full_sentence=None), today=TODAY
    )
    assert plan.bucket == "skipped_no_face"
    assert plan.cards == ()


def test_a_slang_chunk_with_no_gloss_produces_no_card() -> None:
    """PRD §8.5.4 requires four things and a v2 chunk carries two.

    A slang card showing the meaning but not the safe alternative is the card
    §8.5.4 calls "useless and slightly dangerous", and migration 013's
    `cards_informal_shows_the_four_things` CHECK would refuse it anyway. Counted
    and reported so the operator can see which phrases are still unhandled.
    """
    plan = plan_for_chunk(_row(source="slang"), today=TODAY, glosses={})
    assert plan.bucket == "skipped_slang_no_gloss"
    assert plan.cards == ()


GLOSSES = {
    "hard pass": SlangGloss(
        chunk="hard pass",
        neutral_equivalent="I'd rather not, thanks",
        who_says_this="Friends and casual colleagues. Not in a client email.",
    )
}


def test_a_glossed_slang_chunk_becomes_ONE_recognition_card() -> None:
    """**PRD §8.5.2: recognition and listening cards only.**

    Not a cloze card. A cloze asks the learner to produce the phrase into a gap,
    which is what the receptive-first rule exists to prevent — it is a
    production card with a sentence around it, not a milder form of one.
    """
    plan = plan_for_chunk(_row(source="slang"), today=TODAY, glosses=GLOSSES)
    assert plan.bucket == "slang_recognition"
    assert [c["card_type"] for c in plan.cards] == ["recognition"]


def test_the_recognition_card_carries_all_four_of_prds_things() -> None:
    """Otherwise `cards_informal_shows_the_four_things` refuses the INSERT."""
    (card,) = plan_for_chunk(_row(source="slang"), today=TODAY, glosses=GLOSSES).cards
    assert card["register"] == "slang"
    assert card["register_source"] == "operator"
    assert card["context_sentence"] == "That's a hard pass from me."
    assert card["meaning"] == "a firm refusal"
    assert card["neutral_equivalent"] == "I'd rather not, thanks"
    assert card["who_says_this"].startswith("Friends")


def test_the_recognition_front_is_the_line_and_the_back_is_the_phrase() -> None:
    """PRD §5's recognition row: the word in its mined sentence → its meaning.

    Ungapped, deliberately. Gapping it would make it the cloze card §8.5.2 bars.
    """
    (card,) = plan_for_chunk(_row(source="slang"), today=TODAY, glosses=GLOSSES).cards
    assert card["front"] == "That's a hard pass from me."
    assert "_____" not in card["front"]
    assert card["back"] == "hard pass"


def test_a_glossed_slang_chunk_with_no_meaning_is_still_skipped() -> None:
    """The operator supplies two of §8.5.4's four; the chunk must supply the rest."""
    plan = plan_for_chunk(
        _row(source="slang", meaning=None), today=TODAY, glosses=GLOSSES
    )
    assert plan.bucket == "skipped_slang_no_gloss"
    assert plan.cards == ()


def test_a_gloss_matches_across_case_and_spacing() -> None:
    """Normalised on both sides, so an apostrophe or a capital cannot silently
    lose a row the operator did write."""
    plan = plan_for_chunk(
        _row(source="slang", chunk="Hard  Pass"), today=TODAY, glosses=GLOSSES
    )
    assert plan.bucket == "slang_recognition"


def test_every_migrated_card_is_tagged_neutral_and_says_why() -> None:
    """`register_source` is what makes these rows re-taggable at W13 in one
    WHERE — the move `user_lexemes.source = 'assumption'` makes for the
    frequency floor (#93). A default with no provenance would be a guess nobody
    could find again."""
    plan = plan_for_chunk(_row(), today=TODAY)
    for spec in plan.cards:
        assert spec["register"] == "neutral"
        assert spec["register_source"] == "migration_default"


def test_the_production_card_carries_the_chunks_seeded_state() -> None:
    """One card per chunk since W8b, so this is no longer a shared-state test.

    The seeding maths itself is `tests/test_cards_seeding.py`; what is asserted
    here is that the card the pass builds actually carries it.
    """
    (production,) = plan_for_chunk(
        _row(times_right=3, times_wrong=1, streak_right=2), today=TODAY
    ).cards
    assert production["state"].stability == pytest.approx(7.0)
    assert production["seed_basis"]["times_right"] == 3


def test_a_chunk_with_no_history_carries_no_seed_basis() -> None:
    plan = plan_for_chunk(_row(times_right=0, times_wrong=0), today=TODAY)
    assert all(spec["seed_basis"] is None for spec in plan.cards)


# ── against a real database ────────────────────────────────────────────────


@pytest.fixture
def learner_with_chunks():
    """A throwaway learner and three chunks, removed afterwards.

    No `telegram_user_id` at all — `cards` is a user-keyed table created after
    W4b, and a web-only learner owning one is what #92 was closed to make
    possible.
    """
    with psycopg.connect(load_settings().database_url, autocommit=True) as conn:
        row = conn.execute(
            "INSERT INTO users (name, native_language, auth_email, onboarded) "
            "VALUES ('w7-test', 'fa', 'w7-test@example.invalid', TRUE) "
            "RETURNING id"
        ).fetchone()
        user_id = int(row[0])
        for chunk, sentence, meaning, source, tr, tw, sr in (
            ("hard pass", "That's a hard pass from me.", "a firm refusal", "himym", 3, 1, 2),
            ("get away with", "You can't get away with that.", "escape blame", "book_unit_3", 0, 0, 0),
            ("bail on", "Don't bail on me tonight.", "cancel on someone", "slang", 1, 0, 1),
        ):
            conn.execute(
                """
                INSERT INTO chunks (user_id, chunk, full_sentence, meaning, source,
                                    track, next_review, times_right, times_wrong,
                                    streak_right, presented_at)
                VALUES (%s, %s, %s, %s, %s, 'life', CURRENT_DATE, %s, %s, %s, NOW())
                """,
                (user_id, chunk, sentence, meaning, source, tr, tw, sr),
            )
        try:
            yield user_id
        finally:
            conn.execute("DELETE FROM users WHERE id = %s", (user_id,))


def _counts(user_id: int, *, apply: bool, glosses=None) -> dict:
    return dict(
        run(apply=apply, today=TODAY, glosses=glosses).get(str(user_id), {})
    )


def test_the_dry_run_writes_nothing(learner_with_chunks) -> None:
    counts = _counts(learner_with_chunks, apply=False)
    assert counts["chunks_examined"] == 3
    with psycopg.connect(load_settings().database_url) as conn:
        row = conn.execute(
            "SELECT count(*) FROM cards WHERE user_id = %s", (learner_with_chunks,)
        ).fetchone()
    assert int(row[0]) == 0


def test_the_buckets_account_for_every_chunk(learner_with_chunks) -> None:
    """**The accounting identity.** Nothing is silently lost."""
    counts = _counts(learner_with_chunks, apply=False)
    buckets = (
        "production_with_hint",
        "production_no_hint",
        "skipped_no_meaning",
        "slang_recognition",
        "skipped_slang_no_gloss",
        "skipped_no_face",
    )
    assert sum(counts.get(b, 0) for b in buckets) == counts["chunks_examined"]
    assert counts["skipped_slang_no_gloss"] == 1
    assert counts["production_with_hint"] == 2


def test_the_pass_creates_ONE_production_card_per_eligible_chunk(
    learner_with_chunks,
) -> None:
    """**This test was `..._creates_two_cards_per_eligible_chunk` until W8b, and
    that name was true when it was written** — two chunks, a cloze and a
    production card each. It is renamed because the behaviour changed, not
    because the name was ever wrong.

    The `cloze_created` counter is asserted absent rather than left unmentioned:
    a counter that stops being incremented reads identically to a test that
    stopped looking at it.
    """
    counts = _counts(learner_with_chunks, apply=True)
    assert counts["production_created"] == 2
    assert counts.get("cloze_created", 0) == 0
    assert counts.get("cloze_planned", 0) == 0
    with psycopg.connect(load_settings().database_url) as conn:
        rows = conn.execute(
            "SELECT card_type, count(*) FROM cards WHERE user_id = %s "
            "GROUP BY card_type ORDER BY card_type",
            (learner_with_chunks,),
        ).fetchall()
    assert [(r[0], int(r[1])) for r in rows] == [("production", 2)]


def test_the_second_run_writes_nothing(learner_with_chunks) -> None:
    """**Proven, not asserted.** Run it twice; the second run writes nothing.

    Two independent guarantees stand behind this: the `existing` set below, and
    migration 013's `UNIQUE (user_id, source_chunk_id, card_type)`. W4a is why
    there are two — the guarantee you can demonstrate on the Mac is not always
    the one that holds on production.
    """
    _counts(learner_with_chunks, apply=True)
    second = _counts(learner_with_chunks, apply=True)
    assert second.get("production_created", 0) == 0
    assert second.get("refused_by_unique", 0) == 0
    assert second["already_present"] == 2


def test_the_migration_never_touches_chunks(learner_with_chunks) -> None:
    """`chunks` is the migration's own input and v2's live review table."""
    with psycopg.connect(load_settings().database_url) as conn:
        before = conn.execute(
            "SELECT id, chunk, next_review, times_right, times_wrong, streak_right "
            "FROM chunks WHERE user_id = %s ORDER BY id",
            (learner_with_chunks,),
        ).fetchall()
    _counts(learner_with_chunks, apply=True)
    with psycopg.connect(load_settings().database_url) as conn:
        after = conn.execute(
            "SELECT id, chunk, next_review, times_right, times_wrong, streak_right "
            "FROM chunks WHERE user_id = %s ORDER BY id",
            (learner_with_chunks,),
        ).fetchall()
    assert before == after


def test_a_seeded_card_carries_its_basis_and_a_new_one_does_not(
    learner_with_chunks,
) -> None:
    _counts(learner_with_chunks, apply=True)
    with psycopg.connect(load_settings().database_url) as conn:
        rows = conn.execute(
            """
            SELECT k.chunk, c.seeded_from_history, c.stability, c.seed_basis
              FROM cards c JOIN chunks k ON k.id = c.source_chunk_id
             WHERE c.user_id = %s AND c.card_type = 'production'
             ORDER BY k.chunk
            """,
            (learner_with_chunks,),
        ).fetchall()
    by_chunk = {r[0]: r for r in rows}
    seeded = by_chunk["hard pass"]
    assert seeded[1] is True and seeded[2] is not None
    assert seeded[3]["times_right"] == 3
    fresh = by_chunk["get away with"]
    assert fresh[1] is False and fresh[2] is None
    assert fresh[3] == {}


def test_the_pass_writes_no_review_events(learner_with_chunks) -> None:
    """No review event is fabricated anywhere in this slice."""
    _counts(learner_with_chunks, apply=True)
    with psycopg.connect(load_settings().database_url) as conn:
        row = conn.execute(
            "SELECT count(*) FROM card_reviews WHERE user_id = %s",
            (learner_with_chunks,),
        ).fetchone()
    assert int(row[0]) == 0


# ── the census case, against a real database ──────────────────────────────
#
# The 2026-08-25 production census: Navid 5 chunks / 5 slang, Morkyte 5 / 5.
# Two of three learners whose ENTIRE v2 corpus is the S24 slang fan-out. These
# two tests are that learner, and they are the acceptance criterion "the deck is
# non-empty on day one" made falsifiable for the case that broke it.


@pytest.fixture
def slang_only_learner():
    """A learner whose whole corpus is slang. Navid and Morkyte, on production."""
    with psycopg.connect(load_settings().database_url, autocommit=True) as conn:
        row = conn.execute(
            "INSERT INTO users (name, native_language, auth_email, onboarded) "
            "VALUES ('w7-slang', 'fa', 'w7-slang@example.invalid', TRUE) "
            "RETURNING id"
        ).fetchone()
        user_id = int(row[0])
        for chunk, sentence, meaning in (
            ("hard pass", "That's a hard pass from me.", "a firm refusal"),
            ("no cap", "That film was good, no cap.", "honestly, seriously"),
        ):
            conn.execute(
                """
                INSERT INTO chunks (user_id, chunk, full_sentence, meaning, source,
                                    track, next_review, times_right, times_wrong,
                                    streak_right, presented_at)
                VALUES (%s, %s, %s, %s, 'slang', 'life', CURRENT_DATE, 0, 0, 0, NOW())
                """,
                (user_id, chunk, sentence, meaning),
            )
        try:
            yield user_id
        finally:
            conn.execute("DELETE FROM users WHERE id = %s", (user_id,))


def test_a_slang_only_learner_gets_an_empty_deck_without_glosses(
    slang_only_learner,
) -> None:
    """**The failure the production census found, reproduced.**

    This is not a bug being asserted — it is the cost of the §8.5.4 CHECK, made
    visible so nobody rediscovers it on a phone. Without the operator's file
    these two learners open /review to nothing.
    """
    counts = _counts(slang_only_learner, apply=True)
    assert counts["skipped_slang_no_gloss"] == 2
    with psycopg.connect(load_settings().database_url) as conn:
        row = conn.execute(
            "SELECT count(*) FROM cards WHERE user_id = %s", (slang_only_learner,)
        ).fetchone()
    assert int(row[0]) == 0


def test_a_slang_only_learner_gets_a_deck_once_the_operator_writes_the_glosses(
    slang_only_learner,
) -> None:
    """**Acceptance criterion 1, for the learner it failed on.**

    One recognition card per glossed phrase — non-empty, correctly tagged, and
    carrying the safe alternative §8.5.4 exists for. A phrase the operator has
    not yet written stays skipped rather than shipping half a card.
    """
    glosses = {
        "hard pass": SlangGloss(
            "hard pass",
            "I'd rather not, thanks",
            "Friends and casual colleagues. Not in a client email.",
        )
    }
    counts = _counts(slang_only_learner, apply=True, glosses=glosses)
    assert counts["slang_recognition"] == 1
    assert counts["skipped_slang_no_gloss"] == 1
    assert counts["recognition_created"] == 1

    with psycopg.connect(load_settings().database_url) as conn:
        rows = conn.execute(
            "SELECT card_type, register, register_source, neutral_equivalent, "
            "who_says_this FROM cards WHERE user_id = %s",
            (slang_only_learner,),
        ).fetchall()
    assert len(rows) == 1
    card_type, register, register_source, neutral, who = rows[0]
    assert card_type == "recognition"
    assert register == "slang"
    assert register_source == "operator"
    assert neutral and who


def test_the_slang_pass_is_idempotent_too(slang_only_learner) -> None:
    """The recognition card counts as already-migrated on the second run.

    `MIGRATION_CARD_TYPES` exists for exactly this: an anti-join that knew about
    only `cloze` and `production` would re-create every slang card every run.
    """
    glosses = {
        "hard pass": SlangGloss("hard pass", "I'd rather not", "Friends."),
    }
    _counts(slang_only_learner, apply=True, glosses=glosses)
    second = _counts(slang_only_learner, apply=True, glosses=glosses)
    assert second.get("recognition_created", 0) == 0
    assert second["already_present"] == 1
