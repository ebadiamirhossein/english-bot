"""S18d: access approval, central gate, delivery drift, decline cap."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User

from core.db import close_pool, connection
from core.services.access_control import (
    is_approved_telegram,
    approve_access,
    delivery_lister_ids,
    is_approved,
    revoke_access,
)
from core.services.admin_panel import format_admin_home, list_admin_users
from core.services.identity import save_onboarding
from core.services.users import is_registered

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


def test_no_onboarding_bot_data_exports() -> None:
    import apps.bot.handlers.access as access_mod

    assert not hasattr(access_mod, "mark_onboarding")
    assert not hasattr(access_mod, "clear_onboarding")
    assert not hasattr(access_mod, "is_onboarding")


