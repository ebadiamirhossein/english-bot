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
from apps.api.schemas import Health
from core.db import current_schema_version

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


@router.get("/health/auth")
def health_auth(
    user: dict[str, object] | None = Depends(get_current_user),
) -> dict[str, object] | None:
    """Return the resolved session, or explicit ``null``.

    Untyped until W2 gives a session a shape. Its whole reason to exist is
    that "am I signed in, as far as the API is concerned" must be answerable
    with one curl, rather than by hunting through a browser console (W0 risk
    R4).
    """
    return user
