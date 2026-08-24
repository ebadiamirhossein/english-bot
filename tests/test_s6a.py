"""S6a — /test unit N + quiz top-up from book units."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.db import close_pool, connection
from apps.bot.handlers import book_test as book_test_handler
from apps.bot.handlers import quiz as quiz_handler
from apps.bot.handlers.book_test import (
    all_s6a_button_labels,
    parse_test_unit_arg,
    plan_tap_formats,
)
from apps.bot.handlers.correction import init_correction_prompt
from apps.bot.handlers.quiz import init_quiz_prompt
from core.services.books import (
    MergedUnit,
    dedupe_teachable_items,
    find_units_by_number,
    is_word_bank_item,
    select_topup_items,
    teachable_items_for_unit,
    upsert_unit,
)
from core.services.errors import record_errors
from core.services.sessions import (
    abandon_open_book_tests,
    has_session_on,
    insert_session,
)
from core.services.streaks import get_streak, roll_over_day
from core.services.identity import save_onboarding
FAKE_TELEGRAM_ID_BASE = 9_480_000_000

# Real stored strings from Murphy units 1 / 4 / 5 (live dry-run fixtures).
WORD_BANK_ITEM = "verbs: cross, hide, scratch, take, tie, wave"
STATIVE_ITEM = (
    "stative verbs not used in continuous (like, want, need, prefer, know, "
    "understand, realise, recognise, believe, suppose, remember, mean, fit, "
    "belong, contain, consist, seem)"
)
IRREGULAR_ITEM = (
    "irregular verbs (buy, catch, fall, hurt, sell, spend, teach, throw, "
    "write, etc.)"
)
REPORTING_ITEM = (
    "Reporting verbs: agree, apologise, insist, promise, recommend, suggest"
)


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


def _onboard(tid: int, *, morning: str = "07:00", tz: str = "UTC") -> int:
    user_id = save_onboarding(
        tid,
        {
            "name": "S6a Test",
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


def _insert_unit(
    tid: int,
    *,
    book: str,
    unit_number: str,
    title: str,
    items: list[str],
    studied_at: date | None = None,
) -> None:
    upsert_unit(
        tid,
        book,
        MergedUnit(
            unit_number=unit_number,
            unit_title=title,
            target_items=items,
        ),
        studied_at=studied_at or date(2026, 8, 1),
    )


def _insert_due_errors(tid: int, n: int) -> list[int]:
    ids: list[int] = []
    with connection() as conn:
        with conn.transaction():
            for i in range(n):
                row = conn.execute(
                    """
                    INSERT INTO errors (
                        user_id, source, you_said, correct_form,
                        error_type, explanation, next_review
                    ) VALUES (
                        %s, 'text', %s, %s,
                        'subject_verb_agreement', 'test', CURRENT_DATE
                    )
                    RETURNING id
                    """,
                    (tid, f"bad {i}", f"good {i}"),
                ).fetchone()
                ids.append(int(row["id"]))
    return ids


# --- Heuristics -------------------------------------------------------------


def test_word_bank_excludes_real_verbs_list_keeps_stative() -> None:
    assert is_word_bank_item(WORD_BANK_ITEM) is True
    assert is_word_bank_item(STATIVE_ITEM) is False
    assert is_word_bank_item(IRREGULAR_ITEM) is False
    assert is_word_bank_item(REPORTING_ITEM) is False


def test_dedupe_near_duplicates_and_word_bank() -> None:
    items = [
        "Present continuous",
        "present continuous (I am doing)",
        WORD_BANK_ITEM,
        "am/is/are + -ing",
    ]
    out = dedupe_teachable_items(items)
    assert WORD_BANK_ITEM not in out
    assert out[0] == "Present continuous"
    assert "present continuous (I am doing)" not in out
    assert "am/is/are + -ing" in out


def test_unit_number_string_match(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _insert_unit(
        user_id,
        book="murphy",
        unit_number="12",
        title="A",
        items=["item a"],
    )
    _insert_unit(
        user_id,
        book="murphy",
        unit_number="12A",
        title="B",
        items=["item b"],
    )
    _insert_unit(
        user_id,
        book="murphy",
        unit_number="101-102",
        title="C",
        items=["item c"],
    )
    assert len(find_units_by_number(user_id, "12")) == 1
    assert find_units_by_number(user_id, "12")[0]["unit_number"] == "12"
    assert find_units_by_number(user_id, "12A")[0]["unit_number"] == "12A"
    assert find_units_by_number(user_id, "101-102")[0]["unit_number"] == "101-102"
    assert parse_test_unit_arg(["unit", "101-102"]) == "101-102"
    assert parse_test_unit_arg(["unit", "12A"]) == "12A"
    assert parse_test_unit_arg(None) is None


def test_select_topup_counts_and_recency(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _insert_unit(
        user_id,
        book="murphy",
        unit_number="1",
        title="Old",
        items=["old item one", "old item two"],
        studied_at=date(2026, 7, 1),
    )
    _insert_unit(
        user_id,
        book="murphy",
        unit_number="5",
        title="New",
        items=["new item one", "new item two", "new item three"],
        studied_at=date(2026, 8, 5),
    )
    picked = select_topup_items(user_id, 3)
    assert len(picked) == 3
    assert all(p["unit_number"] == "5" for p in picked)


# --- Morning top-up ---------------------------------------------------------


def test_topup_fills_remainder(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, morning="00:00", tz="UTC")
    _insert_due_errors(user_id, 2)
    for i in range(5):
        _insert_unit(
            user_id,
            book="murphy",
            unit_number=str(i + 1),
            title=f"U{i+1}",
            items=[f"point {i}-a", f"point {i}-b"],
            studied_at=date(2026, 8, 1) + timedelta(days=i),
        )

    captured: dict[str, Any] = {}

    def fake_build(user_id, errors, *, chunks=None, book_items=None, chat_fn=None):
        captured["errors"] = errors
        captured["book_items"] = list(book_items or [])
        n = len(errors) + len(book_items or [])
        qs = []
        for i in range(n):
            qs.append(
                {
                    "format": "choice",
                    "prompt": f"Q{i}",
                    "accept": ["a"],
                    "answer": "a",
                    "options": ["a", "b", "c", "d"],
                    "error_type": "subject_verb_agreement",
                    "explanation": "x",
                    **(
                        {"error_id": errors[i].id}
                        if i < len(errors)
                        else {"source": "book"}
                    ),
                }
            )
        return qs, "scenario"

    app = MagicMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc)
    with patch.object(quiz_handler, "_build_quiz_questions", side_effect=fake_build):
        action = asyncio.run(quiz_handler.deliver_morning(app, user_id, now=now))
    assert action == "quiz"
    assert len(captured["errors"]) == 2
    assert len(captured["book_items"]) == 3


def test_topup_zero_due_five_book(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, morning="00:00", tz="UTC")
    for i in range(5):
        _insert_unit(
            user_id,
            book="murphy",
            unit_number=str(i + 1),
            title=f"U{i+1}",
            items=[f"teachable {i}"],
            studied_at=date(2026, 8, 1) + timedelta(days=i),
        )

    def fake_build(user_id, errors, *, chunks=None, book_items=None, chat_fn=None):
        assert errors == []
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
                    "error_type": "subject_verb_agreement",
                    "explanation": "x",
                }
                for i in range(5)
            ],
            "scenario",
        )

    app = MagicMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc)
    with patch.object(quiz_handler, "_build_quiz_questions", side_effect=fake_build):
        action = asyncio.run(quiz_handler.deliver_morning(app, user_id, now=now))
    assert action == "quiz"
    with connection() as conn:
        row = conn.execute(
            "SELECT task_type FROM sessions WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    assert row["task_type"] == "quiz"


def test_topup_five_due_no_book(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, morning="00:00", tz="UTC")
    _insert_due_errors(user_id, 5)
    _insert_unit(
        user_id,
        book="murphy",
        unit_number="1",
        title="U1",
        items=["teachable"],
    )

    def fake_build(user_id, errors, *, chunks=None, book_items=None, chat_fn=None):
        assert len(errors) == 5
        assert book_items == []
        return (
            [
                {
                    "error_id": e.id,
                    "format": "choice",
                    "prompt": "Q",
                    "accept": ["a"],
                    "answer": "a",
                    "options": ["a", "b", "c", "d"],
                }
                for e in errors
            ],
            "scenario",
        )

    app = MagicMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc)
    with patch.object(quiz_handler, "_build_quiz_questions", side_effect=fake_build):
        action = asyncio.run(quiz_handler.deliver_morning(app, user_id, now=now))
    assert action == "quiz"


def test_topup_rescue_one_due_two_book(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, morning="00:00", tz="UTC")
    _insert_due_errors(user_id, 1)
    for i in range(4):
        _insert_unit(
            user_id,
            book="murphy",
            unit_number=str(i + 1),
            title=f"U{i+1}",
            items=[f"point {i}"],
            studied_at=date(2026, 8, 1) + timedelta(days=i),
        )
    day = date(2026, 8, 8)
    with connection() as conn:
        conn.execute(
            """
            UPDATE streaks
               SET rescue_mode_until = %s
             WHERE user_id = %s
            """,
            (day + timedelta(days=3), user_id),
        )

    captured: dict[str, Any] = {}

    def fake_build(user_id, errors, *, chunks=None, book_items=None, chat_fn=None):
        captured["n_err"] = len(errors)
        captured["n_book"] = len(book_items or [])
        n = len(errors) + len(book_items or [])
        return (
            [
                {
                    "format": "choice",
                    "prompt": f"Q{i}",
                    "accept": ["a"],
                    "answer": "a",
                    "options": ["a", "b", "c", "d"],
                    "error_type": "subject_verb_agreement",
                    "explanation": "x",
                    **(
                        {"error_id": errors[0].id}
                        if i == 0
                        else {"source": "book"}
                    ),
                }
                for i in range(n)
            ],
            "scenario",
        )

    app = MagicMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc)
    with patch.object(quiz_handler, "_build_quiz_questions", side_effect=fake_build):
        action = asyncio.run(quiz_handler.deliver_morning(app, user_id, now=now))
    assert action == "quiz"
    assert captured["n_err"] == 1
    assert captured["n_book"] == 2


# --- Grading fork -----------------------------------------------------------


def test_wrong_book_gap_typed_journals_no_mark_result(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    init_correction_prompt()
    init_quiz_prompt()
    day = date(2026, 8, 8)
    payload = {
        "index": 0,
        "correct_count": 0,
        "answered": 0,
        "chat_id": tid,
        "message_id": 99,
        "questions": [
            {
                "source": "book",
                "format": "gap",
                "prompt": "I ___ home",
                "accept": ["went"],
                "answer": "went",
                "error_type": "verb_tense_past",
                "explanation": "Past simple for a finished action.",
                "error_type_label": "Past tense",
                "unit_title": "Past simple",
            }
        ],
    }
    sid = insert_session(user_id, "quiz", day, payload=payload, completed=False)
    payload["session_id"] = sid

    context = MagicMock()
    context.bot.edit_message_text = AsyncMock()

    with patch.object(quiz_handler, "mark_result") as mr:
        asyncio.run(
            quiz_handler._advance_after_answer(
                context,
                user_id,
                sid,
                payload,
                correct=False,
                question=payload["questions"][0],
                user_answer="go",
            )
        )
        mr.assert_not_called()

    with connection() as conn:
        row = conn.execute(
            """
            SELECT source, error_type, you_said, correct_form, next_review
              FROM errors
             WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
    assert row is not None
    assert row["source"] == "quiz"
    assert row["error_type"] == "verb_tense_past"
    assert row["you_said"] == "go"
    assert row["correct_form"] == "went"
    assert row["next_review"] == date.today() + timedelta(days=1)


