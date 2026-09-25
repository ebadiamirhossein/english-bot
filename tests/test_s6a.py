"""S6a — /test unit N + quiz top-up from book units."""

from __future__ import annotations

import logging
import uuid
from datetime import date

import pytest

from core.db import close_pool, connection
from core.services.books import (
    MergedUnit,
    dedupe_teachable_items,
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


# --- Grading fork -----------------------------------------------------------


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


# --- Streak pinning ---------------------------------------------------------


# --- /test command ----------------------------------------------------------


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
