"""Reading engine delivery + chunks (S9a)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.db import connection
from core.services.interests import replace_interests, select_topic
from core.services.reading import (
    ReadingValidationError,
    normalize_for_match,
    validate_reading_payload,
)
from core.services.identity import save_onboarding
FAKE_TELEGRAM_ID_BASE = 9_460_000_000
_TG_ADDRESS_BASE = 9_000_000_000

# Monday 2026-08-03 — a reading day.
_MONDAY_EVENING_UTC = datetime(2026, 8, 3, 18, 5, tzinfo=timezone.utc)  # 21:05 Vilnius
# Tuesday — not a reading day.
_TUESDAY_EVENING_UTC = datetime(2026, 8, 4, 18, 5, tzinfo=timezone.utc)


@pytest.fixture
def fake_telegram_id() -> int:
    return FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)


def _delete_user(telegram_user_id: int) -> None:
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM users WHERE telegram_user_id = %s",
                (telegram_user_id,),
            )


@pytest.fixture
def cleanup_user(fake_telegram_id: int):
    yield fake_telegram_id
    _delete_user(fake_telegram_id)


def _onboard(
    tid: int,
    *,
    evening: str = "21:00",
    morning: str = "07:00",
    tz: str = "Europe/Vilnius",
    track_weights: dict[str, int] | None = None,
) -> int:
    user_id = save_onboarding(
        tid,
        {
            "name": "Reading Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": track_weights
            or {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": morning,
            "evening_time": evening,
        },
    )
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE users SET timezone = %s WHERE telegram_user_id = %s",
                (tz, tid),
            )
    return user_id


def _seed_interests(tid: int, rows: list[tuple[str, str]]) -> None:
    replace_interests(tid, rows)


def _set_interest_meta(
    tid: int,
    topic: str,
    *,
    weight: float,
    last_used: date | None,
) -> None:
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                UPDATE interests
                   SET weight = %s, last_used = %s
                 WHERE user_id = %s AND topic = %s
                """,
                (weight, last_used, tid, topic),
            )


def _words(n: int, seed: str = "word") -> str:
    return " ".join(f"{seed}{i}" for i in range(n))


def _valid_llm_payload(
    *,
    chunks: list[dict[str, str]] | None = None,
    body_override: str | None = None,
) -> dict[str, Any]:
    """Build a valid ~300-word body containing five known chunks."""
    phrases = [
        "market research cycle",
        "client email thread",
        "pricing negotiation room",
        "campaign launch window",
        "brand positioning work",
    ]
    if chunks is None:
        chunks = [
            {
                "chunk": phrases[i],
                "full_sentence": f"They discussed the {phrases[i]}.",
                "meaning": f"gloss {i}",
            }
            for i in range(5)
        ]
    filler = _words(280, "alpha")
    body = (
        f"The team opened with the {phrases[0]}. "
        f"Next came a {phrases[1]} that ran late. "
        f"In the {phrases[2]} they settled terms. "
        f"Then the {phrases[3]} closed. "
        f"Finally {phrases[4]} wrapped the week. "
        f"{filler}"
    )
    if body_override is not None:
        body = body_override
    return {
        "title": "A week in marketing",
        "body": body,
        "questions": [
            {
                "q": f"Q{i}?",
                "options": [f"A{i}", "wrong1", "wrong2", "wrong3"],
                "answer_index": 0,
                "why": f"Because the text says A{i}.",
            }
            for i in range(5)
        ],
        "chunks": chunks,
    }


def _count_rows(tid: int) -> tuple[int, int, int]:
    with connection() as conn:
        readings = conn.execute(
            "SELECT COUNT(*) AS n FROM readings WHERE user_id = %s",
            (tid,),
        ).fetchone()["n"]
        chunks = conn.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE user_id = %s",
            (tid,),
        ).fetchone()["n"]
        sessions = conn.execute(
            """
            SELECT COUNT(*) AS n FROM sessions
             WHERE user_id = %s AND task_type = 'reading'
            """,
            (tid,),
        ).fetchone()["n"]
    return int(readings), int(chunks), int(sessions)


def _mock_app(
    send_side_effect: Exception | None = None,
    *,
    telegram_id: int = 1,
    message_id: int = 100,
) -> MagicMock:
    app = MagicMock()
    msg = MagicMock()
    msg.chat_id = telegram_id
    msg.message_id = message_id
    send = AsyncMock(return_value=msg)
    if send_side_effect is not None:
        send.side_effect = send_side_effect
    app.bot.send_message = send
    return app


