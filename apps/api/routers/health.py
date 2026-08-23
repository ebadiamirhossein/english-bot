"""Liveness routes. The only two routes that exist at W1b.

Both are plain ``def``: they touch the database through a blocking driver, so
running them in FastAPI's threadpool keeps the event loop free (see
``apps/api/README.md``).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from apps.api.deps import get_current_user
from apps.api.schemas import Health, Session
from core.db import current_schema_version
from core.services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health)
def health() -> Health | JSONResponse:
    """Report the applied schema version, read through ``core.db``.

    Reading the version means a broken DATABASE_URL, an unreachable pooler or
    an unmigrated database surfaces here — on the route a monitor polls —
    instead of inside the first user-facing route that happens to query.

    A database that cannot be reached is not a 500: the service is up and
    answering, its dependency is not. 503 with ``ok: false`` is what an uptime
    check can act on, and no exception detail crosses the wire.
    """
    try:
        version = current_schema_version()
    except Exception:
        logger.exception("Health check could not read schema_version")
        return JSONResponse(
            status_code=503, content={"ok": False, "schema_version": None}
        )
    return Health(ok=True, schema_version=version)


@router.get("/health/auth", response_model=Session | None)
def health_auth(
    user: AuthenticatedUser | None = Depends(get_current_user),
) -> Session | None:
    """Return the resolved session, or explicit ``null``.

    **200 with ``null`` for an anonymous caller, never 401.** "Am I signed in,
    as far as the API is concerned" must be answerable with one curl rather than
    by hunting through a browser console (W0 risk R4), and this is also the
    route ``apps/web``'s client guard polls — it needs the two cases to differ
    in the body, not in the status.

    There is deliberately no second ``GET /auth/me``: one route with this job
    means one place for session logic to live.
    """
    if user is None:
        return None
    return Session(
        telegram_user_id=user.telegram_user_id,
        name=user.name,
        expires_at=user.expires_at,
    )
