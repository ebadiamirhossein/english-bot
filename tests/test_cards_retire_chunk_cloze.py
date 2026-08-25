"""`core.cards.retire_chunk_cloze` — what it reaches, and what it can never reach.

Against a real database, because every property here is about which rows a
`DELETE` touches, and that is not a property of a function's arguments.

**The load-bearing test is `test_a_cloze_card_with_no_source_chunk_survives`.**
W13 creates cloze cards from video lines; those carry no `source_chunk_id`, and
the guarantee that this command can never delete one has to be a property of the
predicate rather than of when the command is run. "We ran it before W13" is a
fact about a calendar, and the next person to run it cannot check it.
"""

from __future__ import annotations

import inspect
import secrets
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from core.cards import retire_chunk_cloze
from core.cards.fsrs import CardState
from core.config import load_settings
from core.services import cards as svc

T0 = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)
GOOD = 3


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def learner(db):
    row = db.execute(
        "INSERT INTO users (name, native_language, auth_email, onboarded) "
        "VALUES ('w8b-retire', 'fa', %s, TRUE) RETURNING id",
        (f"w8b-{secrets.token_hex(6)}@example.invalid",),
    ).fetchone()
    user_id = int(row[0])
    db.commit()
    try:
        yield user_id
    finally:
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.commit()


@pytest.fixture
def chunk(db, learner):
    """A v2 chunk to hang a migrated card off. Never modified, as in production."""
    row = db.execute(
        """
        INSERT INTO chunks (user_id, chunk, full_sentence, meaning, source,
                            track, next_review, times_right, times_wrong,
                            streak_right, presented_at)
        VALUES (%s, 'hidden costs', 'The hidden costs add up fast.',
                'unexpected extra expenses', 'himym', 'life', CURRENT_DATE,
                0, 0, 0, NOW())
        RETURNING id
        """,
        (learner,),
    ).fetchone()
    db.commit()
    return int(row[0])


def _state() -> CardState:
    return CardState(
        fsrs_state="review",
        fsrs_step=None,
        stability=10.0,
        difficulty=5.0,
        due=T0 - timedelta(days=1),
        last_review=T0 - timedelta(days=11),
        lapses=0,
        reps=4,
    )


def _card(db, user_id: int, **over) -> int:
    spec = dict(
        card_type="cloze",
        front="The _____ add up fast.",
        back="hidden costs",
        register="neutral",
        register_source="migration_default",
        state=_state(),
        meaning="unexpected extra expenses",
        context_sentence="The hidden costs add up fast.",
        source_ref="himym",
    )
    spec.update(over)
    card_id = svc.create_card(db, user_id, **spec)
    db.commit()
    assert card_id is not None
    return card_id


def _mine(user_id: int) -> list[int]:
    return [
        card.id
        for card, _ in svc.chunk_cloze_cards_with_review_counts()
        if card.user_id == user_id
    ]


def _exists(db, card_id: int) -> bool:
    db.rollback()  # see a committed delete made on another connection
    row = db.execute("SELECT count(*) FROM cards WHERE id = %s", (card_id,)).fetchone()
    return int(row[0]) == 1


# ── what the predicate reaches ─────────────────────────────────────────────


def test_a_chunk_derived_cloze_card_is_a_candidate(db, learner, chunk) -> None:
    card_id = _card(db, learner, source_chunk_id=chunk)
    assert card_id in _mine(learner)


def test_a_cloze_card_with_no_source_chunk_survives(db, learner, chunk, monkeypatch) -> None:
    """**W13's cards are out of reach by construction, not by timing.**

    A cloze card built from a video line carries no `source_chunk_id`. It is not
    a candidate, and a full `--purge` run leaves it in place.
    """
    video = _card(db, learner, source_chunk_id=None, front="She _____ it anyway.")
    migrated = _card(db, learner, source_chunk_id=chunk)

    assert video not in _mine(learner)
    monkeypatch.setattr("builtins.input", lambda *_: str(len(_mine(learner))))
    assert retire_chunk_cloze.main(["--purge"]) == 0

    assert _exists(db, video)
    assert not _exists(db, migrated)


def test_a_production_card_from_a_chunk_survives(db, learner, chunk, monkeypatch) -> None:
    """The phrase → meaning direction is untouched by the ruling."""
    production = _card(
        db, learner, card_type="production", source_chunk_id=chunk,
        front="unexpected extra expenses\nThe _____ add up fast.",
    )
    monkeypatch.setattr("builtins.input", lambda *_: str(len(_mine(learner))))
    retire_chunk_cloze.main(["--purge"])
    assert _exists(db, production)


