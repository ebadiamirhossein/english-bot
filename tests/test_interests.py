"""Interests profile (S9) — save, replace, preserve, min-2, free-text, layout."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from apps.bot import texts
from core.db import close_pool, connection
from apps.bot.handlers.interests import (
    build_option_list,
    can_proceed,
    done_button_label,
    topic_button_label,
    track_ask_body,
    track_topic_button_rows,
)
from core.services.interests import list_interests, replace_interests
from core.services.identity import save_onboarding
FAKE_TELEGRAM_ID_BASE = 9_450_000_000


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
            "name": "Interests Test",
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


def _full_seed() -> list[tuple[str, str]]:
    return [
        ("campaigns", "work"),
        ("negotiation", "work"),
        ("apartments", "life"),
        ("travel", "life"),
        ("space", "curiosity"),
        ("history", "curiosity"),
    ]


def test_save_writes_one_row_per_topic_lowercased(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    replace_interests(
        user_id,
        [
            ("  Campaigns ", "work"),
            ("Client Email", "work"),
            ("Apartments", "life"),
            ("Travel", "life"),
            ("Space", "curiosity"),
            ("History", "curiosity"),
        ],
    )
    rows = list_interests(user_id)
    assert len(rows) == 6
    by_topic = {r.topic: r for r in rows}
    assert set(by_topic) == {
        "campaigns",
        "client email",
        "apartments",
        "travel",
        "space",
        "history",
    }
    assert by_topic["campaigns"].track == "work"
    assert by_topic["client email"].track == "work"
    assert by_topic["apartments"].track == "life"
    assert by_topic["space"].track == "curiosity"
    for row in rows:
        assert row.weight == 1.0
        assert row.last_used is None


def test_rerun_replaces_rather_than_duplicates(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    replace_interests(user_id, _full_seed())
    replace_interests(
        user_id,
        [
            ("pricing", "work"),
            ("interviews", "work"),
            ("cooking", "life"),
            ("humour", "life"),
            ("sport", "curiosity"),
            ("nature", "curiosity"),
        ],
    )
    rows = list_interests(user_id)
    assert len(rows) == 6
    assert {r.topic for r in rows} == {
        "pricing",
        "interviews",
        "cooking",
        "humour",
        "sport",
        "nature",
    }


def test_kept_topic_retains_weight_and_last_used(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    replace_interests(user_id, _full_seed())
    used = date(2026, 7, 1)
    with connection() as conn:
        conn.execute(
            """
            UPDATE interests
               SET weight = 0.4, last_used = %s
             WHERE user_id = %s AND topic = %s AND track = %s
            """,
            (used, user_id, "campaigns", "work"),
        )

    replace_interests(
        user_id,
        [
            ("campaigns", "work"),
            ("pricing", "work"),
            ("apartments", "life"),
            ("travel", "life"),
            ("space", "curiosity"),
            ("history", "curiosity"),
        ],
    )
    rows = {r.topic: r for r in list_interests(user_id)}
    assert rows["campaigns"].weight == pytest.approx(0.4)
    assert rows["campaigns"].last_used == used
    assert rows["pricing"].weight == 1.0
    assert rows["pricing"].last_used is None


def test_custom_topic_survives_noop_change(cleanup_user: int) -> None:
    """Change → Done with no edits must keep custom topics and their weights."""
    tid = cleanup_user
    user_id = _onboard(tid)
    custom = "ai: the future"
    used = date(2026, 6, 15)
    replace_interests(
        user_id,
        [
            ("campaigns", "work"),
            (custom, "work"),
            ("apartments", "life"),
            ("travel", "life"),
            ("space", "curiosity"),
            ("history", "curiosity"),
        ],
    )
    with connection() as conn:
        conn.execute(
            """
            UPDATE interests
               SET weight = 0.7, last_used = %s
             WHERE user_id = %s AND topic = %s AND track = %s
            """,
            (used, user_id, custom, "work"),
        )

    # Simulate Change preload: option lists include DB customs.
    existing = list_interests(user_id)
    selected: dict[str, set[str]] = {"work": set(), "life": set(), "curiosity": set()}
    for row in existing:
        selected[row.track].add(row.topic)
    options = {
        track: build_option_list(track, selected[track])
        for track in ("work", "life", "curiosity")
    }
    assert custom in options["work"]
    assert custom in selected["work"]

    # Simulate Done on every track with no toggles.
    selections = [
        (topic, track)
        for track in ("work", "life", "curiosity")
        for topic in sorted(selected[track])
    ]
    replace_interests(user_id, selections)

    rows = {r.topic: r for r in list_interests(user_id)}
    assert custom in rows
    assert rows[custom].track == "work"
    assert rows[custom].weight == pytest.approx(0.7)
    assert rows[custom].last_used == used


def test_fewer_than_two_selections_cannot_proceed() -> None:
    assert can_proceed(set()) is False
    assert can_proceed({"campaigns"}) is False
    assert can_proceed({"campaigns", "negotiation"}) is True


def test_free_text_topic_trimmed_and_lowercased(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    replace_interests(
        user_id,
        [
            ("  AI: The Future  ", "work"),
            ("negotiation", "work"),
            ("apartments", "life"),
            ("travel", "life"),
            ("space", "curiosity"),
            ("history", "curiosity"),
        ],
    )
    topics = {r.topic for r in list_interests(user_id)}
    assert "ai: the future" in topics
    assert "  AI: The Future  " not in topics


def test_long_label_client_email_gets_own_row() -> None:
    options = list(texts.INTEREST_PRESETS["work"])
    assert "client email" in options
    rows = track_topic_button_rows("work", options, selected=set())
    label = topic_button_label("client email")
    assert len(label) > 12
    matching = [row for row in rows if any(lab == label for lab, _ in row)]
    assert len(matching) == 1
    assert len(matching[0]) == 1
    # Callback carries an index, never the topic string.
    _lab, callback = matching[0][0]
    assert callback.startswith("int:tw:")
    assert "client" not in callback
    index = callback.split(":", 2)[2]
    assert index.isdigit()
    assert options[int(index)] == "client email"


def test_done_button_label_at_0_1_and_2_selections() -> None:
    assert done_button_label(0) == texts.BTN_INTERESTS_DONE_NEED_2
    assert done_button_label(1) == texts.BTN_INTERESTS_DONE_NEED_1
    assert done_button_label(2) == texts.BTN_INTERESTS_DONE_READY
    assert done_button_label(5) == texts.BTN_INTERESTS_DONE_READY


def test_track_body_contains_ask_header_exactly_once() -> None:
    body = track_ask_body("work")
    assert body.count(texts.INTERESTS_ASK_WORK) == 1
    # Standing helper / pick-N copy must not appear in the message body.
    assert "Pick at least two" not in body
    assert texts.BTN_INTERESTS_DONE_NEED_2 not in body
    assert texts.BTN_INTERESTS_DONE_NEED_1 not in body
    assert texts.INTERESTS_DONE_TOAST not in body


def test_below_threshold_done_answers_with_toast() -> None:
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from apps.bot.handlers.interests import WORK, wizard_callback

    update = MagicMock()
    query = MagicMock()
    query.data = "int:done:w"
    query.answer = AsyncMock()
    update.callback_query = query
    update.effective_user = MagicMock(id=1)

    context = MagicMock()
    context.user_data = {
        "interests": {
            "wizard_state": WORK,
            "wizard_message_id": 10,
            "wizard_chat_id": 20,
            "selected": {
                "work": {"campaigns"},
                "life": set(),
                "curiosity": set(),
            },
            "options": {
                "work": list(texts.INTEREST_PRESETS["work"]),
                "life": list(texts.INTEREST_PRESETS["life"]),
                "curiosity": list(texts.INTEREST_PRESETS["curiosity"]),
            },
        }
    }
    context.bot = MagicMock()
    context.bot.edit_message_text = AsyncMock()

    result = asyncio.run(wizard_callback(update, context))

    query.answer.assert_awaited_once_with(text=texts.INTERESTS_DONE_TOAST)
    assert result == WORK


def test_preset_emoji_treatment_consistent_across_tracks() -> None:
    """Every preset label has a leading emoji; none is bare text-only."""
    import unicodedata

    def _starts_with_emoji(label: str) -> bool:
        if not label:
            return False
        # First grapheme cluster may be emoji + variation selector.
        first = label[0]
        return unicodedata.category(first) in {"So", "Sk"} or ord(first) > 0x1F000

    for track, topics in texts.INTEREST_PRESETS.items():
        for topic in topics:
            label = texts.INTEREST_TOPIC_LABELS[topic]
            assert _starts_with_emoji(label), f"{track}/{topic}: {label!r}"
    # Customs (not in the label map) stay plain.
    assert topic_button_label("ai: the future") == "ai: the future"


def test_track_screen_free_text_never_silent() -> None:
    """S26c regression: typing on a track screen (not Other) must get a reply.

    Before the fix, WORK/LIFE/CURIOSITY had no MessageHandler; the parent
    ConversationHandler claimed the update (block=True) and dropped it.
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from apps.bot.handlers.interests import WORK, receive_other

    update = MagicMock()
    message = MagicMock()
    message.text = "Vibe Coding and programming"
    message.reply_text = AsyncMock()
    update.message = message
    update.effective_message = message
    update.effective_user = MagicMock(id=1)

    context = MagicMock()
    context.user_data = {
        "interests": {
            "wizard_state": WORK,
            "wizard_message_id": 10,
            "wizard_chat_id": 20,
            "selected": {
                "work": {"campaigns", "pricing"},
                "life": set(),
                "curiosity": set(),
            },
            "options": {
                "work": list(texts.INTEREST_PRESETS["work"]),
                "life": list(texts.INTEREST_PRESETS["life"]),
                "curiosity": list(texts.INTEREST_PRESETS["curiosity"]),
            },
        }
    }
    context.bot = MagicMock()
    context.bot.edit_message_text = AsyncMock()

    result = asyncio.run(receive_other(update, context))

    assert message.reply_text.await_count >= 1
    body = message.reply_text.await_args.args[0]
    assert "vibe coding and programming" in body.lower()
    assert result == WORK
    selected = context.user_data["interests"]["selected"]["work"]
    assert "vibe coding and programming" in selected


