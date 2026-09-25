"""The one door to Sentry (W23, build run 2 ruling 0.2). #65's operator channel.

``apps/api`` and ``apps/worker`` call four things here and import nothing from
``sentry_sdk`` themselves — ``tests/test_core_boundary.py`` holds that, the way
it holds ``passkeys.py`` as the only door to the WebAuthn library:

* ``init_monitoring(settings, component=...)`` — once, at start-up;
* ``capture_exception(exc, user_id=..., route=...)`` — from the API's single
  exception handler and the worker's ``run_job``;
* ``check_in(...)`` — the worker's liveness monitor (#438);
* ``scrub_event`` — the ``before_send`` hook, public so it can be tested alone.

**OFF WHEN ``SENTRY_DSN`` IS UNSET, AND IT IS UNSET UNTIL THE LAUNCH PASS.**
``init_monitoring`` then builds no client, and every other function here is a
no-op against the SDK's non-recording client — nothing leaves the process.

**WHAT SENTRY RECEIVES — THE WHOLE LIST, BECAUSE ``scrub_event`` IS AN ALLOWLIST
AND NOT A DENYLIST.** An exception's *type*, the stack frames' file, module,
function and line number, the learner's ``users.id``, the tags ``component`` and
``route``, the environment, and the SDK's name and version. For a worker
check-in, the monitor's slug, status, duration and schedule. **Nothing else**:
not the exception's message (``ValueError(f"... {text}")`` would carry learner
text), not a request (body, headers, cookies, query string), not a frame's local
variables, not source lines, not breadcrumbs (log lines), not the host name.
A key the SDK adds in a future version is dropped because it is not on the
list — which is the reason the list is written this way round (ruling 0.2:
*"keeps the user id and the stack trace only"*; CLAUDE.md §5: logs and anything
like them carry ids and route names, never bodies).

**The hook fails closed.** The SDK runs ``before_send`` inside
``capture_internal_exceptions`` and keeps the event only if the hook returns
one, so a scrubber that raised would drop the event rather than send it raw.

**The SDK's automatic integrations are off** (``default_integrations=False``,
``auto_enabling_integrations=False``). The FastAPI/Starlette integrations would
attach the request to every event and the logging integration would turn every
``logger.error`` into an event carrying its message; this module sends only what
the two call sites above hand it. Three harmless integrations are put back by
name: ``Excepthook`` (a crash at start-up), ``Atexit`` (flush on exit), and
``Dedupe``.
"""

from __future__ import annotations

import logging
from typing import Any

import sentry_sdk
from sentry_sdk.crons import MonitorStatus, capture_checkin
from sentry_sdk.integrations.atexit import AtexitIntegration
from sentry_sdk.integrations.dedupe import DedupeIntegration
from sentry_sdk.integrations.excepthook import ExcepthookIntegration
from sentry_sdk.transport import Transport

from core.config import Settings

logger = logging.getLogger(__name__)

#: The processes that report. A tag, so one Sentry project holds both.
COMPONENTS = frozenset({"api", "worker", "probe"})

#: The tags this project sets. Any other tag is dropped by the scrubber.
KEPT_TAGS = frozenset({"component", "route"})

#: Top-level keys an ERROR event keeps. Everything else is dropped.
_ERROR_KEYS = frozenset(
    {"event_id", "timestamp", "level", "platform", "environment", "sdk"}
)

#: Top-level keys a CHECK-IN keeps: what Sentry Crons needs to place it on the
#: monitor's timeline, and nothing that could carry text.
_CHECKIN_KEYS = frozenset(
    {
        "type",
        "event_id",
        "timestamp",
        "check_in_id",
        "monitor_slug",
        "status",
        "duration",
        "monitor_config",
        "environment",
    }
)

#: What a stack frame keeps. Not ``vars`` (local variables — a frame in
#: `/correct` holds the learner's sentence), not ``context_line`` /
#: ``pre_context`` / ``post_context``, not ``abs_path`` (the host's layout).
_FRAME_KEYS = frozenset({"filename", "module", "function", "lineno", "in_app"})


def scrub_event(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any]:
    """``before_send``: rebuild the event from an allowlist.

    Built fresh rather than edited in place, so nothing survives by being
    forgotten. ``hint`` is unused and accepted because the SDK passes it.
    """
    if event.get("type") == "check_in":
        return {k: event[k] for k in _CHECKIN_KEYS if k in event}

    out: dict[str, Any] = {k: event[k] for k in _ERROR_KEYS if k in event}

    user = event.get("user") or {}
    if user.get("id") is not None:
        out["user"] = {"id": str(user["id"])}

    tags = event.get("tags") or {}
    kept = {k: str(v) for k, v in tags.items() if k in KEPT_TAGS}
    if kept:
        out["tags"] = kept

    values = (event.get("exception") or {}).get("values") or []
    if values:
        out["exception"] = {"values": [_scrub_exception(v) for v in values]}
    return out


def _scrub_exception(value: dict[str, Any]) -> dict[str, Any]:
    """The type and the frames. **Never ``value``** — the exception's message."""
    out: dict[str, Any] = {}
    for key in ("type", "module"):
        if key in value:
            out[key] = value[key]
    mechanism = value.get("mechanism")
    if isinstance(mechanism, dict):
        out["mechanism"] = {
            k: mechanism[k] for k in ("type", "handled") if k in mechanism
        }
    frames = ((value.get("stacktrace") or {}).get("frames")) or []
    if frames:
        out["stacktrace"] = {
            "frames": [{k: f[k] for k in _FRAME_KEYS if k in f} for f in frames]
        }
    return out


