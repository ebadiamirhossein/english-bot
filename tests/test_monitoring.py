"""W23: Sentry through `core.monitoring` — the row's acceptance and ruling 0.2.

**THE ACCEPTANCE LINE THIS FILE EXISTS FOR:** *an intentional exception reaches
Sentry with a user id and no message body.* Asserted through the real entry
point (CLAUDE.md §3 rule 1): a signed-in learner POSTs a sentence to the real
`/correct` route through the ASGI transport, the service it calls raises with
that sentence in its message AND in a frame's local variable, the app's single
exception handler reports it, and what the SDK serialised for the network is
read back from a capturing transport. **No real DSN, no network** — the DSN is
an EU-shaped placeholder set the way it is really set (the environment), and
the transport is the only thing replaced.

**RED DEMONSTRATIONS (2026-09-25)** — each mutation made, the named test run
and seen red, the mutation reverted:

* `scrub_event` returning `event` unchanged → the acceptance test red (the
  sentence reached the wire in the exception's `value`).
* `_scrub_exception` keeping `"value"` → the acceptance test and
  `test_the_scrubber_is_an_allowlist` red.
* `_FRAME_KEYS` gaining `"vars"` with `include_local_variables=True` → the
  acceptance test red (a frame carried `vars`, the locals holding the sentence).
  **The sweep's first run of this one reported GREEN, and it was the sweep's
  fault, not the test's:** the two edits were applied in the wrong order, so the
  test ran with `vars` allowed but never collected. Re-run with both applied.
* `_is_eu_sentry_dsn`'s host pattern loosened to `.*sentry\\.io.*` → three of
  the six refusal cases red (the US, the region-qualified US and the look-alike
  host); the other three are refused by the scheme, key and path checks.
* `capture_exception`'s `scope.set_user` line removed → the acceptance test red
  (no user on the event).
* the `monitoring.capture_exception` call removed from
  `apps/api/main.py::handle_unexpected_error` → the acceptance test red (no
  event at all).
* `LIVENESS_JOB` renamed → both check-in tests red.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import psycopg
import pytest

from apps.api.deps import SESSION_COOKIE_SECURE
from apps.worker import jobs as worker_jobs
from core import config as config_mod
from core import monitoring, monitoring_probe
from core.config import load_settings
from core.services import writing
from tests.support import progress_seed as seed
from tests.test_backup_r2 import write_dotenv

#: The shape Sentry's docs give an EU organisation's DSN (read 2026-09-25):
#: *"You must use `o<number>.ingest.de.sentry.io` instead."* A placeholder — no
#: organisation or project with these numbers is ever contacted.
EU_DSN = "https://publickey@o0.ingest.de.sentry.io/0"

#: What a learner typed. It must never appear on the wire.
SENTENCE = "Yesterday I goed to the market with my sister"


@pytest.fixture(autouse=True)
def no_client_left_behind():
    yield
    monitoring.stop()


@pytest.fixture(autouse=True)
def heartbeat_in_tmp(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """W22: `run_job` writes the heartbeat after a successful work job (#438),
    so the check-in tests below would otherwise write the machine's real
    `RUNTIME_DIR/last_job_fire`."""
    monkeypatch.setenv("HEARTBEAT_FILE", str(tmp_path / "last_job_fire"))


@pytest.fixture(autouse=True)
def no_dsn_left_behind(monkeypatch: pytest.MonkeyPatch):
    """Whatever a test's `.env` puts in the process environment is taken out again.

    **FOUND BY THE FULL SUITE, NOT BY THIS FILE.** `load_settings(dotenv_path=…)`
    calls `load_dotenv`, which WRITES the file's `SENTRY_DSN` into `os.environ`;
    `monkeypatch.delenv` on an absent variable records no undo, so the refusal
    tests' US DSN outlived them and every later `load_settings()` in the run —
    823 tests — raised the EU refusal. `setenv` first records the true original
    state (absent), so teardown restores it whatever `load_dotenv` wrote.

    **RED DEMONSTRATION:** the two lines below replaced by `pass`, then this
    file and `tests/test_motivation.py` run together → 15 failed, 15 errors.
    """
    for key in ("SENTRY_DSN", "SENTRY_ENVIRONMENT"):
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)
    yield


@pytest.fixture
def capture(monkeypatch: pytest.MonkeyPatch):
    """The real `init_monitoring`, with the network swapped for memory.

    Everything else is as it is really set: the DSN from the environment, the
    component from the caller, the rest of the SDK options from the module.
    """
    transport = monitoring.CapturingTransport()
    real = monitoring.init_monitoring
    calls: list[str] = []

    def _init(settings, *, component):
        calls.append(component)
        return real(settings, component=component, transport=transport)

    monkeypatch.setattr(monitoring, "init_monitoring", _init)
    transport.calls = calls
    return transport


def _errors(transport) -> list[dict]:
    monitoring.flush(2.0)
    return [p for p in transport.payloads() if p.get("type") != "check_in"]


def _checkins(transport) -> list[dict]:
    monitoring.flush(2.0)
    return [p for p in transport.payloads() if p.get("type") == "check_in"]


# ── the acceptance line ─────────────────────────────────────────────────────


@pytest.fixture
def db():
    with psycopg.connect(load_settings().database_url) as conn:
        yield conn


@pytest.fixture
def learner(db):
    made = seed.make_learner(db, "W23 monitoring")
    yield made
    seed.drop_learner(db, made.user_id)


def test_an_intentional_exception_reaches_sentry_with_a_user_id_and_no_body(
    monkeypatch: pytest.MonkeyPatch, capture, learner, tmp_path
) -> None:
    """User action: a learner submits a journal entry and the correction fails.

    THE ROW'S ACCEPTANCE. The sentence rides out three ways on a real failure —
    the request body, the exception's message, and a local variable in the
    frame that raised — and all three are checked absent from the serialised
    envelope, as are the session cookie and the request itself.
    """
    monkeypatch.setenv("SENTRY_DSN", EU_DSN)
    monkeypatch.setenv("WEBAUTHN_RP_ID", "foundgrant.com")
    monkeypatch.setenv("WEBAUTHN_ORIGIN", "https://app.foundgrant.com")
    monkeypatch.setenv("AUTH_RATE_LIMIT_SALT", "w23-monitoring-salt")
    monkeypatch.setenv("ALERT_THROTTLE_FILE", str(tmp_path / "throttle.json"))

    def _fails(user, text, **kwargs):
        sentence = text  # a local holding the learner's words
        raise ValueError(f"model answer unparseable for: {sentence}")

    monkeypatch.setattr(writing, "correct_submission", _fails)

    from apps.api.main import create_app

    app = create_app()
    # The first import of apps.api.main builds its module-level `app` too, so
    # the count is one or two; what matters is that create_app initialised it.
    assert capture.calls and set(capture.calls) == {"api"}

    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=app, raise_app_exceptions=False, client=("127.0.0.1", 51234)
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            cookies={SESSION_COOKIE_SECURE: learner.cookie},
        ) as http:
            return await http.post("/correct", json={"text": SENTENCE})

    response = asyncio.run(_go())
    assert response.status_code == 500
    assert response.json() == {"error": "internal_error"}

    events = _errors(capture)
    assert len(events) == 1
    event = events[0]
    # WITH a user id — the learner's internal users.id, and nothing else of theirs.
    assert event["user"] == {"id": str(learner.user_id)}
    assert event["tags"] == {"component": "api", "route": "correct"}
    # The stack trace: the type and the frames, down to the function that raised.
    (exc,) = event["exception"]["values"]
    assert exc["type"] == "ValueError"
    assert "value" not in exc
    functions = [f["function"] for f in exc["stacktrace"]["frames"]]
    assert functions[-1] == "_fails"
    assert "correct" in functions
    for frame in exc["stacktrace"]["frames"]:
        assert set(frame) <= {"filename", "module", "function", "lineno", "in_app"}

    # NO message body, anywhere in the bytes the network would have carried.
    wire = capture.wire()
    for leak in ("goed", "market", "sister", "unparseable", learner.cookie):
        assert leak not in wire, leak
    for key in ("request", "breadcrumbs", "extra", "contexts", "server_name",
                "message", "logentry", "modules", "threads"):
        assert key not in event, key


def test_nothing_is_built_or_sent_while_the_dsn_is_unset(
    monkeypatch: pytest.MonkeyPatch, capture
) -> None:
    """Ruling 0.2: *disabled when the DSN is unset* — and it is, until the launch pass."""
    monkeypatch.setenv("SENTRY_DSN", "")
    assert monitoring.init_monitoring(load_settings(), component="api") is False
    assert monitoring.is_on() is False
    try:
        raise RuntimeError(SENTENCE)
    except RuntimeError as exc:
        monitoring.capture_exception(exc, user_id=1, route="correct")
    monitoring.check_in("english-worker", ok=True, duration_s=0.1, interval_minutes=5)
    assert capture.envelopes == []


# ── the scrubber, alone ─────────────────────────────────────────────────────


def test_the_scrubber_is_an_allowlist() -> None:
    """Every key an SDK might add — today's and a future one — is dropped unless listed."""
    raw = {
        "event_id": "e1",
        "timestamp": "2026-09-25T00:00:00Z",
        "level": "error",
        "platform": "python",
        "environment": "production",
        "sdk": {"name": "sentry.python"},
        "server_name": "english-host",
        "message": SENTENCE,
        "logentry": {"message": SENTENCE},
        "request": {"data": SENTENCE, "cookies": "x", "headers": {"Cookie": "x"}},
        "extra": {"text": SENTENCE},
        "breadcrumbs": {"values": [{"message": SENTENCE}]},
        "contexts": {"runtime": {"name": "CPython"}},
        "user": {"id": 7, "email": "a@b.c", "ip_address": "10.0.0.1"},
        "tags": {"component": "api", "route": "correct", "learner_text": SENTENCE},
        "a_key_from_a_future_sdk": SENTENCE,
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "value": SENTENCE,
                    "module": None,
                    "mechanism": {"type": "generic", "handled": True, "data": SENTENCE},
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": "core/services/writing.py",
                                "abs_path": "/home/bot/english-bot/packages/core/services/writing.py",
                                "module": "core.services.writing",
                                "function": "correct_submission",
                                "lineno": 12,
                                "in_app": True,
                                "vars": {"text": SENTENCE},
                                "context_line": f'    text = "{SENTENCE}"',
                                "pre_context": [SENTENCE],
                                "post_context": [SENTENCE],
                            }
                        ]
                    },
                }
            ]
        },
    }
    out = monitoring.scrub_event(raw, {})
    assert SENTENCE not in json.dumps(out)
    assert set(out) == {
        "event_id", "timestamp", "level", "platform", "environment", "sdk",
        "user", "tags", "exception",
    }
    assert out["user"] == {"id": "7"}
    assert out["tags"] == {"component": "api", "route": "correct"}
    (exc,) = out["exception"]["values"]
    assert set(exc) == {"type", "module", "mechanism", "stacktrace"}
    assert exc["mechanism"] == {"type": "generic", "handled": True}
    assert exc["stacktrace"]["frames"] == [
        {
            "filename": "core/services/writing.py",
            "module": "core.services.writing",
            "function": "correct_submission",
            "lineno": 12,
            "in_app": True,
        }
    ]


