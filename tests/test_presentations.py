"""S25 — first-touch presentation; unpresented chunks never graded."""

from __future__ import annotations

import asyncio
import inspect
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import User

from apps.bot import texts
from core.db import close_pool, connection, migrate
from apps.bot.handlers import quiz as quiz_handler
from apps.bot.handlers.book_test import handle_test_command
from apps.bot.handlers.quiz import (
    on_present_ack_callback,
    on_present_orphan_callback,
    open_quiz_awaits_gap_answer,
    presentation_pending,
    s25_present_button_labels,
)
from core.services.anki import fetch_unexported_chunks
from core.services.chunks import (
    CHUNK_PRESENTED_AND_DUE_SQL,
    chunk_due_predicate_sites,
    count_due_chunks,
    due_chunks,
    insert_chunks,
    mark_presented,
    unpresented_chunks,
)
from core.services.errors import record_errors
from core.services.sessions import (
    get_open_quiz_session,
    insert_session,
    update_session_payload,
)
from core.services.shared_content import record_and_fanout_chunks
from core.services.stats import collect_stats
from core.services.users import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_520_000_000
FIXED_TODAY = date(2026, 8, 14)


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


def _onboard(tid: int, *, morning: str = "00:00", tz: str = "UTC") -> None:
    save_onboarding(
        tid,
        {
            "name": "S25 Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": morning,
            "evening_time": "21:00",
        },
    )
    with connection() as conn:
        conn.execute(
            "UPDATE users SET timezone = %s WHERE telegram_user_id = %s",
            (tz, tid),
        )


def _insert_chunk(
    tid: int,
    *,
    chunk: str,
    full_sentence: str | None = None,
    meaning: str = "m",
    source: str = "reading_1",
    next_review: date | None = None,
    presented: bool = True,
    created_at: datetime | None = None,
) -> int:
    sentence = full_sentence or f"They said {chunk} yesterday."
    presented_sql = "NOW()" if presented else "NULL"
    created = created_at or datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    with connection() as conn:
        with conn.transaction():
            row = conn.execute(
                f"""
                INSERT INTO chunks (
                    user_id, chunk, full_sentence, meaning, source, track,
                    exported_to_anki, next_review, presented_at, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, 'life', FALSE, %s, {presented_sql}, %s
                )
                RETURNING id
                """,
                (tid, chunk, sentence, meaning, source, next_review, created),
            ).fetchone()
    assert row is not None
    return int(row["id"])


def _insert_due_error(tid: int) -> None:
    record_errors(
        tid,
        "quiz",
        [
            {
                "you_said": "bad",
                "correct_form": "good",
                "error_type": "quantifier_modifier",
                "explanation": "x",
            }
        ],
    )
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                UPDATE errors
                   SET next_review = %s, resolved = FALSE
                 WHERE user_id = %s
                """,
                (FIXED_TODAY, tid),
            )


def _chunk_row(cid: int) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT presented_at, next_review, times_right, times_wrong,
                   streak_right, source
              FROM chunks WHERE id = %s
            """,
            (cid,),
        ).fetchone()
    assert row is not None
    return dict(row)


def _error_count(tid: int) -> int:
    with connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*)::int AS n FROM errors WHERE user_id = %s",
            (tid,),
        ).fetchone()
    assert row is not None
    return int(row["n"])


def _callback_update(user_id: int, data: str, *, message_id: int = 99) -> MagicMock:
    msg = MagicMock()
    msg.message_id = message_id
    msg.chat_id = user_id
    msg.reply_text = AsyncMock()
    msg.edit_text = AsyncMock()
    query = MagicMock()
    query.id = "1"
    query.data = data
    query.from_user = MagicMock(id=user_id)
    query.message = msg
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update = MagicMock()
    update.callback_query = query
    update.effective_user = MagicMock(id=user_id)
    update.effective_message = msg
    update.message = None
    return update