def _drop_breadcrumb(crumb: dict[str, Any], hint: dict[str, Any]) -> None:
    """No breadcrumbs, ever: they are log lines and HTTP calls by another name."""
    return None


def init_monitoring(
    settings: Settings, *, component: str, transport: Any = None
) -> bool:
    """Start the SDK for this process, or say plainly that it is off.

    ``transport`` exists for the tests and for ``core.monitoring_probe``'s dry
    run, which hand the SDK a capturing transport in place of the network.
    Returns whether a client was built.
    """
    if component not in COMPONENTS:
        raise ValueError(f"unknown monitoring component {component!r}")
    if not settings.sentry_dsn:
        logger.info("Monitoring off component=%s (SENTRY_DSN unset)", component)
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        transport=transport,
        # Ruling 0.2, and the SDK's default — stated so no one has to know that.
        send_default_pii=False,
        default_integrations=False,
        auto_enabling_integrations=False,
        integrations=[
            ExcepthookIntegration(),
            AtexitIntegration(),
            DedupeIntegration(),
        ],
        before_send=scrub_event,
        before_breadcrumb=_drop_breadcrumb,
        max_breadcrumbs=0,
        include_local_variables=False,
        include_source_context=False,
        max_request_body_size="never",
        # No tracing, no profiling, no sessions, no logs: errors and check-ins.
        traces_sample_rate=None,
        profiles_sample_rate=None,
        auto_session_tracking=False,
        send_client_reports=False,
        enable_logs=False,
        # The scrubber drops it anyway; not collecting it is the first line.
        server_name="",
    )
    sentry_sdk.set_tag("component", component)
    # The DSN is not logged: it is a credential (config.py, repr=False).
    logger.info("Monitoring on component=%s region=eu", component)
    return True


def is_on() -> bool:
    return sentry_sdk.get_client().is_active()


def capture_exception(
    exc: BaseException, *, user_id: int | None, route: str
) -> None:
    """Report one exception with the learner's id and the route's name.

    A no-op while monitoring is off. **Never raises**: reporting a failure must
    not turn one failed request into two (the API handler's own rule).
    """
    if not is_on():
        return
    try:
        with sentry_sdk.new_scope() as scope:
            if user_id is not None:
                scope.set_user({"id": str(user_id)})
            scope.set_tag("route", route)
            sentry_sdk.capture_exception(exc)
    except Exception:
        logger.exception("Monitoring failed to capture route=%s", route)


#: The worker's ONE monitor. **Sentry's free plan allows one cron monitor**
#: (pricing page, read 2026-09-25: *"1 cron monitor"*), so the worker has one
#: liveness monitor rather than one per job.
WORKER_MONITOR_SLUG = "english-worker"


def check_in(
    monitor_slug: str,
    *,
    ok: bool,
    duration_s: float,
    interval_minutes: int,
) -> None:
    """One finished run of a scheduled job, reported to Sentry Crons (#438).

    ``monitor_config`` creates the monitor on its first check-in, so nothing is
    configured by hand in Sentry. A missed check-in — the worker is dead — or
    ``failure_issue_threshold`` failed ones in a row opens an issue, and Sentry
    emails the operator. A no-op while monitoring is off; never raises.
    """
    if not is_on():
        return
    try:
        capture_checkin(
            monitor_slug=monitor_slug,
            status=MonitorStatus.OK if ok else MonitorStatus.ERROR,
            duration=duration_s,
            monitor_config={
                "schedule": {
                    "type": "interval",
                    "value": interval_minutes,
                    "unit": "minute",
                },
                "checkin_margin": interval_minutes,
                "max_runtime": interval_minutes,
                # Two in a row, so one transient database blip does not page.
                "failure_issue_threshold": 2,
                "recovery_threshold": 1,
            },
        )
    except Exception:
        logger.exception("Monitoring failed to check in slug=%s", monitor_slug)


class CapturingTransport(Transport):
    """Keeps every envelope in memory instead of sending it.

    For the tests and ``core.monitoring_probe``'s dry run: **the event is
    captured AFTER ``scrub_event`` and the SDK's own serialiser**, so what is
    asserted or printed is byte for byte what the network transport would have
    sent. Lives here so ``sentry_sdk`` still has one importer.
    """

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self.envelopes: list[Any] = []

    def capture_envelope(self, envelope: Any) -> None:
        self.envelopes.append(envelope)

    def wire(self) -> str:
        """Every envelope as it would be sent, decoded, one after another."""
        return "\n".join(e.serialize().decode("utf-8") for e in self.envelopes)

    def payloads(self) -> list[dict[str, Any]]:
        """Each item's JSON payload — error events and check-ins alike."""
        out: list[dict[str, Any]] = []
        for envelope in self.envelopes:
            for item in envelope:
                if item.payload.json is not None:
                    out.append(item.payload.json)
        return out


def flush(timeout_s: float = 5.0) -> None:
    """Send what is queued. The probe calls it; long-running processes need not."""
    if is_on():
        sentry_sdk.flush(timeout=timeout_s)


def stop() -> None:
    """Close the client and fall back to the SDK's non-recording one.

    For the tests, which must leave no client behind for the next test. A
    ``sentry_sdk.init()`` with no DSN would NOT do this: it builds a real client
    that ``is_active()`` and drops every event, which would make ``is_on()``
    true while nothing is sent.
    """
    client = sentry_sdk.get_client()
    if client.is_active():
        client.close(timeout=0)
    sentry_sdk.get_global_scope().set_client(None)
    sentry_sdk.get_isolation_scope().remove_tag("component")
