"""S7a — chunk spaced review inside the daily quiz."""

from __future__ import annotations

import inspect
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.db import close_pool, connection, migrate
from core.services import chunks as chunks_mod
from core.services.books import MergedUnit, upsert_unit
from core.services.calibration import _session_counts, compute_accuracy_window
from core.services.chunks import due_chunks, insert_chunks, mark_chunk_result
from core.services.errors import SPACING_DAYS, due_errors, record_errors, spacing_step
from core.services.sessions import complete_session, insert_session
from core.services.stats import collect_stats, format_stats_message
from core.services.identity import save_onboarding
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


def _onboard(tid: int, *, morning: str = "00:00", tz: str = "UTC") -> int:
    user_id = save_onboarding(
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
    return user_id


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
    presented: bool = True,
) -> int:
    sentence = (
        full_sentence
        if full_sentence is not None
        else f"They said {chunk} yesterday."
    )
    presented_sql = "NOW()" if presented else "NULL"
    with connection() as conn:
        with conn.transaction():
            if next_review is ...:
                row = conn.execute(
                    f"""
                    INSERT INTO chunks (
                        user_id, chunk, full_sentence, meaning, source, track,
                        exported_to_anki, next_review, streak_right, presented_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, 'life', %s, NULL, %s, {presented_sql}
                    )
                    RETURNING id
                    """,
                    (tid, chunk, sentence, meaning, source, exported, streak_right),
                ).fetchone()
            else:
                row = conn.execute(
                    f"""
                    INSERT INTO chunks (
                        user_id, chunk, full_sentence, meaning, source, track,
                        exported_to_anki, next_review, streak_right, presented_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, 'life', %s, %s, %s, {presented_sql}
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
    with connection() as conn:
        presented_col = conn.execute(
            """
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'chunks' AND column_name = 'presented_at'
            """
        ).fetchone()
    assert presented_col is not None
    assert migrate() == []


def test_single_spacing_implementation() -> None:
    errors_src = inspect.getsource(chunks_mod)
    assert "SPACING_DAYS" not in errors_src
    assert "spacing_step" in errors_src
    repo = Path(__file__).resolve().parent.parent
    hits = 0
    for root in (repo / "packages" / "core", repo / "apps"):
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"^SPACING_DAYS\b", text, re.M):
                hits += 1
                assert path.name == "errors.py"
    assert hits == 1


def test_null_next_review_is_due(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    cid = _insert_chunk(user_id, chunk="cut costs")
    selected = due_chunks(user_id, 5, now=FIXED_TODAY)
    assert [c.id for c in selected] == [cid]


def test_due_chunks_order_nulls_first(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    older = _insert_chunk(
        user_id, chunk="by Friday", next_review=FIXED_TODAY - timedelta(days=2)
    )
    never = _insert_chunk(user_id, chunk="cut costs")
    newer = _insert_chunk(user_id, chunk="run the numbers", next_review=FIXED_TODAY)
    future = _insert_chunk(
        user_id,
        chunk="circle back on this",
        next_review=FIXED_TODAY + timedelta(days=3),
    )
    selected = due_chunks(user_id, 10, now=FIXED_TODAY)
    ids = [c.id for c in selected]
    assert never in ids
    assert older in ids and newer in ids
    assert future not in ids
    assert ids.index(never) < ids.index(older)
    assert ids.index(older) < ids.index(newer)


def test_due_chunks_same_date_prefers_newer_id(cleanup_user: int) -> None:
    """S15a: within the same next_review, id DESC (newer first)."""
    tid = cleanup_user
    user_id = _onboard(tid)
    older = _insert_chunk(
        user_id, chunk="by Friday", next_review=FIXED_TODAY
    )
    newer = _insert_chunk(
        user_id, chunk="run the numbers", next_review=FIXED_TODAY
    )
    selected = due_chunks(user_id, 10, now=FIXED_TODAY)
    ids = [c.id for c in selected]
    assert ids.index(newer) < ids.index(older)


def test_bulk_import_does_not_starve_later_capture(cleanup_user: int) -> None:
    """300 imported due tomorrow + one later capture → capture selected first."""
    tid = cleanup_user
    user_id = _onboard(tid)
    tomorrow = FIXED_TODAY + timedelta(days=1)
    for i in range(300):
        _insert_chunk(
            user_id,
            chunk=f"phrase number {i}",
            full_sentence=f"They said phrase number {i} clearly.",
            next_review=tomorrow,
        )
    capture = _insert_chunk(
        user_id,
        chunk="circle back",
        full_sentence="Let's circle back on that.",
        next_review=tomorrow,
        source="capture",
    )
    selected = due_chunks(user_id, 2, now=tomorrow)
    assert selected[0].id == capture
    assert selected[0].chunk == "circle back"


def test_skip_ungapable_pulls_replacement(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    bad = _insert_chunk(
        user_id,
        chunk="missing phrase",
        full_sentence="This sentence has no match.",
    )
    good = _insert_chunk(user_id, chunk="cut costs")
    selected = due_chunks(user_id, 1, now=FIXED_TODAY)
    assert [c.id for c in selected] == [good]
    assert bad not in {c.id for c in selected}


def test_exported_chunk_still_due(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    cid = _insert_chunk(user_id, chunk="cut costs", exported=True)
    selected = due_chunks(user_id, 5, now=FIXED_TODAY)
    assert [c.id for c in selected] == [cid]
    with connection() as conn:
        row = conn.execute(
            "SELECT exported_to_anki FROM chunks WHERE id = %s", (cid,)
        ).fetchone()
    assert row["exported_to_anki"] is True


def test_mark_chunk_result_ladder(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    cid = _insert_chunk(user_id, chunk="cut costs", next_review=FIXED_TODAY)
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
    user_id = _onboard(tid)
    cid = _insert_chunk(user_id, chunk="cut costs")
    before = due_errors(user_id, limit=50)
    mark_chunk_result(cid, False, now=FIXED_TODAY)
    after = due_errors(user_id, limit=50)
    assert len(after) == len(before)
    with connection() as conn:
        n = conn.execute(
            "SELECT COUNT(*)::int AS n FROM errors WHERE user_id = %s",
            (user_id,),
        ).fetchone()["n"]
    assert int(n) == 0


def test_spacing_step_shared() -> None:
    step = spacing_step(correct=True, streak_right=0, today=FIXED_TODAY)
    assert step.next_review == FIXED_TODAY + timedelta(days=3)
    step2 = spacing_step(correct=False, streak_right=3, today=FIXED_TODAY)
    assert step2.streak_right == 0
    assert step2.next_review == FIXED_TODAY + timedelta(days=1)


def test_insert_chunks_sets_tomorrow(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    with connection() as conn:
        with conn.transaction():
            insert_chunks(
                conn,
                user_id,
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
            (user_id,),
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
    user_id = _onboard(tid)
    for i in range(10):
        sid = insert_session(
            user_id,
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

    before = compute_accuracy_window(user_id)
    assert before.answered >= 30
    assert before.accuracy is not None
    assert before.accuracy > 0.9

    sid = insert_session(
        user_id,
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

    after = compute_accuracy_window(user_id)
    assert after.accuracy is not None
    assert after.accuracy >= before.accuracy - 1e-9


def test_stats_shows_due_chunks(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _insert_chunk(user_id, chunk="cut costs")
    _insert_chunk(
        user_id,
        chunk="by Friday",
        next_review=FIXED_TODAY + timedelta(days=10),
    )
    now = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    stats = collect_stats(user_id, now=now)
    assert stats is not None
    assert stats.chunk_total == 2
    assert stats.chunk_due == 1
    body = format_stats_message(stats, include_sweep=False)
    assert "due: 1" in body
    assert "Chunks:" in body
