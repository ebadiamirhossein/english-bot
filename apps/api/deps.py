"""FastAPI dependencies: database handle, the current session, rate limits.

All three are thin. ``get_db`` hands out the same pooled connection every other
process uses; ``get_current_user`` resolves the session cookie through **one**
service call; ``rate_limit`` counts a request against two Postgres-backed
buckets. Nothing here parses a request body or runs a query — CLAUDE.md §2 keeps
that in service functions.

**Everything here is a plain ``def``.** The standing rule (TASKS §6, issue #7)
names ``llm.py`` and ``speech.py``, and nothing in this file touches either — but
the rule exists because *blocking work must not run on the event loop*, and a
psycopg pool checkout and an ECDSA verification both block. A plain ``def`` costs
one threadpool thread; an ``async def`` stalls every concurrent request the
worker is serving.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime, timezone

import psycopg
from fastapi import Depends, HTTPException, Request, Response, status

from core.config import Settings, load_settings
from core.db import connection
from core.services import auth

logger = logging.getLogger(__name__)

# The `__Host-` prefix is only accepted by a browser with Secure, Path=/ and NO
# Domain attribute — a browser-enforced guarantee that no sibling subdomain can
# set or overwrite this cookie. The unprefixed fallback exists solely because
# http://localhost cannot carry a Secure cookie consistently across browsers.
SESSION_COOKIE_SECURE = "__Host-ee_session"
SESSION_COOKIE_INSECURE = "ee_session"

# Not "none". app.foundgrant.com and api.foundgrant.com are different ORIGINS but
# the same SITE, and SameSite is decided by site — so Lax is sent on the
# cross-origin fetch and None would only additionally expose the cookie to
# unrelated sites. What actually stops CSRF here is the CORS preflight on JSON
# POSTs plus the origin allow-list; see apps/api/README.md.
SESSION_COOKIE_SAMESITE = "lax"


def session_cookie_name(settings: Settings) -> str:
    return (
        SESSION_COOKIE_INSECURE
        if settings.auth_cookie_insecure
        else SESSION_COOKIE_SECURE
    )


def set_session_cookie(
    response: Response, settings: Settings, raw_token: str
) -> None:
    """Write the session cookie with the full attribute set.

    Host-only on purpose — no ``domain`` argument. The cookie belongs to
    ``api.foundgrant.com`` and is never sent to Vercel or any other subdomain.
    The consequence is that Next middleware cannot see it, which is why route
    protection in ``apps/web`` is a client guard (known issue #74).
    """
    response.set_cookie(
        key=session_cookie_name(settings),
        value=raw_token,
        max_age=settings.auth_session_days * 24 * 60 * 60,
        path="/",
        secure=not settings.auth_cookie_insecure,
        httponly=True,
        samesite=SESSION_COOKIE_SAMESITE,
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    """Expire the cookie. Always paired with a server-side revoke."""
    response.delete_cookie(
        key=session_cookie_name(settings),
        path="/",
        secure=not settings.auth_cookie_insecure,
        httponly=True,
        samesite=SESSION_COOKIE_SAMESITE,
    )


def get_settings() -> Settings:
    return load_settings()


def get_db() -> Iterator[psycopg.Connection]:
    """Yield a pooled connection for the life of one request.

    A plain ``def`` generator: FastAPI runs it in a threadpool, so the pool's
    blocking checkout never sits on the event loop. See README.md.
    """
    with connection() as conn:
        yield conn


def get_current_user(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> auth.AuthenticatedUser | None:
    """Resolve the caller's session, or ``None``.

    **The only place a session is resolved.** No route repeats this, and
    ``tests/test_auth.py`` asserts it by parsing ``apps/api``.

    The sliding expiry is re-set *here*, on the injected ``Response``, rather
    than in each route: FastAPI merges headers set on a dependency's Response
    into the final one, and doing it per-route is exactly how "no route
    re-implements session lookup" gets broken by accident.

    Known, harmless asymmetry: the database write happens during dependency
    resolution, so if the route below then raises, the row is extended while the
    client's cookie still carries the old ``Max-Age``. The session is valid
    either way and the browser re-learns the expiry on the next success.
    """
    raw = request.cookies.get(session_cookie_name(settings), "")
    if not raw:
        return None
    user = auth.resolve_session(
        raw_token=raw, now=datetime.now(timezone.utc), settings=settings
    )
    if user is None:
        return None
    if user.renewed:
        set_session_cookie(response, settings, raw)
    # Picked up by the exception handler's log line (PRD §10: route names and
    # user ids, never bodies).
    request.state.user_id = user.telegram_user_id
    return user


def require_current_user(
    user: auth.AuthenticatedUser | None = Depends(get_current_user),
) -> auth.AuthenticatedUser:
    """``get_current_user`` or a 401. The dependency every gated route uses."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated"
        )
    return user


def _client_key(request: Request) -> str:
    """Who to count this request against.

    Behind Caddy this is only the real client when uvicorn runs with
    ``--proxy-headers --forwarded-allow-ips 127.0.0.1`` (known issue #76).
    Without those flags every request reports 127.0.0.1 and the per-client half
    of the limit silently collapses into one shared bucket — a failure that
    looks exactly like success, which is why it is named in the unit file and in
    DEPLOYMENT.md rather than left implicit.
    """
    client = request.client
    return client.host if client and client.host else "unknown"


def rate_limit(
    route: str, per_client: int, overall: int, window_seconds: int = 60
):
    """Build a dependency that counts a request against both limits.

    Two limits because either alone is weak: per-client is evaded from many
    addresses, and global-only lets one attacker deny sign-in to the two
    learners. Counted in Postgres, never in memory — the API runs
    ``--workers 2``.
    """

    def _dependency(
        request: Request, settings: Settings = Depends(get_settings)
    ) -> None:
        allowed = auth.check_rate_limit(
            route=route,
            client=_client_key(request),
            per_client=per_client,
            overall=overall,
            window_seconds=window_seconds,
            now=datetime.now(timezone.utc),
            settings=settings,
        )
        if not allowed:
            # No Retry-After: precision here only helps someone tuning an
            # attack, and the two learners will never see this.
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate_limited",
            )

    return _dependency
