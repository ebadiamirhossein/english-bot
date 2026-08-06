"""Interests profile (S9) — save, replace, preserve, min-2, free-text, layout."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from app import texts
from app.db import close_pool, connection
from app.handlers.interests import (
    build_option_list,
    can_proceed,
    done_button_label,
    topic_button_label,
    track_ask_body,
    track_topic_button_rows,
)
from app.services.interests import list_interests, replace_interests
from app.services.users import save_onboarding

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


def _onboard(tid: int) -> None:
    save_onboarding(
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
    _onboard(tid)
    replace_interests(
        tid,
        [
            ("  Campaigns ", "work"),
            ("Client Email", "work"),
            ("Apartments", "life"),
            ("Travel", "life"),
            ("Space", "curiosity"),
            ("History", "curiosity"),
        ],
    )
    rows = list_interests(tid)
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
    _onboard(tid)
    replace_interests(tid, _full_seed())
    replace_interests(
        tid,
        [
            ("pricing", "work"),
            ("interviews", "work"),
            ("cooking", "life"),
            ("humour", "life"),
            ("sport", "curiosity"),
            ("nature", "curiosity"),
        ],
    )
    rows = list_interests(tid)
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
    _onboard(tid)
    replace_interests(tid, _full_seed())
    used = date(2026, 7, 1)
    with connection() as conn:
        conn.execute(
            """
            UPDATE interests
               SET weight = 0.4, last_used = %s
             WHERE user_id = %s AND topic = %s AND track = %s
            """,
            (used, tid, "campaigns", "work"),
        )

    replace_interests(
        tid,
        [
            ("campaigns", "work"),
            ("pricing", "work"),
            ("apartments", "life"),
            ("travel", "life"),
            ("space", "curiosity"),
            ("history", "curiosity"),
        ],
    )
    rows = {r.topic: r for r in list_interests(tid)}
    assert rows["campaigns"].weight == pytest.approx(0.4)
    assert rows["campaigns"].last_used == used
    assert rows["pricing"].weight == 1.0
    assert rows["pricing"].last_used is None


def test_custom_topic_survives_noop_change(cleanup_user: int) -> None:
    """Change → Done with no edits must keep custom topics and their weights."""
    tid = cleanup_user
    _onboard(tid)
    custom = "ai: the future"
    used = date(2026, 6, 15)
    replace_interests(
        tid,
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
            (used, tid, custom, "work"),
        )

    # Simulate Change preload: option lists include DB customs.
    existing = list_interests(tid)
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
    replace_interests(tid, selections)

    rows = {r.topic: r for r in list_interests(tid)}
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
    _onboard(tid)
    replace_interests(
        tid,
        [
            ("  AI: The Future  ", "work"),
            ("negotiation", "work"),
            ("apartments", "life"),
            ("travel", "life"),
            ("space", "curiosity"),
            ("history", "curiosity"),
        ],
    )
    topics = {r.topic for r in list_interests(tid)}
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

    from app.handlers.interests import WORK, wizard_callback

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
