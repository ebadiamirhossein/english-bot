"""S18a /settings editor — tapped-only field writes, stale degrade, labels."""

from __future__ import annotations

import asyncio
import uuid
from datetime import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import BadRequest
from telegram.ext import ConversationHandler, MessageHandler

from apps.bot import texts
from core.db import close_pool, connection
from apps.bot.handlers.settings import (
    MENU,
    WEIGHTS,
    _WEIGHT_PRESETS,
    build_settings_editor_handler,
    field_callback,
    menu_callback,
    on_settings_command,
    on_settings_orphan_callback,
    parse_settings_time_callback,
    s18a_button_labels,
)
from core.services.users import (
    get_user,
    save_onboarding,
    update_cefr_level,
)

FAKE_TELEGRAM_ID_BASE = 9_490_000_000


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


def _onboard(tid: int, **overrides: object) -> None:
    data: dict[str, object] = {
        "name": "Settings Test",
        "native_language": "fa",
        "cefr_level": "B1",
        "efset_baseline": 45,
        "work_domain": "marketing",
        "why_statement": "Speak without freezing up",
        "track_weights": {"work": 40, "life": 40, "curiosity": 20},
        "morning_time": "08:00",
        "evening_time": "21:00",
    }
    data.update(overrides)
    save_onboarding(tid, data)


