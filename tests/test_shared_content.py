"""S24: shared content library — slang fan-out, books, backfill, ledger."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.ext import ApplicationBuilder

from app import texts
from app.db import close_pool, connection
from app.handlers.csv_import import (
    on_share_orphan_callback,
    on_share_slang_callback,
    s24_share_button_labels,
)
from app.services.access_control import (
    approve_access,
    delivery_lister_ids,
    revoke_access,
)
from app.services.books import MergedUnit, upsert_unit
from app.services.chunks import due_chunks, insert_chunks
from app.services.reading import normalize_for_match
from app.services.shared_content import (
    OUTCOME_DELIVERED,
    OUTCOME_SKIPPED_OWNED,
    backfill_shared_library,
    book_content_key,
    list_recipients,
    record_and_fanout_book_units,
    record_and_fanout_chunks,
    try_backfill_soft,
)
from app.services.users import save_onboarding
from app.services.watch_import import (
    classify_csv_format,
    format_meaning,
    map_headers,
    parse_csv_text,
    parse_slang_chunk_items,
)

FAKE_TELEGRAM_ID_BASE = 9_510_000_000
FIXED_TODAY = date(2026, 8, 14)
FIXED_NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)

_SLANG_CSV = (
    "Word,Phonetic,Meaning,Example,Date\r\n"
    'mid,/mɪd/,average or not very good,'
    '"The movie was mid, I fell asleep halfway.",2026-08-14\r\n'
    'no cap,/noʊ kæp/,no lie or for real,'
    '"That presentation was fire, no cap.",2026-08-14\r\n'
)

_TRANCY_HEADERS = ["Word", "Sentence", "Translation", "Title"]
_LR_HEADERS = ["Phrase", "Context / Subtitle", "Definition", "Video title"]
_SLANG_HEADERS = ["Word", "Phonetic", "Meaning", "Example", "Date"]


@pytest.fixture
def fake_telegram_id() -> int:
    return FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)


@pytest.fixture(autouse=True)
def _close_pool_after_test() -> None:
    with connection() as conn:
        with conn.transaction():
            conn.execute("DELETE FROM shared_content_deliveries")
            conn.execute("DELETE FROM shared_content")
    yield
    close_pool()
    with connection() as conn:
        with conn.transaction():
            conn.execute("DELETE FROM shared_content_deliveries")
            conn.execute("DELETE FROM shared_content")


def _delete_user(telegram_user_id: int) -> None:
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM shared_content_deliveries WHERE user_id = %s",
                (telegram_user_id,),
            )
            conn.execute(
                "DELETE FROM users WHERE telegram_user_id = %s",
                (telegram_user_id,),
            )


@pytest.fixture
def cleanup_user(fake_telegram_id: int):
    yield fake_telegram_id
    _delete_user(fake_telegram_id)


@pytest.fixture
def two_users(fake_telegram_id: int):
    a = fake_telegram_id
    b = fake_telegram_id + 1
    yield a, b
    _delete_user(a)
    _delete_user(b)


def _onboard(tid: int, *, name: str = "Shared Test") -> None:
    save_onboarding(
        tid,
        {
            "name": name,
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


def _slang_items() -> list[dict[str, str]]:
    headers, rows = parse_csv_text(_SLANG_CSV)
    items, invalid = parse_slang_chunk_items(headers, rows)
    assert invalid == 0
    return items


def _count_chunks(user_id: int, *, source: str | None = None) -> int:
    with connection() as conn:
        if source is None:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM chunks WHERE user_id = %s",
                (user_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM chunks WHERE user_id = %s AND source = %s",
                (user_id, source),
            ).fetchone()
    return int(row["n"])


def _count_errors(user_id: int) -> int:
    with connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM errors WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    return int(row["n"])


def _count_bot_messages(user_id: int) -> int:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(count), 0)::int AS n
              FROM bot_message_counts WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
    return int(row["n"]) if row else 0


# --- classifier -------------------------------------------------------------


def test_slang_header_exact_signature() -> None:
    assert classify_csv_format(_SLANG_HEADERS) == "slang"
    m = map_headers(_SLANG_HEADERS)
    assert m is not None
    assert m.format == "slang"
    assert m.chunk == "Word"
    assert m.full_sentence == "Example"
    assert m.meaning == "Meaning"
    assert m.phonetic == "Phonetic"


def test_trancy_not_slang_and_slang_not_trancy_or_lr() -> None:
    assert classify_csv_format(_TRANCY_HEADERS) == "trancy"
    assert classify_csv_format(_TRANCY_HEADERS) != "slang"
    assert classify_csv_format(_SLANG_HEADERS) != "trancy"
    assert classify_csv_format(_SLANG_HEADERS) != "language_reactor"
    assert classify_csv_format(_LR_HEADERS) == "language_reactor"
    assert classify_csv_format(_LR_HEADERS) != "slang"
    assert classify_csv_format(["alpha", "beta"]) is None


def test_slang_sample_maps_and_phonetic() -> None:
    headers, rows = parse_csv_text(_SLANG_CSV)
    items, invalid = parse_slang_chunk_items(headers, rows)
    assert invalid == 0
    assert len(items) == 2
    mid = next(i for i in items if i["chunk"] == "mid")
    assert mid["full_sentence"].startswith("The movie was mid")
    assert mid["meaning"] == format_meaning(
        "average or not very good", "/mɪd/"
    )
    assert "/mɪd/" in mid["meaning"]


# --- fan-out / ledger -------------------------------------------------------


def test_fanout_n_users_n_copies(two_users: tuple[int, int]) -> None:
    a, b = two_users
    _onboard(a, name="A")
    _onboard(b, name="B")
    items = _slang_items()
    with patch(
        "app.services.shared_content.list_recipients", return_value=[a, b]
    ):
        stats = record_and_fanout_chunks(
            items, created_by=a, source="slang", rejected=0
        )
    assert stats.imported == 2
    assert stats.duplicates == 0
    assert stats.users_reached == 2
    assert _count_chunks(a, source="slang") == 2
    assert _count_chunks(b, source="slang") == 2
    assert _count_errors(a) == 0
    assert _count_errors(b) == 0


def test_reimport_zero_new_rows(two_users: tuple[int, int]) -> None:
    a, b = two_users
    _onboard(a)
    _onboard(b)
    items = _slang_items()
    with patch(
        "app.services.shared_content.list_recipients", return_value=[a, b]
    ):
        record_and_fanout_chunks(items, created_by=a, source="slang")
        stats = record_and_fanout_chunks(items, created_by=a, source="slang")
    assert stats.imported == 0
    assert stats.duplicates == 2
    assert stats.users_reached == 0
    assert _count_chunks(a, source="slang") == 2
    assert _count_chunks(b, source="slang") == 2


def test_sender_exactly_one_copy_on_share(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    items = _slang_items()
    with patch(
        "app.services.shared_content.list_recipients", return_value=[tid]
    ):
        stats = record_and_fanout_chunks(
            items, created_by=tid, source="slang", rejected=1
        )
    assert _count_chunks(tid, source="slang") == 2
    with connection() as conn:
        n = conn.execute(
            """
            SELECT COUNT(*) AS n FROM chunks
             WHERE user_id = %s AND chunk = %s
            """,
            (tid, "mid"),
        ).fetchone()
    assert int(n["n"]) == 1
    # Reply fields: sender imported/duplicates, file-level rejected, users_reached.
    assert stats.imported == 2
    assert stats.duplicates == 0
    assert stats.rejected == 1
    assert stats.users_reached == 1
    body = texts.IMPORT_SHARE_RESULT.format(
        imported=stats.imported,
        duplicates=stats.duplicates,
        rejected=stats.rejected,
        users_reached=stats.users_reached,
        due=0,
    )
    assert "Your copies — imported: 2" in body
    assert "already had: 0" in body
    assert "skipped: 1" in body
    assert "Users reached: 1" in body


def test_per_user_dedupe_writes_skipped_owned(
    two_users: tuple[int, int],
) -> None:
    a, b = two_users
    _onboard(a)
    _onboard(b)
    with connection() as conn:
        with conn.transaction():
            insert_chunks(
                conn,
                b,
                source="capture",
                track=None,
                chunks=[
                    {
                        "chunk": "no cap",
                        "full_sentence": "That presentation was fire, no cap.",
                        "meaning": "for real",
                    }
                ],
            )
    items = _slang_items()
    with patch(
        "app.services.shared_content.list_recipients", return_value=[a, b]
    ):
        record_and_fanout_chunks(items, created_by=a, source="slang")
    assert _count_chunks(b, source="capture") == 1
    assert _count_chunks(b, source="slang") == 1  # mid only
    with connection() as conn:
        row = conn.execute(
            """
            SELECT d.outcome
              FROM shared_content_deliveries d
              JOIN shared_content sc ON sc.id = d.shared_content_id
             WHERE d.user_id = %s AND sc.content_key = %s
            """,
            (b, normalize_for_match("no cap")),
        ).fetchone()
    assert row["outcome"] == OUTCOME_SKIPPED_OWNED


def test_revoked_user_receives_nothing(two_users: tuple[int, int]) -> None:
    a, b = two_users
    _onboard(a)
    _onboard(b)
    revoke_access(b)
    assert b not in list_recipients()
    items = _slang_items()
    with patch(
        "app.services.shared_content.list_recipients", return_value=[a]
    ):
        record_and_fanout_chunks(items, created_by=a, source="slang")
    assert _count_chunks(a, source="slang") == 2
    assert _count_chunks(b, source="slang") == 0


def _has_chunk(user_id: int, chunk: str) -> bool:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM chunks
             WHERE user_id = %s AND chunk = %s
             LIMIT 1
            """,
            (user_id, chunk),
        ).fetchone()
    return row is not None