def test_wrong_book_bad_error_type_skips_row(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    question = {
        "source": "book",
        "format": "choice",
        "answer": "right",
        "error_type": "not_a_real_type",
        "explanation": "x",
    }
    with caplog.at_level(logging.WARNING):
        written = record_errors(
            user_id,
            "quiz",
            [
                {
                    "you_said": "wrong",
                    "correct_form": "right",
                    "error_type": "not_a_real_type",
                    "explanation": "x",
                }
            ],
        )
    assert written == 0
    assert any("unknown error_type" in r.message for r in caplog.records)
    with connection() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM errors WHERE user_id = %s",
            (user_id,),
        ).fetchone()["n"]
    assert int(n) == 0
    del question


def test_mark_result_not_called_for_book_choice(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    init_correction_prompt()
    init_quiz_prompt()
    day = date(2026, 8, 8)
    payload = {
        "index": 0,
        "correct_count": 0,
        "answered": 0,
        "chat_id": tid,
        "message_id": 99,
        "questions": [
            {
                "source": "book",
                "format": "choice",
                "prompt": "Pick",
                "accept": ["right"],
                "answer": "right",
                "options": ["right", "wrong", "no", "nope"],
                "error_type": "word_order",
                "explanation": "Order matters.",
                "error_type_label": "Word order",
            }
        ],
    }
    sid = insert_session(user_id, "quiz", day, payload=payload, completed=False)
    context = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    with patch.object(quiz_handler, "mark_result") as mr:
        asyncio.run(
            quiz_handler._advance_after_answer(
                context,
                user_id,
                sid,
                dict(payload),
                correct=False,
                question=payload["questions"][0],
                user_answer="wrong",
            )
        )
        mr.assert_not_called()


# --- Streak pinning ---------------------------------------------------------


def test_zero_due_with_books_ignored_is_missed(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, morning="00:00", tz="UTC")
    for i in range(5):
        _insert_unit(
            user_id,
            book="murphy",
            unit_number=str(i + 1),
            title=f"U{i+1}",
            items=[f"teachable {i}"],
            studied_at=date(2026, 8, 1) + timedelta(days=i),
        )
    day = date(2026, 8, 8)
    with connection() as conn:
        conn.execute(
            """
            UPDATE streaks
               SET current_streak = 3,
                   freeze_tokens = 2,
                   last_evaluated_date = %s,
                   last_active_date = %s
             WHERE user_id = %s
            """,
            (day - timedelta(days=1), day - timedelta(days=1), user_id),
        )

    def fake_build(user_id, errors, *, chunks=None, book_items=None, chat_fn=None):
        return (
            [
                {
                    "source": "book",
                    "format": "choice",
                    "prompt": f"Q{i}",
                    "accept": ["a"],
                    "answer": "a",
                    "options": ["a", "b", "c", "d"],
                    "error_type": "subject_verb_agreement",
                    "explanation": "x",
                }
                for i in range(5)
            ],
            "scenario",
        )

    app = MagicMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc)
    with patch.object(quiz_handler, "_build_quiz_questions", side_effect=fake_build):
        action = asyncio.run(quiz_handler.deliver_morning(app, user_id, now=now))
    assert action == "quiz"

    result = roll_over_day(user_id, day)
    assert result.outcome == "missed"
    assert result.freeze_consumed is True
    assert get_streak(user_id).freeze_tokens == 1


