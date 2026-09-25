"""S24: shared content library — slang fan-out, books, backfill, ledger."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from core.db import close_pool, connection
from core.services.access_control import (
    approve_access,
    delivery_lister_ids,
    revoke_access,
)
from core.services.books import MergedUnit
from core.services.chunks import due_chunks, insert_chunks
from core.services.reading import normalize_for_match
from core.services.shared_content import (
    OUTCOME_SKIPPED_OWNED,
    backfill_shared_library,
    book_content_key,
    list_recipients,
    record_and_fanout_book_units,
    record_and_fanout_chunks,
    try_backfill_soft,
)
from core.services.identity import save_onboarding
from core.services.watch_import import (
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


def _onboard(tid: int, *, name: str = "Shared Test") -> int:
    user_id = save_onboarding(
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
    return user_id


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
    a_id = _onboard(a, name="A")
    b_id = _onboard(b, name="B")
    items = _slang_items()
    with patch(
        "core.services.shared_content.list_recipients", return_value=[a_id, b_id]
    ):
        stats = record_and_fanout_chunks(
            items, created_by=a_id, source="slang", rejected=0
        )
    assert stats.imported == 2
    assert stats.duplicates == 0
    assert stats.users_reached == 2
    assert _count_chunks(a_id, source="slang") == 2
    assert _count_chunks(b_id, source="slang") == 2
    assert _count_errors(a_id) == 0
    assert _count_errors(b_id) == 0


def test_reimport_zero_new_rows(two_users: tuple[int, int]) -> None:
    a, b = two_users
    a_id = _onboard(a)
    b_id = _onboard(b)
    items = _slang_items()
    with patch(
        "core.services.shared_content.list_recipients", return_value=[a_id, b_id]
    ):
        record_and_fanout_chunks(items, created_by=a_id, source="slang")
        stats = record_and_fanout_chunks(items, created_by=a_id, source="slang")
    assert stats.imported == 0
    assert stats.duplicates == 2
    assert stats.users_reached == 0
    assert _count_chunks(a_id, source="slang") == 2
    assert _count_chunks(b_id, source="slang") == 2


def test_per_user_dedupe_writes_skipped_owned(
    two_users: tuple[int, int],
) -> None:
    a, b = two_users
    a_id = _onboard(a)
    b_id = _onboard(b)
    with connection() as conn:
        with conn.transaction():
            insert_chunks(
                conn,
                b_id,
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
        "core.services.shared_content.list_recipients", return_value=[a_id, b_id]
    ):
        record_and_fanout_chunks(items, created_by=a_id, source="slang")
    assert _count_chunks(b_id, source="capture") == 1
    assert _count_chunks(b_id, source="slang") == 1  # mid only
    with connection() as conn:
        row = conn.execute(
            """
            SELECT d.outcome
              FROM shared_content_deliveries d
              JOIN shared_content sc ON sc.id = d.shared_content_id
             WHERE d.user_id = %s AND sc.content_key = %s
            """,
            (b_id, normalize_for_match("no cap")),
        ).fetchone()
    assert row["outcome"] == OUTCOME_SKIPPED_OWNED


def test_revoked_user_receives_nothing(two_users: tuple[int, int]) -> None:
    a, b = two_users
    a_id = _onboard(a)
    b_id = _onboard(b)
    revoke_access(b)
    assert b_id not in list_recipients()
    items = _slang_items()
    with patch(
        "core.services.shared_content.list_recipients", return_value=[a_id]
    ):
        record_and_fanout_chunks(items, created_by=a_id, source="slang")
    assert _count_chunks(a_id, source="slang") == 2
    assert _count_chunks(b_id, source="slang") == 0


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
    a_id = _onboard(a)
    items = _slang_items()
    with patch(
        "core.services.shared_content.list_recipients", return_value=[a_id]
    ):
        record_and_fanout_chunks(items, created_by=a_id, source="slang")
    b_id = _onboard(b)
    n = backfill_shared_library(b_id)
    assert n >= 2
    assert _has_chunk(b_id, "mid")
    assert _has_chunk(b_id, "no cap")


def test_backfill_idempotent_redo_onboarding(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    items = _slang_items()
    with patch(
        "core.services.shared_content.list_recipients", return_value=[user_id]
    ):
        record_and_fanout_chunks(items, created_by=user_id, source="slang")
    before = _count_chunks(user_id, source="slang")
    # #448: the redo is the SAME learner onboarding again, so it is keyed on the
    # same Telegram id. This read `_onboard(user_id)` -- the internal id passed
    # where a Telegram id belongs -- which registered a second `Shared Test`
    # user that no fixture named and nothing deleted (300 of them by 2026-09-25).
    assert _onboard(tid) == user_id  # redo
    assert backfill_shared_library(user_id) == 0
    assert _count_chunks(user_id, source="slang") == before


def test_backfill_idempotent_revoke_reapprove(
    two_users: tuple[int, int],
) -> None:
    a, b = two_users
    a_id = _onboard(a)
    b_id = _onboard(b)
    items = _slang_items()
    with patch(
        "core.services.shared_content.list_recipients", return_value=[a_id, b_id]
    ):
        record_and_fanout_chunks(items, created_by=a_id, source="slang")
    before = _count_chunks(b_id, source="slang")
    revoke_access(b)
    approve_access(b_id)
    assert backfill_shared_library(b_id) == 0
    assert _count_chunks(b_id, source="slang") == before


def test_import_then_new_user_same_day(two_users: tuple[int, int]) -> None:
    a, b = two_users
    a_id = _onboard(a)
    items = _slang_items()
    with patch(
        "core.services.shared_content.list_recipients", return_value=[a_id]
    ):
        record_and_fanout_chunks(items, created_by=a_id, source="slang")
    b_id = _onboard(b)
    backfill_shared_library(b_id)
    assert _has_chunk(b_id, "mid")
    assert _has_chunk(b_id, "no cap")
    before = _count_chunks(b_id, source="slang")
    with patch(
        "core.services.shared_content.list_recipients", return_value=[a_id, b_id]
    ):
        stats = record_and_fanout_chunks(items, created_by=a_id, source="slang")
    assert stats.users_reached == 0
    assert _count_chunks(b_id, source="slang") == before


def test_shared_chunks_enter_ladder_and_cap(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    items = _slang_items()
    with patch(
        "core.services.shared_content.list_recipients", return_value=[user_id]
    ):
        record_and_fanout_chunks(items, created_by=user_id, source="slang")
    # S25: fan-out rows are unpresented — present before graded due selection.
    tomorrow = FIXED_TODAY + timedelta(days=1)
    with connection() as conn:
        conn.execute(
            """
            UPDATE chunks
               SET presented_at = NOW(), next_review = %s
             WHERE user_id = %s
            """,
            (tomorrow, user_id),
        )
    selected = due_chunks(user_id, 2, now=tomorrow)
    assert len(selected) == 2
    assert all(c.source == "slang" for c in selected)
    assert _count_errors(user_id) == 0


def test_chunk_first_write_wins(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
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
        "core.services.shared_content.list_recipients", return_value=[user_id]
    ):
        record_and_fanout_chunks(first, created_by=user_id, source="slang")
        record_and_fanout_chunks(second, created_by=user_id, source="slang")
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
            (user_id, word),
        ).fetchone()
    assert "fell asleep" in row["s"]
    assert "fell asleep" in chunk["full_sentence"]


# --- books ------------------------------------------------------------------


def test_book_ledger_key_round_trip(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    unit = MergedUnit(
        unit_number="12",
        unit_title="Articles",
        target_items=["a", "an", "the"],
    )
    key = book_content_key("Murphy", "12")
    assert "\x00" not in key
    assert key == book_content_key("murphy", "12")
    with patch(
        "core.services.shared_content.list_recipients", return_value=[user_id]
    ):
        record_and_fanout_book_units("murphy", [unit], created_by=user_id)
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
    a_id = _onboard(a)
    b_id = _onboard(b)
    unit = MergedUnit("5", "Past simple", ["went", "saw"])
    with patch(
        "core.services.shared_content.list_recipients", return_value=[a_id, b_id]
    ):
        record_and_fanout_book_units("murphy", [unit], created_by=a_id)
    fixed = date(2026, 7, 1)
    with connection() as conn:
        conn.execute(
            """
            UPDATE book_units SET studied_at = %s
             WHERE user_id = %s AND book = %s AND unit_number = %s
            """,
            (fixed, b_id, "murphy", "5"),
        )
    refreshed = MergedUnit("5", "Past simple (revised)", ["went", "saw", "did"])
    with patch(
        "core.services.shared_content.list_recipients", return_value=[a_id, b_id]
    ):
        record_and_fanout_book_units("murphy", [refreshed], created_by=a_id)
    with connection() as conn:
        row = conn.execute(
            """
            SELECT unit_title, target_items, studied_at
              FROM book_units
             WHERE user_id = %s AND book = %s AND unit_number = %s
             ORDER BY id LIMIT 1
            """,
            (b_id, "murphy", "5"),
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


def test_zero_errors_on_fanout(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    before = _count_errors(user_id)
    with patch(
        "core.services.shared_content.list_recipients", return_value=[user_id]
    ):
        record_and_fanout_chunks(_slang_items(), created_by=user_id, source="slang")
    assert _count_errors(user_id) == before == 0