def _row(tid: int) -> dict:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT track_weights, morning_time, evening_time,
                   explanation_language_fallback, cefr_level,
                   work_domain, why_statement, name
              FROM users
             WHERE telegram_user_id = %s
            """,
            (tid,),
        ).fetchone()
    assert row is not None
    return dict(row)


def _ctx(*, chat_id: int = 20, message_id: int = 10) -> MagicMock:
    context = MagicMock()
    context.user_data = {
        "settings": {
            "wizard_chat_id": chat_id,
            "wizard_message_id": message_id,
            "wizard_state": MENU,
        }
    }
    context.bot = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    return context


def _callback_update(tid: int, data: str) -> MagicMock:
    msg = MagicMock()
    msg.edit_text = AsyncMock()
    msg.message_id = 10
    msg.chat_id = tid
    cq = MagicMock()
    cq.data = data
    cq.answer = AsyncMock()
    cq.message = msg
    update = MagicMock()
    update.callback_query = cq
    update.effective_user = MagicMock(id=tid)
    update.effective_message = msg
    update.message = None
    return update


# --- writers ------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["balanced", "work", "life", "mostly"],
)
def test_weight_preset_writes_only_track_weights(
    cleanup_user: int, key: str
) -> None:
    tid = cleanup_user
    _onboard(tid)
    before = _row(tid)
    expected = _WEIGHT_PRESETS[key]

    update = _callback_update(tid, f"set:weights:{key}")
    context = _ctx()
    result = asyncio.run(field_callback(update, context))

    assert result == MENU
    after = _row(tid)
    assert dict(after["track_weights"]) == expected
    assert after["morning_time"] == before["morning_time"]
    assert after["evening_time"] == before["evening_time"]
    assert (
        after["explanation_language_fallback"]
        == before["explanation_language_fallback"]
    )
    assert after["cefr_level"] == before["cefr_level"]
    assert after["work_domain"] == before["work_domain"]
    assert after["why_statement"] == before["why_statement"]
    assert after["name"] == before["name"]


def test_morning_evening_round_trip_preserves_07_00(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid, morning_time="08:00", evening_time="21:00")

    assert parse_settings_time_callback("set:morning:07:00") == "07:00"
    assert parse_settings_time_callback("set:evening:19:00") == "19:00"
    # Naive split(":") would truncate 07:00 → 07
    naive = "set:morning:07:00".split(":")
    assert naive[2] == "07"
    assert naive[2] != "07:00"

    update = _callback_update(tid, "set:morning:07:00")
    context = _ctx()
    asyncio.run(field_callback(update, context))
    user = get_user(tid)
    assert user is not None
    assert user.morning_time == time(7, 0)

    update = _callback_update(tid, "set:evening:19:00")
    context = _ctx()
    asyncio.run(field_callback(update, context))
    user = get_user(tid)
    assert user is not None
    assert user.evening_time == time(19, 0)


def test_fallback_toggle_flips_and_persists(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    with connection() as conn:
        conn.execute(
            """
            UPDATE users
               SET explanation_language_fallback = TRUE
             WHERE telegram_user_id = %s
            """,
            (tid,),
        )
    assert get_user(tid).explanation_language_fallback is True

    update = _callback_update(tid, "set:fallback:off")
    context = _ctx()
    asyncio.run(field_callback(update, context))
    assert get_user(tid).explanation_language_fallback is False

    update = _callback_update(tid, "set:fallback:on")
    context = _ctx()
    asyncio.run(field_callback(update, context))
    assert get_user(tid).explanation_language_fallback is True


def test_menu_shows_current_values_before_choice(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(
        tid,
        track_weights={"work": 60, "life": 25, "curiosity": 15},
        morning_time="07:00",
        evening_time="20:00",
        cefr_level="B2",
    )
    with connection() as conn:
        conn.execute(
            """
            UPDATE users
               SET explanation_language_fallback = FALSE
             WHERE telegram_user_id = %s
            """,
            (tid,),
        )

    msg = MagicMock()
    msg.reply_text = AsyncMock(
        return_value=MagicMock(message_id=42, chat_id=tid)
    )
    update = MagicMock()
    update.message = msg
    update.effective_user = MagicMock(id=tid)
    update.effective_message = msg
    update.callback_query = None
    context = MagicMock()
    context.user_data = {}

    result = asyncio.run(on_settings_command(update, context))
    assert result == MENU
    body = msg.reply_text.await_args.args[0]
    assert "60/25/15" in body
    assert "07:00" in body
    assert "20:00" in body
    assert texts.SETTINGS_FALLBACK_OFF in body
    assert "B2" in body
    assert "/stats" in body
    assert "/interests" in body
    assert "/pause" in body


def test_weights_screen_shows_current_mix(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid, track_weights={"work": 25, "life": 60, "curiosity": 15})
    update = _callback_update(tid, "set:menu:weights")
    context = _ctx()
    result = asyncio.run(menu_callback(update, context))
    assert result == WEIGHTS
    edited = context.bot.edit_message_text.await_args.kwargs["text"]
    assert "25/60/15" in edited


def test_cefr_level_displayed_but_never_written(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid, cefr_level="B1")
    update_cefr_level(tid, "B1")

    msg = MagicMock()
    msg.reply_text = AsyncMock(
        return_value=MagicMock(message_id=42, chat_id=tid)
    )
    update = MagicMock()
    update.message = msg
    update.effective_user = MagicMock(id=tid)
    update.effective_message = msg
    update.callback_query = None
    context = MagicMock()
    context.user_data = {}
    asyncio.run(on_settings_command(update, context))
    body = msg.reply_text.await_args.args[0]
    assert "B1" in body
    assert "/stats" in body

    # No set: callback writes cefr — exercise every field write.
    for data in (
        "set:weights:mostly",
        "set:morning:09:00",
        "set:evening:19:00",
        "set:fallback:off",
    ):
        asyncio.run(field_callback(_callback_update(tid, data), _ctx()))
    assert _row(tid)["cefr_level"] == "B1"

    handler = build_settings_editor_handler()
    patterns: list[str] = []
    for handlers in handler.states.values():
        for h in handlers:
            for ep in h.entry_points:
                pat = getattr(ep, "pattern", None)
                if pat is not None:
                    patterns.append(pat.pattern if hasattr(pat, "pattern") else str(pat))
    joined = " ".join(patterns)
    assert "cefr" not in joined.lower()


def test_double_tap_does_not_raise(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    update = _callback_update(tid, "set:weights:balanced")
    context = _ctx()
    context.bot.edit_message_text = AsyncMock(
        side_effect=BadRequest("Message is not modified")
    )
    result = asyncio.run(field_callback(update, context))
    assert result == MENU


def test_writes_scoped_second_user_untouched(cleanup_user: int) -> None:
    tid_a = cleanup_user
    tid_b = FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)
    while tid_b == tid_a:
        tid_b = FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)
    _delete_user(tid_b)
    try:
        _onboard(tid_a)
        _onboard(
            tid_b,
            track_weights={"work": 40, "life": 40, "curiosity": 20},
            morning_time="08:00",
        )
        before_b = _row(tid_b)

        asyncio.run(
            field_callback(
                _callback_update(tid_a, "set:weights:mostly"), _ctx()
            )
        )
        asyncio.run(
            field_callback(
                _callback_update(tid_a, "set:morning:07:00"), _ctx()
            )
        )

        after_b = _row(tid_b)
        assert dict(after_b["track_weights"]) == dict(
            before_b["track_weights"]
        )
        assert after_b["morning_time"] == before_b["morning_time"]
        assert dict(_row(tid_a)["track_weights"]) == _WEIGHT_PRESETS["mostly"]
    finally:
        _delete_user(tid_b)


def test_stale_callback_cleared_user_data_no_exception(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    update = _callback_update(tid, "set:menu:weights")
    context = MagicMock()
    context.user_data = {}  # restart wiped in-flight state
    context.bot = MagicMock()

    result = asyncio.run(menu_callback(update, context))
    assert result == ConversationHandler.END
    update.callback_query.answer.assert_awaited()
    update.callback_query.message.edit_text.assert_awaited()
    body = update.callback_query.message.edit_text.await_args.args[0]
    assert texts.SETTINGS_STALE in body
    assert get_user(tid).track_weights == {
        "work": 40,
        "life": 40,
        "curiosity": 20,
    }


def test_orphan_set_callback_degrades_warmly(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    update = _callback_update(tid, "set:menu:weights")
    context = MagicMock()
    context.user_data = {}
    asyncio.run(on_settings_orphan_callback(update, context))
    update.callback_query.message.edit_text.assert_awaited()
    assert texts.SETTINGS_STALE in (
        update.callback_query.message.edit_text.await_args.args[0]
    )


def test_no_message_handler_in_settings_editor() -> None:
    handler = build_settings_editor_handler()
    assert handler.conversation_timeout is None
    for state_handlers in handler.states.values():
        for h in state_handlers:
            assert not isinstance(h, MessageHandler)
            for ep in getattr(h, "entry_points", []):
                assert not isinstance(ep, MessageHandler)
    for fb in handler.fallbacks:
        assert type(fb).__name__ == "CommandHandler"


def test_s18a_button_labels_max_20() -> None:
    for label in s18a_button_labels():
        assert len(label) <= 20, f"{label!r} is {len(label)} chars"


def test_morning_evening_presets_match_onboarding() -> None:
    from apps.bot.handlers.settings import _EVENING_TIMES, _MORNING_TIMES

    assert _MORNING_TIMES == ("07:00", "08:00", "09:00")
    assert _EVENING_TIMES == ("19:00", "20:00", "21:00")
