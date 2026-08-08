"""Anki TSV export (S7 / M6)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update
from telegram.ext import ContextTypes

from app import texts
from app.db import close_pool, connection
from app.scheduler import EligibleUser, is_user_due_for_anki
from app.services.anki import (
    build_tsv,
    deliver_weekly,
    export_and_send,
    fetch_unexported_chunks,
    handle_anki_command,
    make_sentence_with_gap,
    row_fields,
    sanitize_tsv_field,
)
from app.services.sessions import (
    bot_initiated_count,
    has_anki_session_on,
    increment_bot_messages,
    local_today,
)
from app.services.users import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_470_000_000

# Saturday 2026-08-08 21:05 Vilnius (UTC+3 in August) — S11 moved Anki off Sunday
_SATURDAY_EVENING_UTC = datetime(2026, 8, 8, 18, 5, tzinfo=timezone.utc)
_SATURDAY_BEFORE_UTC = datetime(2026, 8, 8, 17, 59, tzinfo=timezone.utc)
_SUNDAY_EVENING_UTC = datetime(2026, 8, 9, 18, 5, tzinfo=timezone.utc)
_MONDAY_EVENING_UTC = datetime(2026, 8, 10, 18, 5, tzinfo=timezone.utc)


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


def _onboard(
    tid: int,
    *,
    evening: str = "21:00",
    morning: str = "07:00",
    tz: str = "Europe/Vilnius",
) -> None:
    save_onboarding(
        tid,
        {
            "name": "Anki Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": morning,
            "evening_time": evening,
        },
    )
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE users SET timezone = %s WHERE telegram_user_id = %s",
                (tz, tid),
            )


def _eligible(tid: int, *, evening: str = "21:00") -> EligibleUser:
    h, m = map(int, evening.split(":"))
    return EligibleUser(
        telegram_user_id=tid,
        timezone="Europe/Vilnius",
        morning_time=time(7, 0),
        paused_until=None,
        evening_time=time(h, m),
    )


def _insert_chunk(
    tid: int,
    *,
    chunk: str,
    full_sentence: str | None,
    meaning: str | None = "a meaning",
    source: str | None = "reading_1",
    track: str = "work",
    created_at: datetime | None = None,
) -> int:
    with connection() as conn:
        with conn.transaction():
            if created_at is None:
                row = conn.execute(
                    """
                    INSERT INTO chunks (
                        user_id, chunk, full_sentence, meaning, source, track,
                        exported_to_anki
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, FALSE
                    )
                    RETURNING id
                    """,
                    (tid, chunk, full_sentence, meaning, source, track),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    INSERT INTO chunks (
                        user_id, chunk, full_sentence, meaning, source, track,
                        exported_to_anki, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, FALSE, %s
                    )
                    RETURNING id
                    """,
                    (
                        tid,
                        chunk,
                        full_sentence,
                        meaning,
                        source,
                        track,
                        created_at,
                    ),
                ).fetchone()
    assert row is not None
    return int(row["id"])


def _exported_flags(tid: int) -> dict[int, bool]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, exported_to_anki FROM chunks
             WHERE user_id = %s ORDER BY id
            """,
            (tid,),
        ).fetchall()
    return {int(r["id"]): bool(r["exported_to_anki"]) for r in rows}


def _session_count(tid: int) -> int:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM sessions
             WHERE user_id = %s AND task_type = 'anki_export'
            """,
            (tid,),
        ).fetchone()
    return int(row["n"])


def _mock_app(send_side_effect: Exception | None = None) -> MagicMock:
    app = MagicMock()
    send = AsyncMock()
    if send_side_effect is not None:
        send.side_effect = send_side_effect
    app.bot.send_document = send
    return app


def _parse_tsv(tsv: str) -> list[list[str]]:
    lines = [ln for ln in tsv.split("\n") if ln != ""]
    return [ln.split("\t") for ln in lines]


# --- Gap generation -----------------------------------------------------------


def test_gap_mid_sentence() -> None:
    assert (
        make_sentence_with_gap("I need market research cycle today.", "market research cycle")
        == "I need _____ today."
    )


def test_gap_at_start() -> None:
    assert (
        make_sentence_with_gap("Brand positioning work closed the loop.", "Brand positioning work")
        == "_____ closed the loop."
    )


def test_gap_different_case() -> None:
    assert (
        make_sentence_with_gap("She joined the Stand-up meeting late.", "stand-up meeting")
        == "She joined the _____ late."
    )


def test_gap_curly_apostrophe() -> None:
    # chunk straight, sentence curly
    assert (
        make_sentence_with_gap("The client\u2019s email thread ran long.", "client's email thread")
        == "The _____ ran long."
    )
    # chunk curly, sentence straight
    assert (
        make_sentence_with_gap("The client's email thread ran long.", "client\u2019s email thread")
        == "The _____ ran long."
    )


