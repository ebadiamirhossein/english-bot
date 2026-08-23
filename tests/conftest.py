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

# Must run before any test module imports load_settings / opens the pool.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-anthropic-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-dummy-telegram-token")
