"""S25 — first-touch presentation; unpresented chunks never graded."""

from __future__ import annotations

import inspect
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.db import close_pool, connection, migrate
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
from core.services.sessions import insert_session, update_session_payload
from core.services.shared_content import record_and_fanout_chunks
from core.services.stats import collect_stats
from core.services.identity import save_onboarding
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


def _onboard(tid: int, *, morning: str = "00:00", tz: str = "UTC") -> int:
    user_id = save_onboarding(
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
    return user_id


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


def test_due_chunks_excludes_unpresented(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    hidden = _insert_chunk(user_id, chunk="delulu", presented=False, source="slang")
    shown = _insert_chunk(user_id, chunk="cut costs", presented=True)
    selected = due_chunks(user_id, 10, now=FIXED_TODAY)
    ids = [c.id for c in selected]
    assert shown in ids
    assert hidden not in ids
    assert count_due_chunks(user_id, now=FIXED_TODAY) == 1


def test_due_chunks_includes_after_presented(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    cid = _insert_chunk(
        user_id,
        chunk="delulu",
        presented=False,
        source="slang",
        next_review=FIXED_TODAY,
    )
    assert due_chunks(user_id, 5, now=FIXED_TODAY) == []
    mark_presented(cid, now=FIXED_TODAY)
    assert due_chunks(user_id, 5, now=FIXED_TODAY) == []
    tomorrow = FIXED_TODAY + timedelta(days=1)
    selected = due_chunks(user_id, 5, now=tomorrow)
    assert [c.id for c in selected] == [cid]


def test_unpresented_still_exports_to_anki(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    cid = _insert_chunk(user_id, chunk="delulu", presented=False, source="slang")
    with connection() as conn:
        rows = fetch_unexported_chunks(conn, user_id)
    assert any(r.id == cid for r in rows)


def test_fanout_insert_leaves_presented_null(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    with patch(
        "core.services.shared_content.list_recipients", return_value=[user_id]
    ):
        record_and_fanout_chunks(
            [
                {
                    "chunk": "delulu",
                    "full_sentence": "She is being delulu again.",
                    "meaning": "delusional",
                }
            ],
            created_by=user_id,
            source="slang",
        )
    with connection() as conn:
        row = conn.execute(
            """
            SELECT presented_at, source FROM chunks
             WHERE user_id = %s AND chunk = 'delulu'
            """,
            (user_id,),
        ).fetchone()
    assert row is not None
    assert row["source"] == "slang"
    assert row["presented_at"] is None


def test_user_sourced_insert_sets_presented(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    with connection() as conn:
        with conn.transaction():
            insert_chunks(
                conn,
                user_id,
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
            (user_id,),
        ).fetchone()
    assert row is not None
    assert row["presented_at"] is not None


def test_migration_backfill_slang_null_nonsource_presented(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    slang_id = _insert_chunk(
        user_id, chunk="rizz", source="slang", presented=False
    )
    capture_id = _insert_chunk(
        user_id, chunk="cut costs", source="capture", presented=False
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
                (user_id,),
            )
    assert _chunk_row(slang_id)["presented_at"] is None
    assert _chunk_row(capture_id)["presented_at"] is not None


def test_unpresented_cap_two_oldest_first(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    t0 = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
    a = _insert_chunk(
        user_id, chunk="alpha", presented=False, source="slang", created_at=t0
    )
    b = _insert_chunk(
        user_id, chunk="bravo", presented=False, source="slang", created_at=t1
    )
    _insert_chunk(
        user_id, chunk="charlie", presented=False, source="slang", created_at=t2
    )
    rows = unpresented_chunks(user_id, limit=2)
    assert [c.id for c in rows] == [a, b]


def test_presentation_fifo_across_days(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    t0 = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
    a = _insert_chunk(
        user_id, chunk="alpha", presented=False, source="slang", created_at=t0
    )
    b = _insert_chunk(
        user_id, chunk="bravo", presented=False, source="slang", created_at=t1
    )
    c = _insert_chunk(
        user_id, chunk="charlie", presented=False, source="slang", created_at=t2
    )
    mark_presented(a, now=FIXED_TODAY)
    mark_presented(b, now=FIXED_TODAY)
    rows = unpresented_chunks(user_id, limit=2)
    assert [r.id for r in rows] == [c]


def test_mark_presented_leaves_ladder_unchanged(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    cid = _insert_chunk(user_id, chunk="delulu", presented=False, source="slang")
    mark_presented(cid, now=FIXED_TODAY)
    after = _chunk_row(cid)
    assert after["presented_at"] is not None
    assert after["next_review"] == FIXED_TODAY + timedelta(days=1)
    assert after["times_right"] == 0
    assert after["times_wrong"] == 0
    assert after["streak_right"] == 0


def test_mark_presented_idempotent(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    cid = _insert_chunk(user_id, chunk="delulu", presented=False, source="slang")
    assert mark_presented(cid, now=FIXED_TODAY) is True
    first = _chunk_row(cid)
    assert mark_presented(cid, now=FIXED_TODAY + timedelta(days=3)) is False
    second = _chunk_row(cid)
    assert second["next_review"] == first["next_review"]


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


def test_stats_due_matches_count_due_chunks(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _insert_chunk(user_id, chunk="shown", presented=True, next_review=None)
    _insert_chunk(
        user_id, chunk="hidden", presented=False, source="slang", next_review=None
    )
    now = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
    stats = collect_stats(user_id, now=now)
    assert stats is not None
    assert stats.chunk_due == count_due_chunks(user_id, now=FIXED_TODAY) == 1
