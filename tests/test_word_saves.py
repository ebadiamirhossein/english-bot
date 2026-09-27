"""W31c — tap and save ANY word: the sheet, Save, pending saves, My words.

**Through the real ASGI transport** (CLAUDE.md §3 rule 1): nothing here calls a
route function. `tests/support/netguard.py` is armed session-wide, so a model
call on any of these request paths would raise inside the request rather than
pass — which is how *the app never generates while a learner waits* is known
for the new routes, not read off a comment.

**RED BEFORE THE CODE (2026-09-27):** `GET /video/{id}/word` and `GET /words`
did not exist (404), `SaveWordIn` had no `line`, a word with no gloss answered
`no_gloss` and wrote nothing, an inflected tap missed its lemma's gloss (#468),
and a capture never carried a `lexeme_id` (#469).
"""

from __future__ import annotations

import secrets

import psycopg
import pytest

from core.config import load_settings
from core.services import glosses as glosses_svc
from tests.test_video_route import (  # noqa: F401 -- fixtures, by name
    ID_PREFIX,
    _as,
    _assign_today,
    app,
    auth_env,
    db,
    learner,
    request,
)

TEXT = "we went out last night. the parties were great. I loved the band."


@pytest.fixture
def me(db, learner):
    """The learner, with their pending saves removed BEFORE the shared
    teardown deletes videos (`word_saves_pending.video_id` is RESTRICT)."""
    yield learner
    db.execute("DELETE FROM word_saves_pending WHERE user_id = %s", (learner.user_id,))
    db.execute("DELETE FROM cards WHERE user_id = %s", (learner.user_id,))
    db.commit()


@pytest.fixture
def video(db, me) -> int:
    return _assign_today(db, me, transcript=TEXT, youtube_id=f"{ID_PREFIX}{secrets.token_hex(3)}")


def _gloss(db, video_id: int, word: str = "party", **over) -> None:
    spec = dict(
        video_id=video_id, word=word, context_sentence="a line explain found first",
        cue_start_s=None, definition="a social event with music and friends",
        register="neutral", neutral_equivalent=None, who_says_this=None,
        model="test-model", l1={"fa": "مهمانی", "lt": "vakarėlis"}, source="manual",
    )
    spec.update(over)
    glosses_svc.insert_gloss(db, **spec)
    db.commit()


def _lookup(app, me, video, word, line=None):
    path = f"/video/{video}/word?w={word}" + (f"&line={line}" if line is not None else "")
    return request(app, "GET", path, cookies=_as(me))


def _save(app, me, video, body):
    return request(app, "POST", f"/video/{video}/save-word", json_body=body, cookies=_as(me))


# ── the sheet ────────────────────────────────────────────────────────────────


def test_the_sheet_requires_a_session(app) -> None:
    assert request(app, "GET", "/video/1/word?w=party").status_code == 401


def test_the_sheet_is_a_404_for_a_video_that_is_not_yours(app, db, me) -> None:
    other = _assign_today(db, me, transcript=TEXT, youtube_id=f"{ID_PREFIX}{secrets.token_hex(3)}")
    db.execute("DELETE FROM video_assignments WHERE video_id = %s", (other,))
    db.commit()
    assert _lookup(app, me, other, "party").status_code == 404


def test_the_sheet_shows_the_meaning_and_the_learners_own_language(app, db, me, video) -> None:
    """User action: tapping *parties* under the player. The learner is `fa`."""
    _gloss(db, video)
    body = _lookup(app, me, video, "parties", line=1).json()
    assert body["word"] == "parties"
    assert body["lemma"] == "party"
    assert body["line"] == "the parties were great."
    assert body["meaning"]["definition"] == "a social event with music and friends"
    assert body["meaning"]["register"] == "neutral"
    assert (body["meaning"]["l1"], body["meaning"]["l1_language"]) == ("مهمانی", "fa")
    assert "vakarėlis" not in str(body), "only the learner's own language"
    assert body["saved"] == "none"


