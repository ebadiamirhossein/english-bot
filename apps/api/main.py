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
from apps.api.routers import cards as cards_router
from apps.api.routers import checkpoint as checkpoint_router
from apps.api.routers import correct as correct_router
from apps.api.routers import health as health_router
from apps.api.routers import items as items_router
from apps.api.routers import lessons as lessons_router
from apps.api.routers import session as session_router
from apps.api.routers import video as video_router
from apps.api.routers import conversation as conversation_router
# W14r: `shadow` is no longer imported here — see the unregistration below.
# **The module is NOT orphaned:** `tests/test_shadow_retired.py` imports it
# and mounts it, so a retired router that stopped importing would still fail
# a test rather than rot unnoticed.
from apps.api.routers import week as week_router
from apps.api.routers import progress as progress_router
from apps.api.routers import push as push_router
from apps.api.routers import placement as placement_router
from apps.api.routers import admin as admin_router
from core import monitoring
from core.config import Settings, load_settings
from core.logging import configure_console_logging
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
    """Sentry, through its one door (W23; ``core.monitoring``).

    The W1b stub this replaces promised exactly this shape — *"the DSN is read
    in ``core.config`` like every other environment variable and passed in
    through ``settings``; this function is the one place the SDK's init call
    goes"* — and the SDK call itself now lives in ``core.monitoring``, so
    ``apps/api`` imports no ``sentry_sdk`` at all. Off while ``SENTRY_DSN`` is
    unset, which it is until the launch pass.
    """
    monitoring.init_monitoring(settings, component="api")


def send_operator_alert(text: str) -> None:
    """Write a formatted operator alert to the log at ERROR.

    The bot's channel (``apps.bot.alerts.operator_send``) belongs to the bot
    process; the API cannot borrow it without importing Telegram, which
    CLAUDE.md §2 forbids in every direction.

    **W23: THIS IS NO LONGER THE API'S ONLY CHANNEL (#65).** The exception
    itself goes to Sentry from ``handle_unexpected_error`` — type, frames, user
    id and route, never the message — and Sentry emails the operator. This
    formatted alert carries the exception's MESSAGE and full traceback, which is
    exactly what ruling 0.2 keeps out of Sentry, so it stays in the journal on
    the host and goes nowhere else.
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
    # W23: every unhandled exception, unthrottled — Sentry groups repeats into
    # one issue, which is the throttle's job done better. Never raises.
    monitoring.capture_exception(exc, user_id=user_id, route=route)

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
    # #117: the `API built origins=… routes=…` line below did not appear in
    # `journalctl` on the 2026-08-25 deploy, and a deployment step must not cite
    # evidence that does not exist. The cause is that `apps/api` was the only
    # one of the three apps that never configured logging — the bot and the
    # worker both call `core.logging.configure_logging` at start-up. uvicorn's
    # own config attaches handlers to the `uvicorn.*` loggers only and leaves
    # the ROOT logger bare, so every INFO record from `apps.*` and `core.*`
    # propagated to a root with no handler and fell through to
    # `logging.lastResort`, which emits WARNING and above. The line was being
    # produced and dropped.
    #
    # Console only, and deliberately not `configure_logging`: that installs a
    # RotatingFileHandler, and the API runs `--workers 2` — two processes
    # rotating one file is the hazard `apps/worker/main.py` already gives its
    # own log path to avoid. systemd captures stdout, which is where journalctl
    # reads from, so a stream handler is all this needs.
    configure_console_logging(cfg)
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
    app.include_router(items_router.router)
    app.include_router(cards_router.router)
    app.include_router(session_router.router)
    app.include_router(lessons_router.router)
    app.include_router(checkpoint_router.router)
    app.include_router(video_router.router)
    # ── W14r: THE SHADOW ROUTES ARE NO LONGER REGISTERED, 2026-09-08 ────────
    #
    # The registration this replaces, quoted rather than removed silently
    # (#82's shape, and #348's precedent for an unregistration):
    #
    #     app.include_router(shadow_router.router)
    #
    # **WHY, AND IT IS A MEASUREMENT AND NOT A PREFERENCE (#376).** Azure
    # pronunciation assessment **detects a word said as a different word and
    # does not detect an inflectional ending.** Four deliberate errors were put
    # to it — `model→models`, `window→windows`, `can→can't`, `validation` — and
    # **only `trust` was caught**, at 44.0 against neighbours at 97.
    # **Inflection and agreement are most of what a B1→B2 learner gets wrong
    # and most of what the error journal exists to collect**, so the instrument
    # is blind to the errors this product is built around. And W13b's
    # conversation now does the job the ladder was climbing toward.
    #
    # **OPERATOR RULING 2026-09-08.** W14's three acceptance criteria were met
    # and evidenced; this is a retirement, which is a different sentence from a
    # failure.
    #
    # **NOTHING IS DELETED.** `apps/api/routers/shadow.py`,
    # `services/shadow_score.py`, `speech_api.py`, migration 024,
    # `speech_attempts` and all 29 shadow tests are untouched. The tests build
    # their own app and mount this router explicitly, so the evidence stays
    # runnable while the product stops exposing it.
    #
    # **WHAT IS NOT FIXED BY THIS, SAID SO NOBODY READS THE SILENCE AS AN
    # ANSWER: #364 does not close.** `/talk`'s microphone sends the second
    # learner's voice to OpenAI. The recipient changed; the question did not.
    app.include_router(conversation_router.router)
    app.include_router(week_router.router)
    # W19. Added to BOTH lists in the same commit (#255).
    app.include_router(progress_router.router)
    # W20. Added to BOTH lists in the same commit (#255).
    app.include_router(push_router.router)
    # W18. Added to BOTH lists in the same commit (#255).
    app.include_router(placement_router.router)
    # W23. Added to BOTH lists in the same commit (#255).
    app.include_router(admin_router.router)
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
                    items_router.router,
                    cards_router.router,
                    session_router.router,
                    lessons_router.router,
                    checkpoint_router.router,
                    # **#255, second instance, corrected on the line this slice
                    # was editing anyway.** W13-i registered `video_router`
                    # above and did not add it here, so the startup log — the
                    # deploy's own liveness evidence — has been claiming a route
                    # set the app does not have. The blind spot itself stays
                    # open: nothing checks these two lists agree.
                    video_router.router,
                    # W14r: unregistered above, so it is out of this list
                    # too. **Keeping it here would make the startup log claim a
                    # route set the app does not have** — #255's defect exactly,
                    # which the comment above this block was written about.
                    #
                    #     shadow_router.router,
                    # W13b. **Added to BOTH lists in the same commit**, which is
                    # what the note above says W13-i failed to do -- the blind
                    # spot is still unchecked, so the only defence is doing it
                    # deliberately while editing.
                    conversation_router.router,
                    week_router.router,
                    progress_router.router,
                    push_router.router,
                    placement_router.router,
                    admin_router.router,
                )
                for route in router.routes
            )
        ),
    )
    return app


app = create_app()
