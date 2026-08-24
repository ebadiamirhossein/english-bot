"""The one place a Telegram id becomes a user id, and the only place it may be.

W4b re-keyed the schema: ``users.id`` is the identity of a learner and
``users.telegram_user_id`` is a nullable secondary identifier, because a person
must be able to sign up, learn and pay without a Telegram account
(``docs/PRODUCT-PRINCIPLES.md`` §2). Everywhere else in the codebase ``user_id``
means ``users.id`` -- no exceptions, and no function that quietly accepts either.

**This module and ``access_control`` are the only two in ``packages/core`` whose
SQL may name ``telegram_user_id``**, and ``tests/test_identity_boundary.py``
enforces it by parsing the tree. The rule exists because the failure it prevents
is silent: a Telegram id passed where an internal id belongs returns "no rows"
rather than raising, which is how a feature dies without anybody noticing. The
same instrument guards the lemmatiser (W4) and the service boundary (W1).

``access_control`` keeps its exemption for a different reason: an access request
legitimately exists *before* any ``users`` row does, so it is keyed on the
Telegram id by design and not by accident.
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg.types.json import Jsonb

from core.db import connection

logger = logging.getLogger(__name__)


class UnknownTelegramUser(LookupError):
    """No ``users`` row carries this Telegram id.

    Raised rather than returning ``None`` at call sites that cannot continue
    without an identity. A missing user is a real condition -- somebody who was
    approved but never finished onboarding -- so the caller that *can* handle it
    uses :func:`user_id_for_telegram` instead.
    """


def user_id_for_telegram(telegram_user_id: int) -> int | None:
    """The internal id for this Telegram id, or ``None`` if there is no row."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id
              FROM users
             WHERE telegram_user_id = %s
            """,
            (telegram_user_id,),
        ).fetchone()
    return None if row is None else int(row["id"])


def require_user_id_for_telegram(telegram_user_id: int) -> int:
    """:func:`user_id_for_telegram`, or raise :class:`UnknownTelegramUser`."""
    user_id = user_id_for_telegram(telegram_user_id)
    if user_id is None:
        raise UnknownTelegramUser(
            f"no users row for telegram_user_id={telegram_user_id}"
        )
    return user_id


def telegram_address_for_user(user_id: int) -> int | None:
    """This user's Telegram **delivery address**, or ``None``.

    Deliberately not named ``telegram_id_for_user``. The value is where a
    message is sent, not who the learner is -- the distinction the whole slice
    exists to draw. ``None`` means the learner has no Telegram channel at all,
    which every delivery path must handle rather than assume away.
    """
    with connection() as conn:
        row = conn.execute(
            """
            SELECT telegram_user_id
              FROM users
             WHERE id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None or row["telegram_user_id"] is None:
        return None
    return int(row["telegram_user_id"])


def create_web_user(
    *,
    email: str,
    name: str,
    native_language: str,
    cefr_level: str = "B1",
) -> int:
    """Create a learner with **no Telegram id at all** and return their id.

    The point of W4b, expressed in one function. The ``users`` row, the approved
    ``access_requests`` row and the ``streaks`` row are written in one
    transaction, because a user who exists but is not approved cannot enrol a
    passkey (``auth.begin_registration`` refuses) and a user without a streak row
    breaks the first delivery pass that reads one.

    No route calls this yet -- W4b ships the schema and the service, not a
    sign-up screen. ``python -m core.claim create`` is the operator path.
    """
    address = email.strip().lower()
    with connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """
                INSERT INTO users (
                    telegram_user_id, name, native_language, cefr_level,
                    auth_email, onboarded
                ) VALUES (NULL, %s, %s, %s, %s, TRUE)
                RETURNING id
                """,
                (name, native_language, cefr_level, address),
            ).fetchone()
            assert row is not None
            user_id = int(row["id"])
            conn.execute(
                """
                INSERT INTO access_requests (
                    telegram_user_id, user_id, display_name, status,
                    requested_at, resolved_at
                ) VALUES (NULL, %s, %s, 'approved', NOW(), NOW())
                """,
                (user_id, name),
            )
            conn.execute(
                "INSERT INTO streaks (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (user_id,),
            )
    logger.info("Created web user id=%s (no telegram id)", user_id)
    return user_id


def save_onboarding(telegram_user_id: int, data: dict[str, Any]) -> int:
    """Persist onboarding answers for a Telegram learner. Returns their id.

    Keyed on the Telegram id and living here rather than in ``users`` because
    this is the one write that *creates* identity from a Telegram id -- the exact
    operation this module exists to contain. Everything downstream takes the
    returned internal id.

    Writes all three rows in one transaction. On conflict it updates the profile
    but never touches an existing streak, never un-revokes access, and never
    overwrites ``created_at``.
    """
    weights = data["track_weights"]
    with connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """
                INSERT INTO users (
                    telegram_user_id,
                    name,
                    native_language,
                    cefr_level,
                    efset_baseline,
                    work_domain,
                    why_statement,
                    track_weights,
                    morning_time,
                    evening_time,
                    onboarded
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE
                )
                ON CONFLICT (telegram_user_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    native_language = EXCLUDED.native_language,
                    cefr_level = EXCLUDED.cefr_level,
                    efset_baseline = EXCLUDED.efset_baseline,
                    work_domain = EXCLUDED.work_domain,
                    why_statement = EXCLUDED.why_statement,
                    track_weights = EXCLUDED.track_weights,
                    morning_time = EXCLUDED.morning_time,
                    evening_time = EXCLUDED.evening_time,
                    onboarded = TRUE
                RETURNING id
                """,
                (
                    telegram_user_id,
                    data["name"],
                    data["native_language"],
                    data["cefr_level"],
                    data.get("efset_baseline"),
                    data["work_domain"],
                    data["why_statement"],
                    Jsonb(weights),
                    data["morning_time"],
                    data["evening_time"],
                ),
            ).fetchone()
            assert row is not None
            user_id = int(row["id"])
            conn.execute(
                """
                INSERT INTO streaks (user_id)
                VALUES (%s)
                ON CONFLICT DO NOTHING
                """,
                (user_id,),
            )
            # Approved if missing; never un-revokes (ON CONFLICT DO NOTHING).
            # `user_id` is set on conflict too: a request raised before the users
            # row existed carries NULL there, and the delivery view joins on it,
            # so leaving it would make an approved learner invisible.
            conn.execute(
                """
                INSERT INTO access_requests (
                    telegram_user_id, user_id, display_name, status,
                    requested_at, resolved_at
                ) VALUES (%s, %s, %s, 'approved', NOW(), NOW())
                ON CONFLICT (telegram_user_id) DO UPDATE SET
                    user_id = EXCLUDED.user_id
                """,
                (telegram_user_id, user_id, data["name"]),
            )
    logger.info(
        "Saved onboarding for user_id=%s (telegram_user_id=%s)",
        user_id,
        telegram_user_id,
    )
    return user_id