def test_zero_due_no_books_ignored_is_neutral(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, morning="00:00", tz="UTC")
    day = date(2026, 8, 8)
    with connection() as conn:
        conn.execute(
            """
            UPDATE streaks
               SET current_streak = 3,
                   freeze_tokens = 2,
                   last_evaluated_date = %s,
                   last_active_date = %s
             WHERE user_id = %s
            """,
            (day - timedelta(days=1), day - timedelta(days=1), user_id),
        )
    app = MagicMock()
    app.bot.send_message = AsyncMock(return_value=MagicMock(message_id=42))
    now = datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc)
    action = asyncio.run(quiz_handler.deliver_morning(app, user_id, now=now))
    assert action == "free_practice"
    result = roll_over_day(user_id, day)
    assert result.outcome == "neutral"
    assert get_streak(user_id).freeze_tokens == 2
    assert get_streak(user_id).current_streak == 3


# --- /test command ----------------------------------------------------------


def test_unknown_unit_warm_reply(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _insert_unit(
        user_id,
        book="murphy",
        unit_number="3",
        title="Present",
        items=["am/is/are + -ing"],
    )

    async def _run() -> str:
        update = MagicMock()
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()
        update.effective_user = MagicMock(id=tid)
        context = MagicMock()
        context.args = ["unit", "99"]
        context.bot = MagicMock()
        await book_test_handler.handle_test_command(update, context)
        update.message.reply_text.assert_awaited()
        return update.message.reply_text.await_args.args[0]

    body = asyncio.run(_run())
    assert "99" in body
    assert "3" in body


def test_bare_test_lists_units(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _insert_unit(
        user_id, book="murphy", unit_number="12", title="A", items=["a"]
    )
    _insert_unit(
        user_id, book="murphy", unit_number="12A", title="B", items=["b"]
    )

    async def _run() -> None:
        update = MagicMock()
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()
        update.effective_user = MagicMock(id=tid)
        context = MagicMock()
        context.args = []
        await book_test_handler.handle_test_command(update, context)
        update.message.reply_text.assert_awaited()
        body = update.message.reply_text.await_args.args[0]
        assert "12" in body
        assert "12A" in body
        markup = update.message.reply_text.await_args.kwargs.get("reply_markup")
        assert markup is not None

    asyncio.run(_run())


def test_two_books_same_unit_disambiguates(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _insert_unit(
        user_id, book="murphy", unit_number="12", title="A", items=["a"]
    )
    _insert_unit(
        user_id,
        book="vocabulary_in_use",
        unit_number="12",
        title="B",
        items=["b"],
    )

    async def _run() -> str:
        update = MagicMock()
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()
        update.effective_user = MagicMock(id=tid)
        context = MagicMock()
        context.args = ["unit", "12"]
        await book_test_handler.handle_test_command(update, context)
        return update.message.reply_text.await_args.args[0]

    body = asyncio.run(_run())
    assert "more than one book" in body.lower() or "which one" in body.lower()


def test_one_book_no_disambiguation(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    init_book = book_test_handler.init_book_test_prompt
    init_book()
    init_correction_prompt()
    _insert_unit(
        user_id,
        book="murphy",
        unit_number="12",
        title="A",
        items=["am/is/are + -ing", "actions happening now"],
    )

    def fake_chat(messages, *, system, json_mode=False, max_tokens=0):
        return {
            "scenario": "cafe",
            "questions": [
                {
                    "source": "book",
                    "format": "choice",
                    "prompt": "Pick",
                    "options": ["a", "b", "c", "d"],
                    "answer": "a",
                    "accept": ["a"],
                    "error_type": "subject_verb_agreement",
                    "explanation": "Because.",
                },
                {
                    "source": "book",
                    "format": "order",
                    "prompt": "Pick",
                    "options": ["a", "b", "c", "d"],
                    "answer": "a",
                    "accept": ["a"],
                    "error_type": "word_order",
                    "explanation": "Because.",
                },
            ],
        }

    async def _run() -> None:
        update = MagicMock()
        update.message = AsyncMock()
        update.message.reply_text = AsyncMock()
        update.effective_user = MagicMock(id=tid)
        update.effective_chat = MagicMock(id=tid)
        context = MagicMock()
        context.args = ["unit", "12"]
        context.bot = MagicMock()
        context.bot.send_message = AsyncMock(
            return_value=MagicMock(message_id=55)
        )
        with patch("apps.bot.handlers.book_test.chat", side_effect=fake_chat):
            await book_test_handler.handle_test_command(update, context)
        # Started a set — no which-book prompt
        update.message.reply_text.assert_not_awaited()
        context.bot.send_message.assert_awaited()

    asyncio.run(_run())
    with connection() as conn:
        row = conn.execute(
            """
            SELECT task_type, date, completed FROM sessions
             WHERE user_id = %s AND task_type = 'book_test'
             ORDER BY id DESC
             LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    assert row is not None
    assert row["task_type"] == "book_test"
    assert has_session_on(user_id, row["date"]) is False


def test_new_test_abandons_prior_book_test(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 8)
    old_id = insert_session(
        user_id,
        "book_test",
        day,
        payload={"index": 0, "questions": [], "message_id": 1, "chat_id": tid},
        completed=False,
    )
    n = abandon_open_book_tests(user_id)
    assert n == 1
    with connection() as conn:
        row = conn.execute(
            "SELECT completed, score FROM sessions WHERE id = %s",
            (old_id,),
        ).fetchone()
    assert row["completed"] is True
    assert row["score"] is None


def test_book_test_does_not_block_morning(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 8)
    insert_session(
        user_id,
        "book_test",
        day,
        payload={"index": 0, "questions": []},
        completed=False,
    )
    assert has_session_on(user_id, day) is False


def test_s6a_button_labels_max_20() -> None:
    for label in all_s6a_button_labels():
        assert len(label) <= 20, label


def test_plan_tap_formats_never_gap() -> None:
    for n in range(1, 8):
        fmts = plan_tap_formats(n)
        assert "gap" not in fmts
        assert len(fmts) == n


def test_teachable_items_filters_word_bank(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    _insert_unit(
        user_id,
        book="murphy",
        unit_number="1",
        title="Present continuous",
        items=[
            "Present continuous",
            WORD_BANK_ITEM,
            "am/is/are + -ing",
            STATIVE_ITEM,
        ],
    )
    items = teachable_items_for_unit(user_id, "murphy", "1")
    assert WORD_BANK_ITEM not in items
    assert STATIVE_ITEM in items
    assert "am/is/are + -ing" in items
