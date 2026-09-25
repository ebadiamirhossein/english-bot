"""S9c: reading comprehension grading, resume, rating→weight, legacy skip."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from psycopg.types.json import Jsonb
from telegram import CallbackQuery, Chat, Message, Update, User

from core.db import close_pool, connection
from core.services.interests import adjust_weight_for_rating
from core.services.reading import parse_stored_questions
from core.services.sessions import (
    get_reading_session_by_message,
    insert_session,
)
from core.services.identity import save_onboarding
FAKE_TELEGRAM_ID_BASE = 9_480_000_000


@pytest.fixture
def fake_telegram_id() -> int:
    return FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)


@pytest.fixture(autouse=True)
def _close_pool_after_test() -> None:
    yield
    close_pool()


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


def _onboard(tid: int) -> int:
    user_id = save_onboarding(
        tid,
        {
            "name": "Reading S9c",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": "07:00",
            "evening_time": "21:00",
        },
    )
    return user_id


def _mcq_list() -> list[dict[str, Any]]:
    return [
        {
            "q": f"Question {i}?",
            "options": [f"right{i}", f"w{i}a", f"w{i}b", f"w{i}c"],
            "answer_index": 0,
            "why": f"The text supports right{i}.",
        }
        for i in range(5)
    ]


def _insert_reading(
    tid: int,
    *,
    topic: str = "apartments",
    questions: list[dict[str, Any]] | None = None,
    completed: bool = False,
) -> int:
    qs = questions if questions is not None else _mcq_list()
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO readings (
                user_id, title, body, topic, cefr_level, questions,
                sent_at, completed
            ) VALUES (
                %s, %s, %s, %s, %s, %s, NOW(), %s
            )
            RETURNING id
            """,
            (
                tid,
                "Title",
                "Body text for a reading.",
                topic,
                "B1",
                Jsonb(qs),
                completed,
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _insert_reading_session(
    tid: int,
    reading_id: int,
    *,
    chat_id: int | None = None,
    message_id: int = 500,
    day: date | None = None,
    payload_extra: dict[str, Any] | None = None,
) -> int:
    # Defaults to the learner's own Telegram chat. Before W4b `tid` was both
    # the user id and the chat id; they are different numbers now, so a caller
    # that drives a fabricated Update must pass the Telegram id explicitly.
    chat = chat_id if chat_id is not None else tid
    payload: dict[str, Any] = {
        "reading_id": reading_id,
        "chat_id": chat,
        "message_id": message_id,
    }
    if payload_extra:
        payload.update(payload_extra)
    return insert_session(
        tid,
        "reading",
        day or date(2026, 8, 6),
        payload=payload,
        completed=False,
    )


def _seed_interest(tid: int, topic: str, track: str, weight: float = 1.0) -> None:
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO interests (user_id, topic, track, weight)
                VALUES (%s, %s, %s, %s)
                """,
                (tid, topic, track, weight),
            )


def _callback_update(
    user_id: int,
    data: str,
    *,
    message_id: int = 500,
    update_id: int = 1,
) -> Update:
    user = User(id=user_id, first_name="A", is_bot=False)
    chat = Chat(id=user_id, type="private")
    msg = Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=user,
        text="reading",
    )
    cq = CallbackQuery(
        id="cq1",
        from_user=user,
        chat_instance="x",
        data=data,
        message=msg,
    )
    return Update(update_id=update_id, callback_query=cq)


def _context_with_bot(
    *,
    edit_side_effect: Exception | None = None,
    chat_id: int = 1,
    send_message_id: int = 999,
) -> MagicMock:
    ctx = MagicMock()
    edit = AsyncMock()
    if edit_side_effect is not None:
        edit.side_effect = edit_side_effect
    ctx.bot.edit_message_text = edit
    msg = MagicMock()
    msg.chat_id = chat_id
    msg.message_id = send_message_id
    ctx.bot.send_message = AsyncMock(return_value=msg)
    return ctx


# --- Grading ------------------------------------------------------------------


# --- Parse / legacy -----------------------------------------------------------


def test_parse_stored_questions_accepts_mcq() -> None:
    parsed = parse_stored_questions(_mcq_list())
    assert parsed is not None
    assert len(parsed) == 5
    assert parsed[0].answer_index == 0


def test_parse_stored_questions_rejects_legacy() -> None:
    legacy = [
        {
            "question": "According to the text?",
            "answer": "You often have a longer commute.",
            "distractors": ["a", "b", "c"],
        }
        for _ in range(5)
    ]
    assert parse_stored_questions(legacy) is None


# --- Button labels ------------------------------------------------------------


# --- Weight -------------------------------------------------------------------


def test_rating_map_and_clamps(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _seed_interest(user_id, "apartments", "life", weight=1.0)

    assert adjust_weight_for_rating(user_id, "apartments", 5) == pytest.approx(1.30)
    assert adjust_weight_for_rating(user_id, "apartments", 1) == pytest.approx(1.00)
    assert adjust_weight_for_rating(user_id, "apartments", 2) == pytest.approx(0.85)
    assert adjust_weight_for_rating(user_id, "apartments", 3) == pytest.approx(0.85)
    assert adjust_weight_for_rating(user_id, "apartments", 4) == pytest.approx(1.00)

    with connection() as conn:
        conn.execute(
            "UPDATE interests SET weight = 0.30 WHERE user_id = %s",
            (user_id,),
        )
    assert adjust_weight_for_rating(user_id, "apartments", 1) == pytest.approx(0.25)

    with connection() as conn:
        conn.execute(
            "UPDATE interests SET weight = 2.90 WHERE user_id = %s",
            (user_id,),
        )
    assert adjust_weight_for_rating(user_id, "apartments", 5) == pytest.approx(3.00)


def test_missing_topic_does_not_raise(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    with caplog.at_level(logging.WARNING):
        assert adjust_weight_for_rating(user_id, "nope", 1) is None
    assert any("missing topic" in r.message for r in caplog.records)


# --- Session resolve by message_id --------------------------------------------


def test_resolve_by_message_id_not_orphan(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    orphan_rid = _insert_reading(user_id, topic="orphan-topic")
    insert_session(
        user_id,
        "reading",
        date(2026, 8, 6),
        payload={"reading_id": orphan_rid},
        completed=False,
    )
    good_rid = _insert_reading(user_id, topic="apartments")
    _insert_reading_session(user_id, good_rid, message_id=777)

    found = get_reading_session_by_message(user_id, user_id, 777)
    assert found is not None
    assert found.payload is not None
    assert found.payload["reading_id"] == good_rid
    assert get_reading_session_by_message(user_id, tid, 1) is None


# --- Handler flows ------------------------------------------------------------


