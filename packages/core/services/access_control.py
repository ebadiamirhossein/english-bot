"""Access approval (S18d).

``access_requests`` is the source of truth for who may use the bot.
Pending requests live here before any ``users`` row exists. Revoke flips
status without deleting learning history.

Delivery lists must read the DB view ``approved_onboarded_users`` — never
hand-roll a JOIN. See ``DELIVERY_USER_LISTERS`` for the drift-test contract.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from core.db import connection

logger = logging.getLogger(__name__)

AccessStatus = Literal["pending", "approved", "declined", "revoked"]

# After this many declines, re-requests stay visible in /admin but do not
# DM the operator again.
MAX_OPERATOR_DECLINES = 2


@dataclass(frozen=True)
class AccessRequest:
    telegram_user_id: int
    username: str | None
    display_name: str | None
    status: AccessStatus
    decline_count: int
    requested_at: datetime
    resolved_at: datetime | None


@dataclass(frozen=True)
class RequestAccessResult:
    """Outcome of a stranger tapping Request access."""

    status: AccessStatus
    notify_operator: bool
    already_pending: bool
    capped: bool


def is_approved(telegram_user_id: int) -> bool:
    """True when access_requests.status is approved."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT 1
              FROM access_requests
             WHERE telegram_user_id = %s
               AND status = 'approved'
            """,
            (telegram_user_id,),
        ).fetchone()
    return row is not None


def get_access_request(telegram_user_id: int) -> AccessRequest | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT telegram_user_id, username, display_name, status,
                   decline_count, requested_at, resolved_at
              FROM access_requests
             WHERE telegram_user_id = %s
            """,
            (telegram_user_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_request(row)


def list_pending_requests() -> list[AccessRequest]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT telegram_user_id, username, display_name, status,
                   decline_count, requested_at, resolved_at
              FROM access_requests
             WHERE status = 'pending'
             ORDER BY requested_at ASC
            """
        ).fetchall()
    return [_row_to_request(r) for r in rows]


def count_pending_requests() -> int:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)::int AS n
              FROM access_requests
             WHERE status = 'pending'
            """
        ).fetchone()
    assert row is not None
    return int(row["n"])


def request_access(
    telegram_user_id: int,
    *,
    username: str | None,
    display_name: str | None,
) -> RequestAccessResult:
    """Upsert a pending request. Caller decides whether to DM the operator.

    Rules:
    - Already pending → no second operator DM.
    - decline_count >= MAX_OPERATOR_DECLINES → pending, logged, no operator DM.
    - Otherwise → pending and notify_operator True (if operator configured).
    """
    existing = get_access_request(telegram_user_id)
    if existing is not None and existing.status == "pending":
        return RequestAccessResult(
            status="pending",
            notify_operator=False,
            already_pending=True,
            capped=False,
        )

    decline_count = existing.decline_count if existing is not None else 0
    capped = decline_count >= MAX_OPERATOR_DECLINES
    now = datetime.now(timezone.utc)

    with connection() as conn:
        conn.execute(
            """
            INSERT INTO access_requests (
                telegram_user_id, username, display_name, status,
                decline_count, requested_at, resolved_at
            ) VALUES (%s, %s, %s, 'pending', %s, %s, NULL)
            ON CONFLICT (telegram_user_id) DO UPDATE SET
                username = EXCLUDED.username,
                display_name = EXCLUDED.display_name,
                status = 'pending',
                requested_at = EXCLUDED.requested_at,
                resolved_at = NULL
            """,
            (
                telegram_user_id,
                username,
                display_name,
                decline_count,
                now,
            ),
        )

    if capped:
        logger.warning(
            "access request after decline cap user_id=%s declines=%s "
            "(no operator DM)",
            telegram_user_id,
            decline_count,
        )
        return RequestAccessResult(
            status="pending",
            notify_operator=False,
            already_pending=False,
            capped=True,
        )

    logger.info(
        "access request pending user_id=%s username=%s",
        telegram_user_id,
        username,
    )
    return RequestAccessResult(
        status="pending",
        notify_operator=True,
        already_pending=False,
        capped=False,
    )


