"""S14 load-up mode (M10): prep chunks, no errors/sessions, privacy."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Chat, Message, Update, User

from core.db import close_pool, connection
from core.services.anki import build_tsv, fetch_unexported_chunks
from core.services.prep import (
    EXPECTED_CHUNKS,
    PrepValidationError,
    persist_and_send,
    prep_source,
    slugify_topic,
    validate_prep_payload,
)
from core.services.reading import normalize_for_match
from core.services.identity import save_onboarding
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


def _onboard(tid: int, *, cefr: str = "B1", domain: str = "marketing") -> int:
    user_id = save_onboarding(
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
    return user_id


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
    user_id = _onboard(tid)
    payload = validate_prep_payload(_good_llm(), topic=TOPIC_OK)
    sent: list[str] = []

    async def send() -> None:
        sent.append("ok")

    n = asyncio.run(
        persist_and_send(user_id=user_id, payload=payload, send=send)
    )
    assert n == 10
    assert sent == ["ok"]
    rows = _chunk_rows(user_id)
    assert len(rows) == 10
    expected_source = prep_source(TOPIC_OK)
    assert all(r["source"] == expected_source for r in rows)
    assert expected_source.startswith("prep_")
    for r in rows:
        assert normalize_for_match(r["chunk"]) in normalize_for_match(
            r["full_sentence"]
        )
    assert _error_count(user_id) == 0
    assert _session_count(user_id) == 0


def test_persist_send_failure_rolls_back(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    payload = validate_prep_payload(_good_llm(), topic=TOPIC_OK)

    async def boom() -> None:
        raise RuntimeError("telegram down")

    with pytest.raises(RuntimeError):
        asyncio.run(
            persist_and_send(user_id=user_id, payload=payload, send=boom)
        )
    assert _chunk_rows(user_id) == []
    assert _error_count(user_id) == 0
    assert _session_count(user_id) == 0


def test_prep_chunks_in_anki_tsv(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    payload = validate_prep_payload(_good_llm(), topic=TOPIC_OK)

    async def send() -> None:
        return None

    asyncio.run(persist_and_send(user_id=user_id, payload=payload, send=send))
    with connection() as conn:
        rows = fetch_unexported_chunks(conn, user_id)
    tsv = build_tsv(rows, user_id=user_id)
    assert prep_source(TOPIC_OK) in tsv
    assert "prep_" in tsv
    assert "capture" not in tsv
    assert "reading_" not in tsv


# --- Handler ------------------------------------------------------------------


