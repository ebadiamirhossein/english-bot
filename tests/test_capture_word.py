"""W13-ii: one tap → two cards, and the polite refusal on the second (#178).

Against a real database. **Nothing here reaches a model**: §1a is ruled
PRE-GENERATE, so the definition is already a `video_glosses` row and the request
path only reads it. `tests/support/netguard.py` is armed session-wide, so a
provider call would raise rather than pass silently.

**THE FINDING THIS FILE IS BUILT AROUND, AND THE PLAN'S §2e DID NOT STATE IT.**
§2e says *one tap → two cards of different `card_type` (cloze + production)*.
**For an informal or slang word that pair CANNOT BE INSERTED**: 013's
`cards_receptive_first_until_the_neutral_is_mastered` refuses `production`,
`cloze` and `collocation` for those registers until `neutral_mastered_at` is
set, and `cards_taboo_is_never_productive` refuses `production` for `taboo`.
**Measured against the live schema, all twenty combinations, before a line was
written** — so the pair is chosen by register, which is CLAUDE.md §4's
*receptive-only until the neutral equivalent is mastered* and 013's CHECKs
agreeing rather than a workaround.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

import psycopg
import pytest

from core.config import load_settings
from core.services import cards as cards_svc
from core.services import glosses as glosses_svc

NOW = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)
LINE = "honestly that party was mid"


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def learner(db):
    row = db.execute(
        "INSERT INTO users (name, native_language, auth_email, onboarded) "
        "VALUES ('w13ii-cap', 'fa', %s, TRUE) RETURNING id",
        (f"w13ii-cap-{secrets.token_hex(6)}@example.invalid",),
    ).fetchone()
    user_id = int(row[0])
    db.commit()
    try:
        yield user_id
    finally:
        db.execute("DELETE FROM cards WHERE user_id = %s", (user_id,))
        db.execute("DELETE FROM users WHERE id = %s", (user_id,))
        db.commit()


@pytest.fixture
def video(db):
    row = db.execute(
        """
        INSERT INTO videos (youtube_id, channel_id, accent, track, title,
                            transcript, transcript_status, metadata_refreshed_at)
        VALUES (%s, 'w13ii', 'british', 'life', 'A probe video', %s, 'ok', now())
        RETURNING id
        """,
        (f"w13ii-{secrets.token_hex(5)}", LINE),
    ).fetchone()
    video_id = int(row[0])
    db.commit()
    try:
        yield video_id
    finally:
        db.execute("DELETE FROM videos WHERE id = %s", (video_id,))
        db.commit()


def _gloss(db, video_id: int, **over) -> None:
    spec = dict(
        video_id=video_id,
        word="mid",
        context_sentence=LINE,
        cue_start_s=12.5,
        definition="disappointing, not as good as expected",
        register="slang",
        neutral_equivalent="disappointing",
        who_says_this="younger speakers, to friends",
        model="test-model",
    )
    spec.update(over)
    glosses_svc.insert_gloss(db, **spec)
    db.commit()


# ── the register decides the pair, and the schema decides the register ──────


def test_a_neutral_word_makes_the_productive_pair() -> None:
    assert cards_svc.capture_card_types("neutral") == ("cloze", "production")
    assert cards_svc.capture_card_types("formal") == ("cloze", "production")


def test_a_slang_word_makes_the_receptive_pair() -> None:
    """**Not a workaround: CLAUDE.md §4 and 013's CHECK saying the same thing.**
    *Slang and informal items are receptive-only until the neutral equivalent is
    mastered.* A cloze card for `mid` would be teaching production of slang."""
    for register in ("informal", "slang", "taboo"):
        assert cards_svc.capture_card_types(register) == ("recognition", "audio")


def test_every_pair_this_function_returns_is_actually_insertable(db, learner) -> None:
    """**The assertion that makes the two above mean something.** Both types of
    every pair are driven into the real table, so a CHECK the mapping forgot is
    a failure here rather than a 500 on a learner's tap."""
    from core.cards.fsrs import CardState

    for register in ("formal", "neutral", "informal", "slang", "taboo"):
        for card_type in cards_svc.capture_card_types(register):
            card_id = cards_svc.create_card(
                db,
                learner,
                card_type=card_type,
                front=f"{register}-{card_type}-{secrets.token_hex(3)}",
                back="mid",
                register=register,
                register_source="detected",
                state=CardState(
                    fsrs_state="learning", fsrs_step=0, stability=None,
                    difficulty=None, due=NOW, last_review=None, lapses=0, reps=0,
                ),
                context_sentence=LINE,
                meaning="disappointing",
                neutral_equivalent="disappointing",
                who_says_this="younger speakers, to friends",
            )
            assert card_id is not None, (register, card_type)
    db.commit()


# ── the tap ─────────────────────────────────────────────────────────────────


