"""S14 load-up mode (M10): prep chunks, no errors/sessions, privacy."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, Update, User

from app import texts
from app.db import close_pool, connection
from app.handlers import prep as prep_handler
from app.llm import LLMError
from app.services.anki import build_tsv, fetch_unexported_chunks
from app.services.prep import (
    EXPECTED_CHUNKS,
    PrepValidationError,
    format_prep_reply,
    persist_and_send,
    prep_source,
    slugify_topic,
    validate_prep_payload,
)
from app.services.reading import normalize_for_match
from app.services.users import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_490_000_000

# Fixture topic names a company — must never appear in logs.
COMPANY_TOPIC = "AcmeCorpZX9 budget review"
TOPIC_OK = "marketing budget meeting"


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


def _onboard(tid: int, *, cefr: str = "B1", domain: str = "marketing") -> None:
    save_onboarding(
        tid,
        {
            "name": "Prep Test",
            "native_language": "fa",
            "cefr_level": cefr,
            "efset_baseline": 45,
            "work_domain": domain,
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": "07:00",
            "evening_time": "21:00",
        },
    )


def _chunk(
    phrase: str,
    *,
    sentence: str | None = None,
    meaning: str = "useful phrase",
) -> dict[str, str]:
    sent = sentence if sentence is not None else f"I want to {phrase} today."
    return {"chunk": phrase, "full_sentence": sent, "meaning": meaning}


def _good_llm(
    *,
    n_chunks: int = 10,
    break_index: int | None = None,
    track: Any = "work",
) -> dict[str, Any]:
    base = [
        "push back on",
        "circle back",
        "park that",
        "run the numbers",
        "align on",
        "flag a risk",
        "take offline",
        "ballpark figure",
        "move the needle",
        "close the loop",
        "extra phrase one",
        "extra phrase two",
    ]
    chunks = []
    for i in range(n_chunks):
        phrase = f"{base[i % len(base)]} v{i}"
        item = _chunk(phrase)
        if break_index is not None and i == break_index:
            item["full_sentence"] = "Nothing related here at all."
        chunks.append(item)
    return {
        "track": track,
        "chunks": chunks,
        "frames": [
            "I'd like to push back on ___ because ___",
            "Could we park ___ and come back to it ___?",
            "From my side, ___ looks ___.",
        ],
    }


def _chunk_rows(tid: int) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT chunk, full_sentence, meaning, source, track
              FROM chunks WHERE user_id = %s ORDER BY id
            """,
            (tid,),
        ).fetchall()
    return [dict(r) for r in rows]


def _error_count(tid: int) -> int:
    with connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM errors WHERE user_id = %s",
            (tid,),
        ).fetchone()
    assert row is not None
    return int(row["n"])


def _session_count(tid: int) -> int:
    with connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE user_id = %s",
            (tid,),
        ).fetchone()
    assert row is not None
    return int(row["n"])


def _make_update(tid: int, text: str) -> tuple[Update, MagicMock]:
    user = User(id=tid, first_name="A", is_bot=False)
    chat = Chat(id=tid, type="private")
    message = MagicMock(spec=Message)
    message.text = text
    message.chat_id = tid
    message.reply_text = AsyncMock()
    update = MagicMock(spec=Update)
    update.message = message
    update.effective_user = user
    return update, message


# --- Source / slug ------------------------------------------------------------


def test_prep_source_marker_format() -> None:
    assert prep_source("marketing budget meeting") == (
        "prep_marketing_budget_meeting"
    )
    assert slugify_topic("AcmeCorpZX9 Q3!") == "acmecorpzx9_q3"
    assert prep_source(COMPANY_TOPIC).startswith("prep_")
    assert "capture" not in prep_source(TOPIC_OK)
    assert "reading_" not in prep_source(TOPIC_OK)


# --- Validation ---------------------------------------------------------------


def test_validate_drops_chunk_not_in_sentence() -> None:
    raw = _good_llm(break_index=0)
    payload = validate_prep_payload(raw, topic=TOPIC_OK)
    assert len(payload.chunks) == 9
    for item in payload.chunks:
        assert normalize_for_match(item["chunk"]) in normalize_for_match(
            item["full_sentence"]
        )


def test_validate_rejects_when_all_chunks_bad() -> None:
    raw = _good_llm(n_chunks=3)
    for item in raw["chunks"]:
        item["full_sentence"] = "Nope."
    with pytest.raises(PrepValidationError):
        validate_prep_payload(raw, topic=TOPIC_OK)


def test_validate_track_null_on_omit_or_invalid() -> None:
    assert validate_prep_payload(
        _good_llm(track=None), topic=TOPIC_OK
    ).track is None
    assert validate_prep_payload(
        _good_llm(track=""), topic=TOPIC_OK
    ).track is None
    assert validate_prep_payload(
        _good_llm(track="marketing"), topic=TOPIC_OK
    ).track is None
    assert validate_prep_payload(
        _good_llm(track="work"), topic=TOPIC_OK
    ).track == "work"


