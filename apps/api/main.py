"""FastAPI application factory.

Three things live here and nothing else: CORS, the single exception handler,
and the router table. Business logic is in ``packages/core``; routes are in
``apps/api/routers``.

Run it with::

    uvicorn apps.api.main:app
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.routers import auth as auth_router
from apps.api.routers import correct as correct_router
from apps.api.routers import health as health_router
from core.config import Settings, load_settings
from core.services.alerts import format_alert, should_send_alert

logger = logging.getLogger(__name__)

API_TITLE = "English app API"
API_VERSION = "0.1.0"

# Shown to the client for any unhandled exception. Deliberately says nothing:
# a stack trace, an exception type or a SQL fragment in a response body is a
# free map of the backend (PRD §10 — the client learns nothing it cannot see).
GENERIC_ERROR_BODY = {"error": "internal_error"}

# The dev origin is a constant, not configuration: `pnpm dev` always serves
# on 3000, and putting it in .env means every developer's file drifts.
LOCAL_WEB_ORIGIN = "http://localhost:3000"


def allowed_origins(settings: Settings) -> list[str]:
    """Exactly the origins the browser may call the API from.

    A list, never a regex and never ``*``: the API will carry a session cookie
    from W2, and a wildcard origin with credentials is how a cookie leaks to
    any site that asks. ``WEB_ORIGIN`` is empty until the domain is chosen —
    until then localhost is the only entry, which fails visibly on a phone
    rather than silently allowing everything.
    """
    origins: list[str] = []
    for origin in (settings.web_origin, LOCAL_WEB_ORIGIN):
        if not origin or origin in origins:
            continue
        # Belt and braces: core.config already refuses a WEB_ORIGIN that is
        # not scheme-qualified, but this list is what the middleware trusts,
        # and "the validator upstream catches it" is how wildcards ship.
        if "*" in origin or not origin.startswith(("http://", "https://")):
            logger.error(
                "Refusing unusable CORS origin %r — dropped from the list",
                origin,
            )
            continue
        origins.append(origin)
    return origins


def init_monitoring(settings: Settings) -> None:
    """Sentry hook — a documented no-op at W1b.

    Deliberately does not import an SDK or read a DSN. When monitoring is
    wired, the DSN is read in ``core.config`` like every other environment
    variable and passed in through ``settings``; this function is the one
    place the SDK's init call goes, so nothing else in the app has to know it
    exists. ARCHITECTURE-v3 §2: "v2 had no visibility at all."
    """
    logger.info("Monitoring not configured (W1b stub)")


def send_operator_alert(text: str) -> None:
    """Deliver a formatted operator alert. A logging no-op at W1b.

    The bot's channel (``apps.bot.alerts.operator_send``) belongs to the bot
    process; the API cannot borrow it without importing Telegram, which
    CLAUDE.md §2 forbids in every direction. Until the API has a channel of
    its own, the alert lands in the log at ERROR — visible to whoever reads
    the log, and never silently dropped.
    """
    logger.error("OPERATOR ALERT (unsent — no API channel yet):\n%s", text)


def _route_name(request: Request) -> str:
    """Name of the matched route, or the raw path when nothing matched."""
    route = request.scope.get("route")
    name = getattr(route, "name", None)
    if name:
        return str(name)
    return request.url.path


def _request_user_id(request: Request) -> int | None:
    """User id if a dependency has resolved one. Always ``None`` before W2."""
    value = getattr(request.state, "user_id", None)
    return int(value) if isinstance(value, int) else None


def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Log with route + user, alert the operator, answer with nothing useful.

    Throttling and formatting are ``core.services.alerts`` — the same pair the
    bot's error handler uses, so a burst of API 500s cannot flood on a path
    the bot's throttle does not cover.
    """
    route = _route_name(request)
    user_id = _request_user_id(request)
    # PRD §10: logs carry route names and user ids, never request bodies.
    logger.exception(
        "Unhandled exception route=%s user_id=%s", route, user_id, exc_info=exc
    )

    key = f"api|{type(exc).__name__}|{route}"
    try:
        may_send, suppressed = should_send_alert(
            key, now=datetime.now(timezone.utc)
        )
        if may_send:
            tb = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
            send_operator_alert(
                format_alert(
                    handler=route,
                    user_id=user_id,
                    exc=exc,
                    tb=tb,
                    suppressed=suppressed,
                )
            )
        else:
            logger.warning(
                "Operator alert throttled key=%s suppressed=%s", key, suppressed
            )
    except Exception:
        # Alerting must never turn one failed request into two.
        logger.exception("Failed to raise operator alert for route=%s", route)

    return JSONResponse(status_code=500, content=GENERIC_ERROR_BODY)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. A factory so tests can pass their own settings."""
    cfg = settings or load_settings()
    init_monitoring(cfg)

    app = FastAPI(title=API_TITLE, version=API_VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(cfg),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_exception_handler(Exception, handle_unexpected_error)
    app.include_router(health_router.router)
    app.include_router(auth_router.router)
    app.include_router(correct_router.router)
    logger.info(
        "API built origins=%s routes=%s",
        ",".join(allowed_origins(cfg)),
        ",".join(
            sorted(
                getattr(route, "path", "?")
                for router in (
                    health_router.router,
                    auth_router.router,
                    correct_router.router,
                )
                for route in router.routes
            )
        ),
    )
    return app


app = create_app()
