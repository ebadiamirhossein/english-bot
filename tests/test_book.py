"""Book ingestion (S6) — debounce, merge, upsert, failures, labels (mocked vision)."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import ConversationHandler

from apps.bot import texts
from core.db import close_pool, connection
from apps.bot.handlers.book import (
    COLLECT_PAGES,
    after_batch_choice,
    all_book_button_labels,
    book_choice_keyboard,
    collect_page,
    debounce_job_name,
    process_pages,
    summary_keyboard,
)
from core.llm import LLMError
from core.services.books import (
    MAX_PAGES_PER_BATCH,
    MergedUnit,
    PageFailure,
    build_summary_text,
    count_units_for_user,
    format_page_list,
    format_pages_phrase,
    get_unit_row,
    merge_page_results,
    parse_ocr_payload,
    slugify_book_name,
    union_target_items,
    upsert_unit,
)
from core.services.users import save_onboarding

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


def _onboard(tid: int) -> None:
    save_onboarding(
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


def test_summary_uses_batch_index_not_ocr_numbers() -> None:
    # Successful page OCR reports unit 99; failed page is batch index 2.
    # Summary failure line must name 2 (batch position), not invent "page 99".
    units, failures = merge_page_results(
        [
            (
                1,
                {
                    "unit_number": "99",
                    "unit_title": "X",
                    "target_items": ["a"],
                },
            ),
            (2, PageFailure(2, "unreadable")),
        ],
        user_id=1,
    )
    text = build_summary_text(
        book="murphy",
        units=units,
        failures=failures,
        over_cap=False,
        texts_module=texts,
    )
    unread_line = texts.BOOK_SUMMARY_UNREADABLE.format(
        pages=format_pages_phrase([2]),
        cta=texts.BOOK_SUMMARY_RESHOOT_ONE,
    )
    assert unread_line in text
    assert "Page 2" in text
    assert "Pages 99 couldn't" not in text
    assert format_page_list([3, 7]) == "3 and 7"
    assert format_pages_phrase([3, 7]) == "Pages 3 and 7"


def test_summary_page_pluralisation_1_2_3() -> None:
    cases = [
        ([1], "Page 1", texts.BOOK_SUMMARY_RESHOOT_ONE),
        ([3, 7], "Pages 3 and 7", texts.BOOK_SUMMARY_RESHOOT_MANY),
        ([3, 7, 9], "Pages 3, 7 and 9", texts.BOOK_SUMMARY_RESHOOT_MANY),
    ]
    for indexes, phrase, cta in cases:
        assert format_pages_phrase(indexes) == phrase
        unread = build_summary_text(
            book="murphy",
            units=[],
            failures=[PageFailure(i, "unreadable") for i in indexes],
            over_cap=False,
            texts_module=texts,
        )
        snag = build_summary_text(
            book="murphy",
            units=[],
            failures=[PageFailure(i, "llm") for i in indexes],
            over_cap=False,
            texts_module=texts,
        )
        assert phrase in unread
        assert phrase in snag
        assert cta in unread
        assert cta in snag
        assert "couldn't be read" in unread
        assert "hit a snag on my side" in snag


def test_summary_collapse_over_four_failed_pages() -> None:
    indexes = list(range(1, 11))
    assert format_pages_phrase(indexes) == "All 10 pages"
    snag = build_summary_text(
        book="murphy",
        units=[],
        failures=[PageFailure(i, "llm") for i in indexes],
        over_cap=False,
        texts_module=texts,
    )
    unread = build_summary_text(
        book="murphy",
        units=[],
        failures=[PageFailure(i, "unreadable") for i in indexes],
        over_cap=False,
        texts_module=texts,
    )
    assert "All 10 pages hit a snag on my side" in snag
    assert "All 10 pages couldn't be read" in unread
    assert texts.BOOK_SUMMARY_RESHOOT_MANY in snag
    assert texts.BOOK_SUMMARY_RESHOOT_MANY in unread
    assert "Pages 1, 2, 3" not in snag
    assert texts.BOOK_SUMMARY_RESHOOT_ONE not in snag


def test_upsert_reingest_unions_items(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day1 = date.today() - timedelta(days=3)
    upsert_unit(
        tid,
        "murphy",
        MergedUnit("12A", "Modals", ["can", "could"]),
        studied_at=day1,
    )
    assert count_units_for_user(tid, "murphy", "12A") == 1
    upsert_unit(
        tid,
        "murphy",
        MergedUnit("12A", "Modals", ["could", "might"]),
        studied_at=date.today(),
    )
    assert count_units_for_user(tid, "murphy", "12A") == 1
    row = get_unit_row(tid, "murphy", "12A")
    assert row is not None
    items = row["target_items"]
    if isinstance(items, str):
        import json

        items = json.loads(items)
    assert items == ["can", "could", "might"]
    assert row["studied_at"] == date.today()


# --- Debounce / process ------------------------------------------------------


def test_album_debounce_one_job_one_process() -> None:
    async def _run() -> None:
        uid = 1001
        context = _make_context(uid)
        ocr_calls: list[int] = []

        for i in range(10):
            update = _photo_update(
                uid, file_id=f"fid{i}", media_group_id="mg-shared"
            )
            state = await collect_page(update, context)
            assert state == COLLECT_PAGES

        jobs = context.job_queue.get_jobs_by_name(debounce_job_name(uid))
        assert len(jobs) == 1
        assert len(context.user_data["book"]["pages"]) == 10

        async def fake_get_file(file_id: str) -> MagicMock:
            tg = MagicMock()
            tg.download_as_bytearray = AsyncMock(
                return_value=bytearray(b"\xff\xd8\xff")
            )
            return tg

        context.bot.get_file = AsyncMock(side_effect=fake_get_file)

        def fake_ocr(
            image_bytes: bytes, *, system: str, chat_fn: Any = None
        ) -> dict:
            ocr_calls.append(1)
            n = len(ocr_calls)
            return {
                "unit_number": str(n),
                "unit_title": f"U{n}",
                "target_items": [f"item{n}"],
                "readable": True,
            }

        context.job = jobs[0]

        with (
            patch("apps.bot.handlers.book.ocr_one_page", side_effect=fake_ocr),
            patch(
                "apps.bot.handlers.book.persist_units", return_value=10
            ) as persist,
        ):
            await process_pages(context)
            await process_pages(context)

        assert len(ocr_calls) == 10
        assert persist.call_count == 1

    asyncio.run(_run())


def test_single_non_album_photo_schedules() -> None:
    async def _run() -> None:
        uid = 1002
        context = _make_context(uid)
        update = _photo_update(uid, media_group_id=None)
        await collect_page(update, context)
        jobs = context.job_queue.get_jobs_by_name(debounce_job_name(uid))
        assert len(jobs) == 1
        assert len(context.user_data["book"]["pages"]) == 1

    asyncio.run(_run())


def test_reentrancy_no_duplicate_rows(cleanup_user: int) -> None:
    async def _run() -> None:
        tid = cleanup_user
        _onboard(tid)
        context = _make_context(tid)
        context.user_data["book"]["pages"] = [
            {
                "batch_index": 1,
                "file_id": "f1",
                "mime_type": "image/jpeg",
                "media_group_id": None,
            }
        ]
        context.job = MagicMock(data={"user_id": tid, "chat_id": 42})

        async def fake_get_file(file_id: str) -> MagicMock:
            tg = MagicMock()
            tg.download_as_bytearray = AsyncMock(
                return_value=bytearray(b"\xff\xd8\xff")
            )
            return tg

        context.bot.get_file = AsyncMock(side_effect=fake_get_file)

        with patch(
            "apps.bot.handlers.book.ocr_one_page",
            return_value={
                "unit_number": "12A",
                "unit_title": "Modals",
                "target_items": ["can"],
                "readable": True,
            },
        ):
            await process_pages(context)
            await process_pages(context)

        assert count_units_for_user(tid, "murphy", "12A") == 1

    asyncio.run(_run())


def test_partial_batch_names_page_six(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    async def _run() -> None:
        tid = cleanup_user
        _onboard(tid)
        context = _make_context(tid)
        context.user_data["book"]["pages"] = [
            {
                "batch_index": i,
                "file_id": f"f{i}",
                "mime_type": "image/jpeg",
                "media_group_id": "g",
            }
            for i in range(1, 7)
        ]
        context.job = MagicMock(data={"user_id": tid, "chat_id": 42})

        async def fake_get_file(file_id: str) -> MagicMock:
            tg = MagicMock()
            tg.download_as_bytearray = AsyncMock(
                return_value=bytearray(b"\xff\xd8\xff")
            )
            return tg

        context.bot.get_file = AsyncMock(side_effect=fake_get_file)

        def fake_ocr(
            image_bytes: bytes, *, system: str, chat_fn: Any = None
        ) -> dict:
            fake_ocr.n += 1  # type: ignore[attr-defined]
            n = fake_ocr.n  # type: ignore[attr-defined]
            if n == 6:
                raise LLMError("vision failed")
            return {
                "unit_number": str(n),
                "unit_title": f"U{n}",
                "target_items": [f"i{n}"],
                "readable": True,
            }

        fake_ocr.n = 0  # type: ignore[attr-defined]

        with patch("apps.bot.handlers.book.ocr_one_page", side_effect=fake_ocr):
            await process_pages(context)

        assert count_units_for_user(tid, "murphy", "1") == 1
        assert count_units_for_user(tid, "murphy", "5") == 1
        assert count_units_for_user(tid, "murphy", "6") == 0
        sent = context.bot.send_message.call_args_list[-1]
        summary = sent.kwargs.get("text") or sent.args[1]
        assert "Page 6" in summary
        assert "hit a snag on my side" in summary
        assert "re-shoot that page, one page per photo" in summary
        assert "book batch" in caplog.text
        assert "pages=6" in caplog.text
        assert "units_written=5" in caplog.text

    with caplog.at_level(logging.INFO):
        asyncio.run(_run())


def test_prose_vision_response_soft_skips_page(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    """Plain prose from vision → WARNING + skipped page, never an exception."""

    async def _run() -> None:
        tid = cleanup_user
        _onboard(tid)
        context = _make_context(tid)
        context.user_data["book"]["pages"] = [
            {
                "batch_index": 1,
                "file_id": "prose1",
                "mime_type": "image/jpeg",
                "media_group_id": None,
            }
        ]
        context.job = MagicMock(data={"user_id": tid, "chat_id": 42})

        async def fake_get_file(file_id: str) -> MagicMock:
            tg = MagicMock()
            tg.download_as_bytearray = AsyncMock(
                return_value=bytearray(b"\xff\xd8\xff")
            )
            return tg

        context.bot.get_file = AsyncMock(side_effect=fake_get_file)

        with (
            patch(
                "apps.bot.handlers.book.ocr_one_page",
                side_effect=LLMError(
                    "Response was not valid JSON: Expecting value: "
                    "line 1 column 1 (char 0); "
                    "raw='I cannot extract copyrighted textbook content.'"
                ),
            ),
            caplog.at_level(logging.WARNING),
        ):
            await process_pages(context)

        sent = context.bot.send_message.call_args_list[-1]
        summary = sent.kwargs.get("text") or sent.args[1]
        assert "Page 1" in summary
        assert "hit a snag" in summary
        assert "book OCR page failure" in caplog.text
        assert "copyrighted textbook" in caplog.text

    asyncio.run(_run())


def test_over_cap_silent_once_in_summary() -> None:
    async def _run() -> None:
        uid = 1003
        context = _make_context(uid)
        updates: list[MagicMock] = []

        for i in range(25):
            update = _photo_update(uid, file_id=f"x{i}", media_group_id="big")
            updates.append(update)
            await collect_page(update, context)

        assert len(context.user_data["book"]["pages"]) == MAX_PAGES_PER_BATCH
        assert context.user_data["book"]["over_cap"] is True
        for update in updates:
            for call in update.message.reply_text.call_args_list:
                text = call.args[0] if call.args else call.kwargs.get("text", "")
                assert texts.BOOK_SUMMARY_OVER_CAP not in text

        text = build_summary_text(
            book="murphy",
            units=[MergedUnit("1", "A", ["x"])],
            failures=[],
            over_cap=True,
            texts_module=texts,
        )
        assert texts.BOOK_SUMMARY_OVER_CAP in text
        assert text.count(texts.BOOK_SUMMARY_OVER_CAP) == 1

    asyncio.run(_run())


def test_done_ends_conversation() -> None:
    async def _run() -> None:
        uid = 1004
        context = _make_context(uid, collecting=False)
        update = MagicMock()
        update.effective_user = MagicMock(id=uid)
        query = MagicMock()
        query.data = "book:after:done"
        query.answer = AsyncMock()
        query.edit_message_reply_markup = AsyncMock()
        query.message = MagicMock()
        update.callback_query = query

        result = await after_batch_choice(update, context)
        assert result == ConversationHandler.END
        assert "book" not in context.user_data

    asyncio.run(_run())


def test_add_more_reenables_collecting() -> None:
    async def _run() -> None:
        uid = 1005
        context = _make_context(uid, collecting=False)
        context.user_data["book"]["over_cap"] = True
        update = MagicMock()
        update.effective_user = MagicMock(id=uid)
        query = MagicMock()
        query.data = "book:after:more"
        query.answer = AsyncMock()
        query.edit_message_reply_markup = AsyncMock()
        query.message = MagicMock()
        query.message.reply_text = AsyncMock()
        update.callback_query = query

        result = await after_batch_choice(update, context)
        assert result == COLLECT_PAGES
        assert context.user_data["book"]["collecting"] is True
        assert context.user_data["book"]["over_cap"] is False
        assert context.user_data["book"]["pages"] == []

    asyncio.run(_run())


def test_button_labels_max_20_chars() -> None:
    labels = all_book_button_labels()
    # Also pull labels off the live keyboards.
    for row in book_choice_keyboard().inline_keyboard:
        for btn in row:
            labels.append(btn.text)
    for row in summary_keyboard().inline_keyboard:
        for btn in row:
            labels.append(btn.text)
    for label in labels:
        assert len(label) <= 20, f"label too long: {label!r} ({len(label)})"


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


def test_book_handler_never_writes_photo_bytes_to_disk() -> None:
    book_py = (
        REPO_ROOT / "apps" / "bot" / "handlers" / "book.py"
    ).read_text(encoding="utf-8")
    books_py = (
        REPO_ROOT / "packages" / "core" / "services" / "books.py"
    ).read_text(encoding="utf-8")
    combined = book_py + "\n" + books_py
    assert "download_as_bytearray" in book_py
    assert "write_bytes" not in combined
    assert "NamedTemporaryFile" not in combined
    assert "open(" not in book_py or "Path(" in book_py  # prompt Path read ok
    # Prompt load uses read_text on the .txt prompt — allowed. Photo path must not open().
    assert "open(" not in books_py
    # Handler may only read_text the prompt path, not photo files.
    assert re.search(r"open\([^)]*file_id", book_py) is None
    assert "Path.write" not in combined
