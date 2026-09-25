"""Book ingestion (S6) — debounce, merge, upsert, failures, labels (mocked vision)."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.db import close_pool, connection
from core.llm import LLMError
from core.services.books import (
    MergedUnit,
    PageFailure,
    count_units_for_user,
    get_unit_row,
    merge_page_results,
    parse_ocr_payload,
    slugify_book_name,
    union_target_items,
    upsert_unit,
)
from core.services.identity import save_onboarding
REPO_ROOT = Path(__file__).resolve().parents[1]
FAKE_TELEGRAM_ID_BASE = 9_460_000_000


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
            "name": "Book Test",
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
# --- Fake JobQueue -----------------------------------------------------------


class _FakeJob:
    def __init__(
        self,
        callback: Any,
        *,
        name: str,
        data: dict[str, Any],
        when: float,
    ) -> None:
        self.callback = callback
        self.name = name
        self.data = data
        self.when = when
        self.removed = False

    def schedule_removal(self) -> None:
        self.removed = True


class FakeJobQueue:
    def __init__(self) -> None:
        self._jobs: list[_FakeJob] = []

    def get_jobs_by_name(self, name: str) -> list[_FakeJob]:
        return [j for j in self._jobs if j.name == name and not j.removed]

    def run_once(
        self,
        callback: Any,
        when: float,
        *,
        name: str | None = None,
        data: dict[str, Any] | None = None,
        chat_id: int | None = None,
        user_id: int | None = None,
    ) -> _FakeJob:
        job = _FakeJob(
            callback, name=name or "", data=data or {}, when=float(when)
        )
        self._jobs.append(job)
        return job


def _make_context(
    user_id: int,
    *,
    book: str = "murphy",
    collecting: bool = True,
) -> MagicMock:
    context = MagicMock()
    context.job_queue = FakeJobQueue()
    context.user_data = {
        "book": {
            "book": book,
            "collecting": collecting,
            "processing": False,
            "pages": [],
            "over_cap": False,
        }
    }
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock(
        return_value=MagicMock(message_id=99)
    )
    context.bot.send_chat_action = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.delete_message = AsyncMock()
    return context


def _photo_update(
    user_id: int,
    *,
    file_id: str = "f1",
    media_group_id: str | None = "album1",
    chat_id: int = 42,
) -> MagicMock:
    update = MagicMock()
    update.effective_user = MagicMock(id=user_id)
    message = MagicMock()
    message.chat_id = chat_id
    message.media_group_id = media_group_id
    message.photo = [MagicMock(file_id=file_id)]
    message.document = None
    message.reply_text = AsyncMock()
    update.message = message
    return update


# --- Unit helpers ------------------------------------------------------------


def test_slugify_and_union() -> None:
    assert slugify_book_name("  Vocab In Use! ") == "vocab_in_use"
    assert union_target_items(["a", "b"], ["b", "c"]) == ["a", "b", "c"]


def test_unit_number_stays_string() -> None:
    parsed = parse_ocr_payload(
        {
            "unit_number": "12A",
            "unit_title": "Modals",
            "target_items": ["can", "could"],
            "readable": True,
        },
        batch_index=1,
        user_id=1,
    )
    assert isinstance(parsed, dict)
    assert parsed["unit_number"] == "12A"
    assert isinstance(parsed["unit_number"], str)


def test_continuation_and_orphan(caplog: pytest.LogCaptureFixture) -> None:
    pages: list[tuple[int, Any]] = [
        (
            1,
            {
                "unit_number": "12",
                "unit_title": "Tenses",
                "target_items": ["present perfect"],
            },
        ),
        (
            2,
            {
                "unit_number": None,
                "unit_title": "",
                "target_items": ["for/since"],
            },
        ),
    ]
    units, failures = merge_page_results(pages, user_id=1)
    assert len(units) == 1
    assert units[0].target_items == ["present perfect", "for/since"]
    assert failures == []

    with caplog.at_level(logging.WARNING):
        units2, failures2 = merge_page_results(
            [
                (
                    1,
                    {
                        "unit_number": None,
                        "unit_title": "",
                        "target_items": ["x"],
                    },
                )
            ],
            user_id=99,
        )
    assert units2 == []
    assert len(failures2) == 1
    assert failures2[0].reason == "orphan"
    assert "orphan" in caplog.text


def test_readable_false_and_malformed(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        bad = parse_ocr_payload(
            {"readable": False, "unit_number": "1", "target_items": []},
            batch_index=3,
            user_id=1,
        )
        malformed = parse_ocr_payload(
            "not-a-dict", batch_index=4, user_id=1
        )
    assert isinstance(bad, PageFailure) and bad.reason == "unreadable"
    assert isinstance(malformed, PageFailure) and malformed.reason == "malformed"

    units, failures = merge_page_results(
        [(3, bad), (4, malformed), (5, LLMError("boom"))],
        user_id=1,
    )
    assert units == []
    assert {f.reason for f in failures} == {"unreadable", "malformed", "llm"}


def test_upsert_reingest_unions_items(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day1 = date.today() - timedelta(days=3)
    upsert_unit(
        user_id,
        "murphy",
        MergedUnit("12A", "Modals", ["can", "could"]),
        studied_at=day1,
    )
    assert count_units_for_user(user_id, "murphy", "12A") == 1
    upsert_unit(
        user_id,
        "murphy",
        MergedUnit("12A", "Modals", ["could", "might"]),
        studied_at=date.today(),
    )
    assert count_units_for_user(user_id, "murphy", "12A") == 1
    row = get_unit_row(user_id, "murphy", "12A")
    assert row is not None
    items = row["target_items"]
    if isinstance(items, str):
        import json

        items = json.loads(items)
    assert items == ["can", "could", "might"]
    assert row["studied_at"] == date.today()


# --- Debounce / process ------------------------------------------------------


def test_no_provider_sdk_outside_wrappers() -> None:
    core_dir = REPO_ROOT / "packages" / "core"
    bot_dir = REPO_ROOT / "apps"
    forbidden = re.compile(
        r"^\s*(import anthropic|from anthropic|import openai|from openai)\b"
    )
    allowed = {
        core_dir / "llm.py",
        core_dir / "speech.py",
    }
    offenders: list[str] = []
    for root in (core_dir, bot_dir):
        for path in root.rglob("*.py"):
            if path in allowed:
                continue
            text = path.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if forbidden.search(line):
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{i}:{line.strip()}"
                    )
    assert offenders == []


