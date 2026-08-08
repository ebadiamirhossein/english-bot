"""S9c: reading comprehension grading, resume, rating→weight, legacy skip."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from psycopg.types.json import Jsonb
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.error import BadRequest

from app.db import close_pool, connection
from app.handlers.reading import (
    _MAX_BUTTON_LABEL_CHARS,
    _edit_or_resend,
    all_s9c_button_labels,
    grade_mcq,
    on_reading_callback,
    option_keyboard,
    questions_keyboard,
    rating_keyboard,
    score_from_answers,
)
from app.services.interests import adjust_weight_for_rating, list_interests
from app.services.reading import ReadingMcq, parse_stored_questions
from app.services.sessions import (
    get_reading_session_by_message,
    insert_session,
)
from app.services.users import save_onboarding

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


def _onboard(tid: int) -> None:
    save_onboarding(
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


def test_grade_right_and_wrong_index() -> None:
    assert grade_mcq(2, 2) is True
    assert grade_mcq(0, 2) is False


def test_score_arithmetic_across_five() -> None:
    questions = [
        ReadingMcq(q="q", options=["a", "b", "c", "d"], answer_index=0, why="w")
        for _ in range(5)
    ]
    answers = [0, 0, 1, 0, 2]
    assert score_from_answers(answers, questions) == pytest.approx(0.6)


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


def test_all_s9c_button_labels_within_20() -> None:
    for label in all_s9c_button_labels():
        assert len(label) <= _MAX_BUTTON_LABEL_CHARS, label
    for markup in (questions_keyboard(), option_keyboard(0), rating_keyboard()):
        for row in markup.inline_keyboard:
            for btn in row:
                assert len(btn.text) <= _MAX_BUTTON_LABEL_CHARS


# --- Weight -------------------------------------------------------------------


def test_rating_map_and_clamps(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_interest(tid, "apartments", "life", weight=1.0)

    assert adjust_weight_for_rating(tid, "apartments", 5) == pytest.approx(1.30)
    assert adjust_weight_for_rating(tid, "apartments", 1) == pytest.approx(1.00)
    assert adjust_weight_for_rating(tid, "apartments", 2) == pytest.approx(0.85)
    assert adjust_weight_for_rating(tid, "apartments", 3) == pytest.approx(0.85)
    assert adjust_weight_for_rating(tid, "apartments", 4) == pytest.approx(1.00)

    with connection() as conn:
        conn.execute(
            "UPDATE interests SET weight = 0.30 WHERE user_id = %s",
            (tid,),
        )
    assert adjust_weight_for_rating(tid, "apartments", 1) == pytest.approx(0.25)

    with connection() as conn:
        conn.execute(
            "UPDATE interests SET weight = 2.90 WHERE user_id = %s",
            (tid,),
        )
    assert adjust_weight_for_rating(tid, "apartments", 5) == pytest.approx(3.00)


def test_missing_topic_does_not_raise(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    with caplog.at_level(logging.WARNING):
        assert adjust_weight_for_rating(tid, "nope", 1) is None
    assert any("missing topic" in r.message for r in caplog.records)


# --- Session resolve by message_id --------------------------------------------


def test_resolve_by_message_id_not_orphan(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    orphan_rid = _insert_reading(tid, topic="orphan-topic")
    insert_session(
        tid,
        "reading",
        date(2026, 8, 6),
        payload={"reading_id": orphan_rid},
        completed=False,
    )
    good_rid = _insert_reading(tid, topic="apartments")
    _insert_reading_session(tid, good_rid, message_id=777)

    found = get_reading_session_by_message(tid, tid, 777)
    assert found is not None
    assert found.payload is not None
    assert found.payload["reading_id"] == good_rid
    assert get_reading_session_by_message(tid, tid, 1) is None


# --- Handler flows ------------------------------------------------------------


def test_progress_survives_restart_and_stale_is_noop(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_interest(tid, "apartments", "life", 1.0)
    rid = _insert_reading(tid)
    sid = _insert_reading_session(
        tid,
        rid,
        message_id=500,
        payload_extra={
            "phase": "questions",
            "assessed": True,
            "q_index": 2,
            "answers": [0, 0],
            "questions": _mcq_list(),
        },
    )
    ctx = _context_with_bot(chat_id=tid)

    async def _run() -> None:
        with patch.object(CallbackQuery, "answer", new=AsyncMock()):
            await on_reading_callback(
                _callback_update(tid, "read:a:1:0", message_id=500), ctx
            )
            with connection() as conn:
                row = conn.execute(
                    "SELECT payload FROM sessions WHERE id = %s", (sid,)
                ).fetchone()
            assert row["payload"]["q_index"] == 2
            assert row["payload"]["answers"] == [0, 0]
            assert ctx.bot.edit_message_text.await_count == 0

            await on_reading_callback(
                _callback_update(tid, "read:a:2:0", message_id=500), ctx
            )
            with connection() as conn:
                row = conn.execute(
                    "SELECT payload FROM sessions WHERE id = %s", (sid,)
                ).fetchone()
            assert row["payload"]["q_index"] == 3
            assert row["payload"]["answers"] == [0, 0, 0]
            assert ctx.bot.edit_message_text.await_count == 1

    asyncio.run(_run())


def test_legacy_skip_to_rating_score_null(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_interest(tid, "apartments", "life", 1.0)
    legacy = [
        {
            "question": "Q?",
            "answer": "A",
            "distractors": ["x", "y", "z"],
        }
        for _ in range(5)
    ]
    rid = _insert_reading(tid, questions=legacy)
    sid = _insert_reading_session(tid, rid, message_id=500)
    ctx = _context_with_bot(chat_id=tid)

    async def _run() -> None:
        with patch.object(CallbackQuery, "answer", new=AsyncMock()):
            with caplog.at_level(logging.WARNING):
                await on_reading_callback(
                    _callback_update(tid, "read:start", message_id=500), ctx
                )
            assert any("not MCQ" in r.message for r in caplog.records)
            with connection() as conn:
                sess = conn.execute(
                    "SELECT payload FROM sessions WHERE id = %s", (sid,)
                ).fetchone()
                assert sess["payload"]["phase"] == "rating"
                assert sess["payload"]["assessed"] is False

            await on_reading_callback(
                _callback_update(tid, "read:r:4", message_id=500), ctx
            )
            with connection() as conn:
                reading = conn.execute(
                    "SELECT completed, score, rating FROM readings WHERE id = %s",
                    (rid,),
                ).fetchone()
                sess = conn.execute(
                    "SELECT completed, score FROM sessions WHERE id = %s", (sid,)
                ).fetchone()
            assert reading["completed"] is True
            assert reading["rating"] == 4
            assert reading["score"] is None
            assert sess["completed"] is True
            assert sess["score"] is None
            assert list_interests(tid)[0].weight == pytest.approx(1.15)

    asyncio.run(_run())


def test_full_qa_then_rating_writes_score(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _seed_interest(tid, "apartments", "life", 1.0)
    rid = _insert_reading(tid)
    sid = _insert_reading_session(tid, rid, message_id=500)
    ctx = _context_with_bot(chat_id=tid)

    async def _run() -> None:
        with patch.object(CallbackQuery, "answer", new=AsyncMock()):
            await on_reading_callback(
                _callback_update(tid, "read:start", message_id=500), ctx
            )
            for i in range(5):
                await on_reading_callback(
                    _callback_update(
                        tid, f"read:a:{i}:0", message_id=500, update_id=i + 2
                    ),
                    ctx,
                )
            with connection() as conn:
                sess = conn.execute(
                    "SELECT payload FROM sessions WHERE id = %s", (sid,)
                ).fetchone()
            assert sess["payload"]["phase"] == "rating"
            assert sess["payload"]["score"] == pytest.approx(1.0)

            await on_reading_callback(
                _callback_update(tid, "read:r:5", message_id=500, update_id=20),
                ctx,
            )
            with connection() as conn:
                reading = conn.execute(
                    "SELECT completed, score, rating FROM readings WHERE id = %s",
                    (rid,),
                ).fetchone()
                sess = conn.execute(
                    "SELECT completed, score FROM sessions WHERE id = %s", (sid,)
                ).fetchone()
            assert reading["completed"] is True
            assert reading["rating"] == 5
            assert reading["score"] == pytest.approx(1.0)
            assert sess["score"] == pytest.approx(1.0)
            assert list_interests(tid)[0].weight == pytest.approx(1.30)

    asyncio.run(_run())


def test_edit_failure_resends_and_updates_message_id(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    rid = _insert_reading(tid)
    sid = _insert_reading_session(tid, rid, message_id=500)
    payload = {
        "reading_id": rid,
        "chat_id": tid,
        "message_id": 500,
        "phase": "questions",
    }
    ctx = _context_with_bot(
        edit_side_effect=BadRequest("Message to edit not found"),
        chat_id=tid,
        send_message_id=888,
    )

    async def _run() -> None:
        with caplog.at_level(logging.WARNING):
            new_payload = await _edit_or_resend(
                ctx,
                user_id=tid,
                reading_id=rid,
                session_id=sid,
                payload=payload,
                text="hello",
                reply_markup=None,
            )
        assert new_payload["message_id"] == 888
        assert ctx.bot.send_message.await_count == 1
        assert any("edit failed" in r.message for r in caplog.records)
        found = get_reading_session_by_message(tid, tid, 888)
        assert found is not None
        assert found.id == sid

    asyncio.run(_run())


def test_message_not_modified_swallowed(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    rid = _insert_reading(tid)
    sid = _insert_reading_session(tid, rid, message_id=500)
    payload = {
        "reading_id": rid,
        "chat_id": tid,
        "message_id": 500,
    }
    ctx = _context_with_bot(
        edit_side_effect=BadRequest("Message is not modified"),
        chat_id=tid,
    )

    async def _run() -> None:
        out = await _edit_or_resend(
            ctx,
            user_id=tid,
            reading_id=rid,
            session_id=sid,
            payload=payload,
            text="same",
            reply_markup=None,
        )
        assert out["message_id"] == 500
        assert ctx.bot.send_message.await_count == 0

    asyncio.run(_run())
