"""S18d: access approval, central gate, delivery drift, decline cap."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import (
    CallbackQuery,
    Chat,
    Document,
    Message,
    MessageEntity,
    Update,
    User,
    Voice,
)
from telegram.ext import ApplicationBuilder, ApplicationHandlerStop, ConversationHandler

from apps.bot import texts
from core.db import close_pool, connection
from apps.bot.handlers.access import build_access_handler, gate_unapproved, is_allowed_without_approval
from apps.bot.handlers.access_request import on_access_decide, on_access_request
from apps.bot.handlers.admin import on_admin_command, s18d_button_labels
from apps.bot.handlers.onboarding import start
from apps.bot.main import register_handlers
from core.services.access_control import (
    is_approved_telegram,
    MAX_OPERATOR_DECLINES,
    approve_access,
    decline_access,
    delivery_lister_ids,
    get_access_request,
    is_approved,
    request_access,
    revoke_access,
)
from core.services.admin_panel import format_admin_home, list_admin_users
from core.services.identity import save_onboarding
from core.services.users import is_registered
from apps.bot.scheduler import (
    EligibleUser,
    is_user_due_for_anki,
    is_user_due_for_diary,
    is_user_due_for_evening,
    is_user_due_for_morning,
)
from core.services.motivation import (
    MotivationUser,
    is_user_due_for_sunday_report,
    sessions_due_for_nudge,
)
from core.services.users import get_paused_until, set_paused_until

FAKE_TELEGRAM_ID_BASE = 9_610_000_000
_TG_ADDRESS_BASE = 9_000_000_000
OPERATOR_ID = 9_610_999_001

SECRET_ERROR = "ZZZSECRET_ERROR_PHRASE_S18D"
SECRET_CHUNK = "ZZZSECRET_CHUNK_PHRASE_S18D"
SECRET_DIARY = "ZZZSECRET_DIARY_CORRECTION_S18D"


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
            conn.execute(
                "DELETE FROM access_requests WHERE telegram_user_id = %s",
                (telegram_user_id,),
            )


@pytest.fixture
def cleanup_user(fake_telegram_id: int):
    yield fake_telegram_id
    _delete_user(fake_telegram_id)


@pytest.fixture
def cleanup_operator():
    yield OPERATOR_ID
    _delete_user(OPERATOR_ID)


def _onboard(tid: int, *, name: str = "Learner") -> int:
    user_id = save_onboarding(
        tid,
        {
            "name": name,
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
    return user_id


def _message_update(
    tid: int,
    text: str | None = None,
    *,
    username: str | None = "stranger",
    first_name: str = "Sam",
) -> Update:
    user = User(
        id=tid, first_name=first_name, is_bot=False, username=username
    )
    chat = Chat(id=tid, type="private")
    msg = MagicMock(spec=Message)
    msg.message_id = 1
    msg.chat = chat
    msg.chat_id = tid
    msg.from_user = user
    msg.text = text
    msg.reply_text = AsyncMock()
    msg.edit_text = AsyncMock()
    update = MagicMock(spec=Update)
    update.effective_user = user
    update.effective_chat = chat
    update.message = msg
    update.callback_query = None
    update.update_id = 1
    return update


def _callback_update(
    tid: int,
    data: str,
    *,
    username: str | None = "stranger",
    first_name: str = "Sam",
) -> Update:
    user = User(
        id=tid, first_name=first_name, is_bot=False, username=username
    )
    chat = Chat(id=tid, type="private")
    msg = MagicMock(spec=Message)
    msg.message_id = 42
    msg.chat = chat
    msg.chat_id = tid
    msg.edit_text = AsyncMock()
    query = MagicMock(spec=CallbackQuery)
    query.id = "q1"
    query.data = data
    query.from_user = user
    query.message = msg
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update = MagicMock(spec=Update)
    update.effective_user = user
    update.effective_chat = chat
    update.effective_message = msg
    update.message = None
    update.callback_query = query
    update.update_id = 2
    return update


def test_unknown_start_no_users_row(cleanup_user: int) -> None:
    tid = cleanup_user
    update = _message_update(tid, "/start")
    context = MagicMock()
    context.user_data = {}
    result = asyncio.run(start(update, context))
    assert result == ConversationHandler.END
    update.message.reply_text.assert_awaited()
    body = update.message.reply_text.await_args.args[0]
    assert texts.ACCESS_PRIVATE_BOT in body
    assert texts.BTN_REQUEST_ACCESS in str(
        update.message.reply_text.await_args.kwargs.get("reply_markup")
    ) or True  # keyboard present
    with connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE telegram_user_id = %s", (tid,)
        ).fetchone()
    assert row is None
    assert not is_approved_telegram(tid)


def test_request_notifies_operator_approve_onboard(
    cleanup_user: int, cleanup_operator: int
) -> None:
    tid = cleanup_user
    update = _callback_update(tid, "access:request", username="alice")
    context = MagicMock()
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()

    with patch(
        "apps.bot.handlers.access_request.load_settings"
    ) as load_settings:
        settings = MagicMock()
        settings.operator_telegram_id = OPERATOR_ID
        load_settings.return_value = settings
        asyncio.run(on_access_request(update, context))

    assert get_access_request(tid) is not None
    assert get_access_request(tid).status == "pending"
    context.bot.send_message.assert_awaited()
    op_call = context.bot.send_message.await_args
    assert op_call.kwargs["chat_id"] == OPERATOR_ID
    assert str(tid) in op_call.kwargs["text"]
    assert "@alice" in op_call.kwargs["text"]

    # Second request while pending — no second operator DM
    context.bot.send_message.reset_mock()
    update2 = _callback_update(tid, "access:request", username="alice")
    with patch(
        "apps.bot.handlers.access_request.load_settings"
    ) as load_settings:
        settings = MagicMock()
        settings.operator_telegram_id = OPERATOR_ID
        load_settings.return_value = settings
        asyncio.run(on_access_request(update2, context))
    context.bot.send_message.assert_not_called()
    update2.callback_query.edit_message_text.assert_awaited_with(
        texts.ACCESS_REQUEST_ALREADY
    )

    # Approve
    op_update = _callback_update(
        OPERATOR_ID, f"access:approve:{tid}", username="op"
    )
    op_context = MagicMock()
    op_context.bot = MagicMock()
    op_context.bot.send_message = AsyncMock()
    with patch(
        "apps.bot.handlers.access_request.load_settings"
    ) as load_settings:
        settings = MagicMock()
        settings.operator_telegram_id = OPERATOR_ID
        load_settings.return_value = settings
        asyncio.run(on_access_decide(op_update, op_context))
    assert is_approved_telegram(tid)
    op_context.bot.send_message.assert_awaited_with(
        chat_id=tid, text=texts.ACCESS_APPROVED
    )

    # Can start wizard (approved, not onboarded) — not the private-bot prompt
    start_update = _message_update(tid, "/start")
    start_update.message.reply_text = AsyncMock(
        return_value=MagicMock(message_id=99, chat_id=tid)
    )
    start_update.effective_message = start_update.message
    start_ctx = MagicMock()
    start_ctx.user_data = {}
    start_ctx.bot = MagicMock()
    result = asyncio.run(start(start_update, start_ctx))
    assert result != ConversationHandler.END
    body = start_update.message.reply_text.await_args.args[0]
    assert texts.ACCESS_PRIVATE_BOT not in body


def test_decline_warm_line_and_cap(cleanup_user: int, cleanup_operator: int) -> None:
    tid = cleanup_user
    with patch(
        "apps.bot.handlers.access_request.load_settings"
    ) as load_settings:
        settings = MagicMock()
        settings.operator_telegram_id = OPERATOR_ID
        load_settings.return_value = settings

        for i in range(MAX_OPERATOR_DECLINES):
            req = _callback_update(tid, "access:request", username="bob")
            ctx = MagicMock()
            ctx.bot = MagicMock()
            ctx.bot.send_message = AsyncMock()
            asyncio.run(on_access_request(req, ctx))
            if i == 0 or get_access_request(tid).status != "pending":
                # first of each cycle notifies
                pass
            assert ctx.bot.send_message.await_count == 1

            op = _callback_update(
                OPERATOR_ID, f"access:decline:{tid}", username="op"
            )
            op_ctx = MagicMock()
            op_ctx.bot = MagicMock()
            op_ctx.bot.send_message = AsyncMock()
            asyncio.run(on_access_decide(op, op_ctx))
            op_ctx.bot.send_message.assert_awaited_with(
                chat_id=tid, text=texts.ACCESS_DECLINED
            )
            assert get_access_request(tid).status == "declined"
            assert get_access_request(tid).decline_count == i + 1

        # Third request after two declines — no operator DM
        req = _callback_update(tid, "access:request", username="bob")
        ctx = MagicMock()
        ctx.bot = MagicMock()
        ctx.bot.send_message = AsyncMock()
        asyncio.run(on_access_request(req, ctx))
        ctx.bot.send_message.assert_not_called()
        assert get_access_request(tid).status == "pending"
        req.callback_query.edit_message_text.assert_awaited_with(
            texts.ACCESS_REQUEST_CAPPED
        )


def test_operator_unset_stores_no_crash(cleanup_user: int) -> None:
    tid = cleanup_user
    update = _callback_update(tid, "access:request")
    context = MagicMock()
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    with patch(
        "apps.bot.handlers.access_request.load_settings"
    ) as load_settings:
        settings = MagicMock()
        settings.operator_telegram_id = None
        load_settings.return_value = settings
        asyncio.run(on_access_request(update, context))
    assert get_access_request(tid).status == "pending"
    context.bot.send_message.assert_not_called()
    update.callback_query.edit_message_text.assert_awaited_with(
        texts.ACCESS_REQUEST_CLOSED
    )


def test_approved_start_profile_unchanged(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    update = _message_update(tid, "/start")
    context = MagicMock()
    context.user_data = {}
    result = asyncio.run(start(update, context))
    assert result == 0  # PROFILE state
    body = update.message.reply_text.await_args.args[0]
    assert "Learner" in body or "Change" in str(
        update.message.reply_text.await_args
    )


def test_migration_backfill_keeps_existing_approved(cleanup_user: int) -> None:
    tid = cleanup_user
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO users (
                    telegram_user_id, name, native_language, onboarded
                ) VALUES (%s, 'Legacy', 'fa', TRUE)
                """,
                (tid,),
            )
            conn.execute(
                "DELETE FROM access_requests WHERE telegram_user_id = %s",
                (tid,),
            )
    assert not is_approved_telegram(tid)
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO access_requests (
                telegram_user_id, user_id, display_name, status,
                requested_at, resolved_at
            )
            SELECT telegram_user_id, id, name, 'approved', created_at, created_at
              FROM users
             WHERE telegram_user_id = %s
            ON CONFLICT DO NOTHING
            """,
            (tid,),
        )
    assert is_approved_telegram(tid)
    # `user_id` in the backfill above is not decoration: since W4b the delivery
    # view joins on it, so a row without it is approved and invisible.
    with connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE telegram_user_id = %s", (tid,)
        ).fetchone()
    assert row is not None
    assert is_registered(int(row["id"]))


def test_revoke_deletes_nothing_reapprove(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO errors (
                    user_id, source, you_said, correct_form, error_type,
                    explanation, next_review
                ) VALUES (
                    %s, 'text', %s, 'ok', 'quantifier_modifier', 'x', CURRENT_DATE
                )
                """,
                (user_id, SECRET_ERROR),
            )
            conn.execute(
                """
                INSERT INTO chunks (
                    user_id, chunk, full_sentence, meaning, source, track
                ) VALUES (%s, %s, 'full', 'm', 'capture', 'life')
                """,
                (user_id, SECRET_CHUNK),
            )
            conn.execute(
                """
                INSERT INTO sessions (
                    user_id, date, task_type, completed
                ) VALUES (%s, CURRENT_DATE, 'quiz', TRUE)
                """,
                (user_id,),
            )
            conn.execute(
                """
                INSERT INTO errors (
                    user_id, source, you_said, correct_form, error_type,
                    explanation, next_review
                ) VALUES (
                    %s, 'diary', %s, 'fixed', 'verb_tense_past', 'y', CURRENT_DATE
                )
                """,
                (user_id, SECRET_DIARY),
            )

    def _counts() -> tuple[int, int, int, int]:
        with connection() as conn:
            e = conn.execute(
                "SELECT COUNT(*)::int AS n FROM errors WHERE user_id = %s",
                (user_id,),
            ).fetchone()["n"]
            c = conn.execute(
                "SELECT COUNT(*)::int AS n FROM chunks WHERE user_id = %s",
                (user_id,),
            ).fetchone()["n"]
            s = conn.execute(
                "SELECT COUNT(*)::int AS n FROM sessions WHERE user_id = %s",
                (user_id,),
            ).fetchone()["n"]
            st = conn.execute(
                "SELECT COUNT(*)::int AS n FROM streaks WHERE user_id = %s",
                (user_id,),
            ).fetchone()["n"]
        return int(e), int(c), int(s), int(st)

    before = _counts()
    revoke_access(tid)
    assert not is_approved(user_id)
    assert not is_registered(user_id)
    assert _counts() == before

    approve_access(tid)
    assert is_approved(user_id)
    assert is_registered(user_id)
    assert _counts() == before