def test_the_sheet_without_a_gloss_still_offers_the_word_and_its_line(app, db, me, video) -> None:
    body = _lookup(app, me, video, "band").json()
    assert "meaning" not in body
    assert body["line"] == "I loved the band."
    assert body["saved"] == "none"


# ── Save, with a gloss ───────────────────────────────────────────────────────


def test_a_word_with_a_gloss_saves_two_cards_with_the_line_it_was_tapped_in(app, db, me, video) -> None:
    _gloss(db, video)
    response = _save(app, me, video, {"word": "parties", "line": 1})
    assert (response.status_code, response.json()["state"]) == (200, "saved")
    sentences = {r[0] for r in db.execute(
        "SELECT context_sentence FROM cards WHERE user_id = %s", (me.user_id,)).fetchall()}
    assert sentences == {"the parties were great."}


def test_an_inflected_tap_finds_the_lemmas_gloss(app, db, me, video) -> None:
    """#468: `explain` writes the lemma; a tap on the inflection used to miss."""
    _gloss(db, video)
    assert _save(app, me, video, {"word": "parties"}).json()["state"] == "saved"


def test_a_neutral_capture_carries_its_lexeme_so_a_picture_can_reach_it(app, db, me, video) -> None:
    """#469: `lexeme_images` is keyed on `lexeme_id`; captures wrote NULL."""
    _gloss(db, video)
    _save(app, me, video, {"word": "parties", "line": 1})
    ids = {r[0] for r in db.execute(
        "SELECT c.lexeme_id FROM cards c WHERE c.user_id = %s", (me.user_id,)).fetchall()}
    party = db.execute("SELECT id FROM lexemes WHERE lemma = 'party'").fetchone()[0]
    assert ids == {party}


def test_a_slang_capture_keeps_no_lexeme(app, db, me, video) -> None:
    _gloss(db, video, register="slang", neutral_equivalent="event",
           who_says_this="friends, casually")
    _save(app, me, video, {"word": "parties", "line": 1})
    assert {r[0] for r in db.execute(
        "SELECT lexeme_id FROM cards WHERE user_id = %s", (me.user_id,)).fetchall()} == {None}


def test_a_word_already_in_the_deck_by_its_lexeme_is_already_saved_not_a_500(
    app, db, me, video
) -> None:
    """#178's rule, re-armed by #469: `cards_one_card_per_lemma` is live now."""
    from datetime import datetime, timezone

    from core.cards.fsrs import CardState
    from core.services import cards as cards_svc

    party = db.execute("SELECT id FROM lexemes WHERE lemma = 'party'").fetchone()[0]
    cards_svc.create_card(
        db, me.user_id, card_type="production", front="party", back="x",
        register="neutral", register_source="detected",
        state=CardState("learning", 0, None, None, datetime.now(timezone.utc), None, 0, 0),
        lexeme_id=party,
    )
    db.commit()
    _gloss(db, video)
    response = _save(app, me, video, {"word": "parties", "line": 1})
    assert (response.status_code, response.json()["state"]) == (200, "already_saved")


# ── Save, without a gloss ────────────────────────────────────────────────────


def test_a_word_without_a_gloss_is_pending_and_no_card_is_written(app, db, me, video) -> None:
    """The operator's finding: a word with no gloss could not be saved at all.
    **The card enters the deck only once it has a meaning** (W13-ii/2)."""
    first = _save(app, me, video, {"word": "band", "line": 2})
    second = _save(app, me, video, {"word": "band", "line": 2})
    assert (first.status_code, first.json()["state"]) == (200, "pending")
    assert second.json()["state"] == "pending"
    rows = db.execute(
        "SELECT word, context_sentence, state FROM word_saves_pending WHERE user_id = %s",
        (me.user_id,),
    ).fetchall()
    assert rows == [("band", "I loved the band.", "pending")]
    assert db.execute("SELECT count(*) FROM cards WHERE user_id = %s",
                      (me.user_id,)).fetchone()[0] == 0


