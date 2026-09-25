"""W23: `GET /admin/activity` — the bot's `/admin` panel, ported to the web.

It parses, authorises, calls **one** service function and serialises
(CLAUDE.md §2). **Activity, never content** (TASKS' W23 row; CLAUDE.md §5 *"the
admin panel shows activity, never content"*): the rows are
`core.services.admin_panel`'s, chosen at S18d and unchanged here.

**READ-ONLY.** The bot panel's actions — approve, decline, revoke, pause — are
NOT ported: approving is the bot's access-request flow, which W22 decides the
fate of, and a write surface on a public API is a second authorisation path to
review for a panel two people use. They stay on the bot until W22.

**WHO IS THE OPERATOR: `ADMIN_USER_IDS`**, a `users.id` allowlist in `.env` —
empty means nobody. **404, NOT 403, FOR ANYBODY ELSE** — the answer an unknown
path gets, so the route does not announce that an operator surface exists.

**PLAIN `def`** (standing rule 6 / #7): it blocks on a psycopg pool checkout.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from apps.api.deps import get_settings, rate_limit, require_current_user
from apps.api.schemas import AdminActivityOut, AdminUserOut
from core.config import Settings
from core.services import admin_panel
from core.services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


@router.get(
    "/admin/activity",
    response_model=AdminActivityOut,
    dependencies=[
        Depends(rate_limit("admin", per_client=120, overall=240, window_seconds=3600))
    ],
)
def admin_activity(
    session: AuthenticatedUser = Depends(require_current_user),
    settings: Settings = Depends(get_settings),
) -> AdminActivityOut:
    activity = admin_panel.operator_activity(
        session.id,
        admin_user_ids=settings.admin_user_ids,
        now=datetime.now(timezone.utc),
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="not_found")
    logger.info("admin activity read user_id=%s", session.id)
    return admin_out(activity)


def admin_out(activity: admin_panel.OperatorActivity) -> AdminActivityOut:
    """The wire shape. `scripts/export_admin_fixture.py` builds the frontend's
    fixture through this same function (#190)."""
    return AdminActivityOut(
        pending_requests=activity.pending_requests,
        weekly_goal_days=activity.weekly_goal_days,
        lookback_days=activity.lookback_days,
        users=[
            AdminUserOut(
                id=u.id,
                name=u.name,
                cefr_level=u.cefr_level,
                current_streak=u.current_streak,
                active_days=u.active_days,
                last_active=u.last_active,
                paused=u.paused,
                revoked=u.revoked,
            )
            for u in activity.users
        ],
    )
