"""Domain core. Imports no web framework, no Telegram, no provider SDK.

`packages/core` is installed as the distribution `core`, so every import
reads `from core.services.errors import ...`. The boundary is enforced by
`tests/test_core_boundary.py`.
"""

from __future__ import annotations

from pathlib import Path

# Prompts travel with the core package: they are domain content, not bot
# copy. `apps/bot` keeps only `couple.txt`, its own feature's prompt.
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

__all__ = ["PROMPTS_DIR"]