def test_the_predicate_is_card_type_and_source_chunk_and_never_a_date_or_an_id() -> None:
    """**Acceptance criterion 3, read off the service's own source.**

    `core.services.items.delete_items_by_hash` states the reason one package
    over: a date range sweeps rows nobody looked at, and an id list is a claim
    about the database that stops being true the moment the database changes.
    Asserted rather than reviewed by eye, because this is the guard that keeps a
    W13 card and a graded card out of reach.
    """
    source = inspect.getsource(svc.delete_chunk_cloze_cards)
    predicate = inspect.getsource(svc).split("_CHUNK_CLOZE_SQL = ")[1].split("\n")[0]
    assert "card_type = 'cloze'" in predicate
    assert "source_chunk_id IS NOT NULL" in predicate
    for banned in ("created_at", "id = ANY", "id IN (", "BETWEEN", "due <"):
        assert banned not in source, banned


# ── what stops it ──────────────────────────────────────────────────────────


def test_a_graded_card_stops_the_run_and_nothing_is_deleted(
    db, learner, chunk, monkeypatch
) -> None:
    """**The ruling assumed these were never reviewed. If that is false, stop.**

    The review is written through the real `grade_card`, not inserted by hand:
    the guarantee is about what the deck's own writer produces, and a
    hand-written row could satisfy the query while differing from a real one.
    """
    graded = _card(db, learner, source_chunk_id=chunk)
    svc.grade_card(learner, graded, rating=GOOD, now=T0)

    monkeypatch.setattr("builtins.input", lambda *_: "1")
    assert retire_chunk_cloze.main(["--purge"]) == 1

    assert _exists(db, graded)
    db.rollback()
    row = db.execute(
        "SELECT count(*) FROM card_reviews WHERE card_id = %s", (graded,)
    ).fetchone()
    assert int(row[0]) == 1, "the append-only review log survived"


def test_the_service_refuses_a_graded_card_even_if_the_caller_does_not(
    db, learner, chunk
) -> None:
    """**The second, independent guarantee**, for the read → write race.

    A learner can grade a card between the module's read and the delete, and the
    composite foreign key cascades. This calls the writer directly, with no
    module-level check in front of it, so the SQL guard is proved on its own.
    """
    graded = _card(db, learner, source_chunk_id=chunk)
    svc.grade_card(learner, graded, rating=GOOD, now=T0)
    assert graded not in svc.delete_chunk_cloze_cards()
    assert _exists(db, graded)


def test_the_wrong_count_typed_back_deletes_nothing(db, learner, chunk, monkeypatch) -> None:
    card_id = _card(db, learner, source_chunk_id=chunk)
    monkeypatch.setattr("builtins.input", lambda *_: "99")
    assert retire_chunk_cloze.main(["--purge"]) == 1
    assert _exists(db, card_id)


# ── dry by default, and idempotent ─────────────────────────────────────────


def test_the_default_is_dry_and_deletes_nothing(db, learner, chunk, monkeypatch) -> None:
    card_id = _card(db, learner, source_chunk_id=chunk)

    def _refuse(*_args, **_kwargs):
        raise AssertionError("a dry run must not ask for confirmation")

    monkeypatch.setattr("builtins.input", _refuse)
    assert retire_chunk_cloze.main([]) == 0
    assert _exists(db, card_id)


def test_a_second_run_reports_nothing_to_do(db, learner, chunk, monkeypatch, capsys) -> None:
    """**Acceptance criterion 5.** Proven by running it twice, not asserted."""
    _card(db, learner, source_chunk_id=chunk)
    monkeypatch.setattr("builtins.input", lambda *_: str(len(_mine(learner))))
    assert retire_chunk_cloze.main(["--purge"]) == 0
    capsys.readouterr()

    assert _mine(learner) == []
    monkeypatch.setattr("builtins.input", lambda *_: "0")
    assert retire_chunk_cloze.main(["--purge"]) == 0
    assert "Nothing to do." in capsys.readouterr().out


def test_the_dry_run_prints_every_row_before_anything_is_deleted(
    db, learner, chunk, capsys
) -> None:
    """The dry run is the last record of these sentences — after the purge they
    are gone from the only place they existed."""
    card_id = _card(db, learner, source_chunk_id=chunk)
    retire_chunk_cloze.main([])
    out = capsys.readouterr().out
    assert str(card_id) in out
    assert "The _____ add up fast." in out
    assert "hidden costs" in out


def test_chunks_are_never_touched(db, learner, chunk, monkeypatch) -> None:
    """The cards were derived from chunks; the chunks are not this slice's to
    delete, and `chunks` is v2's live review table until W22."""
    _card(db, learner, source_chunk_id=chunk)
    monkeypatch.setattr("builtins.input", lambda *_: str(len(_mine(learner))))
    retire_chunk_cloze.main(["--purge"])
    db.rollback()
    row = db.execute(
        "SELECT chunk, full_sentence, next_review FROM chunks WHERE id = %s",
        (chunk,),
    ).fetchone()
    assert row is not None and row[0] == "hidden costs"
