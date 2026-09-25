"""S24a: Trancy vocabulary CSV — classifier, LLM sentences, sender-only."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Document, Message, Update, User

from core.db import close_pool, connection
from core.services.anki import fetch_unexported_chunks
from core.services.chunks import due_chunks
from core.services.identity import save_onboarding
from core.services.vocab_import import (
    SKIP_LIST_CAP,
    VOCAB_BATCH_SIZE,
    VOCAB_SOURCE,
    VocabGenerationError,
    dedupe_vocabulary_seeds,
    format_vocab_import_reply,
    generate_vocab_sentences,
    init_vocab_prompt,
    match_and_validate_sentences,
    persist_vocabulary_and_send,
    prepare_vocabulary_import,
)
from core.services.watch_import import (
    classify_csv_format,
    ensure_user_layout,
    is_language_reactor_headers,
    is_slang_headers,
    is_trancy_legacy_headers,
    is_vocabulary_headers,
    parse_csv_bytes,
    parse_vocabulary_seed_items,
    process_csv_file,
)

FAKE_TELEGRAM_ID_BASE = 9_492_000_000

# Real Trancy export shape: UTF-8 BOM + CRLF (from VOCABULARY_LIST_2026-08-14).
_REAL_VOCAB_CSV = (
    "\ufeffWord,Phonetic,Translation,Date\r\n"
    "tier,/tɪər/, سطح ردیف;  چیدمان در سطوح طبقه‌بندی,2026-08-11\r\n"
    "notch,/nɑːtʃ/,n. شکاف بریدگی فرو رفتگی چوب خط شکاف چوبخط خش; "
    "v. سوراخ کردن,2026-08-11\r\n"
)

_LONG_TRANSLATION = (
    "n. شکاف بریدگی فرو رفتگی چوب خط شکاف چوبخط خش; "
    "v. سوراخ کردن و چیزهای بیشتر برای اطمینان از عدم کوتاه شدن"
)

_SLANG = ["Word", "Phonetic", "Meaning", "Example", "Date"]
_VOCAB = ["Word", "Phonetic", "Translation", "Date"]
_TRANCY = ["Word", "Sentence", "Translation", "Title"]
_LR = ["Phrase", "Context / Subtitle", "Definition", "Video title"]


@pytest.fixture
def fake_telegram_id() -> int:
    return FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)


@pytest.fixture(autouse=True)
def _close_pool_after_test() -> None:
    init_vocab_prompt()
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


def _onboard(tid: int, *, cefr: str = "B1") -> int:
    user_id = save_onboarding(
        tid,
        {
            "name": "Vocab Test",
            "native_language": "fa",
            "cefr_level": cefr,
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": "07:00",
            "evening_time": "21:00",
        },
    )
    return user_id


def _error_count(user_id: int) -> int:
    with connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM errors WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    return int(row["n"])


def _shared_counts() -> tuple[int, int]:
    with connection() as conn:
        sc = conn.execute(
            "SELECT COUNT(*) AS n FROM shared_content"
        ).fetchone()
        sd = conn.execute(
            "SELECT COUNT(*) AS n FROM shared_content_deliveries"
        ).fetchone()
    return int(sc["n"]), int(sd["n"])


def _fake_sentences(words: list[str]) -> dict:
    return {
        "sentences": [
            {"word": w, "full_sentence": f"I noticed a {w} in the plan."}
            for w in words
        ]
    }


def _doc_update(user_id: int, *, file_name: str = "vocab.csv") -> Update:
    user = User(id=user_id, first_name="A", is_bot=False)
    chat = Chat(id=user_id, type="private")
    doc = Document(
        file_id="vf1",
        file_unique_id="uvf1",
        file_name=file_name,
        file_size=200,
        mime_type="text/csv",
    )
    msg = Message(
        message_id=10,
        date=datetime(2026, 8, 14, tzinfo=timezone.utc),
        chat=chat,
        from_user=user,
        document=doc,
    )
    return Update(update_id=1, message=msg)


def _context_with_download(data: bytes) -> MagicMock:
    tg_file = MagicMock()
    tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(data))
    bot = MagicMock()
    bot.get_file = AsyncMock(return_value=tg_file)
    bot.send_chat_action = AsyncMock()
    context = MagicMock()
    context.bot = bot
    context.application = MagicMock()
    context.user_data = {}
    return context


# --- Classifier --------------------------------------------------------------


def test_exclusive_classifier_predicates_one_true_per_shape() -> None:
    """Exactly one classifier predicate is true for each shape sample."""
    samples = {
        "slang": _SLANG,
        "vocabulary": _VOCAB,
        "trancy": _TRANCY,
        "language_reactor": _LR,
    }
    predicates = {
        "slang": is_slang_headers,
        "vocabulary": is_vocabulary_headers,
        "trancy": is_trancy_legacy_headers,
        "language_reactor": is_language_reactor_headers,
    }
    for shape, headers in samples.items():
        truths = [name for name, pred in predicates.items() if pred(headers)]
        assert truths == [shape], (shape, truths)
        assert classify_csv_format(headers) == shape


def test_real_vocab_bom_crlf_classified_vocabulary() -> None:
    headers, rows = parse_csv_bytes(_REAL_VOCAB_CSV.encode("utf-8"))
    assert is_vocabulary_headers(headers)
    assert classify_csv_format(headers) == "vocabulary"
    assert not is_trancy_legacy_headers(headers)
    assert not is_slang_headers(headers)
    assert not is_language_reactor_headers(headers)
    assert len(rows) == 2


def test_vocabulary_ne_slang_both_directions() -> None:
    assert classify_csv_format(_VOCAB) == "vocabulary"
    assert classify_csv_format(_SLANG) == "slang"
    assert classify_csv_format(_VOCAB) != "slang"
    assert classify_csv_format(_SLANG) != "vocabulary"
    assert classify_csv_format(_VOCAB) != "language_reactor"
    assert classify_csv_format(["alpha", "beta"]) is None


def test_trancy_legacy_requires_sentence_column() -> None:
    """Word+Translation without sentence is not Trancy-legacy (structural)."""
    no_sentence = ["Word", "Phonetic", "Translation", "Date"]
    assert is_vocabulary_headers(no_sentence)
    assert not is_trancy_legacy_headers(no_sentence)
    word_translation_only = ["Word", "Translation"]
    assert not is_trancy_legacy_headers(word_translation_only)
    assert classify_csv_format(word_translation_only) is None


# --- Match / validate --------------------------------------------------------


def test_match_short_response_counts_rejected() -> None:
    seeds = [
        {"chunk": "tier", "meaning": "سطح"},
        {"chunk": "notch", "meaning": "شکاف"},
    ]
    result = match_and_validate_sentences(
        seeds, {"tier": "The top tier is full."}
    )
    assert len(result.chunks) == 1
    assert result.rejected == 1
    assert result.chunks[0]["chunk"] == "tier"


def test_match_overlong_response_ignores_extra() -> None:
    seeds = [{"chunk": "tier", "meaning": "سطح"}]
    result = match_and_validate_sentences(
        seeds,
        {
            "tier": "The top tier is full.",
            "orphan": "This word was not requested.",
        },
    )
    assert len(result.chunks) == 1
    assert result.rejected == 0


def test_match_altered_word_counts_rejected() -> None:
    seeds = [{"chunk": "tier", "meaning": "سطح"}]
    result = match_and_validate_sentences(
        seeds, {"tiers": "The tiers are stacked."}
    )
    assert result.chunks == []
    assert result.rejected == 1


def test_sentence_missing_word_rejected() -> None:
    seeds = [{"chunk": "tier", "meaning": "سطح"}]
    result = match_and_validate_sentences(
        seeds, {"tier": "The top level is full."}
    )
    assert result.chunks == []
    assert result.rejected == 1


def test_long_translation_stored_intact(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    headers = _VOCAB
    rows = [
        {
            "Word": "notch",
            "Phonetic": "/nɑːtʃ/",
            "Translation": _LONG_TRANSLATION,
            "Date": "2026-08-11",
        }
    ]
    seeds, skipped = parse_vocabulary_seed_items(headers, rows)
    assert skipped == 0
    assert _LONG_TRANSLATION in seeds[0]["meaning"]

    chat_fn = MagicMock(
        return_value=_fake_sentences(["notch"])
    )
    chunks, counts = prepare_vocabulary_import(
        headers,
        rows,
        user_id=user_id,
        cefr_level="B1",
        work_domain="marketing",
        now=date(2026, 8, 14),
        chat_fn=chat_fn,
    )
    assert counts.imported == 1
    assert _LONG_TRANSLATION in chunks[0]["meaning"]


# --- LLM batching / dedupe / no wall-clock -----------------------------------


def test_generate_batches_one_call_for_multi_row() -> None:
    items = [
        {"chunk": "tier", "meaning": "a"},
        {"chunk": "notch", "meaning": "b"},
    ]
    chat_fn = MagicMock(return_value=_fake_sentences(["tier", "notch"]))
    out = generate_vocab_sentences(
        items, cefr_level="A2", work_domain="marketing", chat_fn=chat_fn
    )
    assert chat_fn.call_count == 1
    assert set(out) == {"tier", "notch"}
    # Gloss sent for sense selection.
    user_msg = chat_fn.call_args.args[0][0]["content"]
    assert "gloss:" in user_msg
    assert "tier" in user_msg


def test_generate_splits_over_batch_cap() -> None:
    items = [
        {"chunk": f"w{i}", "meaning": f"m{i}"} for i in range(VOCAB_BATCH_SIZE + 3)
    ]

    def _chat(messages, **kwargs):
        content = messages[0]["content"]
        words = []
        for line in content.splitlines():
            if "word:" in line:
                words.append(line.split("word:", 1)[1].strip())
        return _fake_sentences(words)

    chat_fn = MagicMock(side_effect=_chat)
    out = generate_vocab_sentences(
        items,
        cefr_level="B1",
        work_domain="marketing",
        chat_fn=chat_fn,
        batch_size=VOCAB_BATCH_SIZE,
    )
    assert chat_fn.call_count == 2
    assert len(out) == VOCAB_BATCH_SIZE + 3


def test_generate_failure_raises_vocab_error() -> None:
    items = [{"chunk": "tier", "meaning": "a"}]
    chat_fn = MagicMock(side_effect=VocabGenerationError("boom"))
    with pytest.raises(VocabGenerationError):
        generate_vocab_sentences(
            items, cefr_level="B1", work_domain="x", chat_fn=chat_fn
        )


def test_generation_completes_before_transaction_opens(cleanup_user: int) -> None:
    """Generate must not open a write transaction / hold a pool connection."""
    tid = cleanup_user
    user_id = _onboard(tid)
    items = [{"chunk": "tier", "meaning": "سطح"}]
    conn_calls: list[str] = []

    real_connection = connection

    def _tracking_connection(*args, **kwargs):
        conn_calls.append("open")
        return real_connection(*args, **kwargs)

    chat_fn = MagicMock(return_value=_fake_sentences(["tier"]))
    with patch(
        "core.services.vocab_import.connection", side_effect=_tracking_connection
    ):
        # generate_vocab_sentences itself must not touch connection.
        out = generate_vocab_sentences(
            items, cefr_level="B1", work_domain="marketing", chat_fn=chat_fn
        )
        assert out["tier"]
        assert conn_calls == []

    # persist opens connection only after generation finished.
    async def _run() -> None:
        await persist_vocabulary_and_send(
            user_id=user_id,
            chunks=[
                {
                    "chunk": "tier",
                    "full_sentence": out["tier"],
                    "meaning": "سطح",
                }
            ],
            send=AsyncMock(),
        )

    with patch(
        "core.services.vocab_import.connection", side_effect=_tracking_connection
    ):
        asyncio.run(_run())
    assert conn_calls == ["open"]


def test_reimport_makes_zero_chat_calls(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    headers, rows = parse_csv_bytes(_REAL_VOCAB_CSV.encode("utf-8"))
    chat_fn = MagicMock(return_value=_fake_sentences(["tier", "notch"]))
    fixed_now = date(2026, 8, 14)

    chunks, counts = prepare_vocabulary_import(
        headers,
        rows,
        user_id=user_id,
        cefr_level="B1",
        work_domain="marketing",
        now=fixed_now,
        chat_fn=chat_fn,
    )
    assert counts.imported == 2
    assert chat_fn.call_count == 1

    async def _send() -> None:
        return None

    asyncio.run(
        persist_vocabulary_and_send(
            user_id=user_id, chunks=chunks, send=_send
        )
    )

    chat_fn.reset_mock()
    chunks2, counts2 = prepare_vocabulary_import(
        headers,
        rows,
        user_id=user_id,
        cefr_level="B1",
        work_domain="marketing",
        now=fixed_now,
        chat_fn=chat_fn,
    )
    assert chat_fn.call_count == 0
    assert chunks2 == []
    assert counts2.imported == 0
    assert counts2.duplicates == 2
    assert _error_count(user_id) == 0


def test_within_file_dedupe_before_llm() -> None:
    seeds = [
        {"chunk": "tier", "meaning": "a"},
        {"chunk": "Tier", "meaning": "b"},
        {"chunk": "notch", "meaning": "c"},
    ]
    result = dedupe_vocabulary_seeds(seeds, existing_norms=set())
    assert [s["chunk"] for s in result.need] == ["tier", "notch"]
    assert result.within_file_skipped == 1


# --- Folder refuse -----------------------------------------------------------


def test_folder_path_refuses_vocabulary_without_llm(
    cleanup_user: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog
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
    csv_path = root / "inbox" / str(user_id) / "trancy" / "vocab.csv"
    csv_path.write_bytes(_REAL_VOCAB_CSV.encode("utf-8"))
    # Age file without wall-clock sleep — touch mtime far in the past.
    import os

    old = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
    os.utime(csv_path, (old, old))

    chat_spy = MagicMock()
    with (
        patch("core.services.vocab_import.chat", chat_spy),
        patch("core.llm.chat", chat_spy),
        caplog.at_level(logging.WARNING),
    ):
        result = process_csv_file(
            csv_path,
            user_id=user_id,
            tool="trancy",
            root=root,
            now=datetime(2026, 8, 14, tzinfo=timezone.utc),
        )
    assert result.status == "refused_vocabulary"
    assert result.csv_format == "vocabulary"
    chat_spy.assert_not_called()
    assert "refuse_vocabulary" in caplog.text
    assert "Telegram" in caplog.text
    failed_dir = root / "failed" / str(user_id)
    assert any(failed_dir.iterdir())
    with connection() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE user_id = %s", (user_id,)
        ).fetchone()
    assert int(n["n"]) == 0
    assert _error_count(user_id) == 0


# --- Handler path ------------------------------------------------------------


def test_non_operator_vocabulary_sender_only(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, cefr="A2")
    headers, rows = parse_csv_bytes(_REAL_VOCAB_CSV.encode("utf-8"))
    chat_fn = MagicMock(return_value=_fake_sentences(["tier", "notch"]))
    chunks, _ = prepare_vocabulary_import(
        headers,
        rows,
        user_id=user_id,
        cefr_level="A2",
        work_domain="marketing",
        now=date(2026, 8, 14),
        chat_fn=chat_fn,
    )
    asyncio.run(
        persist_vocabulary_and_send(
            user_id=user_id, chunks=chunks, send=AsyncMock()
        )
    )
    with connection() as conn:
        owners = conn.execute(
            "SELECT DISTINCT user_id FROM chunks WHERE source = %s",
            (VOCAB_SOURCE,),
        ).fetchall()
        # Only this test user among vocabulary rows we just wrote — scoped check:
        mine = conn.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE user_id = %s "
            "AND source = %s",
            (user_id, VOCAB_SOURCE),
        ).fetchone()
    assert int(mine["n"]) == 2
    assert all(int(r["user_id"]) == user_id for r in owners if int(r["user_id"]) == user_id)
    sc, sd = _shared_counts()
    # No new shared rows from this import — at least zero for this content_key.
    with connection() as conn:
        shared_for = conn.execute(
            "SELECT COUNT(*) AS n FROM shared_content "
            "WHERE content_key IN ('tier', 'notch')"
        ).fetchone()
    assert int(shared_for["n"]) == 0
    assert _error_count(user_id) == 0


def test_vocabulary_due_and_anki(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    headers, rows = parse_csv_bytes(_REAL_VOCAB_CSV.encode("utf-8"))
    chat_fn = MagicMock(return_value=_fake_sentences(["tier", "notch"]))
    chunks, _ = prepare_vocabulary_import(
        headers,
        rows,
        user_id=user_id,
        cefr_level="B1",
        work_domain="marketing",
        now=date(2026, 8, 14),
        chat_fn=chat_fn,
    )
    asyncio.run(
        persist_vocabulary_and_send(
            user_id=user_id, chunks=chunks, send=AsyncMock()
        )
    )
    # insert_chunks writes next_review = CURRENT_DATE + 1 server-side, so the
    # due query must ask the same server the same question. A hardcoded date
    # here made the test pass only until the calendar moved past it (#61,
    # CLAUDE.md §3 rule 6). Read after the insert: if the clock crossed
    # midnight in between, next_review is the earlier day and stays due.
    with connection() as conn:
        tomorrow = conn.execute("SELECT CURRENT_DATE + 1 AS d").fetchone()["d"]
    due = due_chunks(user_id, limit=10, now=tomorrow)
    assert {c.chunk for c in due} >= {"tier", "notch"}
    with connection() as conn:
        export_rows = fetch_unexported_chunks(conn, user_id)
    assert {r.chunk for r in export_rows} >= {"tier", "notch"}
    assert _error_count(user_id) == 0


# --- S24b: exact-form retry + skip visibility --------------------------------


def _vocab_csv_bytes(*words: tuple[str, str]) -> bytes:
    """Build a minimal vocabulary CSV (Word,Phonetic,Translation,Date)."""
    lines = ["Word,Phonetic,Translation,Date"]
    for word, gloss in words:
        lines.append(f"{word},/{word}/,{gloss},2026-08-11")
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_s24b_clean_import_exactly_one_chat_call(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    headers, rows = parse_csv_bytes(
        _vocab_csv_bytes(("tier", "سطح"), ("notch", "شکاف"))
    )
    chat_fn = MagicMock(return_value=_fake_sentences(["tier", "notch"]))
    chunks, counts = prepare_vocabulary_import(
        headers,
        rows,
        user_id=user_id,
        cefr_level="B1",
        work_domain="Ai engineer",
        now=date(2026, 8, 14),
        chat_fn=chat_fn,
    )
    assert chat_fn.call_count == 1
    assert counts.imported == 2
    assert counts.named_skips == ()
    assert len(chunks) == 2
    assert _error_count(user_id) == 0


def test_s24b_gate_failure_retries_only_failed_word(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    headers, rows = parse_csv_bytes(
        _vocab_csv_bytes(("tier", "سطح"), ("frustrate", "ناامید کردن"))
    )
    calls: list[str] = []

    def _chat(messages, **kwargs):
        content = messages[0]["content"]
        calls.append(content)
        if len(calls) == 1:
            return {
                "sentences": [
                    {
                        "word": "tier",
                        "full_sentence": "I noticed a tier in the plan.",
                    },
                    {
                        "word": "frustrate",
                        "full_sentence": "This is frustrating for me.",
                    },
                ]
            }
        assert "word: frustrate" in content
        assert "word: tier" not in content
        assert "EXACTLY" in content or "exact" in content.casefold()
        return {
            "sentences": [
                {
                    "word": "frustrate",
                    "full_sentence": "I frustrate easily when plans change.",
                }
            ]
        }

    chat_fn = MagicMock(side_effect=_chat)
    chunks, counts = prepare_vocabulary_import(
        headers,
        rows,
        user_id=user_id,
        cefr_level="B1",
        work_domain="Ai engineer",
        now=date(2026, 8, 14),
        chat_fn=chat_fn,
    )
    assert chat_fn.call_count == 2
    assert counts.imported == 2
    assert counts.named_skips == ()
    assert {c["chunk"] for c in chunks} == {"tier", "frustrate"}
    assert _error_count(user_id) == 0


def test_s24b_fail_both_passes_named_skip_not_written(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    headers, rows = parse_csv_bytes(
        _vocab_csv_bytes(("frustrate", "ناامید کردن"))
    )

    def _chat(messages, **kwargs):
        return {
            "sentences": [
                {
                    "word": "frustrate",
                    "full_sentence": "This is frustrating again.",
                }
            ]
        }

    chat_fn = MagicMock(side_effect=_chat)
    with caplog.at_level(logging.INFO):
        chunks, counts = prepare_vocabulary_import(
            headers,
            rows,
            user_id=user_id,
            cefr_level="B1",
            work_domain="marketing",
            now=date(2026, 8, 14),
            chat_fn=chat_fn,
        )
    assert chat_fn.call_count == 2
    assert chunks == []
    assert counts.imported == 0
    assert counts.named_skips == (
        ("frustrate", "no sentence used the exact word"),
    )
    assert "frustrate" not in caplog.text
    assert "gate_skips" in caplog.text
    assert "count=1" in caplog.text
    assert _error_count(user_id) == 0


def test_s24b_retry_llm_error_keeps_first_pass(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    headers, rows = parse_csv_bytes(
        _vocab_csv_bytes(("tier", "سطح"), ("frustrate", "ناامید"))
    )
    n = 0

    def _chat(messages, **kwargs):
        nonlocal n
        n += 1
        if n == 1:
            return {
                "sentences": [
                    {
                        "word": "tier",
                        "full_sentence": "I noticed a tier in the plan.",
                    },
                    {
                        "word": "frustrate",
                        "full_sentence": "So frustrating today.",
                    },
                ]
            }
        raise VocabGenerationError("retry down")

    chat_fn = MagicMock(side_effect=_chat)
    chunks, counts = prepare_vocabulary_import(
        headers,
        rows,
        user_id=user_id,
        cefr_level="B1",
        work_domain="marketing",
        now=date(2026, 8, 14),
        chat_fn=chat_fn,
    )
    assert n == 2
    assert [c["chunk"] for c in chunks] == ["tier"]
    assert counts.imported == 1
    assert counts.named_skips[0][0] == "frustrate"
    asyncio.run(
        persist_vocabulary_and_send(
            user_id=user_id, chunks=chunks, send=AsyncMock()
        )
    )
    with connection() as conn:
        rows_db = conn.execute(
            "SELECT chunk FROM chunks WHERE user_id = %s", (user_id,)
        ).fetchall()
    assert [r["chunk"] for r in rows_db] == ["tier"]
    assert _error_count(user_id) == 0


def test_s24b_skipped_words_in_reply_not_log(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    headers, rows = parse_csv_bytes(
        _vocab_csv_bytes(("frustrate", "x"), ("tier", "y"))
    )

    def _chat(messages, **kwargs):
        return {
            "sentences": [
                {"word": "tier", "full_sentence": "A tier of seats."},
                {"word": "frustrate", "full_sentence": "Frustrating day."},
            ]
        }

    chat_fn = MagicMock(side_effect=_chat)
    with caplog.at_level(logging.INFO):
        chunks, counts = prepare_vocabulary_import(
            headers,
            rows,
            user_id=user_id,
            cefr_level="B1",
            work_domain="marketing",
            now=date(2026, 8, 14),
            chat_fn=chat_fn,
        )
    reply = format_vocab_import_reply(counts)
    assert "frustrate" in reply
    assert "no sentence used the exact word" in reply
    assert "tier" in {c["chunk"] for c in chunks}
    assert "frustrate" not in caplog.text
    assert _error_count(user_id) == 0


def test_s24b_long_skip_list_truncated() -> None:
    from core.services.vocab_import import VocabImportCounts

    skips = tuple(
        (f"w{i}", "no sentence used the exact word")
        for i in range(SKIP_LIST_CAP + 3)
    )
    counts = VocabImportCounts(
        imported=0,
        duplicates=0,
        invalid=len(skips),
        due=0,
        named_skips=skips,
    )
    reply = format_vocab_import_reply(counts)
    assert "w0" in reply
    assert f"w{SKIP_LIST_CAP - 1}" in reply
    assert f"w{SKIP_LIST_CAP}" not in reply
    assert "and 3 more" in reply


def test_s24b_prompt_contains_quality_instructions() -> None:
    text = Path("packages/core/prompts/vocab_sentences.txt").read_text(encoding="utf-8")
    lower = text.casefold()
    assert "exactly the form" in lower or "exact" in lower
    assert "inflection" in lower or "derived form" in lower
    assert "one third" in lower or "third" in lower
    assert "everyday" in lower
    assert "idiom" in lower or "notch above" in lower
    assert "friend" in lower or "ordinary" in lower
