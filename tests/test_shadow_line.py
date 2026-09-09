"""W14 test 7 — **§1b's ruling, made structural rather than documented.**

The shadow target is `cards.context_sentence` and NEVER a transcript cue.
A video-sourced card carries a rolling-window fragment in that column
(`video.explain._line_for` → `cards.save_captured_word`), identified exactly by
`source_ref LIKE 'video:%'`.

**BOTH DIRECTIONS ARE ASSERTED.** A test that only checked *the video card is
not returned* would pass if the selector returned nothing at all — an assertion
unable to fail for the reason it claims (#345). So the deck-card case asserts
the exact card id it expects.

*(The exclusion selects nothing on production today: `core.video.explain
--apply` has never run. It is tested now because the first video-sourced card
appears the day T1 clears.)*
"""

from __future__ import annotations

import uuid

import pytest

from core.db import connection
from core.services.shadow_score import MIN_SHADOW_CHARS, shadow_line

DECK_SENTENCE = "I'll grab a coffee before the meeting."
CUE_FRAGMENT = "grab a coffee before the"


@pytest.fixture(autouse=True)
def consented(learner, monkeypatch):
    """§1b's selector tests are about the CUE EXCLUSION, not the consent gate.

    The gate (#364) is empty by default, so without this every test here would
    pass for the wrong reason — `None` from the gate is indistinguishable from
    `None` from the predicate under test. Asserted separately in
    `tests/test_shadow_consent_gate.py`.
    """
    monkeypatch.setenv("VOICE_ALLOWED_USER_IDS", str(learner))


@pytest.fixture()
def learner():
    """A user with an empty deck, rolled back afterwards."""
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO users (telegram_user_id, name, native_language,
                               onboarded, timezone, auth_email)
            VALUES (NULL, 'w14-shadow-fixture', 'fa', TRUE, 'Europe/Vilnius',
                    %s)
            RETURNING id
            """,
            (f"w14-shadow-{uuid.uuid4()}@example.test",),
        ).fetchone()
        user_id = int(row["id"])
        conn.commit()
    yield user_id
    with connection() as conn:
        conn.execute("DELETE FROM speech_attempts WHERE user_id = %s", (user_id,))
        conn.execute("DELETE FROM cards WHERE user_id = %s", (user_id,))
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()


def _card(conn, user_id: int, *, sentence: str, source_ref: str | None) -> int:
    row = conn.execute(
        """
        INSERT INTO cards (user_id, card_type, front, back, context_sentence,
                           source_ref, register, register_source,
                           fsrs_state, fsrs_step, due, lapses, reps)
        VALUES (%s, 'production', 'front', 'back', %s, %s, 'neutral',
                'migration_default', 'learning', 0, CURRENT_DATE, 0, 0)
        RETURNING id
        """,
        (user_id, sentence, source_ref),
    ).fetchone()
    return int(row["id"])


def test_a_deck_card_is_offered(learner: int) -> None:
    """The positive. **Without it the negative below proves nothing.**"""
    with connection() as conn:
        card_id = _card(conn, learner, sentence=DECK_SENTENCE, source_ref=None)
        conn.commit()
        line = shadow_line(conn, learner)
    assert line is not None
    assert line.card_id == card_id
    assert line.sentence == DECK_SENTENCE


def test_a_video_sourced_card_is_never_offered_even_when_it_is_the_only_one(
    learner: int,
) -> None:
    """§1b. **`None` here is the correct answer, not a failure to find one.**

    The card is otherwise perfectly eligible — long enough, non-null, due — so
    the ONLY thing excluding it is `source_ref LIKE 'video:%'`.
    """
    with connection() as conn:
        _card(
            conn,
            learner,
            sentence="a sentence long enough to pass the floor",
            source_ref="video:7@3.200",
        )
        conn.commit()
        assert shadow_line(conn, learner) is None


def test_the_deck_card_wins_when_both_exist(learner: int) -> None:
    """The discriminating case: two eligible-looking cards, one excluded."""
    with connection() as conn:
        _card(conn, learner, sentence=CUE_FRAGMENT + " meeting today",
              source_ref="video:7@3.200")
        wanted = _card(conn, learner, sentence=DECK_SENTENCE, source_ref=None)
        conn.commit()
        line = shadow_line(conn, learner)
    assert line is not None and line.card_id == wanted


def test_a_sentence_below_the_floor_is_not_offered(learner: int) -> None:
    """`CompletenessScore` over two words is dominated by its endpoints."""
    short = "Yes I do."
    assert len(short) < MIN_SHADOW_CHARS
    with connection() as conn:
        _card(conn, learner, sentence=short, source_ref=None)
        conn.commit()
        assert shadow_line(conn, learner) is None


def test_a_null_context_sentence_is_not_offered(learner: int) -> None:
    with connection() as conn:
        _card(conn, learner, sentence=None, source_ref=None)
        conn.commit()
        assert shadow_line(conn, learner) is None


def test_the_least_recently_said_line_comes_back_first(learner: int) -> None:
    """Never-shadowed first, then least-recently. **Asserted by id, in order.**"""
    with connection() as conn:
        said = _card(conn, learner, sentence="A sentence said already today.",
                     source_ref=None)
        fresh = _card(conn, learner, sentence="A sentence never said aloud.",
                      source_ref=None)
        conn.execute(
            "INSERT INTO speech_attempts (user_id, card_id, surface,"
            " reference_text, accuracy, fluency, completeness, pron_score,"
            " words, phonemes, audio_seconds, provider)"
            " VALUES (%s, %s, 'shadow', 'A sentence said already today.',"
            " 90, 90, 90, 90, '[]'::jsonb, '[]'::jsonb, 3.0, 'azure')",
            (learner, said),
        )
        conn.commit()
        line = shadow_line(conn, learner)
    assert line is not None
    assert line.card_id == fresh, "a never-shadowed line must come before a said one"
