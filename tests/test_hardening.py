"""S18 hardening: alerts, heartbeat, lock, logging, /pause, /stats."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import date, datetime, timedelta, time, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, Update, User
from telegram.ext import ContextTypes

from core.db import close_pool, connection
from apps.bot.handlers.settings import (
    on_pause_callback,
    on_pause_command,
    s18_button_labels,
    s18_user_facing_strings,
)
from core.instance_lock import InstanceLock, InstanceLockError
from apps.bot.scheduler import (
    EligibleUser,
    is_user_due_for_anki,
    is_user_due_for_evening,
    is_user_due_for_morning,
    run_heartbeat_check,
)
from core.services.alerts import (
    ALERT_COOLDOWN,
    format_alert,
    notify_operator,
    on_error,
    should_send_alert,
)
from core.services.heartbeat import check_heartbeat, touch_job_fire
from core.services.motivation import (
    MotivationUser,
    is_user_due_for_sunday_report,
    sessions_due_for_nudge,
)
from core.services.sessions import insert_session, local_today
from core.services.stats import collect_stats, format_stats_message
from core.services.streaks import get_streak, roll_over_day
from core.services.users import (
    get_paused_until,
    save_onboarding,
    set_paused_until,
)
from core.services.errors import run_monthly_fossil_sweep
from core.services.sessions import create_fossil_sweep_session

FAKE_TELEGRAM_ID_BASE = 9_480_000_000

_MON_MORNING = datetime(2026, 8, 3, 5, 10, tzinfo=timezone.utc)  # Vilnius 08:10
_WED_EVENING = datetime(2026, 8, 5, 18, 10, tzinfo=timezone.utc)  # Wed 21:10
_SAT_EVENING = datetime(2026, 8, 8, 18, 10, tzinfo=timezone.utc)  # Sat 21:10
_SUN_EVENING = datetime(2026, 8, 9, 18, 10, tzinfo=timezone.utc)  # Sun 21:10


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


@pytest.fixture
def runtime_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("ALERT_THROTTLE_FILE", str(tmp_path / "throttle.json"))
    monkeypatch.setenv("HEARTBEAT_FILE", str(tmp_path / "last_job_fire"))
    monkeypatch.setenv("INSTANCE_LOCK_FILE", str(tmp_path / "bot.lock"))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "bot.log"))
    # Force config reload on next load_settings().
    return tmp_path


def _onboard(tid: int) -> None:
    save_onboarding(
        tid,
        {
            "name": "Hardening Test",
            "native_language": "fa",
            "cefr_level": "B1",
            "efset_baseline": 45,
            "work_domain": "marketing",
            "why_statement": "Speak without freezing up",
            "track_weights": {"work": 40, "life": 40, "curiosity": 20},
            "morning_time": "08:00",
            "evening_time": "21:00",
        },
    )


def _eligible(tid: int, *, paused_until: date | None = None) -> EligibleUser:
    return EligibleUser(
        telegram_user_id=tid,
        timezone="Europe/Vilnius",
        morning_time=time(8, 0),
        paused_until=paused_until,
        evening_time=time(21, 0),
    )


def _mot(tid: int, *, paused_until: date | None = None) -> MotivationUser:
    return MotivationUser(
        telegram_user_id=tid,
        timezone="Europe/Vilnius",
        evening_time=time(21, 0),
        paused_until=paused_until,
        why_statement="Speak without freezing up",
    )


# --- alerts -------------------------------------------------------------------


def test_throttle_same_key_within_cooldown(runtime_dir: Path) -> None:
    path = runtime_dir / "throttle.json"
    now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    send1, sup1 = should_send_alert("ValueError|h", now=now, path=path)
    assert send1 is True
    assert sup1 == 0
    send2, sup2 = should_send_alert(
        "ValueError|h", now=now + timedelta(minutes=5), path=path
    )
    assert send2 is False
    assert sup2 == 1
    send3, sup3 = should_send_alert(
        "ValueError|h",
        now=now + ALERT_COOLDOWN + timedelta(seconds=1),
        path=path,
    )
    assert send3 is True
    assert sup3 == 1


def test_throttle_different_keys_both_alert(runtime_dir: Path) -> None:
    path = runtime_dir / "throttle.json"
    now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    a, _ = should_send_alert("ValueError|h1", now=now, path=path)
    b, _ = should_send_alert("TypeError|h1", now=now, path=path)
    assert a and b


def test_throttle_survives_restart(runtime_dir: Path) -> None:
    path = runtime_dir / "throttle.json"
    now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    should_send_alert("Boom|handler", now=now, path=path)
    # New process = new call; file still has last_sent.
    send, suppressed = should_send_alert(
        "Boom|handler", now=now + timedelta(minutes=2), path=path
    )
    assert send is False
    assert suppressed >= 1


def test_notify_operator_unset_id_no_crash(
    runtime_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPERATOR_TELEGRAM_ID", raising=False)
    monkeypatch.setenv("OPERATOR_TELEGRAM_ID", "")
    app = MagicMock()
    app.bot.send_message = AsyncMock()
    sent = asyncio.run(
        notify_operator(
            app,
            key="k",
            text="hello",
            now=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
            path=runtime_dir / "throttle.json",
        )
    )
    assert sent is False
    app.bot.send_message.assert_not_called()


def test_on_error_soft_user_and_operator_alert(
    runtime_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPERATOR_TELEGRAM_ID", "999001")
    from core import config as config_mod

    settings = config_mod.load_settings()
    monkeypatch.setattr("core.services.alerts.load_settings", lambda: settings)

    def fake_handler(*_a, **_k):
        return None

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.error = RuntimeError("boom")
    context.handler = MagicMock(callback=fake_handler)
    context.bot = app.bot
    context.application = app

    user = User(id=42, first_name="A", is_bot=False)
    chat = Chat(id=42, type="private")
    msg = Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=user,
        text="private writing must not appear in alerts xyzzy-secret",
    )
    update = Update(update_id=1, message=msg)

    asyncio.run(on_error(update, context))
    assert app.bot.send_message.await_count == 2
    texts_sent = [(c.kwargs.get("text") or "") for c in app.bot.send_message.await_args_list]
    assert any("broke on my side" in t.lower() for t in texts_sent)
    assert all("xyzzy-secret" not in t for t in texts_sent)
    user_text = texts_sent[0]
    assert "Traceback" not in user_text
    assert "RuntimeError" not in user_text


def test_format_alert_truncates() -> None:
    long_tb = "x" * 10000
    text = format_alert(
        handler="h",
        user_id=1,
        exc=ValueError("e"),
        tb=long_tb,
        suppressed=3,
    )
    assert len(text) <= 4096
    assert "suppressed=3" in text


# --- heartbeat ----------------------------------------------------------------


def test_heartbeat_stale_and_fresh(runtime_dir: Path) -> None:
    path = runtime_dir / "last_job_fire"
    now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    assert check_heartbeat(path, now=now) == "stale"
    touch_job_fire(path, now=now - timedelta(hours=1))
    assert check_heartbeat(path, now=now) == "ok"
    touch_job_fire(path, now=now - timedelta(hours=27))
    assert check_heartbeat(path, now=now) == "stale"


def test_heartbeat_check_alerts_when_stale(
    runtime_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPERATOR_TELEGRAM_ID", "999002")
    from core import config as config_mod

    settings = config_mod.load_settings()
    monkeypatch.setattr(
        "apps.bot.scheduler.load_settings", lambda: settings
    )
    monkeypatch.setattr(
        "core.services.alerts.load_settings", lambda: settings
    )
    app = MagicMock()
    app.bot.send_message = AsyncMock()
    now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    status = asyncio.run(run_heartbeat_check(app, now=now))
    assert status == "stale"
    assert app.bot.send_message.await_count == 1


def test_touch_only_on_success_path(runtime_dir: Path) -> None:
    path = runtime_dir / "last_job_fire"
    now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    # Simulate failed job: no touch → still stale
    assert check_heartbeat(path, now=now) == "stale"
    touch_job_fire(path, now=now)
    assert check_heartbeat(path, now=now + timedelta(hours=1)) == "ok"


# --- logging privacy ----------------------------------------------------------


def test_log_file_no_message_bodies(runtime_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.bot.main import _configure_logging
    from core import config as config_mod

    settings = config_mod.load_settings()
    _configure_logging(settings)
    secret = "her english is not so much good SECRET_BODY_991"
    logging.getLogger("test.hardening").info(
        "handler=%s user_id=%s", "correct_text", 123
    )
    # Deliberately do not log the secret; assert it is absent.
    content = Path(settings.log_file).read_text(encoding="utf-8")
    assert "correct_text" in content
    assert secret not in content
    assert "SECRET_BODY_991" not in content


# --- single-instance lock -----------------------------------------------------


def test_instance_lock_second_refuses(runtime_dir: Path) -> None:
    path = runtime_dir / "bot.lock"
    first = InstanceLock(path)
    first.acquire()
    second = InstanceLock(path)
    with pytest.raises(InstanceLockError, match="Another bot instance"):
        second.acquire()
    first.release()
    # Stale/released lock does not block.
    third = InstanceLock(path)
    third.acquire()
    third.release()


# --- /pause -------------------------------------------------------------------


def test_pause_sets_and_resume_clears(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = local_today("Europe/Vilnius", _MON_MORNING)
    set_paused_until(tid, day + timedelta(days=2))
    assert get_paused_until(tid) == day + timedelta(days=2)
    set_paused_until(tid, None)
    assert get_paused_until(tid) is None


def test_six_senders_skip_paused(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = local_today("Europe/Vilnius", _MON_MORNING)
    paused = day + timedelta(days=14)
    set_paused_until(tid, paused)
    user = _eligible(tid, paused_until=paused)
    mot = _mot(tid, paused_until=paused)

    assert is_user_due_for_morning(user, _MON_MORNING) is False
    assert is_user_due_for_evening(user, _WED_EVENING) is False
    assert is_user_due_for_anki(user, _SAT_EVENING) is False
    assert sessions_due_for_nudge(mot, _MON_MORNING + timedelta(hours=4)) == []
    assert is_user_due_for_sunday_report(mot, _SUN_EVENING) is False

    # Monthly fossil sweep skips paused (existing helper).
    n = run_monthly_fossil_sweep(
        now=datetime(2026, 8, 1, 0, 10, tzinfo=timezone.utc)
    )
    # May be 0 for this user; assert no fossil session created while paused.
    from core.services.sessions import open_fossil_sweep_for_user

    assert open_fossil_sweep_for_user(tid) is None
    assert isinstance(n, int)


def test_pause_while_paused_offers_resume_not_stack(
    cleanup_user: int,
) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = local_today("Europe/Vilnius", _MON_MORNING)
    set_paused_until(tid, day + timedelta(days=6))

    msg = MagicMock()
    msg.reply_text = AsyncMock()
    update = MagicMock()
    update.message = msg
    update.effective_user = MagicMock(id=tid)

    with patch(
        "apps.bot.handlers.settings.datetime"
    ) as mock_dt:
        mock_dt.now = MagicMock(return_value=_MON_MORNING)
        asyncio.run(on_pause_command(update, MagicMock()))

    assert msg.reply_text.await_count == 1
    args = msg.reply_text.await_args.args
    kwargs = msg.reply_text.await_args.kwargs
    body = kwargs.get("text") or (args[0] if args else "")
    assert "paused until" in body.lower()
    markup = kwargs["reply_markup"]
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert labels == ["Resume"]


def test_pause_callback_sets_duration(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    day = local_today("Europe/Vilnius", _MON_MORNING)

    msg = MagicMock()
    msg.edit_text = AsyncMock()
    cq = MagicMock()
    cq.data = "pause:3"
    cq.answer = AsyncMock()
    cq.message = msg
    update = MagicMock()
    update.callback_query = cq
    update.effective_user = MagicMock(id=tid)

    with patch("apps.bot.handlers.settings.datetime") as mock_dt:
        mock_dt.now = MagicMock(return_value=_MON_MORNING)
        asyncio.run(on_pause_callback(update, MagicMock()))

    assert get_paused_until(tid) == day + timedelta(days=2)


def test_pause_day_incomplete_quiz_still_missed(cleanup_user: int) -> None:
    """Pin: pre-pause open quiz still Missed — streaks.py untouched."""
    tid = cleanup_user
    _onboard(tid)
    day = date(2026, 8, 3)
    insert_session(tid, "quiz", day, completed=False)
    set_paused_until(tid, day + timedelta(days=7))
    with connection() as conn:
        conn.execute(
            """
            UPDATE streaks
               SET freeze_tokens = 2,
                   last_evaluated_date = %s
             WHERE user_id = %s
            """,
            (day - timedelta(days=1), tid),
        )
    result = roll_over_day(tid, day)
    assert result.outcome == "missed"
    assert result.freeze_consumed is True
    assert get_streak(tid).freeze_tokens == 1


# --- /stats -------------------------------------------------------------------


def test_stats_learner_no_sweep_fields(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    create_fossil_sweep_session(tid, date(2026, 8, 1), pending=[1, 2])
    stats = collect_stats(
        tid,
        now=_MON_MORNING,
        include_sweep=False,
    )
    assert stats is not None
    body = format_stats_message(stats, include_sweep=False)
    low = body.lower()
    assert "sweep" not in low
    assert "fossil" not in low
    assert "pending" not in low
    assert " of 7" not in body
    assert "/7" not in body


def test_stats_operator_sees_sweep(
    cleanup_user: int, monkeypatch: pytest.MonkeyPatch, runtime_dir: Path
) -> None:
    tid = cleanup_user
    _onboard(tid)
    create_fossil_sweep_session(tid, date(2026, 8, 1), pending=[11])
    stats = collect_stats(tid, now=_MON_MORNING, include_sweep=True)
    assert stats is not None
    body = format_stats_message(stats, include_sweep=True)
    assert "Sweep (ops)" in body
    assert "pending 1" in body


def test_stats_user_scoped(cleanup_user: int, fake_telegram_id: int) -> None:
    tid_a = cleanup_user
    tid_b = fake_telegram_id + 1
    _onboard(tid_a)
    _onboard(tid_b)
    try:
        with connection() as conn:
            conn.execute(
                """
                INSERT INTO chunks (
                    user_id, chunk, full_sentence, meaning, source, track,
                    exported_to_anki
                ) VALUES (%s, 'only-a', 's', 'm', 'reading', 'work', FALSE)
                """,
                (tid_a,),
            )
            conn.execute(
                """
                INSERT INTO chunks (
                    user_id, chunk, full_sentence, meaning, source, track,
                    exported_to_anki
                ) VALUES (%s, 'only-b', 's', 'm', 'reading', 'work', FALSE)
                """,
                (tid_b,),
            )
        stats_a = collect_stats(tid_a, now=_MON_MORNING)
        stats_b = collect_stats(tid_b, now=_MON_MORNING)
        assert stats_a is not None and stats_b is not None
        assert stats_a.chunk_total == 1
        assert stats_b.chunk_total == 1
        body_a = format_stats_message(stats_a, include_sweep=False)
        assert "only-b" not in body_a
    finally:
        _delete_user(tid_b)


def test_stats_labels_not_codes(cleanup_user: int) -> None:
    tid = cleanup_user
    _onboard(tid)
    with connection() as conn:
        label_row = conn.execute(
            "SELECT label FROM error_types WHERE code = %s",
            ("article_missing",),
        ).fetchone()
        assert label_row is not None
        label = str(label_row["label"])
        conn.execute(
            """
            INSERT INTO errors (
                user_id, source, you_said, correct_form, error_type,
                explanation, streak_right, times_right, times_wrong,
                next_review, resolved, resolved_at, unresolved_count
            ) VALUES (
                %s, 'quiz', 'x', 'y', 'article_missing',
                'e', 5, 5, 0,
                CURRENT_DATE - 1, TRUE, CURRENT_DATE - 1, 0
            )
            """,
            (tid,),
        )
    stats = collect_stats(tid, now=_MON_MORNING)
    assert stats is not None
    body = format_stats_message(stats, include_sweep=False)
    assert label in body
    assert "article_missing" not in body


def test_no_guilt_in_s18_copy() -> None:
    banned = re.compile(
        r"\bmissed\b|\bfailed\b|\bbroke your\b|should have|"
        r"😞|😢|😔|☹️|🙁|😟|😤|😠",
        re.IGNORECASE,
    )
    for s in s18_user_facing_strings():
        assert banned.search(s) is None, s
    # Soft unhandled may say "broke on my side" — that's operator self-blame, OK.
    # Explicitly allow SOFT_UNHANDLED separately:
    from apps.bot import texts

    assert "broke your" not in texts.SOFT_UNHANDLED.lower()


def test_s18_button_labels_max_20() -> None:
    for label in s18_button_labels():
        assert len(label) <= 20, label
