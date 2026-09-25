"""Shared pytest fixtures.

ANTHROPIC_API_KEY is required at real startup. Tests inject a dummy so
existing suites that load settings keep working without making the key
optional in production.

TELEGRAM_BOT_TOKEN gets the same treatment from W1: `core.config` no longer
requires it (the API and worker must boot without a bot token), but
`apps.bot` does, and bot tests load settings.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Must run before any test module imports load_settings / opens the pool.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-anthropic-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-dummy-telegram-token")

# So `from tests.support...` resolves the same way from any invocation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.support import netguard  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def block_outbound_network():
    """Fail loudly when a test opens a socket to anything but loopback.

    The reasoning, the incident behind it, and what this does *not* cover
    (child processes) are all in ``tests/support/netguard.py``.
    ``tests/test_network_guard.py`` proves it is not inert.
    """
    saved = netguard.install()
    try:
        yield
    finally:
        netguard.uninstall(saved)


@pytest.fixture(autouse=True, scope="session")
def syllabus_units_exist():
    """The 24 units, present before any test writes an `items` row.

    W8's migration 014 discharges migration 012's cross-slice contract by adding
    `items.unit_number -> syllabus_units.unit_number`. That column has carried a
    number since 012 and referred to nothing, and the committed item fixtures in
    `tests/fixtures/items/valid.json` declare units 2-6 -- so from 014 onward an
    item fixture cannot be written until the units it names exist.

    This is the same class of prerequisite as `lexemes` for the ledger tests and
    `python -m core.db migrate` for the migration tests: fixed reference content
    the schema depends on. It is seeded here rather than left as a manual step
    so a fresh clone stays green after `migrate` alone, and it is idempotent --
    `upsert_units` rewrites nothing on a second run.

    Skipped, not failed, when there is no database: most of the suite is pure
    and must keep running without one. **The skip is narrow on purpose.** The
    first version of this fixture caught bare `Exception` and returned, and it
    swallowed a real `KeyError` -- `core.db`'s pool uses `dict_row`, so the
    `row[0]` it used to read `schema_version` was never going to work. Every
    dependent test then errored on the foreign key with no hint why. A broad
    except around setup is a green suite over an unreachable path
    (CLAUDE.md §3 rule 4), so only the connection failure is tolerated.
    """
    from core.db import connection
    from core.services.syllabus import upsert_units
    from core.syllabus.content import units

    try:
        conn_cm = connection()
    except Exception:  # noqa: BLE001 -- no database configured at all
        return
    try:
        with conn_cm as conn:
            row = conn.execute("SELECT MAX(version) AS version FROM schema_version").fetchone()
            version = int((row or {}).get("version") or 0)
            if version < 14:
                return
            upsert_units(conn, units())
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        import psycopg

        if isinstance(exc, psycopg.OperationalError):
            return  # database not reachable; the pure suite still runs
        raise


# ── #448: no test may leave a `users` row behind ─────────────────────────────


def _count_users(conn) -> int | None:
    try:
        return int(conn.execute("SELECT count(*) FROM users").fetchone()[0])
    except Exception:  # noqa: BLE001 -- no table yet, or the database went away
        return None


@pytest.fixture(scope="session")
def _users_guard_conn():
    """A private autocommit connection for the guard below, or None.

    Private so the guard neither opens nor closes ``core.db``'s pool — dozens of
    modules close the pool after every test, and a guard that reopened it would
    change what they test.
    """
    try:
        import psycopg

        from core.config import load_settings

        conn = psycopg.connect(load_settings().database_url, autocommit=True)
    except Exception:  # noqa: BLE001 -- no database: the pure suite still runs
        yield None
        return
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def no_test_leaves_a_user_behind(request, _users_guard_conn):
    """#448. Fails the test whose teardown left more `users` rows than it found.

    The dev database had accumulated 8,125 users by 2026-09-25 — +27 per full
    run — because two teardowns deleted by the wrong key and reported nothing:
    ``DELETE FROM users WHERE id = %s`` given a Telegram id matches no row and
    succeeds. Nothing noticed until a scheduler test took six minutes. This is
    the detector that was missing: a count before the test, a count after every
    fixture has torn down (this one is set up first, so it tears down last).

    Module- and session-scoped fixtures set up before it and tear down after it,
    so a user they hold for a whole file is not counted against one test.
    """
    if _users_guard_conn is None:
        yield
        return
    before = _count_users(_users_guard_conn)
    yield
    after = _count_users(_users_guard_conn)
    if before is not None and after is not None and after > before:
        pytest.fail(
            f"{request.node.nodeid} left {after - before} users row(s) behind "
            f"({before} -> {after}); its teardown must delete what it created "
            "(#448)",
            pytrace=False,
        )