def test_gap_not_found_falls_back(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.services.anki import ChunkExportRow, row_fields

    row = ChunkExportRow(
        id=42,
        chunk="missing phrase",
        full_sentence="Nothing related here.",
        meaning="m",
        source="s",
    )
    with caplog.at_level(logging.WARNING):
        fields = row_fields(row, user_id=99)
    assert fields == ("missing phrase", "missing phrase", "m", "s")
    assert len(fields) == 4
    assert any("chunk_not_in_sentence" in r.message for r in caplog.records)
    assert any("user_id=99" in r.message for r in caplog.records)
    assert any("chunk_id=42" in r.message for r in caplog.records)


def test_null_fields_become_empty_strings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.services.anki import ChunkExportRow

    row = ChunkExportRow(
        id=7,
        chunk="alone",
        full_sentence=None,
        meaning=None,
        source=None,
    )
    with caplog.at_level(logging.WARNING):
        fields = row_fields(row, user_id=1)
    assert fields == ("alone", "alone", "", "")
    assert "None" not in "\t".join(fields)
    assert any("empty_full_sentence" in r.message for r in caplog.records)


# --- TSV escaping -------------------------------------------------------------


def test_sanitize_tab_and_newline() -> None:
    assert sanitize_tsv_field("hello\tworld\nagain") == "hello world again"
    assert "\t" not in sanitize_tsv_field("a\tb")
    assert "\n" not in sanitize_tsv_field("a\nb")


def test_escaping_tab_newline_single_row_four_fields(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_chunk(
        tid,
        chunk="hello\tworld\nagain",
        full_sentence="Say hello\tworld\nagain please.",
        meaning="has\ttab\nand newline",
        source="src\twith\nbreaks",
    )
    with connection() as conn:
        rows = fetch_unexported_chunks(conn, tid)
    tsv = build_tsv(rows, user_id=tid)
    parsed = _parse_tsv(tsv)
    assert len(parsed) == 1
    assert len(parsed[0]) == 4
    for field in parsed[0]:
        assert "\t" not in field
        assert "\n" not in field
        assert "\r" not in field


def test_every_row_exactly_four_fields_mixed(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_chunk(
        tid,
        chunk="alpha",
        full_sentence="The alpha case is clear.",
        meaning="m1",
        source="s1",
    )
    _insert_chunk(
        tid,
        chunk="beta",
        full_sentence=None,
        meaning=None,
        source=None,
    )
    _insert_chunk(
        tid,
        chunk="gamma\tdelta",
        full_sentence="A gamma\tdelta phrase.",
        meaning="m\n3",
        source="s3",
    )
    with connection() as conn:
        rows = fetch_unexported_chunks(conn, tid)
    tsv = build_tsv(rows, user_id=tid)
    parsed = _parse_tsv(tsv)
    assert len(parsed) == 3
    for row in parsed:
        assert len(row) == 4


def test_ordering_created_at_ascending(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    t1 = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
    # Insert out of chronological order
    id_late = _insert_chunk(
        tid,
        chunk="third",
        full_sentence="The third item.",
        created_at=t3,
    )
    id_early = _insert_chunk(
        tid,
        chunk="first",
        full_sentence="The first item.",
        created_at=t1,
    )
    id_mid = _insert_chunk(
        tid,
        chunk="second",
        full_sentence="The second item.",
        created_at=t2,
    )
    with connection() as conn:
        rows = fetch_unexported_chunks(conn, tid)
    assert [r.id for r in rows] == [id_early, id_mid, id_late]
    tsv = build_tsv(rows, user_id=tid)
    answers = [r[1] for r in _parse_tsv(tsv)]
    assert answers == ["first", "second", "third"]


# --- Mark-after-send / idempotency --------------------------------------------


def test_mark_only_after_successful_send(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(
        tid,
        chunk="export me",
        full_sentence="Please export me now.",
    )
    day = local_today("Europe/Vilnius", _SATURDAY_EVENING_UTC)
    sent: list[tuple[bytes, str, str]] = []

    async def ok_send(data: bytes, filename: str, caption: str) -> None:
        sent.append((data, filename, caption))

    count = asyncio.run(
        export_and_send(
            user_id=tid,
            local_date=day,
            send_document=ok_send,
            claim_session=True,
            caption="cap",
        )
    )
    assert count == 1
    assert len(sent) == 1
    assert _exported_flags(tid)[cid] is True
    assert _session_count(tid) == 1
    assert sent[0][1] == f"english-bot-{day.isoformat()}.tsv"


def test_failed_send_leaves_unexported_and_no_session(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(
        tid,
        chunk="keep me",
        full_sentence="Please keep me unexported.",
    )
    day = local_today("Europe/Vilnius", _SATURDAY_EVENING_UTC)

    async def boom(_data: bytes, _filename: str, _caption: str) -> None:
        raise RuntimeError("telegram down")

    with pytest.raises(RuntimeError):
        asyncio.run(
            export_and_send(
                user_id=tid,
                local_date=day,
                send_document=boom,
                claim_session=True,
                caption="cap",
            )
        )
    assert _exported_flags(tid)[cid] is False
    assert _session_count(tid) == 0


def test_second_export_only_new_chunks(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_chunk(
        tid,
        chunk="old",
        full_sentence="The old card.",
    )
    day = local_today("Europe/Vilnius", _SATURDAY_EVENING_UTC)
    app = _mock_app()
    action = asyncio.run(deliver_weekly(app, tid, now=_SATURDAY_EVENING_UTC))
    assert action == "anki_export"
    assert app.bot.send_document.await_count == 1

    _insert_chunk(
        tid,
        chunk="new",
        full_sentence="The new card.",
    )
    # Manual path — no session claim; only unexported
    sent: list[bytes] = []

    async def capture(data: bytes, _f: str, _c: str) -> None:
        sent.append(data)

    count = asyncio.run(
        export_and_send(
            user_id=tid,
            local_date=day,
            send_document=capture,
            claim_session=False,
            caption="cap",
        )
    )
    assert count == 1
    parsed = _parse_tsv(sent[0].decode("utf-8"))
    assert len(parsed) == 1
    assert parsed[0][1] == "new"


# --- Weekly / command / ceiling -----------------------------------------------


def test_weekly_empty_sends_nothing(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    app = _mock_app()
    with caplog.at_level(logging.INFO):
        action = asyncio.run(deliver_weekly(app, tid, now=_SATURDAY_EVENING_UTC))
    assert action == "skipped_empty"
    assert app.bot.send_document.await_count == 0
    assert _session_count(tid) == 0
    assert any("nothing to export" in r.message for r in caplog.records)


def test_anki_command_empty_replies_without_document(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = tid
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = MagicMock()
    context.bot.send_document = AsyncMock()

    asyncio.run(handle_anki_command(update, context))

    update.message.reply_text.assert_awaited_once_with(texts.ANKI_EMPTY)
    context.bot.send_document.assert_not_awaited()


def test_ceiling_skips_weekly(
    cleanup_user: int, caplog: pytest.LogCaptureFixture
) -> None:
    tid = cleanup_user
    _onboard(tid)
    cid = _insert_chunk(
        tid,
        chunk="blocked",
        full_sentence="This blocked card stays.",
    )
    day = local_today("Europe/Vilnius", _SATURDAY_EVENING_UTC)
    for _ in range(3):
        increment_bot_messages(tid, day)
    app = _mock_app()
    with caplog.at_level(logging.WARNING):
        action = asyncio.run(deliver_weekly(app, tid, now=_SATURDAY_EVENING_UTC))
    assert action == "skipped_ceiling"
    assert app.bot.send_document.await_count == 0
    assert _exported_flags(tid)[cid] is False
    assert _session_count(tid) == 0
    assert any("ceiling_reached" in r.message for r in caplog.records)


def test_weekly_increments_ceiling_command_does_not(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_chunk(
        tid,
        chunk="one",
        full_sentence="The one card.",
    )
    day = local_today("Europe/Vilnius", _SATURDAY_EVENING_UTC)
    assert bot_initiated_count(tid, day) == 0
    app = _mock_app()
    assert asyncio.run(deliver_weekly(app, tid, now=_SATURDAY_EVENING_UTC)) == "anki_export"
    assert bot_initiated_count(tid, day) == 1

    _insert_chunk(
        tid,
        chunk="two",
        full_sentence="The two card.",
    )
    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = tid
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = MagicMock()
    context.bot.send_document = AsyncMock()
    asyncio.run(handle_anki_command(update, context))
    assert bot_initiated_count(tid, day) == 1
    context.bot.send_document.assert_awaited()


def test_weekly_poll_twice_one_document(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    _insert_chunk(
        tid,
        chunk="once",
        full_sentence="Export once only.",
    )
    app = _mock_app()
    user = _eligible(tid)
    assert is_user_due_for_anki(user, _SATURDAY_EVENING_UTC) is True

    action1 = asyncio.run(deliver_weekly(app, tid, now=_SATURDAY_EVENING_UTC))
    assert action1 == "anki_export"
    assert is_user_due_for_anki(user, _SATURDAY_EVENING_UTC) is False

    action2 = asyncio.run(deliver_weekly(app, tid, now=_SATURDAY_EVENING_UTC))
    assert action2 == "skipped_existing"
    assert app.bot.send_document.await_count == 1
    assert _session_count(tid) == 1
    assert has_anki_session_on(
        tid, local_today("Europe/Vilnius", _SATURDAY_EVENING_UTC)
    )


def test_eligibility_saturday_evening_only(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    user = _eligible(tid)
    assert is_user_due_for_anki(user, _SATURDAY_EVENING_UTC) is True
    assert is_user_due_for_anki(user, _SATURDAY_BEFORE_UTC) is False
    assert is_user_due_for_anki(user, _SUNDAY_EVENING_UTC) is False
    assert is_user_due_for_anki(user, _MONDAY_EVENING_UTC) is False
