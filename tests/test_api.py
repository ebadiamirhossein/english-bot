"""W1b: the API scaffold, exercised through the real ASGI transport.

CLAUDE.md §3 rule 1 — v2 shipped 161 green tests over a dead feature because
every one of them called a handler directly. Nothing here calls a route
function; every request goes through ``httpx.ASGITransport`` into the app
``uvicorn apps.api.main:app`` serves.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from fastapi import FastAPI

from apps.api import main as api_main
from apps.api.deps import get_current_user
from apps.api.main import (
    GENERIC_ERROR_BODY,
    LOCAL_WEB_ORIGIN,
    allowed_origins,
    create_app,
)
from core.config import Settings, load_settings

API_DIR = Path(__file__).resolve().parents[1] / "apps" / "api"


def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    raise_app_exceptions: bool = True,
) -> httpx.Response:
    """One request through the ASGI transport, synchronously."""

    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=app, raise_app_exceptions=raise_app_exceptions
        )
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.request(method, path, headers=headers or {})

    return asyncio.run(_go())


@pytest.fixture
def app() -> FastAPI:
    return create_app()


# --- health -------------------------------------------------------------------


def _schema_version_from_database() -> int:
    """Read the version the test's own way — never through the route's helper.

    CLAUDE.md §3 rule 5: an expected value computed by the function under test
    proves only that the function agrees with itself. This opens its own
    connection and writes its own query.
    """
    settings = load_settings()
    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    assert row is not None
    return int(row[0] or 0)


def test_current_schema_version_matches_the_database() -> None:
    """The function itself, not just the route that calls it.

    Expected value read on a separate connection with its own query, so this
    is not the function agreeing with itself (CLAUDE.md §3 rule 5).
    """
    from core.db import current_schema_version

    version = current_schema_version()
    assert isinstance(version, int)
    assert version == _schema_version_from_database()


def test_current_schema_version_runs_no_ddl() -> None:
    """Structural: /health polls this, and a probe must not create tables.

    ``status()`` calls ``_ensure_schema_version`` — a ``CREATE TABLE IF NOT
    EXISTS`` — which is exactly why the route does not call it. Someone
    "fixing" a fresh-database edge case by reusing that helper here would
    reintroduce DDL on a route a monitor hits every minute; this fails on that
    commit.
    """
    import ast
    import inspect

    from core import db

    tree = ast.parse(inspect.getsource(db.current_schema_version))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            statement = " ".join(node.value.upper().split())
            assert not statement.startswith(("CREATE", "ALTER", "DROP", "TRUNCATE")), (
                f"current_schema_version issues DDL: {node.value!r}"
            )
        if isinstance(node, ast.Call):
            called = node.func
            name = getattr(called, "attr", getattr(called, "id", ""))
            assert name != "_ensure_schema_version", (
                "current_schema_version must not create schema_version"
            )


def test_health_reports_the_applied_schema_version(app: FastAPI) -> None:
    response = _request(app, "GET", "/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["schema_version"] == _schema_version_from_database()
    # Floor: migrations 001–008 exist in the repo, so a database this suite can
    # talk to has at least 8 applied. Catches a route that answers 0 or null.
    assert body["schema_version"] >= 8


def test_health_answers_503_when_the_database_is_unreachable(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of reading the DB here: the failure surfaces on /health."""

    def _boom() -> int:
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(
        "apps.api.routers.health.current_schema_version", _boom
    )
    response = _request(app, "GET", "/health")
    assert response.status_code == 503
    assert response.json() == {"ok": False, "schema_version": None}
    assert "connection refused" not in response.text


def test_health_auth_returns_explicit_null(app: FastAPI) -> None:
    response = _request(app, "GET", "/health/auth")
    assert response.status_code == 200
    # Literally `null`, not `{}` and not an empty body: W2's acceptance is
    # "curl says whether I am signed in".
    assert response.text.strip() == "null"
    assert json.loads(response.text) is None


