"""Pydantic models — the source of truth for the OpenAPI client.

``apps/web/lib/api.ts`` is written against the schema these produce, so a
field renamed here shows up as a type error in the frontend rather than as a
runtime surprise (ARCHITECTURE-v3 §3).

**The WebAuthn credential JSON is deliberately not modelled here.** It arrives
as a plain ``dict`` and goes straight to ``core.passkeys``, which parses it with
py_webauthn's own parser. A hand-written pydantic mirror of the WebAuthn
response shape would be a second, subtly-wrong copy of a spec that already has a
maintained parser, and a mismatch would reach the learner as "it didn't work".
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from core.services.correction import MAX_CHARS as CORRECTION_MAX_CHARS
from core.services.correction import MIN_CHARS as CORRECTION_MIN_CHARS


class Health(BaseModel):
    """``GET /health``. ``schema_version`` is null only when the DB is down."""

    ok: bool
    schema_version: int | None


class Session(BaseModel):
    """A resolved session. The body of a successful sign-in, and of /health/auth."""

    telegram_user_id: int
    name: str
    expires_at: datetime


class RegisterBeginRequest(BaseModel):
    """First enrolment. Both fields are required and neither is ever logged."""

    email: str = Field(min_length=3, max_length=320)
    claim_token: str = Field(min_length=8, max_length=256)


class CredentialEnvelope(BaseModel):
    """Carries the raw ``PublicKeyCredential`` JSON under one key.

    The credential is a free-form ``dict`` on purpose (see the module docstring):
    py_webauthn parses and validates it. Wrapping it in an envelope rather than
    posting it at the top level keeps room for sibling fields — which is exactly
    what ``RegisterFinishRequest`` needs.
    """

    credential: dict[str, Any]


class RegisterFinishRequest(CredentialEnvelope):
    """The attestation plus the claim token it is being spent against.

    The token travels in the **body**, never in a query string: URLs reach
    access logs, browser history and Referer headers, and this one is a
    single-use authentication factor.
    """

    claim_token: str = Field(min_length=8, max_length=256)


class Passkey(BaseModel):
    """One credential as its owner sees it. No key material, no sign count."""

    id: str
    nickname: str | None
    created_at: datetime
    last_used_at: datetime | None
    backed_up: bool | None


class CorrectRequest(BaseModel):
    """`POST /correct`. The bounds are the service's, not a second opinion."""

    text: str = Field(min_length=CORRECTION_MIN_CHARS, max_length=CORRECTION_MAX_CHARS)


class Correction(BaseModel):
    """One correction, in the v2 shape the learners already read in Telegram.

    `murphy_units` is the Murphy reference for the error type — the "why" half,
    which is the half that teaches.
    """

    you_said: str
    correct_form: str
    error_type: str
    explanation: str
    murphy_units: str | None = None


class CorrectionResult(BaseModel):
    """What one piece of writing produced.

    `has_errors: false` with a `did_well` is the ordinary good outcome, not an
    empty response — the praise is the content in that case.
    """

    is_english: bool
    has_errors: bool
    did_well: str
    corrections: list[Correction] = []


__all__ = [
    "CorrectRequest",
    "Correction",
    "CorrectionResult",
    "CredentialEnvelope",
    "Health",
    "Passkey",
    "RegisterBeginRequest",
    "RegisterFinishRequest",
    "Session",
]