def test_a_check_in_keeps_only_what_crons_needs() -> None:
    raw = {
        "type": "check_in",
        "check_in_id": "c1",
        "monitor_slug": "english-worker",
        "status": "ok",
        "duration": 0.2,
        "monitor_config": {"schedule": {"type": "interval", "value": 5, "unit": "minute"}},
        "environment": "production",
        "contexts": {"trace": {"trace_id": "t"}},
        "server_name": "english-host",
        "extra": {"text": SENTENCE},
    }
    out = monitoring.scrub_event(raw, {})
    assert set(out) == {
        "type", "check_in_id", "monitor_slug", "status", "duration",
        "monitor_config", "environment",
    }


# ── the EU region, enforced at load ─────────────────────────────────────────


@pytest.mark.parametrize(
    "dsn",
    [
        "https://k@o1.ingest.sentry.io/2",  # a US organisation
        "https://k@o1.ingest.us.sentry.io/2",  # a US organisation, region-qualified
        "https://k@o1.ingest.de.sentry.io.example.com/2",  # a look-alike host
        "https://k@example.com/ingest.de.sentry.io/2",  # the EU name in the path
        "http://k@o1.ingest.de.sentry.io/2",  # not TLS
        "https://o1.ingest.de.sentry.io/2",  # no key
    ],
)
def test_a_dsn_outside_the_eu_region_is_refused_at_load(tmp_path, monkeypatch, dsn) -> None:
    """Ruling 0.2: EU data region. A US DSN would send traces to Iowa, silently."""
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    with pytest.raises(config_mod.ConfigError) as caught:
        config_mod.load_settings(dotenv_path=write_dotenv(tmp_path, SENTRY_DSN=dsn))
    assert "SENTRY_DSN must be an EU-region DSN" in str(caught.value)
    # The DSN is a credential: the refusal names the rule, never the value.
    assert dsn not in str(caught.value)