def approve_access(telegram_user_id: int) -> AccessRequest | None:
    now = datetime.now(timezone.utc)
    with connection() as conn:
        conn.execute(
            """
            UPDATE access_requests
               SET status = 'approved',
                   resolved_at = %s
             WHERE telegram_user_id = %s
            """,
            (now, telegram_user_id),
        )
    logger.info("access approved user_id=%s", telegram_user_id)
    return get_access_request(telegram_user_id)


def decline_access(telegram_user_id: int) -> AccessRequest | None:
    now = datetime.now(timezone.utc)
    with connection() as conn:
        conn.execute(
            """
            UPDATE access_requests
               SET status = 'declined',
                   decline_count = decline_count + 1,
                   resolved_at = %s
             WHERE telegram_user_id = %s
            """,
            (now, telegram_user_id),
        )
    logger.info("access declined user_id=%s", telegram_user_id)
    return get_access_request(telegram_user_id)


def revoke_access(telegram_user_id: int) -> AccessRequest | None:
    """Revoke without deleting users or learning rows."""
    now = datetime.now(timezone.utc)
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO access_requests (
                telegram_user_id, status, decline_count, requested_at, resolved_at
            ) VALUES (%s, 'revoked', 0, %s, %s)
            ON CONFLICT (telegram_user_id) DO UPDATE SET
                status = 'revoked',
                resolved_at = EXCLUDED.resolved_at
            """,
            (telegram_user_id, now, now),
        )
    logger.info("access revoked user_id=%s", telegram_user_id)
    return get_access_request(telegram_user_id)


def ensure_approved_row(
    telegram_user_id: int, *, display_name: str | None = None
) -> None:
    """Insert approved if missing; never un-revoke or overwrite status.

    Used by save_onboarding so test fixtures and first-time saves keep
    ``is_registered`` working without granting access to a revoked user.
    """
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO access_requests (
                telegram_user_id, display_name, status,
                requested_at, resolved_at
            ) VALUES (%s, %s, 'approved', NOW(), NOW())
            ON CONFLICT (telegram_user_id) DO NOTHING
            """,
            (telegram_user_id, display_name),
        )


def _row_to_request(row: Any) -> AccessRequest:
    return AccessRequest(
        telegram_user_id=int(row["telegram_user_id"]),
        username=row["username"],
        display_name=row["display_name"],
        status=row["status"],  # type: ignore[arg-type]
        decline_count=int(row["decline_count"]),
        requested_at=row["requested_at"],
        resolved_at=row["resolved_at"],
    )


def _ids_from_rows(rows: list[Any]) -> set[int]:
    return {int(r["telegram_user_id"]) for r in rows}


def delivery_lister_ids() -> dict[str, Callable[[], set[int]]]:
    """Canonical delivery list call sites for the revoke drift test.

    Every bot-initiated eligible-user list must appear here. A new list that
    forgets the view will not be in this dict — add it when you add the list.
    """
    from apps.bot.scheduler import list_candidate_users
    from apps.bot.services import couple
    from core.services import (
        calibration,
        errors,
        motivation,
        shared_content,
        watch_import,
    )

    def _candidate() -> set[int]:
        return {u.telegram_user_id for u in list_candidate_users()}

    def _motivation() -> set[int]:
        return {u.telegram_user_id for u in motivation.list_motivation_users()}

    def _fossil() -> set[int]:
        return set(errors.list_fossil_sweep_user_ids())

    def _calibration() -> set[int]:
        return set(calibration.list_calibration_user_ids())

    def _couple() -> set[int]:
        return set(couple.registered_user_ids())

    def _watch() -> set[int]:
        return set(watch_import.list_registered_user_ids())

    def _shared() -> set[int]:
        return set(shared_content.list_recipients())

    return {
        "list_candidate_users": _candidate,
        "list_motivation_users": _motivation,
        "list_fossil_sweep_user_ids": _fossil,
        "list_calibration_user_ids": _calibration,
        "registered_user_ids": _couple,
        "list_registered_user_ids": _watch,
        "list_recipients": _shared,
    }
