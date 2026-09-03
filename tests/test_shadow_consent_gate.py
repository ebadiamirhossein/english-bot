"""W14 — **the consent gate. TEMPORARY, and what removes it is written down.**

────────────────────────────────────────────────────────────────────────────────
WHY THIS EXISTS

`speech_attempts` is the first thing this product has ever built that sends a
learner's **voice** to a third party. §1c's four data-processing questions are
**unanswered**, and the fourth is *whether the second learner should be asked at
all* — she is a person whose voice would leave the country in a request she did
not make.

**W14 shipped code-complete WITHOUT this gate, and that was a real gap**: block 4
offered *Say it* to **any** onboarded learner with a usable card, and
`score_attempt` and the route had no condition at all. Deploying would have put
the control on her phone.

**WHAT THE GATE KEYS ON: `SHADOW_ALLOWED_USER_IDS`, an explicit allowlist of
`users.id`, and it FAILS CLOSED.** Unset means **nobody**, not everybody.

**Not a hardcoded id**, for two reasons: the operator is a different `users.id`
on the dev database and on production, so a literal would be wrong in one of
them; and a learner's id baked into the repository is the wrong place for it.

**WHAT REMOVES THE GATE — both, not either:**

1. **The second learner's agreement** that her voice may leave her device and be
   processed by Microsoft.
2. **Answers to §1c's four questions**: retention and whether it can be turned
   off; where audio is processed **and whether that holds on the FREE tier**;
   what the DPA says about voice; and whether voice is special-category data
   here.

**Until both, this stays.** Filed as #364 so it is not removed by someone who
reads it as a feature flag.

**THE GATE DOES NOT ANNOUNCE ITSELF.** A blocked learner gets no control and a
`404` — **indistinguishable from having no shadowable line**, which is an
ordinary state. A `403` would tell her a feature exists that she is excluded
from, which is a worse thing to put on someone's phone than nothing at all.
"""

from __future__ import annotations

import struct
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import psycopg
import pytest

from core.config import load_settings
from core.db import connection
from core.services import shadow_score

SENTENCE = "I'll grab a coffee before the meeting."


def wav(seconds: float = 1.0, rate: int = 16000) -> bytes:
    frames = int(seconds * rate)
    data = b"\x00\x00" * frames
    return (
        b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
        b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data" + struct.pack("<I", len(data)) + data
    )


@pytest.fixture
def learner():
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO users (telegram_user_id, name, native_language,
                               onboarded, timezone, auth_email)
            VALUES (NULL, 'w14-gate', 'lt', TRUE, 'Europe/Vilnius', %s)
            RETURNING id
            """,
            (f"w14-gate-{uuid.uuid4()}@example.test",),
        ).fetchone()
        user_id = int(row["id"])
        conn.execute(
            """
            INSERT INTO cards (user_id, card_type, front, back,
                               context_sentence, register, register_source,
                               fsrs_state, fsrs_step, due, lapses, reps)
            VALUES (%s, 'production', 'coffee', 'kava', %s, 'neutral',
                    'migration_default', 'learning', 0, CURRENT_DATE, 0, 0)
            """,
            (user_id, SENTENCE),
        )
        conn.commit()
    yield user_id
    with connection() as conn:
        conn.execute("DELETE FROM speech_attempts WHERE user_id = %s", (user_id,))
        conn.execute("DELETE FROM cards WHERE user_id = %s", (user_id,))
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()


def test_the_allowlist_is_empty_by_default_and_that_direction_is_the_point(
    monkeypatch,
) -> None:
    """**Unset means NOBODY.** Forgetting it costs a feature, never a voice."""
    monkeypatch.delenv("SHADOW_ALLOWED_USER_IDS", raising=False)
    assert load_settings().shadow_allowed_user_ids == ()


def test_a_learner_not_on_the_allowlist_is_offered_no_line(
    learner: int, monkeypatch
) -> None:
    """The card is otherwise perfect, so **only the gate can be excluding it.**"""
    monkeypatch.setenv("SHADOW_ALLOWED_USER_IDS", str(learner + 1000))
    with connection() as conn:
        assert shadow_score.shadow_line(conn, learner) is None


def test_a_learner_on_the_allowlist_is_offered_the_line(
    learner: int, monkeypatch
) -> None:
    """**The positive control.** Without it the negative above would pass even
    if `shadow_line` were broken and returned `None` for everyone (#345)."""
    monkeypatch.setenv("SHADOW_ALLOWED_USER_IDS", str(learner))
    with connection() as conn:
        line = shadow_score.shadow_line(conn, learner)
    assert line is not None
    assert line.sentence == SENTENCE


def test_an_allowlist_of_several_ids_is_parsed(learner: int, monkeypatch) -> None:
    monkeypatch.setenv("SHADOW_ALLOWED_USER_IDS", f" 99 , {learner} ,101 ")
    with connection() as conn:
        assert shadow_score.shadow_line(conn, learner) is not None


def test_scoring_refuses_for_a_blocked_learner_before_any_provider_call(
    learner: int, monkeypatch
) -> None:
    """**The gate is not cosmetic.** Hiding the control is not enough — the
    route is reachable with a card id, so the service refuses too.

    Asserts **no provider call**, because a gate that refuses only after sending
    the audio would have already done the thing it exists to prevent.
    """
    monkeypatch.setenv("SHADOW_ALLOWED_USER_IDS", "")
    monkeypatch.setenv("AZURE_SPEECH_KEY", "test-key-not-real")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "test-region")
    with connection() as conn:
        card = conn.execute(
            "SELECT id FROM cards WHERE user_id = %s", (learner,)
        ).fetchone()

    with patch("core.speech_api.httpx.post") as called:
        with pytest.raises(shadow_score.NotConsented):
            shadow_score.score_attempt(learner, int(card["id"]), wav())
    assert called.call_count == 0, "no audio may leave this process for a blocked learner"

    with connection() as conn:
        count = conn.execute(
            "SELECT count(*) AS n FROM speech_attempts WHERE user_id = %s",
            (learner,),
        ).fetchone()["n"]
    assert count == 0