def test_health_auth_renders_whatever_the_dependency_resolves(
    app: FastAPI,
) -> None:
    """A W2 auth failure has to be visible here, so the route must read the dep.

    W2 gave the session a shape, so the override now returns the dataclass
    ``get_current_user`` really returns. The W1b version of this test handed
    back a bare dict, which was right while the dependency was a stub and is
    wrong now — the route serialises a typed body and a dict would 500.
    """
    from datetime import datetime, timedelta, timezone

    from core.services.auth import AuthenticatedUser

    expires = datetime.now(timezone.utc) + timedelta(days=30)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        telegram_user_id=7222549221, name="Test", expires_at=expires
    )
    try:
        response = _request(app, "GET", "/health/auth")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["telegram_user_id"] == 7222549221
    assert body["name"] == "Test"


# --- CORS ---------------------------------------------------------------------


def _settings_with(web_origin: str) -> Settings:
    from dataclasses import replace

    return replace(load_settings(), web_origin=web_origin)


def test_allowed_origins_is_exactly_two_when_web_origin_is_set() -> None:
    origins = allowed_origins(_settings_with("https://app.example.com"))
    assert origins == ["https://app.example.com", LOCAL_WEB_ORIGIN]


def test_allowed_origins_never_contains_a_wildcard() -> None:
    for web_origin in (
        "",
        "https://app.example.com",
        "*",
        "https://*.example.com",
        "app.example.com",
    ):
        origins = allowed_origins(_settings_with(web_origin))
        assert LOCAL_WEB_ORIGIN in origins
        assert not any("*" in o for o in origins)
        assert all(o.startswith(("http://", "https://")) for o in origins)


def test_web_origin_must_be_a_usable_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Set the variable the way it is really set, and fail at startup.

    CORS compares origins literally: `https://app.example.com/` matches
    nothing a browser ever sends, and the symptom is a blank screen on a phone
    with a console message nobody is reading (CLAUDE.md §3 rule 3).
    """
    from core.config import ConfigError

    for bad in ("app.example.com", "https://app.example.com/"):
        monkeypatch.setenv("WEB_ORIGIN", bad)
        with pytest.raises(ConfigError, match="WEB_ORIGIN"):
            load_settings()

    monkeypatch.setenv("WEB_ORIGIN", "https://app.example.com")
    assert load_settings().web_origin == "https://app.example.com"
    monkeypatch.delenv("WEB_ORIGIN")
    assert load_settings().web_origin == ""


def test_cors_middleware_has_no_regex_and_no_wildcard(app: FastAPI) -> None:
    """A credentialed wildcard hands the W2 session cookie to any origin."""
    cors = [
        mw
        for mw in app.user_middleware
        if mw.cls.__name__ == "CORSMiddleware"
    ]
    assert len(cors) == 1
    kwargs = cors[0].kwargs
    assert kwargs.get("allow_origin_regex") in (None, "")
    assert "*" not in kwargs["allow_origins"]
    assert kwargs["allow_credentials"] is True


def test_cors_allows_the_local_web_origin(app: FastAPI) -> None:
    response = _request(
        app, "GET", "/health", headers={"Origin": LOCAL_WEB_ORIGIN}
    )
    assert response.headers.get("access-control-allow-origin") == LOCAL_WEB_ORIGIN


def test_cors_refuses_an_unknown_origin(app: FastAPI) -> None:
    response = _request(
        app, "GET", "/health", headers={"Origin": "https://evil.example"}
    )
    assert response.headers.get("access-control-allow-origin") is None


def test_cors_tells_the_browser_credentials_are_allowed(app: FastAPI) -> None:
    """W2 puts a session cookie on this API.

    ``credentials: "include"`` in the browser is only honoured when the response
    carries ``Access-Control-Allow-Credentials: true`` *and* a concrete origin.
    Without this header the cookie is silently dropped and every request after
    sign-in is anonymous — a failure invisible on localhost, because the phone
    is where the two origins are really different.
    """
    response = _request(
        app, "GET", "/health", headers={"Origin": LOCAL_WEB_ORIGIN}
    )
    assert response.headers.get("access-control-allow-origin") == LOCAL_WEB_ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_refuses_credentials_to_an_unknown_origin(app: FastAPI) -> None:
    """The other half: a site that is not ours gets no usable grant.

    Note what is asserted and what is not. Starlette emits
    ``Access-Control-Allow-Credentials: true`` on *every* CORS response, allowed
    origin or not — it withholds only ``Access-Control-Allow-Origin``. That is
    safe, because a browser requires **both** before it will expose a
    credentialed response, so the missing origin header is the whole refusal.

    Asserting the absence of the credentials header instead would fail against
    correct code and invite someone to "fix" the middleware. The origin header
    is the one that decides.
    """
    response = _request(
        app, "GET", "/health", headers={"Origin": "https://evil.example"}
    )
    assert response.headers.get("access-control-allow-origin") is None


def test_cors_preflight_allows_a_json_post_from_the_web_origin(
    app: FastAPI,
) -> None:
    """Every auth route is a JSON POST, which is never a simple request.

    That preflight, answered only for the two allowed origins, is what actually
    stops CSRF here — not ``SameSite=Lax``, which treats any subdomain of the
    site as same-site. If a route ever accepted a form encoding it would become
    a simple request and lose this, which is why no auth route does.
    """
    response = _request(
        app,
        "OPTIONS",
        "/auth/login/begin",
        headers={
            "Origin": LOCAL_WEB_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.headers.get("access-control-allow-origin") == LOCAL_WEB_ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"
    assert "POST" in (response.headers.get("access-control-allow-methods") or "")


def test_cors_preflight_from_an_unknown_origin_is_not_allowed(
    app: FastAPI,
) -> None:
    response = _request(
        app,
        "OPTIONS",
        "/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") is None


# --- the single exception handler ---------------------------------------------


SECRET = "SELECT password FROM users WHERE id = 1"


def _app_with_a_failing_route() -> FastAPI:
    application = create_app()

    @application.get("/_test_boom")
    def boom() -> None:
        raise RuntimeError(SECRET)

    return application


@pytest.fixture
def hermetic_throttle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point the real alert throttle at tmp_path.

    Configuration is read the way it is really read (CLAUDE.md §3 rule 3):
    ``should_send_alert`` calls ``load_settings()``, so the env var is the
    only lever that works — stubbing the function would test nothing.
    """
    path = tmp_path / "alert_throttle.json"
    monkeypatch.setenv("ALERT_THROTTLE_FILE", str(path))
    return path


