"""S7a — chunk spaced review inside the daily quiz."""

from __future__ import annotations

import asyncio
import inspect
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import texts
from app.db import close_pool, connection, migrate
from app.handlers import quiz as quiz_handler
from app.handlers.quiz import (
    assign_formats,
    build_chunk_question,
    grade_chunk_answer,
    plan_formats,
    typed_gap_count,
)
from app.services import chunks as chunks_mod
from app.services.books import MergedUnit, upsert_unit
from app.services.calibration import _session_counts, compute_accuracy_window
from app.services.chunks import (
    count_due_chunks,
    due_chunks,
    insert_chunks,
    mark_chunk_result,
)
from app.services.errors import SPACING_DAYS, due_errors, record_errors, spacing_step
from app.services.sessions import complete_session, insert_session
from app.services.stats import collect_stats, format_stats_message
from app.services.users import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_490_000_000
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
FIXED_TODAY = date(2026, 8, 10)


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
            "name": "S7a Test",
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
    next_review: date | None | object = ...,
    exported: bool = False,
    streak_right: int = 0,
) -> int:
    sentence = (
        full_sentence
        if full_sentence is not None
        else f"They said {chunk} yesterday."
    )
    with connection() as conn:
        with conn.transaction():
            if next_review is ...:
                row = conn.execute(
                    """
                    INSERT INTO chunks (
                        user_id, chunk, full_sentence, meaning, source, track,
                        exported_to_anki, next_review, streak_right
                    ) VALUES (
                        %s, %s, %s, %s, %s, 'life', %s, NULL, %s
                    )
                    RETURNING id
                    """,
                    (tid, chunk, sentence, meaning, source, exported, streak_right),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    INSERT INTO chunks (
                        user_id, chunk, full_sentence, meaning, source, track,
                        exported_to_anki, next_review, streak_right
                    ) VALUES (
                        %s, %s, %s, %s, %s, 'life', %s, %s, %s
                    )
                    RETURNING id
                    """,
                    (
                        tid,
                        chunk,
                        sentence,
                        meaning,
                        source,
                        exported,
                        next_review,
                        streak_right,
                    ),
                ).fetchone()
    assert row is not None
    return int(row["id"])


def _insert_due_errors(tid: int, n: int) -> list[int]:
    for i in range(n):
        record_errors(
            tid,
            "quiz",
            [
                {
                    "you_said": f"bad {i}",
                    "correct_form": f"good {i}",
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
            rows = conn.execute(
                "SELECT id FROM errors WHERE user_id = %s ORDER BY id",
                (tid,),
            ).fetchall()
    return [int(r["id"]) for r in rows]


def _insert_unit(tid: int, *, unit_number: str, items: list[str]) -> None:
    upsert_unit(
        tid,
        "murphy",
        MergedUnit(
            unit_number=unit_number,
            unit_title=f"Unit {unit_number}",
            target_items=items,
        ),
        studied_at=FIXED_TODAY,
    )


def test_migration_004_idempotent_sql() -> None:
    sql = (MIGRATIONS / "004_chunk_review.sql").read_text(encoding="utf-8")
    with connection() as conn:
        with conn.transaction():
            conn.execute(sql)
            conn.execute(sql)
        cols = {
            r["column_name"]
            for r in conn.execute(
                """
                SELECT column_name FROM information_schema.columns
                 WHERE table_name = 'chunks'
                   AND column_name IN (
                     'next_review', 'times_right', 'times_wrong', 'streak_right'
                   )
                """
            ).fetchall()
        }
    assert cols == {
        "next_review",
        "times_right",
        "times_wrong",
        "streak_right",
    }
    assert migrate() == []


def test_single_spacing_implementation() -> None:
    errors_src = inspect.getsource(chunks_mod)
    assert "SPACING_DAYS" not in errors_src
    assert "spacing_step" in errors_src
    root = Path(__file__).resolve().parent.parent / "app"
    hits = 0
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"^SPACING_DAYS\b", text, re.M):
            hits += 1
            assert path.name == "errors.py"
    assert hits == 1


def test_null_next_review_is_due(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(tid, chunk="cut costs")
    selected = due_chunks(tid, 5, now=FIXED_TODAY)
    assert [c.id for c in selected] == [cid]


def test_due_chunks_order_nulls_first(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    older = _insert_chunk(
        tid, chunk="by Friday", next_review=FIXED_TODAY - timedelta(days=2)
    )
    never = _insert_chunk(tid, chunk="cut costs")
    newer = _insert_chunk(tid, chunk="run the numbers", next_review=FIXED_TODAY)
    future = _insert_chunk(
        tid,
        chunk="circle back on this",
        next_review=FIXED_TODAY + timedelta(days=3),
    )
    selected = due_chunks(tid, 10, now=FIXED_TODAY)
    ids = [c.id for c in selected]
    assert never in ids
    assert older in ids and newer in ids
    assert future not in ids
    assert ids.index(never) < ids.index(older)
    assert ids.index(older) < ids.index(newer)


def test_skip_ungapable_pulls_replacement(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    bad = _insert_chunk(
        tid,
        chunk="missing phrase",
        full_sentence="This sentence has no match.",
    )
    good = _insert_chunk(tid, chunk="cut costs")
    selected = due_chunks(tid, 1, now=FIXED_TODAY)
    assert [c.id for c in selected] == [good]
    assert bad not in {c.id for c in selected}


def test_exported_chunk_still_due(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(tid, chunk="cut costs", exported=True)
    selected = due_chunks(tid, 5, now=FIXED_TODAY)
    assert [c.id for c in selected] == [cid]
    with connection() as conn:
        row = conn.execute(
            "SELECT exported_to_anki FROM chunks WHERE id = %s", (cid,)
        ).fetchone()
    assert row["exported_to_anki"] is True


def test_selection_cap_two_errors_three_chunks(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_due_errors(tid, 2)
    for phrase in ("cut costs", "by Friday", "run the numbers"):
        _insert_chunk(tid, chunk=phrase)
    _insert_unit(
        tid, unit_number="1", items=["present continuous", "stative verbs"]
    )

    captured: dict[str, Any] = {}

    def fake_build(user_id, errors, *, chunks=None, book_items=None, chat_fn=None):
        captured["errors"] = errors
        captured["chunks"] = list(chunks or [])
        captured["book_items"] = list(book_items or [])
        n = len(errors) + len(chunks or []) + len(book_items or [])
        qs = [
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
        ]
        return qs, "scenario"

    app = MagicMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    with patch.object(quiz_handler, "_build_quiz_questions", side_effect=fake_build):
        action = asyncio.run(quiz_handler.deliver_morning(app, tid, now=now))
    assert action == "quiz"
    assert len(captured["errors"]) == 2
    assert len(captured["chunks"]) == 2
    assert len(captured["book_items"]) == 1
    assert count_due_chunks(tid, now=FIXED_TODAY) == 3


def test_zero_errors_zero_chunks_book_topup(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    for i in range(5):
        _insert_unit(tid, unit_number=str(i + 1), items=[f"teachable {i}"])

    def fake_build(user_id, errors, *, chunks=None, book_items=None, chat_fn=None):
        assert errors == []
        assert list(chunks or []) == []
        assert len(book_items or []) == 5
        return (
            [
                {
                    "source": "book",
                    "format": "choice",
                    "prompt": f"Q{i}",
                    "accept": ["a"],
                    "answer": "a",
                    "options": ["a", "b", "c", "d"],
                    "error_type": "quantifier_modifier",
                    "explanation": "x",
                }
                for i in range(5)
            ],
            "scenario",
        )

    app = MagicMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    with patch.object(quiz_handler, "_build_quiz_questions", side_effect=fake_build):
        action = asyncio.run(quiz_handler.deliver_morning(app, tid, now=now))
    assert action == "quiz"


def test_typed_mix_holds_with_chunks() -> None:
    fmts = assign_formats(2, 2, 1)
    assert len(fmts) == 5
    assert fmts.count("gap") == 2
    assert fmts[2] == "gap" and fmts[3] == "gap"
    assert assign_formats(5, 0, 0) == plan_formats(5)
    assert typed_gap_count(5) == 2


def test_grade_chunk_answer_article_tolerant() -> None:
    expect = ["the background of daily life"]
    assert grade_chunk_answer("background of daily life", expect)
    assert grade_chunk_answer("the background of daily life", expect)
    assert grade_chunk_answer("a background of daily life", expect)
    assert not grade_chunk_answer("background of life", expect)
    assert not grade_chunk_answer("daily life background of", expect)


def test_mark_chunk_result_ladder(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(tid, chunk="cut costs", next_review=FIXED_TODAY)
    mark_chunk_result(cid, True, now=FIXED_TODAY)
    with connection() as conn:
        row = conn.execute(
            "SELECT streak_right, times_right, times_wrong, next_review "
            "FROM chunks WHERE id = %s",
            (cid,),
        ).fetchone()
    assert int(row["streak_right"]) == 1
    assert int(row["times_right"]) == 1
    assert row["next_review"] == FIXED_TODAY + timedelta(days=SPACING_DAYS[1])

    mark_chunk_result(cid, False, now=FIXED_TODAY)
    with connection() as conn:
        row = conn.execute(
            "SELECT streak_right, times_wrong, next_review FROM chunks WHERE id = %s",
            (cid,),
        ).fetchone()
    assert int(row["streak_right"]) == 0
    assert int(row["times_wrong"]) == 1
    assert row["next_review"] == FIXED_TODAY + timedelta(days=1)


def test_wrong_chunk_writes_zero_errors(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(tid, chunk="cut costs")
    before = due_errors(tid, limit=50)
    mark_chunk_result(cid, False, now=FIXED_TODAY)
    after = due_errors(tid, limit=50)
    assert len(after) == len(before)
    with connection() as conn:
        n = conn.execute(
            "SELECT COUNT(*)::int AS n FROM errors WHERE user_id = %s",
            (tid,),
        ).fetchone()["n"]
    assert int(n) == 0


def test_spacing_step_shared() -> None:
    step = spacing_step(correct=True, streak_right=0, today=FIXED_TODAY)
    assert step.next_review == FIXED_TODAY + timedelta(days=3)
    step2 = spacing_step(correct=False, streak_right=3, today=FIXED_TODAY)
    assert step2.streak_right == 0
    assert step2.next_review == FIXED_TODAY + timedelta(days=1)


def test_build_chunk_question_gap(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(
        tid,
        chunk="cut costs",
        full_sentence="We need to cut costs this quarter.",
    )
    chunk = due_chunks(tid, 1, now=FIXED_TODAY)[0]
    q = build_chunk_question(chunk)
    assert q["source"] == "chunk"
    assert q["chunk_id"] == cid
    assert q["format"] == "gap"
    assert "_____" in q["prompt"] or "___" in q["prompt"]
    assert q["answer"] == "cut costs"
    assert texts.QUIZ_CHUNK_LABEL == q["error_type_label"]
    assert len(texts.QUIZ_CHUNK_LABEL) <= 20


def test_insert_chunks_sets_tomorrow(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    with connection() as conn:
        with conn.transaction():
            insert_chunks(
                conn,
                tid,
                source="capture",
                track=None,
                chunks=[
                    {
                        "chunk": "cut costs",
                        "full_sentence": "We cut costs carefully.",
                        "meaning": "reduce spending",
                    }
                ],
            )
        row = conn.execute(
            """
            SELECT next_review, (CURRENT_DATE + 1) AS tomorrow
              FROM chunks WHERE user_id = %s
            """,
            (tid,),
        ).fetchone()
    assert row["next_review"] == row["tomorrow"]


def test_session_counts_prefers_calib() -> None:
    payload = {
        "correct_count": 1,
        "answered": 5,
        "calib_correct": 3,
        "calib_answered": 3,
    }
    c, n = _session_counts(payload, 0.2)
    assert (c, n) == (3, 3)


def test_chunk_misses_do_not_drop_calibration(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    for i in range(10):
        sid = insert_session(
            tid,
            "quiz",
            FIXED_TODAY - timedelta(days=i),
            payload={
                "correct_count": 5,
                "answered": 5,
                "calib_correct": 5,
                "calib_answered": 5,
                "questions": [],
            },
            completed=True,
        )
        complete_session(sid, 1.0)

    before = compute_accuracy_window(tid)
    assert before.answered >= 30
    assert before.accuracy is not None
    assert before.accuracy > 0.9

    sid = insert_session(
        tid,
        "quiz",
        FIXED_TODAY,
        payload={
            "correct_count": 3,
            "answered": 5,
            "calib_correct": 3,
            "calib_answered": 3,
            "questions": [
                {"source": "chunk"},
                {"source": "chunk"},
                {"error_id": 1},
                {"error_id": 2},
                {"error_id": 3},
            ],
        },
        completed=True,
    )
    complete_session(sid, 0.6)

    after = compute_accuracy_window(tid)
    assert after.accuracy is not None
    assert after.accuracy >= before.accuracy - 1e-9


def test_advance_chunk_skips_calib_and_errors(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(tid, chunk="cut costs", next_review=FIXED_TODAY)
    payload: dict[str, Any] = {
        "index": 0,
        "correct_count": 0,
        "answered": 0,
        "calib_correct": 0,
        "calib_answered": 0,
        "questions": [
            {
                "source": "chunk",
                "chunk_id": cid,
                "format": "gap",
                "prompt": "We need to _____ this quarter.",
                "answer": "cut costs",
                "accept": ["cut costs"],
                "explanation": "reduce",
                "error_type_label": "Phrase",
            }
        ],
        "chat_id": tid,
        "message_id": 1,
    }
    sid = insert_session(tid, "quiz", FIXED_TODAY, payload=payload, completed=False)
    payload["session_id"] = sid
    context = MagicMock()
    context.bot.edit_message_text = AsyncMock()

    asyncio.run(
        quiz_handler._advance_after_answer(
            context,
            tid,
            sid,
            payload,
            correct=False,
            question=payload["questions"][0],
            user_answer="wrong",
            now=FIXED_TODAY,
        )
    )
    assert payload["answered"] == 1
    assert payload["correct_count"] == 0
    assert payload["calib_answered"] == 0
    assert payload["calib_correct"] == 0
    with connection() as conn:
        n_err = conn.execute(
            "SELECT COUNT(*)::int AS n FROM errors WHERE user_id = %s",
            (tid,),
        ).fetchone()["n"]
        row = conn.execute(
            "SELECT times_wrong, next_review FROM chunks WHERE id = %s",
            (cid,),
        ).fetchone()
    assert int(n_err) == 0
    assert int(row["times_wrong"]) == 1
    assert row["next_review"] == FIXED_TODAY + timedelta(days=1)


def test_stats_shows_due_chunks(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_chunk(tid, chunk="cut costs")
    _insert_chunk(
        tid,
        chunk="by Friday",
        next_review=FIXED_TODAY + timedelta(days=10),
    )
    now = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    stats = collect_stats(tid, now=now)
    assert stats is not None
    assert stats.chunk_total == 2
    assert stats.chunk_due == 1
    body = format_stats_message(stats, include_sweep=False)
    assert "due: 1" in body
    assert "Chunks:" in body