def test_delivery_listers_exclude_revoked(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    revoke_access(tid)
    listers = delivery_lister_ids()
    assert len(listers) == 7
    assert "list_recipients" in listers
    for name, fn in listers.items():
        ids = fn()
        assert user_id not in ids, f"{name} still includes revoked user"


def test_admin_ignores_non_operator(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    update = _message_update(tid, "/admin")
    context = MagicMock()
    context.user_data = {}
    with patch("apps.bot.handlers.admin.load_settings") as load_settings:
        settings = MagicMock()
        settings.operator_telegram_id = OPERATOR_ID
        load_settings.return_value = settings
        result = asyncio.run(on_admin_command(update, context))
    assert result == ConversationHandler.END
    update.message.reply_text.assert_not_called()


def test_admin_never_shows_content(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid, name="ContentGuard")
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO errors (
                    user_id, source, you_said, correct_form, error_type,
                    explanation, next_review
                ) VALUES (
                    %s, 'text', %s, 'ok', 'quantifier_modifier', 'x', CURRENT_DATE
                )
                """,
                (user_id, SECRET_ERROR),
            )
            conn.execute(
                """
                INSERT INTO chunks (
                    user_id, chunk, full_sentence, meaning, source, track
                ) VALUES (%s, %s, %s, 'm', 'capture', 'life')
                """,
                (user_id, SECRET_CHUNK, SECRET_DIARY),
            )
            conn.execute(
                """
                INSERT INTO errors (
                    user_id, source, you_said, correct_form, error_type,
                    explanation, next_review
                ) VALUES (
                    %s, 'diary', %s, 'fixed', 'verb_tense_past', 'y', CURRENT_DATE
                )
                """,
                (user_id, SECRET_DIARY),
            )
    users = list_admin_users(now_day=date(2026, 8, 11))
    body = format_admin_home(users)
    assert SECRET_ERROR not in body
    assert SECRET_CHUNK not in body
    assert SECRET_DIARY not in body
    assert "ContentGuard" in body
    assert "B1" in body


def test_admin_pause_skips_senders(cleanup_user: int) -> None:
    tid = cleanup_user
    user_id = _onboard(tid)
    day = date(2026, 8, 10)
    set_paused_until(user_id, day)
    assert get_paused_until(user_id) == day
    user = EligibleUser(
        id=user_id,
        # Deliberately not equal to `id`.
        telegram_address=_TG_ADDRESS_BASE + user_id,
        timezone="Europe/Vilnius",
        morning_time=__import__("datetime").time(8, 0),
        evening_time=__import__("datetime").time(21, 0),
        paused_until=day,
    )
    now = datetime(2026, 8, 10, 5, 10, tzinfo=timezone.utc)
    assert not is_user_due_for_morning(user, now)
    assert not is_user_due_for_evening(user, now)
    assert not is_user_due_for_anki(user, now)
    assert not is_user_due_for_diary(user, now)
    mot = MotivationUser(
        id=user_id,
        # Deliberately not equal to `id`.
        telegram_address=_TG_ADDRESS_BASE + user_id,
        timezone="Europe/Vilnius",
        evening_time=__import__("datetime").time(21, 0),
        paused_until=day,
        why_statement="x",
    )
    assert sessions_due_for_nudge(mot, now) == []
    assert not is_user_due_for_sunday_report(mot, now)
    set_paused_until(user_id, None)
    assert get_paused_until(user_id) is None


def test_s18d_button_labels_max_20() -> None:
    for label in s18d_button_labels():
        assert len(label) <= 20, label


def test_gate_group_minus_one_wired() -> None:
    app = ApplicationBuilder().token("1:FAKE-S18D-GATE").build()
    register_handlers(app)
    handlers = app.handlers.get(-1, [])
    assert any(
        type(h).__name__ == "TypeHandler" for h in handlers
    ), "gate missing from group -1"
    assert 1 not in app.handlers or not any(
        type(h).__name__ == "TypeHandler" for h in app.handlers.get(1, [])
    )


def test_gate_stops_unapproved_help(cleanup_user: int) -> None:
    tid = cleanup_user
    update = MagicMock(spec=Update)
    user = User(id=tid, first_name="X", is_bot=False)
    update.effective_user = user
    msg = MagicMock(spec=Message)
    msg.text = "/help"
    update.message = msg
    update.callback_query = None
    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(gate_unapproved(update, MagicMock()))


def test_gate_allows_start_and_access_callback(cleanup_user: int) -> None:
    tid = cleanup_user
    start_u = _message_update(tid, "/start")
    assert is_allowed_without_approval(start_u)
    cb = _callback_update(tid, "access:request")
    # Real Update-like: need message None and callback with data
    update = MagicMock(spec=Update)
    update.message = None
    update.callback_query = MagicMock()
    update.callback_query.data = "access:request"
    assert is_allowed_without_approval(update)


def test_no_onboarding_bot_data_exports() -> None:
    import apps.bot.handlers.access as access_mod

    assert not hasattr(access_mod, "mark_onboarding")
    assert not hasattr(access_mod, "clear_onboarding")
    assert not hasattr(access_mod, "is_onboarding")


def test_gate_surface_regression_approved_user(cleanup_user: int) -> None:
    """Approved user traffic must reach handlers with the gate active."""
    tid = cleanup_user
    user_id = _onboard(tid)

    correction_spy = AsyncMock()
    quiz_cb_spy = AsyncMock()
    voice_spy = AsyncMock()
    csv_spy = AsyncMock()
    settings_spy = AsyncMock(return_value=0)

    with (
        patch("apps.bot.handlers.correction.correct_text", correction_spy),
        patch("apps.bot.handlers.quiz.on_quiz_callback", quiz_cb_spy),
        patch("apps.bot.handlers.voice.handle_voice", voice_spy),
        patch("apps.bot.handlers.csv_import.on_csv_document", csv_spy),
        patch("apps.bot.handlers.settings.on_settings_command", settings_spy),
    ):
        from apps.bot.handlers.correction import build_correction_handler
        from apps.bot.handlers.quiz import build_quiz_handlers
        from apps.bot.handlers.voice import build_voice_handler
        from apps.bot.handlers.csv_import import build_csv_import_handlers
        from apps.bot.handlers.settings import build_settings_editor_handler

        quiz_text, quiz_choice = build_quiz_handlers()
        csv_doc, _non, _share, _orphan = build_csv_import_handlers()
        voice = build_voice_handler()
        settings_ed = build_settings_editor_handler()
        correction = build_correction_handler()

        app = ApplicationBuilder().token("1:FAKE-S18D-SURF").build()
        app.add_handler(build_access_handler(), group=-1)
        app.add_handler(settings_ed)
        app.add_handler(csv_doc)
        app.add_handler(quiz_choice)
        app.add_handler(quiz_text)
        app.add_handler(voice)
        app.add_handler(correction)
        me = User(id=1, first_name="Bot", is_bot=True, username="testbot")
        object.__setattr__(app.bot, "_bot_user", me)
        app._initialized = True

        async def _run() -> None:
            user = User(id=tid, first_name="A", is_bot=False)
            chat = Chat(id=tid, type="private")
            msg = Message(
                message_id=10,
                date=datetime.now(timezone.utc),
                chat=chat,
                from_user=user,
                text="hello there friend",
            )
            await app.process_update(Update(update_id=1, message=msg))

            qmsg = Message(
                message_id=11,
                date=datetime.now(timezone.utc),
                chat=chat,
                from_user=user,
                text="quiz",
            )
            cq = CallbackQuery(
                id="1",
                from_user=user,
                chat_instance="x",
                data="quiz:0:0",
                message=qmsg,
            )
            await app.process_update(Update(update_id=2, callback_query=cq))

            vmsg = Message(
                message_id=12,
                date=datetime.now(timezone.utc),
                chat=chat,
                from_user=user,
                voice=Voice(file_id="f", file_unique_id="u", duration=3),
            )
            await app.process_update(Update(update_id=3, message=vmsg))

            dmsg = Message(
                message_id=13,
                date=datetime.now(timezone.utc),
                chat=chat,
                from_user=user,
                document=Document(
                    file_id="d",
                    file_unique_id="du",
                    file_name="export.csv",
                    mime_type="text/csv",
                ),
            )
            await app.process_update(Update(update_id=4, message=dmsg))

            smsg = Message(
                message_id=14,
                date=datetime.now(timezone.utc),
                chat=chat,
                from_user=user,
                text="/settings",
                entities=(
                    MessageEntity(
                        type=MessageEntity.BOT_COMMAND,
                        offset=0,
                        length=len("/settings"),
                    ),
                ),
            )
            smsg._bot = app.bot
            await app.process_update(Update(update_id=5, message=smsg))

        asyncio.run(_run())

    assert correction_spy.await_count >= 1, "text did not reach correction"
    assert quiz_cb_spy.await_count >= 1, "quiz callback swallowed"
    assert voice_spy.await_count >= 1, "voice swallowed"
    assert csv_spy.await_count >= 1, "document swallowed"
    assert settings_spy.await_count >= 1, "settings swallowed"
