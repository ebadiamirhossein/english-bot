"""S15 real-life capture (M11): chunks only, dispatch-safe, privacy."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, Update, User

from apps.bot import texts
from core.db import close_pool, connection
from apps.bot.handlers import capture as capture_handler
from core.llm import LLMError
from core.services.anki import build_tsv, fetch_unexported_chunks
from core.services.capture import (
    CAPTURE_SOURCE,
    CaptureValidationError,
    format_capture_reply,
    persist_and_send,
    target_chunk_count,
    validate_capture_payload,
)
from core.services.reading import normalize_for_match
from core.services.sessions import has_session_on
from core.services.identity import save_onboarding
FAKE_TELEGRAM_ID_BASE = 9_480_000_000

PII_NAME = "MiraChenZX9"
PII_FIGURE = "€42,750"
PRIVATE_PROSE = (
    f"Please send the Q3 forecast to {PII_NAME} by Friday "
    f"({PII_FIGURE}). We can circle back after the standup."
)

PASSAGE_OK = (
    "Could you circle back on the proposal by Friday? "
    "Happy to jump on a quick call if that helps."
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


def _onboard(tid: int) -> int:
    user_id = save_onboarding(
        tid,
        {
            "name": "Capture Test",
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


def _good_llm(
    *,
    track: Any = None,
    with_pii_carriers: bool = False,
) -> dict[str, Any]:
    if with_pii_carriers:
        return {
            "ok": True,
            "explanation": "A polite work follow-up asking for a reply.",
            "track": "work",
            "chunks": [
                {
                    "chunk": "circle back",
                    "full_sentence": (
                        f"Please ask {PII_NAME} to circle back ({PII_FIGURE})."
                    ),
                    "meaning": "return to a topic later",
                }
            ],
        }
    return {
        "ok": True,
        "explanation": "A polite work follow-up asking for a reply.",
        "track": track,
        "chunks": [
            {
                "chunk": "circle back",
                "full_sentence": "Could you circle back on the proposal?",
                "meaning": "return to a topic later",
            },
            {
                "chunk": "jump on a quick call",
                "full_sentence": "Happy to jump on a quick call if that helps.",
                "meaning": "have a short phone or video meeting",
            },
        ],
    }


def _sanitized_pii_llm() -> dict[str, Any]:
    """Prompt-contract mock: generic carriers, no name/figure."""
    return {
        "ok": True,
        "explanation": "A work email asking for a forecast by a deadline.",
        "track": None,
        "chunks": [
            {
                "chunk": "by Friday",
                "full_sentence": "Please send the forecast by Friday.",
                "meaning": "before the end of the week",
            },
            {
                "chunk": "circle back",
                "full_sentence": "We can circle back after the meeting.",
                "meaning": "return to discuss again",
            },
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


# --- Validation ---------------------------------------------------------------


def test_target_chunk_count_adaptive() -> None:
    assert target_chunk_count("short slack note here now") == 1
    long = " ".join(["word"] * 120)
    assert target_chunk_count(long) == 3
    huge = " ".join(["word"] * 400)
    assert target_chunk_count(huge) == 5


def test_validate_drops_chunk_not_in_sentence() -> None:
    raw = _good_llm()
    raw["chunks"][0]["full_sentence"] = "Nothing related here."
    payload = validate_capture_payload(raw)
    assert len(payload.chunks) == 1
    assert payload.chunks[0]["chunk"] == "jump on a quick call"


def test_validate_rejects_when_all_chunks_bad() -> None:
    raw = _good_llm()
    for item in raw["chunks"]:
        item["full_sentence"] = "Nope."
    with pytest.raises(CaptureValidationError):
        validate_capture_payload(raw)


def test_validate_ok_false() -> None:
    with pytest.raises(CaptureValidationError):
        validate_capture_payload({"ok": False, "chunks": []})


def test_validate_track_null_on_omit_or_invalid() -> None:
    assert validate_capture_payload(_good_llm(track=None)).track is None
    assert validate_capture_payload(_good_llm(track="")).track is None
    assert validate_capture_payload(_good_llm(track="marketing")).track is None
    assert validate_capture_payload(_good_llm(track="work")).track == "work"


def test_validate_normalises_chunk_match() -> None:
    raw = {
        "ok": True,
        "explanation": "Polite follow-up wording.",
        "track": None,
        "chunks": [
            {
                "chunk": "circle back",
                "full_sentence": "Could you Circle  Back on this?",
                "meaning": "return later",
            }
        ],
    }
    payload = validate_capture_payload(raw)
    assert len(payload.chunks) == 1
    assert (
        normalize_for_match("circle back")
        in normalize_for_match(payload.chunks[0]["full_sentence"])
    )


def test_validate_does_not_redact_pii_in_code() -> None:
    """No Python redaction — a PII-laden mock still validates if chunk matches."""
    payload = validate_capture_payload(_good_llm(with_pii_carriers=True))
    assert PII_NAME in payload.chunks[0]["full_sentence"]
    assert PII_FIGURE in payload.chunks[0]["full_sentence"]


# --- Persist ------------------------------------------------------------------


def test_persist_writes_chunks_zero_errors(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    payload = validate_capture_payload(_good_llm(track=None))
    sent: list[str] = []

    async def send() -> None:
        sent.append("ok")

    n = asyncio.run(
        persist_and_send(user_id=user_id, payload=payload, send=send)
    )
    assert n == 2
    assert sent == ["ok"]
    rows = _chunk_rows(user_id)
    assert len(rows) == 2
    assert all(r["source"] == CAPTURE_SOURCE for r in rows)
    assert all(r["track"] is None for r in rows)
    for r in rows:
        assert normalize_for_match(r["chunk"]) in normalize_for_match(
            r["full_sentence"]
        )
    assert _error_count(user_id) == 0
    assert has_session_on(user_id, date(2026, 8, 9)) is False


def test_persist_send_failure_rolls_back(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    payload = validate_capture_payload(_good_llm())

    async def boom() -> None:
        raise RuntimeError("telegram down")

    with pytest.raises(RuntimeError):
        asyncio.run(
            persist_and_send(user_id=user_id, payload=payload, send=boom)
        )
    assert _chunk_rows(user_id) == []
    assert _error_count(user_id) == 0


def test_pii_fixture_sanitized_carriers_persist(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    payload = validate_capture_payload(_sanitized_pii_llm())

    async def send() -> None:
        return None

    asyncio.run(persist_and_send(user_id=user_id, payload=payload, send=send))
    rows = _chunk_rows(user_id)
    assert rows
    blob = " ".join(
        f"{r['chunk']} {r['full_sentence']} {r['meaning']}" for r in rows
    )
    assert PII_NAME not in blob
    assert PII_FIGURE not in blob
    assert "€" not in blob


def test_captured_chunks_in_anki_tsv(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    payload = validate_capture_payload(_good_llm())

    async def send() -> None:
        return None

    asyncio.run(persist_and_send(user_id=user_id, payload=payload, send=send))
    with connection() as conn:
        rows = fetch_unexported_chunks(conn, user_id)
    tsv = build_tsv(rows, user_id=user_id)
    assert CAPTURE_SOURCE in tsv
    assert "circle back" in tsv
    assert "reading_" not in tsv


# --- Handler ------------------------------------------------------------------


def test_handler_success_no_errors_no_body_in_logs(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    update, message = _make_update(tid, PRIVATE_PROSE)
    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()

    async def _run() -> None:
        with (
            patch(
                "apps.bot.handlers.capture.chat",
                return_value=_sanitized_pii_llm(),
            ),
            caplog.at_level(logging.INFO),
        ):
            await capture_handler._run_capture(update, context, PRIVATE_PROSE)

    asyncio.run(_run())
    message.reply_text.assert_awaited_once()
    reply = message.reply_text.await_args.args[0]
    assert "by Friday" in reply or "circle back" in reply
    assert texts.CAPTURE_SELF_HINT in reply or len(reply) <= 400
    assert _error_count(user_id) == 0
    assert PII_NAME not in caplog.text
    assert PII_FIGURE not in caplog.text
    assert PRIVATE_PROSE not in caplog.text
    assert f"user_id={user_id}" in caplog.text
    assert "handler=capture" in caplog.text


def test_handler_over_length_no_llm(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    long_text = "x" * (capture_handler._MAX_CHARS + 1)
    update, message = _make_update(tid, long_text)
    context = MagicMock()
    context.args = []
    # Use command path with args
    context.args = [long_text]
    update.message.text = f"/capture {long_text}"

    with patch("apps.bot.handlers.capture.chat") as chat_mock:
        asyncio.run(capture_handler.on_capture_command(update, context))
    chat_mock.assert_not_called()
    message.reply_text.assert_awaited_once_with(texts.CAPTURE_TOO_LONG)


def test_handler_under_length_no_llm(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    update, message = _make_update(tid, "too short")
    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()

    with patch("apps.bot.handlers.capture.chat") as chat_mock:
        asyncio.run(
            capture_handler.on_forwarded_capture(update, context)
        )
    chat_mock.assert_not_called()
    message.reply_text.assert_awaited_once_with(texts.CAPTURE_TOO_SHORT)


def test_handler_bare_capture_usage_no_llm(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    update, message = _make_update(tid, "/capture")
    context = MagicMock()
    context.args = []

    with patch("apps.bot.handlers.capture.chat") as chat_mock:
        asyncio.run(capture_handler.on_capture_command(update, context))
    chat_mock.assert_not_called()
    message.reply_text.assert_awaited_once_with(texts.CAPTURE_USAGE)


def test_handler_malformed_json_warm_degrade(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    update, message = _make_update(tid, PASSAGE_OK)
    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()

    async def _run() -> None:
        with (
            patch("apps.bot.handlers.capture.chat", return_value="not-json-object"),
            caplog.at_level(logging.WARNING),
        ):
            await capture_handler._run_capture(update, context, PASSAGE_OK)

    asyncio.run(_run())
    message.reply_text.assert_awaited_once_with(texts.CAPTURE_FAILED)
    assert _chunk_rows(user_id) == []
    assert any("raw=" in r.message for r in caplog.records)
    assert PASSAGE_OK not in caplog.text


def test_handler_llm_error_warm_degrade(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    update, message = _make_update(tid, PASSAGE_OK)
    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()

    async def _run() -> None:
        with patch(
            "apps.bot.handlers.capture.chat",
            side_effect=LLMError("boom"),
        ):
            await capture_handler._run_capture(update, context, PASSAGE_OK)

    asyncio.run(_run())
    message.reply_text.assert_awaited_once_with(texts.LLM_FAILED)
    assert _chunk_rows(user_id) == []


def test_handler_ok_false_warm_degrade(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    update, message = _make_update(tid, PASSAGE_OK)
    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()

    async def _run() -> None:
        with patch(
            "apps.bot.handlers.capture.chat",
            return_value={"ok": False, "chunks": []},
        ):
            await capture_handler._run_capture(update, context, PASSAGE_OK)

    asyncio.run(_run())
    message.reply_text.assert_awaited_once_with(texts.CAPTURE_NOTHING_USEFUL)
    assert _chunk_rows(user_id) == []
    assert _error_count(user_id) == 0


def test_handler_send_failure_no_chunks(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    update, message = _make_update(tid, PASSAGE_OK)
    # First reply (capture body) fails; soft CAPTURE_FAILED succeeds.
    message.reply_text = AsyncMock(
        side_effect=[RuntimeError("send failed"), None]
    )
    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()

    async def _run() -> None:
        with patch(
            "apps.bot.handlers.capture.chat",
            return_value=_good_llm(),
        ):
            await capture_handler._run_capture(update, context, PASSAGE_OK)

    asyncio.run(_run())
    assert _chunk_rows(user_id) == []
    assert message.reply_text.await_count == 2
    assert message.reply_text.await_args.args[0] == texts.CAPTURE_FAILED


def test_format_reply_includes_hint_when_short() -> None:
    body = format_capture_reply(
        explanation="A short follow-up.",
        chunks=[
            {
                "chunk": "circle back",
                "full_sentence": "x",
                "meaning": "return later",
            }
        ],
        hint=texts.CAPTURE_SELF_HINT,
    )
    assert texts.CAPTURE_SELF_HINT in body
    assert len(body) <= 400


def test_s15_button_labels_max_20() -> None:
    """S15 ships no buttons; keep the label loop for any future BTN_CAPTURE_*."""
    labels = [
        getattr(texts, name)
        for name in dir(texts)
        if name.startswith("BTN_CAPTURE")
    ]
    for label in labels:
        assert isinstance(label, str)
        assert len(label) <= 20, label
