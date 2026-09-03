"""W14 — migration 024's shape, read from `information_schema`.

**The privacy rule is expressed as an ABSENT COLUMN, so the test that protects
it must read the real catalogue and not the `.sql` text.** A comment saying
*there is no transcript column* is worth nothing the day someone adds one; a
query over `information_schema` notices.
"""

from __future__ import annotations

import pytest

from core.db import connection


def _columns() -> dict[str, dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
              FROM information_schema.columns
             WHERE table_name = 'speech_attempts'
            """
        ).fetchall()
    return {r["column_name"]: dict(r) for r in rows}


def test_the_table_holds_scores_and_nothing_a_transcript_could_hide_in() -> None:
    """**The absence IS the rule** (CLAUDE.md §5, PRD §8, ARCHITECTURE §5:133).

    Azure's response carries a recognised transcript of the learner's voice. It
    is discarded in-request. **A column that existed would eventually be
    filled**, so none does — and the check is on the FULL column set rather than
    on a banned-name list, because the next author's column will not be called
    `transcript`.
    """
    columns = _columns()
    assert columns, "speech_attempts does not exist — is 024 applied?"
    assert set(columns) == {
        "id",
        "user_id",
        "session_id",
        "card_id",
        "surface",
        "reference_text",
        "accuracy",
        "fluency",
        "completeness",
        "pron_score",
        "prosody",
        "words",
        "phonemes",
        "audio_seconds",
        "provider",
        "created_at",
    }, (
        "The column set is exact on purpose: a new free-text column is how a "
        "recognised transcript would arrive, and it would arrive innocently."
    )


def test_prosody_and_session_id_are_nullable_and_the_scores_are_not() -> None:
    """NULL means **not measured**, never zero (#330's shape).

    `prosody` is nullable because the €0.264/hr add-on is **not bought**;
    `session_id` because a shadow attempt outside a sitting is not a defect.
    The four aggregates are NOT NULL because a scored attempt that produced no
    score is not a row worth keeping.
    """
    columns = _columns()
    assert columns["prosody"]["is_nullable"] == "YES"
    assert columns["session_id"]["is_nullable"] == "YES"
    assert columns["card_id"]["is_nullable"] == "YES"
    for name in ("accuracy", "fluency", "completeness", "pron_score"):
        assert columns[name]["is_nullable"] == "NO", name
    for name in ("user_id", "surface", "reference_text", "words", "phonemes",
                 "audio_seconds", "provider"):
        assert columns[name]["is_nullable"] == "NO", name


def test_user_id_keys_on_the_surrogate_identity_and_not_on_telegram() -> None:
    """PRODUCT-PRINCIPLES §2, asserted rather than asserted-in-a-comment."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT kcu.column_name, ccu.table_name AS target, ccu.column_name AS target_col
              FROM information_schema.table_constraints tc
              JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
              JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
             WHERE tc.table_name = 'speech_attempts'
               AND tc.constraint_type = 'FOREIGN KEY'
            """
        ).fetchall()
    targets = {r["column_name"]: (r["target"], r["target_col"]) for r in rows}
    assert targets["user_id"] == ("users", "id")
    assert targets["session_id"] == ("sessions", "id")
    assert targets["card_id"] == ("cards", "id")


_INSERT = (
    "INSERT INTO speech_attempts (user_id, surface, reference_text,"
    " accuracy, fluency, completeness, pron_score, words, phonemes,"
    " audio_seconds, provider)"
    " SELECT id, %s, %s, %s, 90, 90, 90, %s::jsonb, %s::jsonb, 3.0, 'azure'"
    " FROM users LIMIT 1"
)

_VALID = ("shadow", "a real sentence here", 90, "[]", "[]")


def _insert(args) -> None:
    """One insert in its own transaction, always rolled back.

    Never committed: a constraint test that left rows behind would make the
    NEXT test's counts depend on this one's order.
    """
    with connection() as conn:
        try:
            conn.execute(_INSERT, args)
        finally:
            conn.rollback()


def test_the_valid_row_inserts_and_this_test_is_why_the_others_can_fail() -> None:
    """**The positive control.** Without it every rejection below would pass
    even if `_INSERT` were malformed and the table rejected everything — an
    assertion unable to fail for the reason it claims (#345).
    """
    _insert(_VALID)


@pytest.mark.parametrize(
    "args, why",
    [
        (("retell", "a real sentence here", 90, "[]", "[]"),
         "surface is one value wide until W15 widens it (012 §3's move)"),
        (("shadow", "a real sentence here", 101, "[]", "[]"),
         "scores are HundredMark, 0-100"),
        (("shadow", "a real sentence here", 90, "{}", "[]"),
         "words must be a JSON array — W17 unnests it"),
        (("shadow", "a real sentence here", 90, "[]", "{}"),
         "phonemes must be a JSON array — W17 unnests it"),
        (("shadow", "   ", 90, "[]", "[]"),
         "a blank reference_text scores nothing"),
    ],
)
def test_the_checks_refuse_what_they_say_they_refuse(args, why: str) -> None:
    with pytest.raises(Exception):
        _insert(args)