def test_unhandled_error_returns_a_generic_body_with_no_stack_trace(
    hermetic_throttle: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_main, "send_operator_alert", lambda text: None)
    response = _request(
        _app_with_a_failing_route(),
        "GET",
        "/_test_boom",
        raise_app_exceptions=False,
    )
    assert response.status_code == 500
    assert response.json() == GENERIC_ERROR_BODY
    for leak in (SECRET, "RuntimeError", "Traceback", "apps/api"):
        assert leak not in response.text


def test_unhandled_error_logs_route_and_user_but_not_the_body(
    hermetic_throttle: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(api_main, "send_operator_alert", lambda text: None)
    with caplog.at_level(logging.ERROR, logger="apps.api.main"):
        _request(
            _app_with_a_failing_route(),
            "GET",
            "/_test_boom",
            raise_app_exceptions=False,
        )
    messages = [r.getMessage() for r in caplog.records]
    assert any("route=boom" in m and "user_id=None" in m for m in messages)


def test_unhandled_error_alerts_once_then_throttles(
    hermetic_throttle: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []
    monkeypatch.setattr(api_main, "send_operator_alert", sent.append)
    application = _app_with_a_failing_route()
    for _ in range(3):
        _request(
            application, "GET", "/_test_boom", raise_app_exceptions=False
        )
    assert len(sent) == 1
    assert "RuntimeError" in sent[0]
    assert "boom" in sent[0]
    assert hermetic_throttle.is_file()


def test_alerting_failure_does_not_break_the_response(
    hermetic_throttle: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One failed request must never become two."""

    def _explode(*args: Any, **kwargs: Any) -> None:
        raise OSError("throttle file is read-only")

    monkeypatch.setattr(api_main, "should_send_alert", _explode)
    response = _request(
        _app_with_a_failing_route(),
        "GET",
        "/_test_boom",
        raise_app_exceptions=False,
    )
    assert response.status_code == 500
    assert response.json() == GENERIC_ERROR_BODY


# --- the plain-`def` convention (apps/api/README.md) ---------------------------

# `core/llm.py` and `core/speech.py` are synchronous. Inside an `async def`
# route, one of these calls blocks the event loop and stalls every other
# request the worker is serving — known issue #7 with a wider blast radius.
BLOCKING_CALLS = {
    ("llm", "chat"),
    ("speech", "transcribe"),
    ("speech", "synthesize"),
}
HTTP_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options"}
)


def _is_route(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True when the function is decorated with @router.get / @app.post / ..."""
    for decorator in node.decorator_list:
        call = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(call, ast.Attribute) and call.attr in HTTP_METHODS:
            return True
    return False


def _blocking_names(tree: ast.AST) -> set[str]:
    """Names bound by `from core.llm import chat` and friends."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        module = node.module.rsplit(".", 1)[-1]
        for alias in node.names:
            if (module, alias.name) in BLOCKING_CALLS:
                bound.add(alias.asname or alias.name)
    return bound


# The sanctioned escape when a route genuinely must be async: push the
# blocking call off the loop, exactly as S9a did for the bot.
OFF_LOOP_HELPERS = frozenset({"to_thread", "run_in_threadpool", "run_sync"})


def _off_loop_node_ids(node: ast.AST) -> set[int]:
    """Ids of every node passed to asyncio.to_thread() and friends."""
    exempt: set[int] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        name = func.attr if isinstance(func, ast.Attribute) else (
            func.id if isinstance(func, ast.Name) else ""
        )
        if name not in OFF_LOOP_HELPERS:
            continue
        for arg in list(child.args) + [kw.value for kw in child.keywords]:
            for inner in ast.walk(arg):
                exempt.add(id(inner))
    return exempt


def _references_blocking_call(
    node: ast.AST, bound: set[str]
) -> str | None:
    """Return the offending reference, or None."""
    exempt = _off_loop_node_ids(node)
    for child in ast.walk(node):
        if id(child) in exempt:
            continue
        if isinstance(child, ast.Attribute) and isinstance(
            child.value, ast.Name
        ):
            if (child.value.id, child.attr) in BLOCKING_CALLS:
                return f"{child.value.id}.{child.attr}"
        elif isinstance(child, ast.Name) and child.id in bound:
            return child.id
    return None


def _async_routes_with_blocking_calls(source: str, filename: str) -> list[str]:
    tree = ast.parse(source, filename=filename)
    bound = _blocking_names(tree)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        if not _is_route(node):
            continue
        hit = _references_blocking_call(node, bound)
        if hit:
            offenders.append(f"{filename}:{node.lineno} {node.name} → {hit}")
    return offenders


_OFFENDING_SOURCE = '''
from fastapi import APIRouter
from core import llm

router = APIRouter()


@router.post("/correct")
async def correct(text: str) -> dict:
    return llm.chat(text)
'''

_COMPLIANT_SOURCE = '''
import asyncio

from fastapi import APIRouter
from core import llm
from core.speech import transcribe

router = APIRouter()


@router.post("/correct")
def correct(text: str) -> dict:
    return llm.chat(text)


@router.post("/voice")
async def voice(blob: bytes) -> dict:
    return await asyncio.to_thread(transcribe, blob)
'''


def test_the_plain_def_detector_actually_detects() -> None:
    """The rule has nothing to catch yet, so prove the detector is not inert.

    CLAUDE.md §3 rule 4: a green test over an unreachable path proves nothing.
    """
    assert _async_routes_with_blocking_calls(_OFFENDING_SOURCE, "fake.py") == [
        "fake.py:9 correct → llm.chat"
    ]
    # A plain `def` route calling llm.chat is correct, and
    # `await asyncio.to_thread(transcribe, ...)` is the sanctioned escape.
    # Flagging either would push people to hide the call instead.
    assert _async_routes_with_blocking_calls(_COMPLIANT_SOURCE, "fake.py") == []


def test_llm_and_speech_routes_are_plain_def() -> None:
    offenders: list[str] = []
    for path in sorted(API_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        offenders += _async_routes_with_blocking_calls(
            path.read_text(encoding="utf-8"), str(path.name)
        )
    assert offenders == [], (
        "A route that calls llm.chat / speech.transcribe / speech.synthesize "
        "must be a plain `def` (apps/api/README.md): " + "; ".join(offenders)
    )
