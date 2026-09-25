"""S15b: Telegram CSV document import — pipeline reuse, privacy, access."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Chat, Document, Message, Update, User

from core.db import close_pool, connection
from core.services.identity import save_onboarding
from core.services.watch_import import (
    clear_orphan_warnings,
    detect_tool_from_headers,
    import_csv_bytes,
    process_csv_file,
    ensure_user_layout,
)

FAKE_TELEGRAM_ID_BASE = 9_490_000_000
DISTINCTIVE = "UNIQUE_SENTENCE_XYZ_SHOULD_NEVER_APPEAR_IN_LOGS"

_TRANCY_CSV = (
    "Word,Sentence,Translation,Title\n"
    f'circle back,"{DISTINCTIVE} circle back later",revisit,HIMYM\n'
    'run the numbers,"We need to run the numbers first",calculate,HIMYM\n'
)

_BAD_HEADERS_CSV = f"alpha,beta,gamma\na,{DISTINCTIVE},c\n"


@pytest.fixture
def fake_telegram_id() -> int:
    return FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)


@pytest.fixture(autouse=True)
def _close_pool_after_test() -> None:
    clear_orphan_warnings()
    yield
    close_pool()
    clear_orphan_warnings()


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
            "name": "CSV Doc Test",
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


def _doc_update(
    telegram_user_id: int,
    *,
    file_name: str,
    file_size: int | None = 100,
    file_id: str = "file-1",
    update_id: int = 1,
) -> Update:
    user = User(id=telegram_user_id, first_name="A", is_bot=False)
    chat = Chat(id=telegram_user_id, type="private")
    doc = Document(
        file_id=file_id,
        file_unique_id=f"u-{file_id}",
        file_name=file_name,
        file_size=file_size,
        mime_type="text/csv" if file_name.endswith(".csv") else "application/pdf",
    )
    msg = Message(
        message_id=10,
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=user,
        document=doc,
    )
    return Update(update_id=update_id, message=msg)


def _context_with_download(data: bytes) -> MagicMock:
    tg_file = MagicMock()
    tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(data))
    bot = MagicMock()
    bot.get_file = AsyncMock(return_value=tg_file)
    app = MagicMock()
    context = MagicMock()
    context.bot = bot
    context.application = app
    return context


# --- Shared pipeline ---------------------------------------------------------


def test_one_mapping_implementation() -> None:
    """The entrances must not drift into two mappers. (W22 deleted the Telegram
    entrance, `apps/bot/handlers/csv_import.py`, and the half of this test that
    read it; the one-mapper half is about `core` and stays.)"""
    src = Path("packages/core/services/watch_import.py").read_text(encoding="utf-8")
    assert src.count("def map_headers(") == 1
    assert src.count("def import_csv_rows(") == 1
    assert "def import_csv_bytes(" in src
    assert "def process_csv_file(" in src


def test_detect_tool_trancy_and_lr_and_fallback() -> None:
    assert (
        detect_tool_from_headers(
            ["Word", "Sentence", "Translation", "Title"]
        )
        == "trancy"
    )
    assert (
        detect_tool_from_headers(
            ["Word", "Phonetic", "Translation", "Date"]
        )
        == "vocabulary"
    )
    assert (
        detect_tool_from_headers(
            ["Phrase", "Context / Subtitle", "Definition", "Video title"]
        )
        == "language_reactor"
    )
    assert (
        detect_tool_from_headers(["Phrase", "Sentence", "Meaning"]) == "csv"
    )


def test_import_csv_bytes_happy_path(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    now = datetime.now(timezone.utc)
    with caplog.at_level(logging.INFO):
        result = import_csv_bytes(
            _TRANCY_CSV.encode("utf-8"),
            user_id=user_id,
            filename="export.csv",
            now=now,
        )
    assert result.status == "imported"
    assert result.imported == 2
    assert result.duplicates == 0
    assert result.invalid == 0
    assert result.due_after is not None
    assert result.source_tool == "trancy"
    assert DISTINCTIVE not in caplog.text
    with connection() as conn:
        rows = conn.execute(
            "SELECT chunk, source FROM chunks WHERE user_id = %s ORDER BY id",
            (user_id,),
        ).fetchall()
    assert len(rows) == 2
    assert str(rows[0]["source"]).startswith("subtitle_trancy_")


def test_attribution_is_sender(cleanup_user: int, fake_telegram_id: int) -> None:
    tid_a = cleanup_user
    tid_b = fake_telegram_id + 1_000_000
    assert tid_a != tid_b
    user_id = _onboard(tid_a)
    tid_b_id = _onboard(tid_b)
    try:
        now = datetime.now(timezone.utc)
        import_csv_bytes(
            _TRANCY_CSV.encode("utf-8"),
            user_id=user_id,
            filename="a.csv",
            now=now,
        )
        import_csv_bytes(
            _TRANCY_CSV.encode("utf-8"),
            user_id=tid_b_id,
            filename="b.csv",
            now=now,
        )
        with connection() as conn:
            n_a = conn.execute(
                "SELECT COUNT(*) AS n FROM chunks WHERE user_id = %s",
                (user_id,),
            ).fetchone()
            n_b = conn.execute(
                "SELECT COUNT(*) AS n FROM chunks WHERE user_id = %s",
                (tid_b_id,),
            ).fetchone()
            cross = conn.execute(
                "SELECT COUNT(*) AS n FROM chunks WHERE user_id = %s "
                "AND chunk IN (SELECT chunk FROM chunks WHERE user_id = %s)",
                (user_id, tid_b_id),
            ).fetchone()
        assert int(n_a["n"]) == 2
        assert int(n_b["n"]) == 2
        # Same phrases under both users is fine; ownership must not merge.
        assert int(cross["n"]) == 2
        with connection() as conn:
            wrong = conn.execute(
                "SELECT COUNT(*) AS n FROM chunks WHERE user_id = %s "
                "AND id IN (SELECT id FROM chunks WHERE user_id = %s)",
                (user_id, tid_b_id),
            ).fetchone()
        assert int(wrong["n"]) == 0
    finally:
        _delete_user(tid_b)


def test_dedupe_across_folder_and_telegram(
    cleanup_user: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    root = tmp_path / "watch"
    root.mkdir()
    monkeypatch.setattr(
        "core.services.watch_import.load_settings",
        lambda: MagicMock(watch_dir=str(root)),
    )
    monkeypatch.setattr(
        "core.services.watch_import.assert_path_outside_repo",
        lambda path, label="WATCH_DIR": Path(path).resolve(),
    )
    ensure_user_layout(root, user_id)
    csv_path = root / "inbox" / str(user_id) / "trancy" / "export.csv"
    csv_path.write_text(_TRANCY_CSV, encoding="utf-8")
    # Age via utime without sleeping the wall clock.
    import os
    import time
    from core.services.watch_import import IMPORT_STABLE_AFTER
    from datetime import timedelta

    age = IMPORT_STABLE_AFTER + timedelta(seconds=30)
    ts = time.time() - age.total_seconds()
    os.utime(csv_path, (ts, ts))

    now = datetime.now(timezone.utc)
    folder = process_csv_file(
        csv_path, user_id=user_id, tool="trancy", root=root, now=now
    )
    assert folder.imported == 2

    telegram = import_csv_bytes(
        _TRANCY_CSV.encode("utf-8"),
        user_id=user_id,
        filename="export.csv",
        now=now,
    )
    assert telegram.imported == 0
    assert telegram.duplicates == 2


def test_watch_dir_unset_telegram_still_works(
    cleanup_user: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    monkeypatch.setattr(
        "core.services.watch_import.load_settings",
        lambda: MagicMock(watch_dir=""),
    )
    from core.services.watch_import import watch_dir_configured

    assert watch_dir_configured() == ""
    result = import_csv_bytes(
        _TRANCY_CSV.encode("utf-8"),
        user_id=user_id,
        filename="export.csv",
        now=datetime.now(timezone.utc),
    )
    assert result.imported == 2


