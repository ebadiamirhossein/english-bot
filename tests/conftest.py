"""Shared pytest fixtures.

ANTHROPIC_API_KEY is required at real startup. Tests inject a dummy so
existing suites that load settings keep working without making the key
optional in production.
"""

from __future__ import annotations

import os

# Must run before any test module imports load_settings / opens the pool.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-anthropic-key")
