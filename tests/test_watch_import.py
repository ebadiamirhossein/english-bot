"""Watched-folder CSV import + Anki outbox (S15a)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.db import close_pool, connection
from core.services.anki import export_and_send, fetch_unexported_chunks
from core.services.paths import PathSafetyError, assert_path_outside_repo, repo_root
from core.services.users import save_onboarding
from core.services.watch_import import (
    IMPORT_STABLE_AFTER,
    clear_orphan_warnings,
    collect_root_orphans,
    ensure_user_layout,
    map_headers,
    process_csv_file,
    resolve_watch_root,
    scan_user_inbox,
    source_marker,
    warn_root_orphans,
    watch_dir_configured,
)

FAKE_TELEGRAM_ID_BASE = 9_480_000_000
DISTINCTIVE = "UNIQUE_SENTENCE_XYZ_SHOULD_NEVER_APPEAR_IN_LOGS"


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


def _onboard(tid: int) -> None:
    save_onboarding(
        tid,
        {
            "name": "Watch Test",
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


def _age_file(path: Path, *, older_than: timedelta = IMPORT_STABLE_AFTER) -> None:
    """Set mtime so the file is considered stable (no wall-clock sleep)."""
    age = older_than + timedelta(seconds=30)
    ts = time.time() - age.total_seconds()
    os.utime(path, (ts, ts))


def _write_csv(path: Path, header: str, rows: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = header + "\n" + "\n".join(rows) + "\n"
    path.write_text(body, encoding="utf-8")
    return path


def test_map_headers_trancy_shape() -> None:
    headers = ["Word", "Sentence", "Translation", "Title", "Extra Notes"]
    m = map_headers(headers)
    assert m is not None
    assert m.chunk == "Word"
    assert m.full_sentence == "Sentence"
    assert m.meaning == "Translation"
    assert m.material == "Title"


def test_map_headers_language_reactor_shape() -> None:
    headers = [
        "Phrase",
        "Context / Subtitle",
        "Definition",
        "Video title",
        "Timestamp",
    ]
    m = map_headers(headers)
    assert m is not None
    assert m.chunk == "Phrase"
    assert m.full_sentence == "Context / Subtitle"
    assert m.meaning == "Definition"
    assert m.material == "Video title"


def test_map_headers_unrecognisable() -> None:
    assert map_headers(["col_a", "col_b", "col_c"]) is None


def test_source_marker() -> None:
    assert source_marker("trancy", "HIMYM S02E04") == "subtitle_trancy_himym_s02e04"
    assert (
        source_marker("language_reactor", "The Office")
        == "subtitle_language_reactor_the_office"
    )
    assert source_marker("csv", "") == "subtitle_csv_untitled"


def test_detect_tool_from_headers() -> None:
    from core.services.watch_import import (
        classify_csv_format,
        detect_tool_from_headers,
    )

    assert (
        detect_tool_from_headers(["Word", "Sentence", "Translation", "Title"])
        == "trancy"
    )
    assert (
        detect_tool_from_headers(
            ["Phrase", "Context / Subtitle", "Definition", "Video title"]
        )
        == "language_reactor"
    )
    assert detect_tool_from_headers(["Phrase", "Sentence", "Meaning"]) == "csv"
    assert classify_csv_format(["Phrase", "Sentence", "Meaning"]) is None

    slang = ["Word", "Phonetic", "Meaning", "Example", "Date"]
    assert detect_tool_from_headers(slang) == "slang"
    assert classify_csv_format(slang) == "slang"
    assert classify_csv_format(
        ["Word", "Sentence", "Translation", "Title"]
    ) == "trancy"
    # Mutual exclusion: slang signature is not Trancy/LR.
    assert classify_csv_format(slang) != "trancy"
    assert classify_csv_format(slang) != "language_reactor"
    # Token presence of Word/Meaning alone is not slang.
    assert (
        classify_csv_format(["Word", "Sentence", "Translation"]) == "trancy"
    )
    assert (
        classify_csv_format(["Word", "Phonetic", "Translation", "Date"])
        == "vocabulary"
    )
    assert classify_csv_format(
        ["Word", "Phonetic", "Translation", "Date"]
    ) != "trancy"


def test_assert_path_outside_repo_refuses_inside() -> None:
    inside = repo_root() / "should-not-use-as-watch"
    with pytest.raises(PathSafetyError):
        assert_path_outside_repo(inside, label="WATCH_DIR")


@pytest.fixture
def watch_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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
    return root


def test_import_happy_path_moves_processed(
    cleanup_user: int, watch_root: Path
) -> None:
    tid = cleanup_user
    _onboard(tid)
    ensure_user_layout(watch_root, tid)
    csv_path = watch_root / "inbox" / str(tid) / "trancy" / "export.csv"
    _write_csv(
        csv_path,
        "Word,Sentence,Translation,Title",
        [
            f'circle back,"{DISTINCTIVE} circle back later",revisit,HIMYM',
            'run the numbers,"We need to run the numbers first",calculate,HIMYM',
        ],
    )
    _age_file(csv_path)
    now = datetime.now(timezone.utc)
    result = process_csv_file(
        csv_path, user_id=tid, tool="trancy", root=watch_root, now=now
    )
    assert result.status == "imported"
    assert result.imported == 2
    assert result.duplicates == 0
    assert result.invalid == 0
    assert not csv_path.exists()
    processed = list((watch_root / "processed" / str(tid)).glob("*.csv"))
    assert len(processed) == 1
    with connection() as conn:
        rows = conn.execute(
            "SELECT chunk, source, next_review, (CURRENT_DATE + 1) AS tomorrow "
            "FROM chunks WHERE user_id = %s ORDER BY id",
            (tid,),
        ).fetchall()
    assert len(rows) == 2
    assert rows[0]["next_review"] == rows[0]["tomorrow"]
    assert str(rows[0]["source"]).startswith("subtitle_trancy_")


def test_unrecognisable_headers_to_failed(
    cleanup_user: int, watch_root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    ensure_user_layout(watch_root, tid)
    csv_path = watch_root / "inbox" / str(tid) / "bad.csv"
    _write_csv(csv_path, "alpha,beta,gamma", [f"a,{DISTINCTIVE},c"])
    _age_file(csv_path)
    with caplog.at_level(logging.WARNING):
        result = process_csv_file(
            csv_path,
            user_id=tid,
            tool="csv",
            root=watch_root,
            now=datetime.now(timezone.utc),
        )
    assert result.status == "failed_headers"
    assert result.imported == 0
    assert not csv_path.exists()
    failed = list((watch_root / "failed" / str(tid)).glob("*.csv"))
    assert len(failed) == 1
    assert "failed_headers" in caplog.text
    assert DISTINCTIVE not in caplog.text
    with connection() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE user_id = %s", (tid,)
        ).fetchone()
    assert int(n["n"]) == 0


def test_row_level_dedupe(cleanup_user: int, watch_root: Path) -> None:
    tid = cleanup_user
    _onboard(tid)
    ensure_user_layout(watch_root, tid)
    header = "Phrase,Context,Definition"
    rows = [
        'cut costs,"We need to cut costs this quarter",reduce spending',
    ]
    p1 = watch_root / "inbox" / str(tid) / "a.csv"
    _write_csv(p1, header, rows)
    _age_file(p1)
    now = datetime.now(timezone.utc)
    r1 = process_csv_file(
        p1, user_id=tid, tool="language_reactor", root=watch_root, now=now
    )
    assert r1.imported == 1

    p2 = watch_root / "inbox" / str(tid) / "b.csv"
    _write_csv(
        p2,
        header,
        rows
        + [
            'run the numbers,"Please run the numbers again",calculate',
        ],
    )
    _age_file(p2)
    r2 = process_csv_file(
        p2, user_id=tid, tool="language_reactor", root=watch_root, now=now
    )
    assert r2.imported == 1
    assert r2.duplicates == 1
    with connection() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE user_id = %s", (tid,)
        ).fetchone()
    assert int(n["n"]) == 2


def test_chunk_not_in_sentence_skipped(
    cleanup_user: int, watch_root: Path
) -> None:
    tid = cleanup_user
    _onboard(tid)
    ensure_user_layout(watch_root, tid)
    p = watch_root / "inbox" / str(tid) / "x.csv"
    _write_csv(
        p,
        "Word,Sentence,Translation",
        [
            'missing phrase,"This sentence has no match.",nope',
            'cut costs,"We must cut costs now.",reduce',
        ],
    )
    _age_file(p)
    r = process_csv_file(
        p,
        user_id=tid,
        tool="csv",
        root=watch_root,
        now=datetime.now(timezone.utc),
    )
    assert r.imported == 1
    assert r.invalid == 1


def test_young_file_not_processed(
    cleanup_user: int, watch_root: Path
) -> None:
    tid = cleanup_user
    _onboard(tid)
    ensure_user_layout(watch_root, tid)
    p = watch_root / "inbox" / str(tid) / "fresh.csv"
    _write_csv(
        p,
        "Word,Sentence,Translation",
        ['cut costs,"We must cut costs now.",reduce'],
    )
    now = datetime.now(timezone.utc)
    result = scan_user_inbox(watch_root, tid, now=now)
    assert result.settling == 1
    assert result.files == []
    assert p.exists()


def test_collision_safe_processed(
    cleanup_user: int, watch_root: Path
) -> None:
    tid = cleanup_user
    _onboard(tid)
    ensure_user_layout(watch_root, tid)
    processed = watch_root / "processed" / str(tid)
    (processed / "export.csv").write_text("prior", encoding="utf-8")
    p = watch_root / "inbox" / str(tid) / "export.csv"
    _write_csv(
        p,
        "Word,Sentence,Translation",
        ['cut costs,"We must cut costs now.",reduce'],
    )
    _age_file(p)
    process_csv_file(
        p,
        user_id=tid,
        tool="csv",
        root=watch_root,
        now=datetime.now(timezone.utc),
    )
    names = sorted(x.name for x in processed.iterdir())
    assert "export.csv" in names
    assert any(n.startswith("export_") and n.endswith(".csv") for n in names)
    assert (processed / "export.csv").read_text(encoding="utf-8") == "prior"


def test_root_orphan_not_imported(
    cleanup_user: int, watch_root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    ensure_user_layout(watch_root, tid)
    orphan = watch_root / "inbox" / "orphan.csv"
    _write_csv(
        orphan,
        "Word,Sentence,Translation",
        [f'x,"{DISTINCTIVE}",y'],
    )
    _age_file(orphan)
    names = collect_root_orphans(watch_root)
    assert "orphan.csv" in names
    with caplog.at_level(logging.WARNING):
        newly = warn_root_orphans(names)
        again = warn_root_orphans(names)
    assert newly == ["orphan.csv"]
    assert again == []
    assert orphan.exists()
    assert DISTINCTIVE not in caplog.text
    scan = scan_user_inbox(watch_root, tid, now=datetime.now(timezone.utc))
    assert scan.total_imported == 0


def test_imported_appears_in_anki_export(
    cleanup_user: int, watch_root: Path
) -> None:
    tid = cleanup_user
    _onboard(tid)
    ensure_user_layout(watch_root, tid)
    p = (
        watch_root
        / "inbox"
        / str(tid)
        / "language_reactor"
        / "lr.csv"
    )
    _write_csv(
        p,
        "Phrase,Context,Definition,Show",
        [
            'circle back,"Let us circle back tomorrow.",revisit,The Office',
        ],
    )
    _age_file(p)
    process_csv_file(
        p,
        user_id=tid,
        tool="language_reactor",
        root=watch_root,
        now=datetime.now(timezone.utc),
    )
    with connection() as conn:
        rows = fetch_unexported_chunks(conn, tid)
    assert len(rows) == 1
    assert rows[0].source is not None
    assert rows[0].source.startswith("subtitle_language_reactor_")


def test_anki_outbox_write_and_failure_tolerant(
    cleanup_user: int, watch_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tid = cleanup_user
    _onboard(tid)
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO chunks (
                    user_id, chunk, full_sentence, meaning, source, track,
                    exported_to_anki, next_review
                ) VALUES (
                    %s, 'cut costs', 'We must cut costs now.', 'reduce',
                    'capture', NULL, FALSE, CURRENT_DATE + 1
                )
                """,
                (tid,),
            )

    sent: list[tuple[bytes, str, str]] = []

    async def _send(tsv_bytes: bytes, filename: str, caption: str) -> None:
        sent.append((tsv_bytes, filename, caption))

    n = asyncio.run(
        export_and_send(
            user_id=tid,
            local_date=datetime.now(timezone.utc).date(),
            send_document=_send,
            claim_session=False,
            caption="cap",
        )
    )
    assert n == 1
    assert sent
    out = list((watch_root / "outbox" / str(tid)).glob("*.tsv"))
    assert len(out) == 1

    with connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO chunks (
                    user_id, chunk, full_sentence, meaning, source, track,
                    exported_to_anki, next_review
                ) VALUES (
                    %s, 'by Friday', 'Done by Friday.', 'deadline',
                    'capture', NULL, FALSE, CURRENT_DATE + 1
                )
                """,
                (tid,),
            )
    sent.clear()

    def _boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(
        "core.services.watch_import.write_anki_outbox",
        _boom,
    )
    n2 = asyncio.run(
        export_and_send(
            user_id=tid,
            local_date=datetime.now(timezone.utc).date(),
            send_document=_send,
            claim_session=False,
            caption="cap",
        )
    )
    assert n2 == 1
    assert sent
    with connection() as conn:
        pending = fetch_unexported_chunks(conn, tid)
    assert pending == []


def test_scan_noop_when_watch_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "core.services.watch_import.load_settings",
        lambda: MagicMock(watch_dir=""),
    )
    assert watch_dir_configured() == ""
    with pytest.raises(ValueError):
        resolve_watch_root()
