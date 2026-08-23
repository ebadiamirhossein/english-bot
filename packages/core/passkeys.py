"""WebAuthn ceremony wrapper — the only module that imports ``webauthn``.

The same rule ``llm.py`` and ``speech.py`` follow, for the same reason: the
library's types stay behind one door, so the services and routes above deal in
``bytes``, ``str`` and small dataclasses. ``tests/test_core_boundary.py`` fails
the commit that imports ``webauthn`` anywhere else.

Nothing here touches the database, the clock or the network. ``py_webauthn``
makes no network calls at all — we request ``attestation="none"``, so there is
no metadata service to reach — which is why a WebAuthn "provider contract" has
no live call to verify (CLAUDE.md §3 rule 2). Its honest equivalent is the phone
check: a real authenticator, a real browser, a real origin.

Verified against **py_webauthn 2.8.0**. Every signature below was read off the
installed package rather than remembered.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Any

import webauthn
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

logger = logging.getLogger(__name__)

# 32 bytes of CSPRNG. The browser's `timeout` is a hint; the server-side row's
# expiry is the rule (see core.services.auth).
CHALLENGE_BYTES = 32

# Advice to the browser only, in milliseconds.
CEREMONY_TIMEOUT_MS = 60_000


class PasskeyError(Exception):
    """A ceremony did not verify. Carries no detail meant for a client.

    Every ``webauthn`` exception is converted to this one, so no caller has to
    import the library to catch a failure and no library message reaches a
    response body.
    """


@dataclass(frozen=True)
class RegisteredCredential:
    """What a verified registration yields, as plain data."""

    credential_id: bytes
    public_key: bytes
    sign_count: int
    aaguid: str | None
    credential_device_type: str | None
    backed_up: bool | None
    transports: tuple[str, ...]
    user_verified: bool


@dataclass(frozen=True)
class VerifiedAssertion:
    """What a verified authentication yields, as plain data."""

    credential_id: bytes
    new_sign_count: int
    user_verified: bool


def new_challenge() -> bytes:
    """A fresh ceremony challenge."""
    return secrets.token_bytes(CHALLENGE_BYTES)


def b64url_encode(raw: bytes) -> str:
    """Bytes → unpadded base64url, the encoding WebAuthn JSON uses."""
    return bytes_to_base64url(raw)


def b64url_decode(value: str) -> bytes:
    """Unpadded base64url → bytes.

    Raises ``PasskeyError`` on anything that is not valid base64url. Callers
    turn that into a 404, never a 500: a credential id that cannot be decoded is
    a request for something that cannot exist, not a server fault.
    """
    try:
        return base64url_to_bytes(value)
    except Exception as exc:  # noqa: BLE001 — any decode failure is the same answer
        raise PasskeyError("credential id is not valid base64url") from exc


def registration_options_json(
    *,
    rp_id: str,
    rp_name: str,
    user_handle: bytes,
    user_name: str,
    user_display_name: str,
    challenge: bytes,
    exclude_credential_ids: tuple[bytes, ...] = (),
) -> str:
    """Creation options for ``navigator.credentials.create()``, as JSON.

    ``resident_key=REQUIRED`` makes the credential discoverable, which is what
    lets sign-in ask for no typed identifier — the browser offers the passkey
    and the assertion carries the user handle.

    ``user_verification=REQUIRED`` because the passkey is the only factor: Face
    ID, Touch ID or a device PIN is what makes possession alone insufficient.

    ``attestation=NONE``: two known learners on their own devices. Attestation
    would add an enterprise trust-store problem for no benefit and leak the
    device model.
    """
    options = webauthn.generate_registration_options(
        rp_id=rp_id,
        rp_name=rp_name,
        user_id=user_handle,
        user_name=user_name,
        user_display_name=user_display_name,
        challenge=challenge,
        timeout=CEREMONY_TIMEOUT_MS,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            # authenticator_attachment deliberately unset: a platform
            # authenticator (iPhone, Mac) and a security key are both fine, and
            # constraining it forecloses a recovery option for no gain.
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=cid) for cid in exclude_credential_ids
        ],
    )
    return webauthn.options_to_json(options)


def authentication_options_json(*, rp_id: str, challenge: bytes) -> str:
    """Request options for ``navigator.credentials.get()``, as JSON.

    ``allow_credentials`` is deliberately empty. That is what makes this a
    discoverable-credential flow: nothing user-specific crosses the wire, so an
    unauthenticated caller learns nothing from this route.
    """
    options = webauthn.generate_authentication_options(
        rp_id=rp_id,
        challenge=challenge,
        timeout=CEREMONY_TIMEOUT_MS,
        allow_credentials=[],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return webauthn.options_to_json(options)


def verify_registration(
    *,
    credential: dict[str, Any],
    expected_challenge: bytes,
    expected_rp_id: str,
    expected_origin: str,
) -> RegisteredCredential:
    """Verify an attestation. Raises ``PasskeyError`` if anything is off.

    ``py_webauthn`` checks the origin, the RP ID hash, the challenge, the user
    presence and verification flags, the attestation format and the public-key
    algorithm. The credential dict is passed through as-is: the library parses
    it itself, and a hand-written pydantic mirror of the WebAuthn response shape
    would be a second, subtly-wrong copy of a spec that already has a maintained
    parser.
    """
    try:
        verified = webauthn.verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=expected_rp_id,
            expected_origin=expected_origin,
            require_user_presence=True,
            require_user_verification=True,
        )
    except WebAuthnException as exc:
        logger.warning("Registration did not verify: %s", type(exc).__name__)
        raise PasskeyError("registration did not verify") from exc

    return RegisteredCredential(
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=int(verified.sign_count),
        aaguid=verified.aaguid,
        credential_device_type=_enum_value(verified.credential_device_type),
        backed_up=verified.credential_backed_up,
        transports=_transports(credential),
        user_verified=bool(verified.user_verified),
    )


def verify_authentication(
    *,
    credential: dict[str, Any],
    expected_challenge: bytes,
    expected_rp_id: str,
    expected_origin: str,
    public_key: bytes,
    current_sign_count: int,
) -> VerifiedAssertion:
    """Verify an assertion. Raises ``PasskeyError`` if anything is off.

    **Sign-count regression is a hard failure and the library enforces it**
    (``verify_authentication_response.py:159``): it raises when
    ``(new > 0 or stored > 0) and new <= stored``. The important half of that
    condition is the first: ``stored == 0 and new == 0`` is **not** a
    regression, and must not be treated as one — Apple passkeys always report 0,
    so the opposite rule would lock both learners out on day one.

    On a genuine regression the credential is deliberately **not** disabled: the
    legitimate authenticator's counter keeps rising and keeps working, while the
    clone's stays below and keeps failing. Disabling would lock out the victim
    alongside the clone.
    """
    try:
        verified = webauthn.verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=expected_rp_id,
            expected_origin=expected_origin,
            credential_public_key=public_key,
            credential_current_sign_count=current_sign_count,
            require_user_verification=True,
        )
    except WebAuthnException as exc:
        logger.warning("Assertion did not verify: %s", type(exc).__name__)
        raise PasskeyError("assertion did not verify") from exc

    return VerifiedAssertion(
        credential_id=verified.credential_id,
        new_sign_count=int(verified.new_sign_count),
        user_verified=bool(verified.user_verified),
    )


def credential_id_from_response(credential: dict[str, Any]) -> bytes:
    """The raw credential id out of a ``navigator.credentials`` response."""
    raw = credential.get("rawId") or credential.get("id")
    if not isinstance(raw, str) or not raw:
        raise PasskeyError("response carries no credential id")
    return b64url_decode(raw)


def user_handle_from_response(credential: dict[str, Any]) -> bytes | None:
    """The user handle an assertion carries, or ``None``.

    A discoverable credential always carries one; its absence means the
    authenticator did something this app does not support, and the caller turns
    that into a 401 rather than guessing at a user.
    """
    response = credential.get("response")
    if not isinstance(response, dict):
        raise PasskeyError("response is missing")
    handle = response.get("userHandle")
    if handle in (None, ""):
        return None
    if not isinstance(handle, str):
        raise PasskeyError("userHandle is not a string")
    return b64url_decode(handle)


def _transports(credential: dict[str, Any]) -> tuple[str, ...]:
    """Transport hints, which the verifier does not return but the response has.

    Stored only so a later ceremony can hint the browser at the right
    authenticator; nothing depends on them being present or correct.
    """
    response = credential.get("response")
    if not isinstance(response, dict):
        return ()
    transports = response.get("transports")
    if not isinstance(transports, list):
        return ()
    return tuple(t for t in transports if isinstance(t, str))


def _enum_value(value: Any) -> str | None:
    """``credential_device_type`` comes back as an enum; store its value."""
    if value is None:
        return None
    return str(getattr(value, "value", value))
