"""Pydantic response models — the source of truth for the OpenAPI client.

``apps/web/lib/api.ts`` is written against the schema these produce, so a
field renamed here shows up as a type error in the frontend rather than as a
runtime surprise (ARCHITECTURE-v3 §3).

W2 adds ``Session`` here and gives ``GET /health/auth`` a typed body. It has
none today on purpose: inventing the shape of a session before Better Auth is
wired would mean guessing, and the guess would be copied into the frontend.
"""

from __future__ import annotations

from pydantic import BaseModel


class Health(BaseModel):
    """``GET /health``. ``schema_version`` is null only when the DB is down."""

    ok: bool
    schema_version: int | None


__all__ = ["Health"]
