"""A programmable software authenticator.

Why this and not fixture attestation/assertion blobs: a canned blob bakes its
challenge, its origin and its sign count into a signature that cannot be
regenerated. It therefore cannot exercise challenge binding, origin binding or
sign-count progression — the three things most worth testing. This can produce,
on demand, a wrong challenge, a wrong origin, a wrong RP ID, a lower sign count
and a one-byte-tampered signature.

**CLAUDE.md §3 rule 5: this file imports nothing from ``core.passkeys``.** It
builds CBOR, COSE and authenticator data from the WebAuthn spec directly. If it
borrowed the module's own encoders, every verification test below would only
prove that the module agrees with itself.

``cbor2`` and ``cryptography`` are py_webauthn's own dependencies, so nothing new
is installed for this. They are libraries, not the code under test.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
from dataclasses import dataclass, field

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

# Authenticator data flags (WebAuthn §6.1).
FLAG_UP = 0x01  # user present
FLAG_UV = 0x04  # user verified
FLAG_BE = 0x08  # backup eligible
FLAG_BS = 0x10  # backed up
FLAG_AT = 0x40  # attested credential data included

# A made-up authenticator identity. `none` attestation means nobody checks it.
AAGUID = b"\x00" * 16

COSE_KTY = 1
COSE_ALG = 3
COSE_CRV = -1
COSE_X = -2
COSE_Y = -3
COSE_KTY_EC2 = 2
COSE_ALG_ES256 = -7
COSE_CRV_P256 = 1


def b64url(raw: bytes) -> str:
    """Unpadded base64url, the encoding every WebAuthn JSON field uses."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _cose_public_key(public_numbers: ec.EllipticCurvePublicNumbers) -> bytes:
    return cbor2.dumps(
        {
            COSE_KTY: COSE_KTY_EC2,
            COSE_ALG: COSE_ALG_ES256,
            COSE_CRV: COSE_CRV_P256,
            COSE_X: public_numbers.x.to_bytes(32, "big"),
            COSE_Y: public_numbers.y.to_bytes(32, "big"),
        }
    )


@dataclass
class SoftAuthenticator:
    """One passkey on one imaginary device.

    ``sign_count`` starts at 0 and is *not* auto-incremented, so a test can
    replay a count deliberately. ``backed_up`` mirrors what an iCloud-synced
    passkey reports.
    """

    credential_id: bytes = field(default_factory=lambda: os.urandom(32))
    sign_count: int = 0
    _key: ec.EllipticCurvePrivateKey = field(
        default_factory=lambda: ec.generate_private_key(ec.SECP256R1())
    )

    # --- registration ---------------------------------------------------

    def register(
        self,
        *,
        challenge: bytes,
        origin: str,
        rp_id: str,
        user_verified: bool = True,
    ) -> dict:
        """A ``navigator.credentials.create()`` response, as JSON-ready dict."""
        client_data = self._client_data("webauthn.create", challenge, origin)
        flags = FLAG_UP | FLAG_AT | FLAG_BE | FLAG_BS
        if user_verified:
            flags |= FLAG_UV
        auth_data = self._authenticator_data(rp_id, flags, self.sign_count)
        auth_data += (
            AAGUID
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + _cose_public_key(self._key.public_key().public_numbers())
        )
        attestation = cbor2.dumps(
            {"fmt": "none", "attStmt": {}, "authData": auth_data}
        )
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "attestationObject": b64url(attestation),
                "transports": ["internal", "hybrid"],
            },
            "clientExtensionResults": {},
        }

    # --- authentication -------------------------------------------------

    def authenticate(
        self,
        *,
        challenge: bytes,
        origin: str,
        rp_id: str,
        user_handle: bytes | None,
        sign_count: int | None = None,
        user_verified: bool = True,
        tamper_signature: bool = False,
    ) -> dict:
        """A ``navigator.credentials.get()`` response, as JSON-ready dict.

        ``sign_count=None`` advances the stored counter by one, which is what a
        real authenticator does. Pass an explicit value to replay or regress it.
        """
        if sign_count is None:
            self.sign_count += 1
            sign_count = self.sign_count

        client_data = self._client_data("webauthn.get", challenge, origin)
        flags = FLAG_UP | FLAG_BE | FLAG_BS
        if user_verified:
            flags |= FLAG_UV
        auth_data = self._authenticator_data(rp_id, flags, sign_count)

        signed = auth_data + hashlib.sha256(client_data).digest()
        signature = self._key.sign(signed, ec.ECDSA(hashes.SHA256()))
        if tamper_signature:
            # Flip one bit in the middle of the DER blob. Structurally still a
            # signature, mathematically not this one.
            middle = len(signature) // 2
            signature = (
                signature[:middle]
                + bytes([signature[middle] ^ 0x01])
                + signature[middle + 1 :]
            )

        response: dict[str, object] = {
            "clientDataJSON": b64url(client_data),
            "authenticatorData": b64url(auth_data),
            "signature": b64url(signature),
        }
        response["userHandle"] = b64url(user_handle) if user_handle else None
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": response,
            "clientExtensionResults": {},
        }

    # --- internals ------------------------------------------------------

    @staticmethod
    def _client_data(ceremony: str, challenge: bytes, origin: str) -> bytes:
        return json.dumps(
            {
                "type": ceremony,
                "challenge": b64url(challenge),
                "origin": origin,
                "crossOrigin": False,
            },
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def _authenticator_data(rp_id: str, flags: int, sign_count: int) -> bytes:
        return (
            hashlib.sha256(rp_id.encode("utf-8")).digest()
            + bytes([flags])
            + struct.pack(">I", sign_count)
        )


def challenge_from(credential: dict) -> bytes:
    """The challenge a response carries, read the way the server reads it.

    Used by tests that need to look a challenge row up without going through the
    service. Written out here rather than imported so this file stays
    independent of the code under test.
    """
    client_data = credential["response"]["clientDataJSON"]
    padded = client_data + "=" * (-len(client_data) % 4)
    parsed = json.loads(base64.urlsafe_b64decode(padded))
    raw = parsed["challenge"]
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