def test_the_sentence_is_the_servers_never_the_clients(app, db, me, video) -> None:
    """A forged index (a line without the word) falls back to the first line
    that holds it; a `sentence` field in the body is not a field at all."""
    _save(app, me, video, {"word": "band", "line": 0, "sentence": "INJECTED"})
    (sentence,) = db.execute(
        "SELECT context_sentence FROM word_saves_pending WHERE user_id = %s", (me.user_id,)
    ).fetchone()
    assert sentence == "I loved the band."


def test_a_purged_transcript_with_no_gloss_has_no_line_to_keep(app, db, me) -> None:
    purged = _assign_today(db, me, transcript=None, youtube_id=f"{ID_PREFIX}{secrets.token_hex(3)}")
    assert _save(app, me, purged, {"word": "band"}).json()["state"] == "no_line"


def test_the_sheet_says_a_pending_word_is_pending(app, db, me, video) -> None:
    _save(app, me, video, {"word": "band", "line": 2})
    assert _lookup(app, me, video, "band").json()["saved"] == "pending"


# ── My words ─────────────────────────────────────────────────────────────────


def test_my_words_requires_a_session(app) -> None:
    assert request(app, "GET", "/words").status_code == 401


def test_my_words_lists_saved_and_waiting_words_and_never_a_count(app, db, me, video) -> None:
    _gloss(db, video)
    _save(app, me, video, {"word": "parties", "line": 1})
    _save(app, me, video, {"word": "band", "line": 2})
    body = request(app, "GET", "/words", cookies=_as(me)).json()
    assert set(body) <= {"words", "next_before"}
    got = {(w["word"], w["state"], w["sentence"]) for w in body["words"]}
    assert got == {("party", "in_deck", "the parties were great."),
                   ("band", "pending", "I loved the band.")}
    # Newest first: the pending word was saved second.
    assert body["words"][0]["word"] == "band"
    assert "count" not in str(body) and "total" not in str(body)


def test_a_pending_save_promises_a_meaning_only_while_the_job_is_on(
    app, db, me, video, monkeypatch
) -> None:
    """C4: with `WORD_GLOSS_JOB` off, nothing will fill the meaning, so the
    answer must not say it is coming. An exported variable wins over `.env`."""
    monkeypatch.setenv("WORD_GLOSS_JOB", "0")
    assert _save(app, me, video, {"word": "band", "line": 2}).json()["meaning_soon"] is False
    monkeypatch.setenv("WORD_GLOSS_JOB", "1")
    assert _save(app, me, video, {"word": "loved", "line": 2}).json()["meaning_soon"] is True


def test_the_word_fixtures_match_the_wire(app, db, me, video) -> None:
    """#190 for W31c's Vitest and Playwright fixtures: `write.fixture.json`'s
    word bodies are built through the real response models; this holds their
    keys to what the routes actually serve."""
    import json
    from pathlib import Path

    committed = json.loads(
        (Path(__file__).resolve().parents[1] / "apps/web/components/write/write.fixture.json")
        .read_text(encoding="utf-8")
    )
    _gloss(db, video)
    served = _lookup(app, me, video, "parties", line=1).json()
    assert set(committed["word_lookup_meaning"]) == set(served)
    assert set(committed["word_lookup_meaning"]["meaning"]) == set(served["meaning"])
    none = _lookup(app, me, video, "band").json()
    assert set(committed["word_lookup_none"]) == set(none)

    pending = _save(app, me, video, {"word": "band", "line": 2}).json()
    assert set(committed["save_pending_soon"]) == set(pending)
    saved = _save(app, me, video, {"word": "parties", "line": 1}).json()
    assert set(committed["save_saved"]) == set(saved)

    words = request(app, "GET", "/words", cookies=_as(me)).json()
    assert set(committed["my_words"]) - {"next_before"} == set(words) - {"next_before"}
    assert set(committed["my_words"]["words"][0]) == set(words["words"][0])