def test_migration_007_presented_at_column() -> None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'chunks' AND column_name = 'presented_at'
            """
        ).fetchone()
    assert row is not None
    assert migrate() == []


def test_chunk_due_predicate_sites_use_shared_sql() -> None:
    """Drift guard: due_chunks, count_due_chunks, /stats share one predicate."""
    sites = chunk_due_predicate_sites()
    assert set(sites) == {"due_chunks", "count_due_chunks", "_chunk_counts"}
    for name, fn in sites.items():
        src = inspect.getsource(fn)
        assert "CHUNK_PRESENTED_AND_DUE_SQL" in src, name
    assert "presented_at IS NOT NULL" in CHUNK_PRESENTED_AND_DUE_SQL


def test_s25_button_labels_max_20() -> None:
    for label in s25_present_button_labels():
        assert len(label) <= 20, label


def test_due_chunks_excludes_unpresented(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    hidden = _insert_chunk(tid, chunk="delulu", presented=False, source="slang")
    shown = _insert_chunk(tid, chunk="cut costs", presented=True)
    selected = due_chunks(tid, 10, now=FIXED_TODAY)
    ids = [c.id for c in selected]
    assert shown in ids
    assert hidden not in ids
    assert count_due_chunks(tid, now=FIXED_TODAY) == 1


def test_due_chunks_includes_after_presented(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(
        tid,
        chunk="delulu",
        presented=False,
        source="slang",
        next_review=FIXED_TODAY,
    )
    assert due_chunks(tid, 5, now=FIXED_TODAY) == []
    mark_presented(cid, now=FIXED_TODAY)
    assert due_chunks(tid, 5, now=FIXED_TODAY) == []
    tomorrow = FIXED_TODAY + timedelta(days=1)
    selected = due_chunks(tid, 5, now=tomorrow)
    assert [c.id for c in selected] == [cid]


def test_unpresented_still_exports_to_anki(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(tid, chunk="delulu", presented=False, source="slang")
    with connection() as conn:
        rows = fetch_unexported_chunks(conn, tid)
    assert any(r.id == cid for r in rows)


def test_fanout_insert_leaves_presented_null(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    with patch(
        "core.services.shared_content.list_recipients", return_value=[tid]
    ):
        record_and_fanout_chunks(
            [
                {
                    "chunk": "delulu",
                    "full_sentence": "She is being delulu again.",
                    "meaning": "delusional",
                }
            ],
            created_by=tid,
            source="slang",
        )
    with connection() as conn:
        row = conn.execute(
            """
            SELECT presented_at, source FROM chunks
             WHERE user_id = %s AND chunk = 'delulu'
            """,
            (tid,),
        ).fetchone()
    assert row is not None
    assert row["source"] == "slang"
    assert row["presented_at"] is None


def test_user_sourced_insert_sets_presented(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    with connection() as conn:
        with conn.transaction():
            insert_chunks(
                conn,
                tid,
                source="capture",
                track="life",
                chunks=[
                    {
                        "chunk": "circle back",
                        "full_sentence": "Let's circle back on Friday.",
                        "meaning": "return to a topic",
                    }
                ],
            )
    with connection() as conn:
        row = conn.execute(
            """
            SELECT presented_at FROM chunks
             WHERE user_id = %s AND chunk = 'circle back'
            """,
            (tid,),
        ).fetchone()
    assert row is not None
    assert row["presented_at"] is not None


def test_migration_backfill_slang_null_nonsource_presented(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    slang_id = _insert_chunk(
        tid, chunk="rizz", source="slang", presented=False
    )
    capture_id = _insert_chunk(
        tid, chunk="cut costs", source="capture", presented=False
    )
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                UPDATE chunks
                   SET presented_at = created_at
                 WHERE user_id = %s
                   AND (source <> 'slang' OR source IS NULL)
                   AND presented_at IS NULL
                """,
                (tid,),
            )
    assert _chunk_row(slang_id)["presented_at"] is None
    assert _chunk_row(capture_id)["presented_at"] is not None


