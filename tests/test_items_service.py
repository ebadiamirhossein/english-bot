"""`core.services.items` against a real database.

The refusal test is the one that matters: `insert_item` will not write an item
whose report is not `ok`. That is the second of three layers behind "no item
reaches a learner without a validation record" (the CHECK is the first, the
single-writer parse test in `test_core_boundary` is the third).
"""

from __future__ import annotations

import psycopg
import pytest

from core.config import load_settings
from core.items.gates import ValidationReport
from core.items.grading import normalise_variants
from core.items.schema import content_hash, parse, payload_keys
from core.services import items as svc
from core.services.items import ItemWriteError

PASSED = ValidationReport("passed")


def _draft(**over):
    raw = {
        "item_type": "cloze_cued",
        "track": "life",
        "lexeme": "go",
        "prompt_text": "I ___ to the shops yesterday.",
        "answer": "went",
    }
    raw.update(over)
    raw["accepted_variants"] = normalise_variants(raw["answer"])
    return parse(raw)


@pytest.fixture
def learner():
    """A throwaway user, removed afterwards. `users.id` is the identity (011).

    Reachable by `auth_email` and carrying **no `telegram_user_id` at all**.
    That is deliberate: `items` and `item_attempts` are the first user-keyed
    tables created after W4b, and a web-only learner owning them is exactly what
    #92 was closed to make possible. If a foreign key here pointed at
    `telegram_user_id`, this fixture could not exist.
    """
    with psycopg.connect(load_settings().database_url, autocommit=True) as conn:
        row = conn.execute(
            "INSERT INTO users (name, native_language, auth_email, onboarded) "
            "VALUES ('w5-test', 'fa', 'w5-test@example.invalid', TRUE) "
            "RETURNING id"
        ).fetchone()
        user_id = int(row[0])
        try:
            yield user_id
        finally:
            conn.execute("DELETE FROM users WHERE id = %s", (user_id,))


def test_a_validated_item_round_trips(learner) -> None:
    item = _draft()
    item_id = svc.insert_item(learner, item, PASSED, model="test-model")
    assert item_id is not None

    stored = svc.list_bank(learner)
    assert len(stored) == 1
    assert stored[0].prompt_text == item.prompt_text
    assert stored[0].answer == "went"
    assert stored[0].accepted_variants == ("went",)
    assert stored[0].register == "neutral"
    assert stored[0].response_mode == "typed"


def test_the_grammar_target_round_trips_with_no_migration(learner) -> None:
    """W10c's binding ruling, proved end to end against a real database.

    **The claim being tested is that no DDL was needed.** `items.unit_number`
    says which unit an item belongs to and `items.error_type` names one of
    nineteen coarse journal codes — all four of unit 1's grammar targets collapse
    onto `verb_tense_past` — so neither can say which of the 82 targets an item
    tests. `grammar_target` is a field on `BaseItem`, and `schema.payload_of`
    derives the payload by SUBTRACTING the promoted columns, so it persists into
    the existing `payload` JSONB and `StoredItem.as_item` rehydrates it through
    `**payload`.

    If that derivation ever stopped working, the field would be dropped on write
    and read back as `None` — silently, with the item still valid — and block 3
    would serve items nothing could tell apart. `schema_version` stays at 16.
    """
    target = "past simple and past continuous in the same sentence"
    svc.insert_item(
        learner, _draft(grammar_target=target, unit_number=1),
        PASSED, model="test-model",
    )
    stored = svc.list_bank(learner)[0]
    assert stored.payload["grammar_target"] == target
    assert stored.as_item().grammar_target == target
    assert stored.unit_number == 1


def test_the_grammar_target_never_reaches_the_learner(learner) -> None:
    """It is in `projection.NEVER_VISIBLE`, and the reason is not privacy.

    Naming the target on the wire tells the learner what CATEGORY of answer is
    wanted, and hands `gates.probe_target` the answer to the question it exists
    to ask.
    """
    svc.insert_item(
        learner, _draft(grammar_target="past simple: regular and irregular verbs"),
        PASSED, model="test-model",
    )
    presentation = svc.presentations_for(learner)[0]
    assert "grammar_target" not in presentation.projection


def test_focus_items_serves_only_the_unit_asked_for(learner) -> None:
    """Block 3's read. `bank_for_session` + the projection, and nothing else."""
    svc.insert_item(learner, _draft(unit_number=1), PASSED, model="test-model")
    svc.insert_item(
        learner,
        _draft(unit_number=3, prompt_text="I ___ smoke, but I gave up.",
               answer="used to"),
        PASSED, model="test-model",
    )
    unit_one = svc.focus_items(learner, unit_number=1)
    assert len(unit_one) == 1
    assert "shops" in unit_one[0].projection["prompt_text"]
    assert len(svc.focus_items(learner, unit_number=3)) == 1
    assert svc.focus_items(learner, unit_number=2) == []