def test_one_tap_writes_two_cards_carrying_the_line_and_the_timestamp(
    db, learner, video
) -> None:
    """**Acceptance criterion 1, in full.** Both cards carry the exact transcript
    line and the timestamp, which exists because 021 stored the cues."""
    _gloss(db, video)
    result = cards_svc.save_captured_word(
        learner, video_id=video, word="mid", now=NOW
    )
    assert result.state == "saved"
    assert len(result.card_ids) == 2

    rows = db.execute(
        "SELECT card_type, context_sentence, source_ref, source_title, "
        "       captured_at, register, register_source, lexeme_id, front, meaning "
        "  FROM cards WHERE user_id = %s ORDER BY card_type",
        (learner,),
    ).fetchall()
    assert [r[0] for r in rows] == ["audio", "recognition"]
    for row in rows:
        assert row[1] == LINE
        assert row[2] == f"video:{video}@12.500"
        assert row[3] == "A probe video"
        assert row[4] is not None
        assert (row[5], row[6]) == ("slang", "detected")
        # #181: a slang card is written with lexeme_id NULL — outside the
        # lemma-keyed guarantees, exactly as the 15 migrated recognition cards
        # already are. Stated as a deferral with its cost, not as a fix.
        assert row[7] is None
        # #158: the capture path never puts `meaning` into `front`.
        assert row[9] not in row[8]


def test_a_video_without_cues_gives_the_sentence_and_no_timestamp(
    db, learner, video
) -> None:
    """**The third state, and it is not an error.** `source_ref` names the video
    and stops there; nothing is invented for the offset."""
    _gloss(db, video, cue_start_s=None)
    cards_svc.save_captured_word(learner, video_id=video, word="mid", now=NOW)
    row = db.execute(
        "SELECT source_ref, context_sentence FROM cards WHERE user_id = %s LIMIT 1",
        (learner,),
    ).fetchone()
    assert row[0] == f"video:{video}"
    assert row[1] == LINE


def test_a_word_with_no_gloss_is_refused_and_writes_nothing(
    db, learner, video
) -> None:
    """**§1a is pre-generate, so an ungiossed word is a fact and not a prompt.**
    The route serialises this as an explicit state; it never generates on a tap,
    which is the standing ruling this whole slice is built on.
    """
    result = cards_svc.save_captured_word(
        learner, video_id=video, word="unglossed", now=NOW
    )
    assert result.state == "no_gloss"
    assert result.card_ids == ()
    count = db.execute(
        "SELECT count(*) FROM cards WHERE user_id = %s", (learner,)
    ).fetchone()
    assert count[0] == 0


# ── #178, the polite refusal ────────────────────────────────────────────────


def test_a_second_tap_is_already_saved_and_not_an_error(db, learner, video) -> None:
    """**#178.** A second tap on a saved word must not be a 500 in front of a
    learner who did a normal thing — and must not silently look like success
    either, or the surface cannot tell them what happened."""
    _gloss(db, video)
    first = cards_svc.save_captured_word(learner, video_id=video, word="mid", now=NOW)
    second = cards_svc.save_captured_word(learner, video_id=video, word="mid", now=NOW)

    assert first.state == "saved"
    assert second.state == "already_saved"
    assert second.card_ids == ()
    # The positive control: the first tap really did write, so `already_saved`
    # is the pre-check firing and not both taps failing (#345).
    count = db.execute(
        "SELECT count(*) FROM cards WHERE user_id = %s", (learner,)
    ).fetchone()
    assert count[0] == 2


def test_the_three_states_are_distinct_values(db, learner, video) -> None:
    """`saved`, `already_saved` and `no_gloss` are three different answers to
    three different questions. A boolean would collapse two of them."""
    assert len({"saved", "already_saved", "no_gloss"}) == 3
    _gloss(db, video)
    states = {
        cards_svc.save_captured_word(learner, video_id=video, word="mid", now=NOW).state,
        cards_svc.save_captured_word(learner, video_id=video, word="mid", now=NOW).state,
        cards_svc.save_captured_word(learner, video_id=video, word="nope", now=NOW).state,
    }
    assert states == {"saved", "already_saved", "no_gloss"}


def test_a_slang_capture_is_matched_by_line_and_front_not_by_lemma(
    db, learner, video
) -> None:
    """**#181's deferral, asserted rather than described.** A slang card has
    `lexeme_id NULL`, so `cards_one_card_per_lemma` cannot see it and
    `lemmas_with_a_card` cannot either. The already-saved check for such a
    capture is by `(user_id, context_sentence, front)`.

    **The cost is stated and not fixed: two slang captures of the same phrase
    from two DIFFERENT lines would both be written**, because the line is part
    of the key. #181's identity question stays open.
    """
    _gloss(db, video)
    cards_svc.save_captured_word(learner, video_id=video, word="mid", now=NOW)
    assert cards_svc.save_captured_word(
        learner, video_id=video, word="mid", now=NOW
    ).state == "already_saved"

    # A different line is a different capture, and this is the cost.
    _gloss(db, video, word="mid2", context_sentence="the sequel was mid too")
    assert cards_svc.save_captured_word(
        learner, video_id=video, word="mid2", now=NOW
    ).state == "saved"