def test_an_eu_dsn_is_read_from_the_env_file_and_kept_out_of_repr(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
    settings = config_mod.load_settings(
        dotenv_path=write_dotenv(tmp_path, SENTRY_DSN="https://k3y@o4509.ingest.de.sentry.io/4510")
    )
    assert settings.sentry_dsn == "https://k3y@o4509.ingest.de.sentry.io/4510"
    assert settings.sentry_environment == "production"
    assert "k3y" not in repr(settings)


def test_the_dsn_defaults_to_off(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    settings = config_mod.load_settings(dotenv_path=write_dotenv(tmp_path))
    assert settings.sentry_dsn == ""


# ── the worker: exceptions and the liveness monitor (#438) ──────────────────


def _worker_on(monkeypatch, capture) -> None:
    monkeypatch.setenv("SENTRY_DSN", EU_DSN)
    assert monitoring.init_monitoring(load_settings(), component="worker") is True


def test_a_failing_worker_job_reports_its_name_and_no_message(monkeypatch, capture) -> None:
    _worker_on(monkeypatch, capture)

    def _explodes() -> None:
        raise RuntimeError(SENTENCE)

    worker_jobs.run_job(worker_jobs.Job("streak_rollover", _explodes, 900, 0))
    (event,) = _errors(capture)
    assert event["tags"] == {"component": "worker", "route": "job:streak_rollover"}
    assert "user" not in event
    assert "goed" not in capture.wire()
    # Not the liveness job, so no check-in.
    assert _checkins(capture) == []


def test_the_liveness_job_checks_in_ok_every_run(monkeypatch, capture) -> None:
    """#438: a dead worker is a missed check-in, which Sentry alerts on."""
    _worker_on(monkeypatch, capture)
    worker_jobs.run_job(worker_jobs.Job("push_poll", lambda: None, 300, 0))
    (checkin,) = _checkins(capture)
    assert checkin["monitor_slug"] == "english-worker"
    assert checkin["status"] == "ok"
    assert checkin["monitor_config"]["schedule"] == {
        "type": "interval", "value": 5, "unit": "minute",
    }


def test_the_liveness_job_checks_in_error_when_it_fails(monkeypatch, capture) -> None:
    """#438's other half: a worker that is up and failing every tick."""
    _worker_on(monkeypatch, capture)

    def _explodes() -> None:
        raise RuntimeError("database unavailable")

    worker_jobs.run_job(worker_jobs.Job("push_poll", _explodes, 300, 0))
    (checkin,) = _checkins(capture)
    assert checkin["status"] == "error"
    assert len(_errors(capture)) == 1


# ── W22: the two alarms the bot used to send by Telegram ────────────────────
#
# RED DEMONSTRATIONS (2026-09-25, `python -B`, caches cleared): with the
# `monitoring.capture_exception(HeartbeatStale(), …)` line removed from
# `apps/worker/jobs.py::heartbeat`, `test_a_stale_heartbeat_reaches_sentry_by_type`
# went red (no event); with the R2 half's `BackupStale` capture removed,
# `test_a_stale_backup_reaches_sentry_by_type` went red. Both restored.


def test_a_stale_heartbeat_reaches_sentry_by_type(monkeypatch, capture, tmp_path) -> None:
    """The bot sent the operator "Heartbeat STALE…" by Telegram. The worker has no
    Telegram (PRODUCT-PRINCIPLES §1), so the alarm is an exception TYPE on #65's
    channel — the scrubber would drop any message, and there is none to drop."""
    _worker_on(monkeypatch, capture)
    worker_jobs.run_job(worker_jobs.Job("heartbeat", worker_jobs.heartbeat, 3600, 0))
    (event,) = _errors(capture)
    (exc,) = event["exception"]["values"]
    assert exc["type"] == "HeartbeatStale"
    assert "value" not in exc
    assert event["tags"] == {"component": "worker", "route": "job:heartbeat"}
    # The check ran fine, so it did not ALSO report itself as a failed job, and
    # the alarm did not refresh its own pulse.
    assert not (tmp_path / "last_job_fire").exists()


def test_a_fresh_heartbeat_sends_nothing(monkeypatch, capture, tmp_path) -> None:
    _worker_on(monkeypatch, capture)
    worker_jobs.run_job(worker_jobs.Job("push_poll", lambda: None, 300, 0))
    worker_jobs.run_job(worker_jobs.Job("heartbeat", worker_jobs.heartbeat, 3600, 0))
    assert _errors(capture) == []


def test_a_stale_backup_reaches_sentry_by_type(monkeypatch, capture) -> None:
    """R2 unconfigured and required is the loud case (#31): it must page."""
    _worker_on(monkeypatch, capture)
    for key in ("R2_ACCOUNT_ID", "R2_BUCKET", "R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("BACKUP_R2_REQUIRED", "1")
    monkeypatch.setenv("BACKUP_OFFSITE_DIR", "")
    worker_jobs.run_job(
        worker_jobs.Job("backup_freshness", worker_jobs.backup_freshness, 3600, 0)
    )
    (event,) = _errors(capture)
    (exc,) = event["exception"]["values"]
    assert exc["type"] == "BackupStale"
    assert event["tags"] == {"component": "worker", "route": "job:backup_freshness"}


def test_the_registered_liveness_job_is_the_five_minute_push_poll() -> None:
    """Hardcoded (§3 rule 5): the monitor's schedule is derived from this interval."""
    registered = {job.name: job for job in worker_jobs.JOBS}
    assert worker_jobs.LIVENESS_JOB == "push_poll"
    assert registered["push_poll"].interval_seconds == 300


# ── the probe's dry run (rehearsed, §5c) ────────────────────────────────────


def test_the_probe_dry_run_sends_nothing_and_finds_no_canary(monkeypatch, capsys) -> None:
    monkeypatch.setenv("SENTRY_DSN", "")
    assert monitoring_probe.main(["--user", "7"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN — nothing sent" in out
    assert "events=1 user_id_present=True canary_absent=True" in out
    assert "goed" not in out


def test_the_probe_refuses_to_send_without_a_dsn(monkeypatch, capsys) -> None:
    monkeypatch.setenv("SENTRY_DSN", "")
    assert monitoring_probe.main(["--user", "7", "--send"]) == 1
    assert "SENTRY_DSN is not set" in capsys.readouterr().out