def test_focus_items_serves_at_most_the_eight_prd_asks_for(learner) -> None:
    """PRD §4.1 block 3 is eight items. A bank that grew past that must not
    hand the whole thing to a session."""
    for n in range(12):
        svc.insert_item(
            learner,
            _draft(unit_number=1, prompt_text=f"I ___ there {n} times last year."),
            PASSED, model="test-model",
        )
    assert len(svc.focus_items(learner, unit_number=1)) == svc.FOCUS_ITEM_COUNT


def test_the_payload_carries_exactly_the_types_extra_keys(learner) -> None:
    """A field added to a model is persisted from the moment it exists."""
    svc.insert_item(learner, _draft(), PASSED, model="test-model")
    stored = svc.list_bank(learner)[0]
    assert set(stored.payload) == payload_keys("cloze_cued")


def test_insert_refuses_an_item_that_failed_a_gate(learner) -> None:
    discarded = ValidationReport("discarded", blind_solver=("ambiguous",))
    with pytest.raises(ItemWriteError):
        svc.insert_item(learner, _draft(), discarded, model="test-model")
    assert svc.list_bank(learner) == []


def test_a_duplicate_is_a_no_op_and_not_an_error(learner) -> None:
    """Asking for fresh items and getting one you already have is normal."""
    item = _draft()
    first = svc.insert_item(learner, item, PASSED, model="test-model")
    second = svc.insert_item(learner, item, PASSED, model="test-model")
    assert first is not None
    assert second is None
    assert len(svc.list_bank(learner)) == 1


def test_two_learners_get_their_own_copy_of_the_same_item(learner) -> None:
    """Fan-out: `UNIQUE (user_id, content_hash)` is scoped to the learner."""
    with psycopg.connect(load_settings().database_url, autocommit=True) as conn:
        row = conn.execute(
            "INSERT INTO users (name, native_language, auth_email, onboarded) "
            "VALUES ('w5-test-2', 'fa', 'w5-test-2@example.invalid', TRUE) "
            "RETURNING id"
        ).fetchone()
        other = int(row[0])
        try:
            item = _draft()
            assert svc.insert_item(learner, item, PASSED, model="m") is not None
            assert svc.insert_item(other, item, PASSED, model="m") is not None
            assert len(svc.list_bank(learner)) == 1
            assert len(svc.list_bank(other)) == 1
        finally:
            conn.execute("DELETE FROM users WHERE id = %s", (other,))


def test_a_target_outside_the_seed_list_is_grown_not_dropped(learner) -> None:
    """W4's growable-`lexemes` rule, inherited rather than re-decided."""
    item = _draft(lexeme="zqxkappa", prompt_text="I ___ it yesterday.", answer="went")
    item_id = svc.insert_item(learner, item, PASSED, model="test-model")
    with psycopg.connect(load_settings().database_url) as conn:
        row = conn.execute(
            "SELECT l.lemma, l.origin, l.freq_rank FROM items i "
            "JOIN lexemes l ON l.id = i.lexeme_id WHERE i.id = %s",
            (item_id,),
        ).fetchone()
    assert row == ("zqxkappa", "grown", None), (
        "010: a grown lemma has a NULL freq_rank, which means 'rarer than the "
        "seed tail' and keeps it out of the assumed-known floor"
    )


def test_an_attempt_records_what_cannot_be_reconstructed(learner) -> None:
    """`latency_ms` and `cue_shown` have no reader until W7. That is the point."""
    item_id = svc.insert_item(learner, _draft(), PASSED, model="test-model")
    attempt_id = svc.record_attempt(
        learner,
        item_id,
        correct=False,
        graded_by="deterministic",
        response_text="goed",
        chosen_option="goed",
        latency_ms=4200,
        cue_shown="first_letter_length",
        audio_seconds=None,
    )
    assert attempt_id > 0

    with psycopg.connect(load_settings().database_url) as conn:
        row = conn.execute(
            "SELECT response_text, chosen_option, latency_ms, cue_shown, "
            "       graded_by, correct, attempt_no "
            "FROM item_attempts WHERE id = %s",
            (attempt_id,),
        ).fetchone()
    assert row == ("goed", "goed", 4200, "first_letter_length",
                   "deterministic", False, 1)
    assert svc.attempt_counts(learner) == {"attempts": 1, "correct": 0}


def test_deleting_a_learner_takes_their_items_and_attempts(learner) -> None:
    """ON DELETE CASCADE through the composite FK."""
    item_id = svc.insert_item(learner, _draft(), PASSED, model="test-model")
    svc.record_attempt(learner, item_id, correct=True, graded_by="deterministic")
    with psycopg.connect(load_settings().database_url, autocommit=True) as conn:
        conn.execute("DELETE FROM users WHERE id = %s", (learner,))
        left = conn.execute(
            "SELECT count(*) FROM item_attempts WHERE user_id = %s", (learner,)
        ).fetchone()
    assert left[0] == 0


def test_the_stored_hash_matches_the_pure_function(learner) -> None:
    item = _draft()
    item_id = svc.insert_item(learner, item, PASSED, model="test-model")
    with psycopg.connect(load_settings().database_url) as conn:
        row = conn.execute(
            "SELECT content_hash FROM items WHERE id = %s", (item_id,)
        ).fetchone()
    assert row[0] == content_hash(item)