def test_wizard_save_confirmation_names_all_three_tracks() -> None:
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from telegram.ext import ConversationHandler

    from apps.bot import identity as bot_identity
    from apps.bot.handlers.interests import CURIOSITY, wizard_callback

    update = MagicMock()
    query = MagicMock()
    query.data = "int:done:c"
    query.answer = AsyncMock()
    update.callback_query = query
    update.effective_user = MagicMock(id=9_999_001)

    context = MagicMock()
    context.user_data = {
        # What the group -1 gate would have stashed. This is a copy test with a
        # mocked save, so it needs an identity but not a users row.
        bot_identity.USER_ID_KEY: 1,
        "interests": {
            "wizard_state": CURIOSITY,
            "wizard_message_id": 10,
            "wizard_chat_id": 20,
            "selected": {
                "work": {"pricing", "standups"},
                "life": {"travel", "cooking"},
                "curiosity": {"space", "sport"},
            },
            "options": {
                "work": list(texts.INTEREST_PRESETS["work"]),
                "life": list(texts.INTEREST_PRESETS["life"]),
                "curiosity": list(texts.INTEREST_PRESETS["curiosity"]),
            },
        }
    }
    context.bot = MagicMock()
    context.bot.edit_message_text = AsyncMock()

    with patch("apps.bot.handlers.interests.replace_interests") as mock_save:
        result = asyncio.run(wizard_callback(update, context))

    assert result == ConversationHandler.END
    mock_save.assert_called_once()
    edited = context.bot.edit_message_text.await_args.kwargs["text"]
    assert "Work" in edited
    assert "Life" in edited
    assert "Curiosity" in edited
    assert "pricing" in edited
    assert "travel" in edited
    assert "space" in edited
    assert "Got it" in edited


def test_interests_handler_registers_text_on_track_states() -> None:
    """Track states must include a TEXT MessageHandler (S26c silent-drop fix)."""
    from telegram.ext import MessageHandler

    from apps.bot.handlers.interests import (
        CURIOSITY,
        LIFE,
        WORK,
        build_interests_handler,
    )

    ch = build_interests_handler()
    for state in (WORK, LIFE, CURIOSITY):
        handlers = ch.states[state]
        assert any(isinstance(h, MessageHandler) for h in handlers), state
