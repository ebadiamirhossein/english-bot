"""W31d — word practice (W24f, un-deferred by C6), through the real ASGI app.

**The one billed thing here, the word's audio, is stubbed** at
`core.speech.synthesize` (the wrapper, standing rule 7's boundary for speech);
the netguard fixture refuses any socket. The pictures are rows this module
inserts under a `File:W31dtest` prefix and removes — `lexeme_images` is global.

**RED BEFORE THE CODE (2026-09-27):** `/practice/*` did not exist (404) and
keep going offered no `practice`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.cards.fsrs import CardState
from core.services import cards as cards_svc
from core.services import keep_going
from tests.test_video_route import (  # noqa: F401 -- fixtures, by name
    _as,
    app,
    auth_env,
    db,
    learner,
    request,
)

NOW = datetime.now(timezone.utc)
PAST = NOW - timedelta(days=1)
LATER = NOW + timedelta(days=5)
PICTURED = ("parrot", "spoon", "ladder", "elbow", "apple")


@pytest.fixture
def me(db, learner):
    yield learner
    db.rollback()
    db.execute("DELETE FROM card_reviews WHERE card_id IN (SELECT id FROM cards WHERE user_id = %s)",
               (learner.user_id,))
    db.execute("DELETE FROM cards WHERE user_id = %s", (learner.user_id,))
    db.commit()


@pytest.fixture
def pictures(db):
    for lemma in PICTURED:
        db.execute(
            """
            INSERT INTO lexeme_images (lexeme_id, commons_file, source_url, original_sha1, author,
                                       licence, mime, width, height, bytes)
            SELECT id, %s, %s, %s, 'W31d Tester', 'CC0', 'image/jpeg', 10, 10, '\\xff'::bytea
              FROM lexemes WHERE lemma = %s
            ON CONFLICT (lexeme_id) DO NOTHING
            """,
            (f"File:W31dtest_{lemma}.jpg",
             f"https://commons.wikimedia.org/wiki/File:W31dtest_{lemma}.jpg", "0" * 40, lemma),
        )
    db.commit()
    yield
    db.rollback()
    db.execute("DELETE FROM lexeme_images WHERE commons_file LIKE 'File:W31dtest%%'")
    db.commit()


def _card(db, me, word: str, *, due: datetime, register: str = "neutral",
          sentence: str | None = None, definition: str = "a thing", lexeme: bool = True,
          source_ref: str = "video:1@1.000") -> int:
    lexeme_id = None
    if lexeme:
        row = db.execute("SELECT id FROM lexemes WHERE lemma = %s", (word,)).fetchone()
        lexeme_id = row[0] if row else None
    extra = {}
    if register in ("informal", "slang"):
        extra = {"meaning": definition, "neutral_equivalent": "thing", "who_says_this": "friends"}
    card_id = cards_svc.create_card(
        db, me.user_id, card_type="recognition" if register not in ("neutral", "formal") else "production",
        front=word, back=definition, register=register, register_source="detected",
        state=CardState("review", None, 3.0, 5.0, due, due - timedelta(days=3), 0, 2),
        source_ref=source_ref, context_sentence=sentence or f"I saw a {word} yesterday.",
        lexeme_id=lexeme_id, **extra,
    )
    db.commit()
    return card_id


def _start(app, me) -> list[dict]:
    response = request(app, "POST", "/practice/start", json_body={}, cookies=_as(me))
    assert response.status_code == 200, response.text
    return response.json()["exercises"]


def _answer(app, me, card_id, kind, response_text):
    return request(app, "POST", "/practice/answer", cookies=_as(me),
                   json_body={"card_id": card_id, "kind": kind, "response": response_text})


# ── the drill ────────────────────────────────────────────────────────────────


def test_practice_requires_a_session(app) -> None:
    assert request(app, "POST", "/practice/start", json_body={}).status_code == 401


def test_due_cards_come_first_and_the_top_up_is_marked_ungraded(app, db, me) -> None:
    due = _card(db, me, "kettle", due=PAST)
    later = _card(db, me, "chair", due=LATER)
    exercises = _start(app, me)
    assert [e["card_id"] for e in exercises] == [due, later]
    assert [e["graded"] for e in exercises] == [True, False]


def test_one_exercise_per_word_and_at_most_eight(app, db, me) -> None:
    words = ["kettle", "chair", "band", "parrot", "spoon", "ladder", "elbow", "apple", "table", "window"]
    for w in words:
        _card(db, me, w, due=PAST)
    # A second card for the same word (no lexeme, so the per-lemma index allows it).
    _card(db, me, "kettle", due=PAST, sentence="the kettle is on.", lexeme=False)
    exercises = _start(app, me)
    assert len(exercises) == 8
    assert len({e["card_id"] for e in exercises}) == 8


def test_a_card_that_names_no_word_is_left_out(app, db, me) -> None:
    """Not a video capture and no lexeme: its front could be a gloss or a sentence."""
    _card(db, me, "zzqphrase", due=PAST, lexeme=False, source_ref="import:lr")
    assert _start(app, me) == []


def test_slang_is_never_a_type_it_exercise(app, db, me) -> None:
    _card(db, me, "kettle", due=PAST, register="slang")
    assert _start(app, me) == []


def test_pictures_appear_only_for_pictured_words_with_four_choices(app, db, me, pictures) -> None:
    for w in ("parrot", "spoon", "kettle"):
        _card(db, me, w, due=PAST)
    by_word = {}
    for e in _start(app, me):
        card = db.execute("SELECT front FROM cards WHERE id = %s", (e["card_id"],)).fetchone()[0]
        by_word[card] = e
    assert by_word["kettle"]["kind"] in ("hear_type", "meaning_type")
    parrot = by_word["parrot"]
    assert parrot["kind"] in ("picture_to_word", "word_to_picture")
    assert len(parrot["options"]) == 4
    if parrot["kind"] == "picture_to_word":
        assert "parrot" in [o["value"] for o in parrot["options"]]
        assert parrot["image"]["author"] == "W31d Tester"
    else:
        assert all(o["image"]["author"] == "W31d Tester" for o in parrot["options"])


def test_every_exercise_keeps_its_sentence_and_a_typed_one_hides_the_word(app, db, me) -> None:
    _card(db, me, "kettle", due=PAST, sentence="the kettles were boiling.")
    (e,) = _start(app, me)
    assert e["kind"] in ("hear_type", "meaning_type")
    assert e["sentence"] == "the _____ were boiling."


# ── answers ──────────────────────────────────────────────────────────────────


def _reviews(db, card_id) -> list[tuple]:
    return db.execute(
        "SELECT rating, typed_matched FROM card_reviews WHERE card_id = %s ORDER BY id", (card_id,)
    ).fetchall()


def test_a_right_answer_on_a_due_card_is_graded_good_through_fsrs(app, db, me) -> None:
    card = _card(db, me, "kettle", due=PAST)
    body = _answer(app, me, card, "meaning_type", " Kettle ").json()
    assert (body["correct"], body["graded"], body["answer"]) == (True, True, "kettle")
    assert body["sentence"] == "I saw a kettle yesterday."
    # `typed_matched` is the reviewer's measure against the card's back; the
    # drill asks for the word, so it records none (NULL) and the rating speaks.
    assert _reviews(db, card) == [(3, None)]
    (due,) = db.execute("SELECT due FROM cards WHERE id = %s", (card,)).fetchone()
    assert due > NOW


def test_a_wrong_answer_on_a_due_card_is_again_and_says_the_word(app, db, me) -> None:
    card = _card(db, me, "kettle", due=PAST)
    body = _answer(app, me, card, "hear_type", "cattle").json()
    assert (body["correct"], body["graded"], body["answer"]) == (False, True, "kettle")
    assert _reviews(db, card) == [(1, None)]


def test_a_top_up_card_is_practice_only_and_nothing_is_written(app, db, me) -> None:
    """Q8: reviewing early moves FSRS stability (R7), so a not-due card is never graded."""
    card = _card(db, me, "chair", due=LATER)
    before = db.execute("SELECT due, reps FROM cards WHERE id = %s", (card,)).fetchone()
    body = _answer(app, me, card, "meaning_type", "chair").json()
    assert (body["correct"], body["graded"]) == (True, False)
    assert _reviews(db, card) == []
    assert db.execute("SELECT due, reps FROM cards WHERE id = %s", (card,)).fetchone() == before


def test_choosing_the_right_picture_is_correct(app, db, me, pictures) -> None:
    card = _card(db, me, "parrot", due=PAST)
    (image_id,) = db.execute(
        "SELECT li.id FROM lexeme_images li JOIN lexemes l ON l.id = li.lexeme_id WHERE l.lemma = 'parrot'"
    ).fetchone()
    assert _answer(app, me, card, "word_to_picture", str(image_id)).json()["correct"] is True


def test_a_kind_that_does_not_fit_the_card_is_refused_and_nothing_is_written(app, db, me) -> None:
    plain = _card(db, me, "kettle", due=PAST)
    slang = _card(db, me, "chair", due=PAST, register="slang")
    assert _answer(app, me, plain, "picture_to_word", "kettle").status_code == 404
    assert _answer(app, me, slang, "hear_type", "chair").status_code == 404
    assert _reviews(db, plain) == [] and _reviews(db, slang) == []


def test_someone_elses_card_is_a_404(app, db, me) -> None:
    assert _answer(app, me, 2**31 - 7, "hear_type", "x").status_code == 404


# ── the word, spoken ─────────────────────────────────────────────────────────


def test_the_audio_speaks_the_word_through_the_wrapper(app, db, me, monkeypatch) -> None:
    from core import speech

    spoken: list[str] = []
    monkeypatch.setattr(speech, "synthesize", lambda text, **k: spoken.append(text) or b"ID3fake")
    card = _card(db, me, "kettle", due=PAST)
    response = request(app, "GET", f"/practice/{card}/audio", cookies=_as(me))
    assert (response.status_code, response.content) == (200, b"ID3fake")
    assert spoken == ["kettle"]


def test_a_provider_failure_is_a_503_and_never_names_the_word(app, db, me, monkeypatch) -> None:
    from core import speech

    def fail(text, **k):
        raise speech.SpeechError("down")

    monkeypatch.setattr(speech, "synthesize", fail)
    card = _card(db, me, "kettle", due=PAST)
    response = request(app, "GET", f"/practice/{card}/audio", cookies=_as(me))
    assert response.status_code == 503
    assert "kettle" not in response.text


# ── keep going ───────────────────────────────────────────────────────────────


TUESDAY = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)
SUNDAY = datetime(2026, 10, 4, 9, 0, tzinfo=timezone.utc)


def test_keep_going_offers_practice_once_there_are_four_words(db, me) -> None:
    for w in ("kettle", "chair", "band"):
        _card(db, me, w, due=LATER)
    assert "practice" not in keep_going.options(me.user_id, now=TUESDAY)
    _card(db, me, "table", due=LATER)
    assert "practice" in keep_going.options(me.user_id, now=TUESDAY)


def test_keep_going_never_offers_practice_on_sunday(db, me) -> None:
    for w in ("kettle", "chair", "band", "table"):
        _card(db, me, w, due=LATER)
    assert "practice" not in keep_going.options(me.user_id, now=SUNDAY)


def test_the_drill_fixtures_match_the_wire(app, db, me, pictures) -> None:
    """#190 for W31d's Vitest and Playwright fixtures."""
    import json
    from pathlib import Path

    committed = json.loads(
        (Path(__file__).resolve().parents[1] / "apps/web/components/write/write.fixture.json")
        .read_text(encoding="utf-8")
    )
    _card(db, me, "parrot", due=PAST)
    _card(db, me, "kettle", due=PAST)
    _card(db, me, "spoon", due=PAST)
    served = _start(app, me)
    kinds = {e["kind"]: e for e in served}
    for fixture_ex in committed["practice_start"]["exercises"]:
        if fixture_ex["kind"] in kinds:
            assert set(fixture_ex) == set(kinds[fixture_ex["kind"]])
    assert kinds, "the served drill was empty; this comparison read nothing"
    card = db.execute("SELECT id FROM cards WHERE user_id = %s AND front = 'kettle'",
                      (me.user_id,)).fetchone()[0]
    answered = _answer(app, me, card, "meaning_type", "kettle").json()
    assert set(committed["practice_right"]) == set(answered)


# ── Q9 (B): picture candidates from saved words ─────────────────────────────


def test_a_word_a_learner_saved_leads_the_picture_proposals(db, me) -> None:
    """Ruling Q9 (B): a picture on a word nobody saved reaches nobody (the 18 of
    W24b), so the proposer puts saved words first. *kettle* has no card and is
    not in the syllabus, so before a save it is not proposed at all."""
    from core.services import lexeme_images as images
    from tests.test_video_route import ID_PREFIX, _assign_today

    assert "kettle" not in images.proposal_lemmas(3000)
    video = _assign_today(db, me, transcript="the kettle is on.", youtube_id=f"{ID_PREFIX}q9b01")
    db.execute(
        "INSERT INTO word_saves_pending (user_id, video_id, word, lemma, context_sentence) "
        "VALUES (%s, %s, 'kettle', NULL, 'the kettle is on.')",
        (me.user_id, video),
    )
    db.commit()
    try:
        proposals = images.proposal_lemmas(3000)
        assert "kettle" in proposals
        assert proposals.index("kettle") < proposals.index("dozen")
    finally:
        db.execute("DELETE FROM word_saves_pending WHERE user_id = %s", (me.user_id,))
        db.commit()