def test_backfill_at_onboarding(two_users: tuple[int, int]) -> None:
    a, b = two_users
    _onboard(a)
    items = _slang_items()
    with patch(
        "app.services.shared_content.list_recipients", return_value=[a]
    ):
        record_and_fanout_chunks(items, created_by=a, source="slang")
    _onboard(b)
    n = backfill_shared_library(b)
    assert n >= 2
    assert _has_chunk(b, "mid")
    assert _has_chunk(b, "no cap")


def test_backfill_idempotent_redo_onboarding(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    items = _slang_items()
    with patch(
        "app.services.shared_content.list_recipients", return_value=[tid]
    ):
        record_and_fanout_chunks(items, created_by=tid, source="slang")
    before = _count_chunks(tid, source="slang")
    _onboard(tid)  # redo
    assert backfill_shared_library(tid) == 0
    assert _count_chunks(tid, source="slang") == before


def test_backfill_idempotent_revoke_reapprove(
    two_users: tuple[int, int],
) -> None:
    a, b = two_users
    _onboard(a)
    _onboard(b)
    items = _slang_items()
    with patch(
        "app.services.shared_content.list_recipients", return_value=[a, b]
    ):
        record_and_fanout_chunks(items, created_by=a, source="slang")
    before = _count_chunks(b, source="slang")
    revoke_access(b)
    approve_access(b)
    assert backfill_shared_library(b) == 0
    assert _count_chunks(b, source="slang") == before


def test_import_then_new_user_same_day(two_users: tuple[int, int]) -> None:
    a, b = two_users
    _onboard(a)
    items = _slang_items()
    with patch(
        "app.services.shared_content.list_recipients", return_value=[a]
    ):
        record_and_fanout_chunks(items, created_by=a, source="slang")
    _onboard(b)
    backfill_shared_library(b)
    assert _has_chunk(b, "mid")
    assert _has_chunk(b, "no cap")
    before = _count_chunks(b, source="slang")
    with patch(
        "app.services.shared_content.list_recipients", return_value=[a, b]
    ):
        stats = record_and_fanout_chunks(items, created_by=a, source="slang")
    assert stats.users_reached == 0
    assert _count_chunks(b, source="slang") == before


def test_shared_chunks_enter_ladder_and_cap(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    items = _slang_items()
    with patch(
        "app.services.shared_content.list_recipients", return_value=[tid]
    ):
        record_and_fanout_chunks(items, created_by=tid, source="slang")
    # S25: fan-out rows are unpresented — present before graded due selection.
    tomorrow = FIXED_TODAY + timedelta(days=1)
    with connection() as conn:
        conn.execute(
            """
            UPDATE chunks
               SET presented_at = NOW(), next_review = %s
             WHERE user_id = %s
            """,
            (tomorrow, tid),
        )
    selected = due_chunks(tid, 2, now=tomorrow)
    assert len(selected) == 2
    assert all(c.source == "slang" for c in selected)
    assert _count_errors(tid) == 0


def test_chunk_first_write_wins(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    word = f"zwid_{uuid.uuid4().hex[:8]}"
    first = [
        {
            "chunk": word,
            "full_sentence": f"The movie was {word}, I fell asleep halfway.",
            "meaning": "average or not very good (/mɪd/)",
        }
    ]
    second = [
        {
            "chunk": word,
            "full_sentence": f"That take was {word}.",
            "meaning": "meh",
        }
    ]
    with patch(
        "app.services.shared_content.list_recipients", return_value=[tid]
    ):
        record_and_fanout_chunks(first, created_by=tid, source="slang")
        record_and_fanout_chunks(second, created_by=tid, source="slang")
    with connection() as conn:
        row = conn.execute(
            """
            SELECT payload->>'full_sentence' AS s
              FROM shared_content
             WHERE kind = 'chunk' AND content_key = %s
            """,
            (normalize_for_match(word),),
        ).fetchone()
        chunk = conn.execute(
            "SELECT full_sentence FROM chunks WHERE user_id = %s AND chunk = %s",
            (tid, word),
        ).fetchone()
    assert "fell asleep" in row["s"]
    assert "fell asleep" in chunk["full_sentence"]


# --- books ------------------------------------------------------------------


def test_book_ledger_key_round_trip(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    unit = MergedUnit(
        unit_number="12",
        unit_title="Articles",
        target_items=["a", "an", "the"],
    )
    key = book_content_key("Murphy", "12")
    assert "\x00" not in key
    assert key == book_content_key("murphy", "12")
    with patch(
        "app.services.shared_content.list_recipients", return_value=[tid]
    ):
        record_and_fanout_book_units("murphy", [unit], created_by=tid)
    with connection() as conn:
        row = conn.execute(
            """
            SELECT content_key, payload->>'unit_title' AS title
              FROM shared_content
             WHERE kind = 'book_unit' AND content_key = %s
            """,
            (key,),
        ).fetchone()
    assert row is not None
    assert row["content_key"] == key
    assert row["title"] == "Articles"


def test_book_refresh_preserves_studied_at(
    two_users: tuple[int, int],
) -> None:
    a, b = two_users
    _onboard(a)
    _onboard(b)
    unit = MergedUnit("5", "Past simple", ["went", "saw"])
    with patch(
        "app.services.shared_content.list_recipients", return_value=[a, b]
    ):
        record_and_fanout_book_units("murphy", [unit], created_by=a)
    fixed = date(2026, 7, 1)
    with connection() as conn:
        conn.execute(
            """
            UPDATE book_units SET studied_at = %s
             WHERE user_id = %s AND book = %s AND unit_number = %s
            """,
            (fixed, b, "murphy", "5"),
        )
    refreshed = MergedUnit("5", "Past simple (revised)", ["went", "saw", "did"])
    with patch(
        "app.services.shared_content.list_recipients", return_value=[a, b]
    ):
        record_and_fanout_book_units("murphy", [refreshed], created_by=a)
    with connection() as conn:
        row = conn.execute(
            """
            SELECT unit_title, target_items, studied_at
              FROM book_units
             WHERE user_id = %s AND book = %s AND unit_number = %s
             ORDER BY id LIMIT 1
            """,
            (b, "murphy", "5"),
        ).fetchone()
    assert row["studied_at"] == fixed
    assert "revised" in (row["unit_title"] or "")


def test_list_recipients_in_delivery_listers() -> None:
    assert "list_recipients" in delivery_lister_ids()
    assert delivery_lister_ids()["list_recipients"]() == set(list_recipients())


def test_try_backfill_soft_never_raises(cleanup_user: int) -> None:
    tid = cleanup_user
    # No users row — no-op success path.
    assert try_backfill_soft(tid) is True


def test_s24_button_labels_max_20() -> None:
    for label in s24_share_button_labels():
        assert len(label) <= 20, label


def test_share_orphan_warm_line(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    before = _count_chunks(tid)
    user = User(id=tid, first_name="A", is_bot=False)
    chat = Chat(id=tid, type="private")
    msg = MagicMock(spec=Message)
    msg.reply_text = AsyncMock()
    query = MagicMock(spec=CallbackQuery)
    query.data = "share:slang:yes"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = msg
    update = Update(update_id=1, callback_query=query)
    object.__setattr__(update, "_effective_user", user)
    object.__setattr__(update, "_effective_chat", chat)
    context = MagicMock()
    context.user_data = {}  # no pending — restart cleared it
    asyncio.run(on_share_orphan_callback(update, context))
    query.edit_message_text.assert_awaited()
    assert texts.IMPORT_SHARE_STALE in str(
        query.edit_message_text.await_args
    )
    assert _count_chunks(tid) == before  # no partial import


def test_zero_errors_on_fanout(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    before = _count_errors(tid)
    with patch(
        "app.services.shared_content.list_recipients", return_value=[tid]
    ):
        record_and_fanout_chunks(_slang_items(), created_by=tid, source="slang")
    assert _count_errors(tid) == before == 0