# --- Eligibility --------------------------------------------------------------


# --- Topic selection ----------------------------------------------------------


def test_topic_selection_prefers_weight_and_older_last_used(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _seed_interests(
        user_id,
        [
            ("alpha topic", "work"),
            ("beta topic", "work"),
            ("gamma topic", "life"),
        ],
    )
    today = date(2026, 8, 3)
    _set_interest_meta(
        user_id, "alpha topic", weight=1.0, last_used=today - timedelta(days=2)
    )
    _set_interest_meta(
        user_id, "beta topic", weight=3.0, last_used=today - timedelta(days=2)
    )
    _set_interest_meta(
        user_id, "gamma topic", weight=1.0, last_used=today - timedelta(days=2)
    )

    chosen = select_topic(user_id, {"work": 40, "life": 40, "curiosity": 20}, today)
    assert chosen is not None
    assert chosen.topic == "beta topic"


def test_topic_selection_higher_track_weight_wins(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _seed_interests(
        user_id,
        [
            ("work topic", "work"),
            ("life topic", "life"),
        ],
    )
    today = date(2026, 8, 3)
    chosen = select_topic(user_id, {"work": 60, "life": 25, "curiosity": 15}, today)
    assert chosen is not None
    assert chosen.topic == "work topic"


def test_topic_selection_alpha_tiebreak_stable(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _seed_interests(
        user_id,
        [
            ("zebra", "work"),
            ("apple", "work"),
        ],
    )
    today = date(2026, 8, 3)
    weights = {"work": 40, "life": 40, "curiosity": 20}
    first = select_topic(user_id, weights, today)
    second = select_topic(user_id, weights, today)
    assert first is not None and second is not None
    assert first.topic == "apple"
    assert second.topic == "apple"


# --- Validation ---------------------------------------------------------------


def test_chunk_capital_and_apostrophe_normalise() -> None:
    phrases_body = (
        "Market research cycle sits at the centre of every brief. "
        "The client's email thread ran for three days. "
        "A pricing negotiation room held the tension. "
        "The campaign launch window finally opened. "
        "Brand positioning work closed the loop. "
    )
    filler = _words(280)
    body = phrases_body + filler

    raw = {
        "title": "T",
        "body": body,
        "questions": [
            {
                "q": "q?",
                "options": ["a", "b", "c", "d"],
                "answer_index": 0,
                "why": "The text says so clearly.",
            }
            for _ in range(5)
        ],
        "chunks": [
            {
                "chunk": "market research cycle",
                "full_sentence": "Market research cycle sits at the centre.",
                "meaning": "m1",
            },
            {
                "chunk": "client\u2019s email thread",
                "full_sentence": "The client's email thread ran.",
                "meaning": "m2",
            },
            {
                "chunk": "pricing negotiation room",
                "full_sentence": "s",
                "meaning": "m3",
            },
            {
                "chunk": "campaign launch window",
                "full_sentence": "s",
                "meaning": "m4",
            },
            {
                "chunk": "brand positioning work",
                "full_sentence": "s",
                "meaning": "m5",
            },
        ],
    }
    validated = validate_reading_payload(raw)
    assert validated.chunks[0]["chunk"] == "market research cycle"
    assert validated.chunks[1]["chunk"] == "client\u2019s email thread"


def test_normalize_for_match_basics() -> None:
    assert normalize_for_match("Hello  World") == normalize_for_match("hello world")
    assert "don" in normalize_for_match("don\u2019t")


def test_validate_rejects_four_chunks() -> None:
    raw = _valid_llm_payload()
    raw["chunks"] = raw["chunks"][:4]
    with pytest.raises(ReadingValidationError):
        validate_reading_payload(raw)


def test_validate_rejects_legacy_question_shape() -> None:
    raw = _valid_llm_payload()
    raw["questions"] = [
        {
            "question": "q?",
            "answer": "a",
            "distractors": ["x", "y", "z"],
        }
        for _ in range(5)
    ]
    with pytest.raises(ReadingValidationError):
        validate_reading_payload(raw)


def test_validate_rejects_why_over_25_words() -> None:
    raw = _valid_llm_payload()
    raw["questions"][0]["why"] = " ".join(f"w{i}" for i in range(26))
    with pytest.raises(ReadingValidationError):
        validate_reading_payload(raw)


# --- Delivery paths -----------------------------------------------------------