def test_validate_never_invents_work_track() -> None:
    payload = validate_prep_payload(_good_llm(track=None), topic=TOPIC_OK)
    assert payload.track is None


def test_validate_caps_at_ten_chunks() -> None:
    raw = _good_llm(n_chunks=12)
    payload = validate_prep_payload(raw, topic=TOPIC_OK)
    assert len(payload.chunks) == EXPECTED_CHUNKS


# --- Persist ------------------------------------------------------------------


def test_persist_writes_prep_chunks_zero_errors_zero_sessions(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    payload = validate_prep_payload(_good_llm(), topic=TOPIC_OK)
    sent: list[str] = []

    async def send() -> None:
        sent.append("ok")

    n = asyncio.run(
        persist_and_send(user_id=tid, payload=payload, send=send)
    )
    assert n == 10
    assert sent == ["ok"]
    rows = _chunk_rows(tid)
    assert len(rows) == 10
    expected_source = prep_source(TOPIC_OK)
    assert all(r["source"] == expected_source for r in rows)
    assert expected_source.startswith("prep_")
    for r in rows:
        assert normalize_for_match(r["chunk"]) in normalize_for_match(
            r["full_sentence"]
        )
    assert _error_count(tid) == 0
    assert _session_count(tid) == 0


def test_persist_send_failure_rolls_back(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    payload = validate_prep_payload(_good_llm(), topic=TOPIC_OK)

    async def boom() -> None:
        raise RuntimeError("telegram down")

    with pytest.raises(RuntimeError):
        asyncio.run(
            persist_and_send(user_id=tid, payload=payload, send=boom)
        )
    assert _chunk_rows(tid) == []
    assert _error_count(tid) == 0
    assert _session_count(tid) == 0


def test_prep_chunks_in_anki_tsv(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    payload = validate_prep_payload(_good_llm(), topic=TOPIC_OK)

    async def send() -> None:
        return None

    asyncio.run(persist_and_send(user_id=tid, payload=payload, send=send))
    with connection() as conn:
        rows = fetch_unexported_chunks(conn, tid)
    tsv = build_tsv(rows, user_id=tid)
    assert prep_source(TOPIC_OK) in tsv
    assert "prep_" in tsv
    assert "capture" not in tsv
    assert "reading_" not in tsv


# --- Handler ------------------------------------------------------------------


def test_handler_success_persists_and_no_topic_in_logs(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    update, message = _make_update(tid, f"/prep {COMPANY_TOPIC}")
    context = MagicMock()
    context.args = COMPANY_TOPIC.split()
    context.bot.send_chat_action = AsyncMock()

    async def _run() -> None:
        with (
            patch(
                "app.handlers.prep.chat",
                return_value=_good_llm(),
            ),
            caplog.at_level(logging.INFO),
        ):
            await prep_handler.on_prep_command(update, context)

    asyncio.run(_run())
    message.reply_text.assert_awaited_once()
    reply = message.reply_text.await_args.args[0]
    assert texts.PREP_SECTION_CHUNKS in reply
    assert texts.PREP_SECTION_FRAMES in reply
    assert "▸" in reply
    rows = _chunk_rows(tid)
    assert len(rows) == 10
    assert all(r["source"] == prep_source(COMPANY_TOPIC) for r in rows)
    assert _error_count(tid) == 0
    assert _session_count(tid) == 0
    assert COMPANY_TOPIC not in caplog.text
    assert "AcmeCorpZX9" not in caplog.text
    assert f"user_id={tid}" in caplog.text
    assert "handler=prep" in caplog.text


def test_handler_partial_chunks_sends_and_warns(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    update, message = _make_update(tid, f"/prep {TOPIC_OK}")
    context = MagicMock()
    context.args = TOPIC_OK.split()
    context.bot.send_chat_action = AsyncMock()
    # 9 good + 1 broken → 9 after validation
    raw = _good_llm(n_chunks=10, break_index=5)

    async def _run() -> None:
        with (
            patch("app.handlers.prep.chat", return_value=raw),
            caplog.at_level(logging.WARNING),
        ):
            await prep_handler.on_prep_command(update, context)

    asyncio.run(_run())
    message.reply_text.assert_awaited_once()
    assert len(_chunk_rows(tid)) == 9
    assert any(
        "partial_chunks" in r.message and "count=9" in r.message
        for r in caplog.records
    )


def test_handler_bare_prep_usage_no_llm(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    update, message = _make_update(tid, "/prep")
    context = MagicMock()
    context.args = []

    with patch("app.handlers.prep.chat") as chat_mock:
        asyncio.run(prep_handler.on_prep_command(update, context))
    chat_mock.assert_not_called()
    message.reply_text.assert_awaited_once_with(texts.PREP_USAGE)


def test_handler_short_topic_usage_no_llm(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    update, message = _make_update(tid, "/prep ab")
    context = MagicMock()
    context.args = ["ab"]

    with patch("app.handlers.prep.chat") as chat_mock:
        asyncio.run(prep_handler.on_prep_command(update, context))
    chat_mock.assert_not_called()
    message.reply_text.assert_awaited_once_with(texts.PREP_USAGE)


def test_handler_over_length_no_llm(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    long_topic = "x" * (prep_handler._MAX_TOPIC_CHARS + 1)
    update, message = _make_update(tid, f"/prep {long_topic}")
    context = MagicMock()
    context.args = [long_topic]

    with patch("app.handlers.prep.chat") as chat_mock:
        asyncio.run(prep_handler.on_prep_command(update, context))
    chat_mock.assert_not_called()
    message.reply_text.assert_awaited_once_with(texts.PREP_TOO_LONG)


def test_handler_malformed_json_warm_degrade(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    update, message = _make_update(tid, f"/prep {TOPIC_OK}")
    context = MagicMock()
    context.args = TOPIC_OK.split()
    context.bot.send_chat_action = AsyncMock()

    async def _run() -> None:
        with (
            patch("app.handlers.prep.chat", return_value="not-json-object"),
            caplog.at_level(logging.WARNING),
        ):
            await prep_handler.on_prep_command(update, context)

    asyncio.run(_run())
    message.reply_text.assert_awaited_once_with(texts.PREP_FAILED)
    assert _chunk_rows(tid) == []
    assert any("raw=" in r.message for r in caplog.records)
    assert TOPIC_OK not in caplog.text


def test_handler_llm_error_warm_degrade(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    update, message = _make_update(tid, f"/prep {TOPIC_OK}")
    context = MagicMock()
    context.args = TOPIC_OK.split()
    context.bot.send_chat_action = AsyncMock()

    async def _run() -> None:
        with patch(
            "app.handlers.prep.chat",
            side_effect=LLMError("boom"),
        ):
            await prep_handler.on_prep_command(update, context)

    asyncio.run(_run())
    message.reply_text.assert_awaited_once_with(texts.LLM_FAILED)
    assert _chunk_rows(tid) == []


def test_handler_send_failure_no_chunks(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    update, message = _make_update(tid, f"/prep {TOPIC_OK}")
    message.reply_text = AsyncMock(
        side_effect=[RuntimeError("send failed"), None]
    )
    context = MagicMock()
    context.args = TOPIC_OK.split()
    context.bot.send_chat_action = AsyncMock()

    async def _run() -> None:
        with patch(
            "app.handlers.prep.chat",
            return_value=_good_llm(),
        ):
            await prep_handler.on_prep_command(update, context)

    asyncio.run(_run())
    assert _chunk_rows(tid) == []
    assert message.reply_text.await_count == 2
    assert message.reply_text.await_args.args[0] == texts.PREP_FAILED


def test_cefr_and_work_domain_reach_prompt(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid, cefr="C1", domain="product design")
    update, message = _make_update(tid, f"/prep {TOPIC_OK}")
    context = MagicMock()
    context.args = TOPIC_OK.split()
    context.bot.send_chat_action = AsyncMock()
    captured: dict[str, Any] = {}

    def fake_chat(messages: Any, **kwargs: Any) -> dict[str, Any]:
        captured["system"] = kwargs.get("system")
        captured["messages"] = messages
        return _good_llm()

    async def _run() -> None:
        with patch("app.handlers.prep.chat", side_effect=fake_chat):
            await prep_handler.on_prep_command(update, context)

    asyncio.run(_run())
    system = captured["system"]
    assert system is not None
    assert "C1" in system
    assert "product design" in system
    assert TOPIC_OK in captured["messages"][0]["content"]


def test_format_reply_separates_chunks_and_frames() -> None:
    body = format_prep_reply(
        topic=TOPIC_OK,
        chunks=[
            {
                "chunk": "push back on",
                "full_sentence": "I want to push back on that.",
                "meaning": "politely disagree",
            }
        ],
        frames=["I'd like to push back on ___ because ___"],
    )
    assert texts.PREP_TITLE.format(topic=TOPIC_OK) in body
    assert texts.PREP_SECTION_CHUNKS in body
    assert texts.PREP_SECTION_FRAMES in body
    assert "1. push back on — politely disagree" in body
    assert "▸ I'd like to push back on ___ because ___" in body
    # Frames section after phrases
    assert body.index(texts.PREP_SECTION_CHUNKS) < body.index(
        texts.PREP_SECTION_FRAMES
    )


def test_s14_button_labels_max_20() -> None:
    """S14 ships no buttons; keep the label loop for any future BTN_PREP_*."""
    labels = [
        getattr(texts, name)
        for name in dir(texts)
        if name.startswith("BTN_PREP")
    ]
    for label in labels:
        assert isinstance(label, str)
        assert len(label) <= 20, label