def test_unpresented_cap_two_oldest_first(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    t0 = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
    a = _insert_chunk(
        tid, chunk="alpha", presented=False, source="slang", created_at=t0
    )
    b = _insert_chunk(
        tid, chunk="bravo", presented=False, source="slang", created_at=t1
    )
    _insert_chunk(
        tid, chunk="charlie", presented=False, source="slang", created_at=t2
    )
    rows = unpresented_chunks(tid, limit=2)
    assert [c.id for c in rows] == [a, b]


def test_presentation_fifo_across_days(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    t0 = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
    a = _insert_chunk(
        tid, chunk="alpha", presented=False, source="slang", created_at=t0
    )
    b = _insert_chunk(
        tid, chunk="bravo", presented=False, source="slang", created_at=t1
    )
    c = _insert_chunk(
        tid, chunk="charlie", presented=False, source="slang", created_at=t2
    )
    mark_presented(a, now=FIXED_TODAY)
    mark_presented(b, now=FIXED_TODAY)
    rows = unpresented_chunks(tid, limit=2)
    assert [r.id for r in rows] == [c]


def test_mark_presented_leaves_ladder_unchanged(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(tid, chunk="delulu", presented=False, source="slang")
    mark_presented(cid, now=FIXED_TODAY)
    after = _chunk_row(cid)
    assert after["presented_at"] is not None
    assert after["next_review"] == FIXED_TODAY + timedelta(days=1)
    assert after["times_right"] == 0
    assert after["times_wrong"] == 0
    assert after["streak_right"] == 0


def test_mark_presented_idempotent(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(tid, chunk="delulu", presented=False, source="slang")
    assert mark_presented(cid, now=FIXED_TODAY) is True
    first = _chunk_row(cid)
    assert mark_presented(cid, now=FIXED_TODAY + timedelta(days=3)) is False
    second = _chunk_row(cid)
    assert second["next_review"] == first["next_review"]


def test_presentations_only_no_quiz_sent(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_chunk(tid, chunk="delulu", presented=False, source="slang")
    app = MagicMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
    action = asyncio.run(quiz_handler.deliver_morning(app, tid, now=now))
    assert action == "free_practice"
    assert unpresented_chunks(tid, limit=1)
    assert _chunk_row(unpresented_chunks(tid, limit=1)[0].id)["presented_at"] is None


def test_morning_quiz_attaches_presentations(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_due_error(tid)
    cid = _insert_chunk(tid, chunk="delulu", presented=False, source="slang")

    def fake_build(user_id, errors, *, chunks=None, book_items=None, chat_fn=None):
        return (
            [
                {
                    "format": "choice",
                    "prompt": "Q0",
                    "accept": ["a"],
                    "answer": "a",
                    "options": ["a", "b", "c", "d"],
                    "error_type": "quantifier_modifier",
                    "explanation": "x",
                    "error_id": errors[0].id,
                }
            ],
            "scenario",
        )

    app = MagicMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
    with patch.object(quiz_handler, "_build_quiz_questions", side_effect=fake_build):
        action = asyncio.run(quiz_handler.deliver_morning(app, tid, now=now))
    assert action == "quiz"
    session = get_open_quiz_session(tid)
    assert session is not None
    payload = session.payload or {}
    assert len(payload.get("presentations") or []) == 1
    assert int(payload["presentations"][0]["chunk_id"]) == cid
    send_kwargs = app.bot.send_message.await_args.kwargs
    assert "New phrase" in send_kwargs["text"]
    assert _chunk_row(cid)["presented_at"] is None


def test_rescue_skips_presentations(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_due_error(tid)
    _insert_chunk(tid, chunk="delulu", presented=False, source="slang")
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                UPDATE streaks
                   SET rescue_mode_until = %s
                 WHERE user_id = %s
                """,
                (FIXED_TODAY + timedelta(days=3), tid),
            )

    def fake_build(user_id, errors, *, chunks=None, book_items=None, chat_fn=None):
        n = max(1, len(errors))
        return (
            [
                {
                    "format": "choice",
                    "prompt": f"Q{i}",
                    "accept": ["a"],
                    "answer": "a",
                    "options": ["a", "b", "c", "d"],
                    "error_type": "quantifier_modifier",
                    "explanation": "x",
                    "error_id": errors[0].id if errors else None,
                }
                for i in range(n)
            ],
            "scenario",
        )

    app = MagicMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
    with patch.object(quiz_handler, "_build_quiz_questions", side_effect=fake_build):
        action = asyncio.run(quiz_handler.deliver_morning(app, tid, now=now))
    assert action == "quiz"
    session = get_open_quiz_session(tid)
    assert session is not None
    assert session.payload.get("presentations") == []


def test_weekly_skips_presentations(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_due_error(tid)
    _insert_chunk(tid, chunk="delulu", presented=False, source="slang")

    def fake_build(user_id, errors, *, chunks=None, book_items=None, chat_fn=None):
        assert list(chunks or []) == []
        return (
            [
                {
                    "format": "choice",
                    "prompt": "Q0",
                    "accept": ["a"],
                    "answer": "a",
                    "options": ["a", "b", "c", "d"],
                    "error_type": "quantifier_modifier",
                    "explanation": "x",
                    "error_id": errors[0].id,
                }
            ],
            "scenario",
        )

    app = MagicMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)
    with patch.object(quiz_handler, "_build_quiz_questions", side_effect=fake_build):
        action = asyncio.run(quiz_handler.deliver_morning(app, tid, now=now))
    assert action == "quiz"
    session = get_open_quiz_session(tid)
    assert session is not None
    assert session.payload.get("weekly_test") is True
    assert session.payload.get("presentations") == []


def test_unpresented_not_in_morning_graded_chunks(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_due_error(tid)
    hidden = _insert_chunk(
        tid,
        chunk="delulu",
        presented=False,
        source="slang",
        next_review=FIXED_TODAY,
    )
    captured: dict[str, Any] = {}

    def fake_build(user_id, errors, *, chunks=None, book_items=None, chat_fn=None):
        captured["chunks"] = list(chunks or [])
        return (
            [
                {
                    "format": "choice",
                    "prompt": "Q0",
                    "accept": ["a"],
                    "answer": "a",
                    "options": ["a", "b", "c", "d"],
                    "error_type": "quantifier_modifier",
                    "explanation": "x",
                    "error_id": errors[0].id,
                }
            ],
            "scenario",
        )

    app = MagicMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
    with patch.object(quiz_handler, "_build_quiz_questions", side_effect=fake_build):
        asyncio.run(quiz_handler.deliver_morning(app, tid, now=now))
    assert all(c.id != hidden for c in captured["chunks"])


def test_book_test_has_no_presentations(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_chunk(tid, chunk="delulu", presented=False, source="slang")
    update = MagicMock()
    update.effective_user = User(id=tid, first_name="A", is_bot=False)
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["unit", "12"]
    asyncio.run(handle_test_command(update, context))
    session = get_open_quiz_session(tid)
    if session is not None and session.payload:
        assert not session.payload.get("presentations")


def _open_quiz_with_presentations(
    tid: int, chunk_ids: list[int], *, message_id: int = 42
) -> int:
    presentations = [
        {
            "chunk_id": cid,
            "chunk": f"c{cid}",
            "full_sentence": f"Sentence {cid}.",
            "meaning": "m",
        }
        for cid in chunk_ids
    ]
    payload = {
        "index": 0,
        "correct_count": 0,
        "answered": 0,
        "calib_correct": 0,
        "calib_answered": 0,
        "questions": [
            {
                "format": "choice",
                "prompt": "Q0",
                "accept": ["a"],
                "answer": "a",
                "options": ["a", "b"],
                "error_type": "quantifier_modifier",
                "explanation": "x",
            }
        ],
        "scenario": "s",
        "chat_id": tid,
        "message_id": message_id,
        "presentations": presentations,
        "present_index": 0,
    }
    sid = insert_session(
        tid, "quiz", FIXED_TODAY, payload=payload, completed=False
    )
    payload["session_id"] = sid
    update_session_payload(sid, payload)
    return sid


def test_present_ack_sets_presented_and_advances(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(tid, chunk="delulu", presented=False, source="slang")
    _open_quiz_with_presentations(tid, [cid])
    errors_before = _error_count(tid)

    context = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    update = _callback_update(tid, f"present:ack:{cid}")
    with patch(
        "apps.bot.handlers.quiz.local_today", return_value=FIXED_TODAY
    ):
        asyncio.run(on_present_ack_callback(update, context))

    row = _chunk_row(cid)
    assert row["presented_at"] is not None
    assert row["next_review"] == FIXED_TODAY + timedelta(days=1)
    assert row["streak_right"] == 0
    assert _error_count(tid) == errors_before

    session = get_open_quiz_session(tid)
    assert session is not None
    assert int(session.payload["present_index"]) == 1
    assert not presentation_pending(session.payload)


def test_present_ack_repeated_is_noop(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(tid, chunk="delulu", presented=False, source="slang")
    _open_quiz_with_presentations(tid, [cid])
    context = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    update = _callback_update(tid, f"present:ack:{cid}")
    with patch(
        "apps.bot.handlers.quiz.local_today", return_value=FIXED_TODAY
    ):
        asyncio.run(on_present_ack_callback(update, context))
        edits_after_first = context.bot.edit_message_text.await_count
        asyncio.run(on_present_ack_callback(update, context))
    assert context.bot.edit_message_text.await_count == edits_after_first
    session = get_open_quiz_session(tid)
    assert session is not None
    assert int(session.payload["present_index"]) == 1


def test_present_ack_out_of_order_is_noop(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    a = _insert_chunk(
        tid,
        chunk="alpha",
        presented=False,
        source="slang",
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    b = _insert_chunk(
        tid,
        chunk="bravo",
        presented=False,
        source="slang",
        created_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )
    _open_quiz_with_presentations(tid, [a, b])
    context = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    with patch(
        "apps.bot.handlers.quiz.local_today", return_value=FIXED_TODAY
    ):
        asyncio.run(
            on_present_ack_callback(
                _callback_update(tid, f"present:ack:{b}"), context
            )
        )
    assert context.bot.edit_message_text.await_count == 0
    assert _chunk_row(a)["presented_at"] is None
    assert _chunk_row(b)["presented_at"] is None
    session = get_open_quiz_session(tid)
    assert session is not None
    assert int(session.payload["present_index"]) == 0


def test_present_ack_does_not_affect_score_or_early_limit(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(tid, chunk="delulu", presented=False, source="slang")
    sid = _open_quiz_with_presentations(tid, [cid])
    session = get_open_quiz_session(tid)
    assert session is not None
    payload = dict(session.payload)
    payload["early_limit"] = 2
    update_session_payload(sid, payload)

    context = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    with patch(
        "apps.bot.handlers.quiz.local_today", return_value=FIXED_TODAY
    ):
        asyncio.run(
            on_present_ack_callback(
                _callback_update(tid, f"present:ack:{cid}"), context
            )
        )
    session = get_open_quiz_session(tid)
    assert session is not None
    p = session.payload
    assert int(p.get("answered", 0)) == 0
    assert int(p.get("correct_count", 0)) == 0
    assert int(p.get("calib_answered", 0)) == 0
    assert int(p.get("early_limit")) == 2


def test_present_orphan_warm_line(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    update = _callback_update(tid, "present:ack:999")
    context = MagicMock()
    asyncio.run(on_present_orphan_callback(update, context))
    update.callback_query.edit_message_text.assert_awaited()
    assert texts.PRESENT_STALE in str(
        update.callback_query.edit_message_text.await_args
    )


def test_open_quiz_awaits_gap_false_during_presentation(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(tid, chunk="delulu", presented=False, source="slang")
    _open_quiz_with_presentations(tid, [cid])
    session = get_open_quiz_session(tid)
    assert session is not None
    payload = dict(session.payload)
    payload["questions"][0]["format"] = "gap"
    update_session_payload(session.id, payload)
    assert open_quiz_awaits_gap_answer(tid) is False


def test_stats_due_matches_count_due_chunks(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_chunk(tid, chunk="shown", presented=True, next_review=None)
    _insert_chunk(
        tid, chunk="hidden", presented=False, source="slang", next_review=None
    )
    now = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
    stats = collect_stats(tid, now=now)
    assert stats is not None
    assert stats.chunk_due == count_due_chunks(tid, now=FIXED_TODAY) == 1
