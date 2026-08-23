"""FastAPI dependencies: database handle and the current session.

Both are deliberately thin. ``get_db`` hands out the same pooled connection
every other process uses; ``get_current_user`` is a stub until W2 wires Better
Auth. Nothing here parses a request body or runs a query — CLAUDE.md §2 keeps
that in service functions.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import psycopg

from core.db import connection

logger = logging.getLogger(__name__)


def get_db() -> Iterator[psycopg.Connection]:
    """Yield a pooled connection for the life of one request.

    A plain ``def`` generator: FastAPI runs it in a threadpool, so the pool's
    blocking checkout never sits on the event loop. See README.md.
    """
    with connection() as conn:
        yield conn


def get_current_user() -> dict[str, object] | None:
    """Resolve the caller's session. Always ``None`` until W2.

    W2 replaces the body with a Better Auth session lookup. The signature is
    already the one routes will depend on, so adding auth changes this file
    and no route. ``GET /health/auth`` renders whatever this returns, which is
    how a W2 auth failure stays one ``curl`` away (W0 risk R4).
    """
    return None
