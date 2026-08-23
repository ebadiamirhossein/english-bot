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
