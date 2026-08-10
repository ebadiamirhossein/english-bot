"""S8 couple challenge: scoring, poll, session-marker inertness."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app import texts
from app.config import Settings
from app.db import close_pool, connection
from app.handlers import couple as couple_handler
from app.handlers.couple import (
    generate_question_from_error,
    run_couple_poll,
    wrap_error_row,
)
from app.scheduler import EligibleUser, is_user_due_for_morning
from app.services.calibration import compute_accuracy_window
from app.services.couple import (
    add_point,
    claim_sunday_leaderboard,
    claim_win,
    couple_local_today,
    feature_ready,
    get_challenge_for_date,
    get_open_challenge,
    insert_challenge_if_absent,
    leaderboard_marker_row,
    pick_source_error,
    points_for,
    registered_user_ids,
    scores_for_week,
    week_start,
)
from app.services.sessions import has_session_on
from app.services.streaks import evaluate_pending, get_streak, roll_over_day
from app.services.users import save_onboarding

FAKE_TELEGRAM_ID_BASE = 9_490_000_000
COUPLE_CHAT = -100999888777
VILNIUS = ZoneInfo("Europe/Vilnius")

_GUILT = re.compile(
    r"\b(fail(ed|ure)?|broke your|disappoint|guilt|lazy|should have|"
    r"missed|wrong)\b|😞|😢|😔|☹️|🙁|😟|😤|😠",
    re.IGNORECASE,
)


@pytest.fixture
def fake_ids() -> tuple[int, int]:
    base = FAKE_TELEGRAM_ID_BASE + (uuid.uuid4().int % 1_000_000_000)
    return base, base + 1


@pytest.fixture(autouse=True)
def _close_pool_after_test() -> None:
    yield
    close_pool()


def _delete_user(telegram_user_id: int) -> None:
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM couple_challenges WHERE winner_user_id = %s",
                (telegram_user_id,),
            )
            conn.execute(
                "DELETE FROM couple_scores WHERE user_id = %s",
                (telegram_user_id,),
            )
            conn.execute(
                "DELETE FROM users WHERE telegram_user_id = %s",
                (telegram_user_id,),
            )


def _delete_challenge_day(day: date) -> None:
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                "DELETE FROM couple_challenges WHERE date = %s", (day,)
            )


@pytest.fixture
def cleanup_pair(fake_ids: tuple[int, int]):
    a, b = fake_ids
    yield a, b
    for tid in (a, b):
        _delete_user(tid)


def _onboard(tid: int, *, name: str = "Couple Test") -> None:
    save_onboarding(
        tid,
        {
            "name": name,
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


def _settings(*, couple_chat_id: int | None = COUPLE_CHAT) -> Settings:
    return Settings(
        database_url="postgresql://x:y@localhost:5433/english_bot",
        telegram_bot_token="token",
        llm_api_key="test-key",
        couple_chat_id=couple_chat_id,
    )


def _insert_error(
    tid: int,
    *,
    you_said: str = "so much good",
    correct_form: str = "very good",
    times_wrong: int = 0,
    next_review: date | None = None,
) -> int:
    review = next_review if next_review is not None else date(2026, 8, 1)
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO errors (
                user_id, source, you_said, correct_form, error_type,
                explanation, next_review, times_wrong
            ) VALUES (
                %s, 'text', %s, %s, 'quantifier_modifier',
                'Use very.', %s, %s
            )
            RETURNING id
            """,
            (tid, you_said, correct_form, review, times_wrong),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _set_last_evaluated(tid: int, day: date | None) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE streaks
               SET last_evaluated_date = %s
             WHERE user_id = %s
            """,
            (day, tid),
        )


def s8_user_facing_strings() -> list[str]:
    names = [
        n
        for n in dir(texts)
        if n.startswith("COUPLE_") and not n.startswith("COUPLE_BTN")
    ]
    out: list[str] = []
    for name in names:
        val = getattr(texts, name)
        if not isinstance(val, str):
            continue
        out.append(
            val.format(
                question="q",
                chat_id=1,
                name="Alex",
                points=3,
            )
        )
    return out


def s8_button_labels() -> list[str]:
    return [
        getattr(texts, n)
        for n in dir(texts)
        if n.startswith("BTN_COUPLE") and isinstance(getattr(texts, n), str)
    ]


# --- helpers / unit ----------------------------------------------------------


def test_week_start_monday() -> None:
    assert week_start(date(2026, 8, 9)) == date(2026, 8, 3)  # Sunday
    assert week_start(date(2026, 8, 10)) == date(2026, 8, 10)  # Monday


def test_feature_ready_requires_chat_and_two_users(
    cleanup_pair: tuple[int, int],
) -> None:
    a, b = cleanup_pair
    assert feature_ready(_settings(couple_chat_id=None)) is False
    _onboard(a, name="A")
    with patch(
        "app.services.couple.registered_user_ids", return_value=[a]
    ):
        assert feature_ready(_settings()) is False
    _onboard(b, name="B")
    with patch(
        "app.services.couple.registered_user_ids",
        return_value=sorted([a, b]),
    ):
        assert feature_ready(_settings()) is True


def test_pick_source_error_from_journal(
    cleanup_pair: tuple[int, int],
) -> None:
    a, b = cleanup_pair
    _onboard(a, name="A")
    _onboard(b, name="B")
    ids = sorted([a, b])
    day = date(2026, 8, 10)
    primary = ids[day.toordinal() % 2]
    other = b if primary == a else a
    eid = _insert_error(
        primary, you_said="primary-only-form", times_wrong=5
    )
    _insert_error(other, you_said="other-form", times_wrong=1)
    with patch(
        "app.services.couple.registered_user_ids", return_value=ids
    ):
        err = pick_source_error(day)
    assert err is not None
    assert err.id == eid
    assert err.you_said == "primary-only-form"


def test_atomic_claim_race_one_winner(
    cleanup_pair: tuple[int, int],
) -> None:
    a, b = cleanup_pair
    _onboard(a, name="A")
    _onboard(b, name="B")
    day = date(2026, 8, 11)
    _delete_challenge_day(day)
    cid = insert_challenge_if_absent(day, "Fill: ___", "very")
    assert cid is not None
    assert claim_win(cid, a) is True
    assert claim_win(cid, b) is False
    ch = get_challenge_for_date(day)
    assert ch is not None
    assert ch.winner_user_id == a
    week = week_start(day)
    add_point(a, week)
    # Second claim must not add a second point for B
    assert points_for(a, week) == 1
    assert points_for(b, week) == 0
    _delete_challenge_day(day)


def test_wrong_answer_warm_reply_no_point(
    cleanup_pair: tuple[int, int],
) -> None:
    a, b = cleanup_pair
    _onboard(a, name="A")
    _onboard(b, name="B")
    day = couple_local_today(datetime.now(timezone.utc))
    _delete_challenge_day(day)
    insert_challenge_if_absent(day, "Fill ___", "very")
    week = week_start(day)

    async def _run() -> None:
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = "so much"
        update.message.reply_text = AsyncMock()
        update.effective_user = MagicMock(id=a, first_name="A")
        with patch(
            "app.handlers.couple.couple_local_today", return_value=day
        ):
            await couple_handler.on_couple_answer(update, MagicMock())
        update.message.reply_text.assert_awaited_once_with(
            texts.COUPLE_TRY_AGAIN
        )
        assert get_open_challenge(day) is not None
        assert points_for(a, week) == 0

    asyncio.run(_run())
    _delete_challenge_day(day)


def test_already_claimed_no_second_point(
    cleanup_pair: tuple[int, int],
) -> None:
    a, b = cleanup_pair
    _onboard(a, name="A")
    _onboard(b, name="B")
    day = couple_local_today(datetime.now(timezone.utc))
    _delete_challenge_day(day)
    cid = insert_challenge_if_absent(day, "Fill ___", "very")
    assert cid is not None
    assert claim_win(cid, a) is True
    week = week_start(day)
    add_point(a, week)
    ch = get_challenge_for_date(day)
    assert ch is not None
    # Simulate the race window: handler still sees an "open" row, but the
    # conditional UPDATE finds winner_user_id already set.
    from app.services.couple import CoupleChallenge

    open_view = CoupleChallenge(
        id=ch.id,
        date=ch.date,
        question=ch.question,
        answer=ch.answer,
        winner_user_id=None,
        answered_at=None,
    )

    async def _run() -> None:
        update_b = MagicMock()
        update_b.message = MagicMock()
        update_b.message.text = "very"
        update_b.message.reply_text = AsyncMock()
        update_b.effective_user = MagicMock(id=b, first_name="B")
        with (
            patch(
                "app.handlers.couple.couple_local_today", return_value=day
            ),
            patch(
                "app.handlers.couple.get_open_challenge",
                return_value=open_view,
            ),
        ):
            await couple_handler.on_couple_answer(update_b, MagicMock())
        update_b.message.reply_text.assert_awaited_once_with(
            texts.COUPLE_ALREADY_CLAIMED
        )
        assert points_for(a, week) == 1
        assert points_for(b, week) == 0

    asyncio.run(_run())
    _delete_challenge_day(day)


def test_scores_reset_on_week_boundary(
    cleanup_pair: tuple[int, int],
) -> None:
    a, b = cleanup_pair
    _onboard(a)
    _onboard(b)
    w1 = date(2026, 8, 3)
    w2 = date(2026, 8, 10)
    add_point(a, w1)
    add_point(a, w1)
    add_point(b, w1)
    assert scores_for_week(w1)[a] == 2
    assert scores_for_week(w2).get(a, 0) == 0
    add_point(a, w2)
    assert points_for(a, w2) == 1
    assert points_for(a, w1) == 2


# --- poll --------------------------------------------------------------------


def test_poll_inert_when_chat_unset(
    cleanup_pair: tuple[int, int],
) -> None:
    a, b = cleanup_pair
    _onboard(a)
    _onboard(b)
    app = MagicMock()
    app.bot.send_message = AsyncMock()
    now = datetime(2026, 8, 10, 15, 10, tzinfo=timezone.utc)  # 18:10 Vilnius

    async def _run() -> None:
        actions = await run_couple_poll(
            app, now=now, settings=_settings(couple_chat_id=None)
        )
        assert actions == ["inert"]
        app.bot.send_message.assert_not_awaited()

    asyncio.run(_run())


def test_poll_inert_with_one_user(cleanup_pair: tuple[int, int]) -> None:
    a, _b = cleanup_pair
    _onboard(a)
    # Only one of the pair onboarded; other users may exist in DB — gate on
    # feature_ready for *exactly* our chat with a settings mock that still
    # needs >=2 users globally. If the shared DB already has ≥2 users this
    # still posts; so assert via registered count for our fixtures alone by
    # patching registered_user_ids.
    app = MagicMock()
    app.bot.send_message = AsyncMock()
    now = datetime(2026, 8, 10, 15, 10, tzinfo=timezone.utc)

    async def _run() -> None:
        with patch(
            "app.handlers.couple.feature_ready", return_value=False
        ):
            actions = await run_couple_poll(
                app, now=now, settings=_settings()
            )
        assert actions == ["inert"]
        app.bot.send_message.assert_not_awaited()

    asyncio.run(_run())


def test_one_user_feature_ready_false(cleanup_pair: tuple[int, int]) -> None:
    a, _b = cleanup_pair
    _onboard(a)
    with patch(
        "app.services.couple.registered_user_ids", return_value=[a]
    ):
        assert feature_ready(_settings()) is False


def test_question_posts_from_real_error(
    cleanup_pair: tuple[int, int],
) -> None:
    a, b = cleanup_pair
    _onboard(a, name="A")
    _onboard(b, name="B")
    day = date(2026, 8, 10)  # Monday
    _delete_challenge_day(day)
    _insert_error(a, you_said="so much good", correct_form="very good")
    _insert_error(b, you_said="I go yesterday", correct_form="I went yesterday")

    app = MagicMock()
    app.bot.send_message = AsyncMock(
        return_value=MagicMock(chat_id=COUPLE_CHAT, message_id=1)
    )
    now = datetime(2026, 8, 10, 15, 5, tzinfo=timezone.utc)  # 18:05 Vilnius

    captured: dict[str, Any] = {}

    def _fake_chat(messages, **kwargs):  # noqa: ANN001
        captured["user_content"] = messages[0]["content"]
        return {"question": "Say it better: her English is ___", "answer": "very good"}

    async def _run() -> None:
        with (
            patch("app.handlers.couple.feature_ready", return_value=True),
            patch("app.handlers.couple.chat", side_effect=_fake_chat),
            patch(
                "app.handlers.couple.registered_user_ids",
                return_value=sorted([a, b]),
            ),
            patch(
                "app.services.couple.registered_user_ids",
                return_value=sorted([a, b]),
            ),
        ):
            actions = await run_couple_poll(
                app, now=now, settings=_settings()
            )
        assert "question" in actions
        app.bot.send_message.assert_awaited()
        body = app.bot.send_message.await_args.kwargs.get("text") or (
            app.bot.send_message.await_args.args[1]
            if len(app.bot.send_message.await_args.args) > 1
            else app.bot.send_message.await_args.kwargs["text"]
        )
        # send_message(chat_id=..., text=...)
        kwargs = app.bot.send_message.await_args.kwargs
        assert kwargs["chat_id"] == COUPLE_CHAT
        assert "Tonight's challenge" in kwargs["text"]
        assert "so much good" in captured["user_content"] or (
            "I go yesterday" in captured["user_content"]
        )
        ch = get_challenge_for_date(day)
        assert ch is not None
        assert ch.answer == "very good"

    asyncio.run(_run())
    _delete_challenge_day(day)


def test_sunday_leaderboard_once(
    cleanup_pair: tuple[int, int],
) -> None:
    a, b = cleanup_pair
    _onboard(a, name="Alex")
    _onboard(b, name="Sam")
    # Sunday 2026-08-09 18:10 Vilnius = 15:10 UTC
    sunday = date(2026, 8, 9)
    _delete_challenge_day(sunday)
    insert_challenge_if_absent(sunday, "already", "x")  # skip question path
    week = week_start(sunday)
    add_point(a, week)
    add_point(a, week)
    add_point(b, week)

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    now = datetime(2026, 8, 9, 15, 10, tzinfo=timezone.utc)

    async def _run() -> None:
        with (
            patch("app.handlers.couple.feature_ready", return_value=True),
            patch(
                "app.handlers.couple.registered_user_ids",
                return_value=sorted([a, b]),
            ),
            patch(
                "app.services.couple.registered_user_ids",
                return_value=sorted([a, b]),
            ),
        ):
            first = await run_couple_poll(
                app, now=now, settings=_settings()
            )
            second = await run_couple_poll(
                app, now=now, settings=_settings()
            )
        assert "leaderboard" in first
        assert "skipped_existing_leaderboard" in second
        # One leaderboard send (question skipped_existing may not send)
        lb_calls = [
            c
            for c in app.bot.send_message.await_args_list
            if "This week's challenge" in (c.kwargs.get("text") or "")
        ]
        assert len(lb_calls) == 1
        marker = leaderboard_marker_row(min(a, b), sunday)
        assert marker is not None
        assert marker["completed"] is False

    asyncio.run(_run())
    _delete_challenge_day(sunday)


# --- session marker inertness ------------------------------------------------


def test_leaderboard_marker_rollover_neutral(
    cleanup_pair: tuple[int, int],
) -> None:
    a, b = cleanup_pair
    _onboard(a)
    _onboard(b)
    sunday = date(2026, 8, 9)
    assert claim_sunday_leaderboard(sunday, a) is True
    marker = leaderboard_marker_row(a, sunday)
    assert marker is not None
    assert marker["completed"] is False
    _set_last_evaluated(a, sunday - timedelta(days=1))
    result = roll_over_day(a, sunday)
    assert result.outcome == "neutral"
    # Still incomplete
    marker2 = leaderboard_marker_row(a, sunday)
    assert marker2 is not None
    assert marker2["completed"] is False


def test_leaderboard_marker_does_not_block_morning(
    cleanup_pair: tuple[int, int],
) -> None:
    a, b = cleanup_pair
    _onboard(a)
    _onboard(b)
    sunday = date(2026, 8, 9)
    assert claim_sunday_leaderboard(sunday, a) is True
    assert has_session_on(a, sunday) is False
    user = EligibleUser(
        telegram_user_id=a,
        timezone="Europe/Vilnius",
        morning_time=__import__("datetime").time(7, 0),
        paused_until=None,
    )
    # Monday morning after that Sunday marker day — use Sunday morning slot
    morning = datetime(2026, 8, 9, 4, 10, tzinfo=timezone.utc)  # 07:10 Vilnius
    assert is_user_due_for_morning(user, morning) is True


def test_leaderboard_marker_not_in_calibration(
    cleanup_pair: tuple[int, int],
) -> None:
    a, b = cleanup_pair
    _onboard(a)
    _onboard(b)
    sunday = date(2026, 8, 9)
    assert claim_sunday_leaderboard(sunday, a) is True
    before = compute_accuracy_window(a)
    # Marker incomplete and wrong type — window unchanged (still empty)
    after = compute_accuracy_window(a)
    assert after.answered == before.answered == 0


def test_leaderboard_marker_backfill_neutral(
    cleanup_pair: tuple[int, int],
) -> None:
    a, b = cleanup_pair
    _onboard(a)
    _onboard(b)
    sunday = date(2026, 8, 9)
    assert claim_sunday_leaderboard(sunday, a) is True
    # Walk a range including Sunday via evaluate_pending
    _set_last_evaluated(a, date(2026, 8, 6))  # before Fri
    # now = Monday 2026-08-10 10:00 Vilnius → closed_through = Aug 9 (after 03:00)
    now = datetime(2026, 8, 10, 7, 0, tzinfo=timezone.utc)
    results = evaluate_pending(a, timezone="Europe/Vilnius", now=now)
    by_day = {r.day: r.outcome for r in results}
    assert by_day.get(sunday) == "neutral"
    # Neighbouring days without sessions also Neutral
    for d in (date(2026, 8, 7), date(2026, 8, 8)):
        if d in by_day:
            assert by_day[d] == "neutral"
    streak = get_streak(a)
    assert streak.freeze_tokens == 2  # no freeze from Neutral days


def test_wrap_error_includes_journal_forms(
    cleanup_pair: tuple[int, int],
) -> None:
    a, b = cleanup_pair
    _onboard(a)
    _onboard(b)
    eid = _insert_error(a, you_said="so much good", correct_form="very good")
    from app.services.errors import get_error_for_user

    err = get_error_for_user(a, eid)
    assert err is not None
    wrapped = wrap_error_row(err)
    assert "so much good" in wrapped
    assert "very good" in wrapped


def test_generate_question_uses_to_thread(
    cleanup_pair: tuple[int, int],
) -> None:
    a, b = cleanup_pair
    _onboard(a)
    _onboard(b)
    eid = _insert_error(a)
    from app.services.errors import get_error_for_user

    err = get_error_for_user(a, eid)
    assert err is not None

    async def _run() -> None:
        with patch(
            "app.handlers.couple.chat",
            return_value={"question": "Q?", "answer": "A"},
        ) as chat_mock:
            result = await generate_question_from_error(err)
        assert result == ("Q?", "A")
        chat_mock.assert_called_once()

    asyncio.run(_run())


def test_no_guilt_in_s8_copy() -> None:
    for s in s8_user_facing_strings():
        assert _GUILT.search(s) is None, s


def test_s8_button_labels_max_20() -> None:
    for label in s8_button_labels():
        assert len(label) <= 20, label


def test_insert_challenge_idempotent() -> None:
    day = date(2026, 8, 14)
    _delete_challenge_day(day)
    first = insert_challenge_if_absent(day, "q1", "a1")
    second = insert_challenge_if_absent(day, "q2", "a2")
    assert first is not None
    assert second is None
    ch = get_challenge_for_date(day)
    assert ch is not None
    assert ch.question == "q1"
    _delete_challenge_day(day)
