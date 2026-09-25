"""W20 — Web Push request construction: RFC 8291 encryption and RFC 8292 VAPID.

**The policy half; `core/push_api.py` is the door.** `speech.py`/`speech_api.py`'s
split: this module builds the request (the encrypted body, the `Authorization`
header, the `TTL`) and never touches the network; `push_api.py` sends it and maps
the answer. Nothing else in the tree builds or sends a push.

**NO LIBRARY, DELIBERATELY.** `pywebpush` pulls `aiohttp`, `requests` and `six`
into a core that already carries `cryptography` (via `webauthn`) and `httpx`.
The two RFCs need an ECDH, two HKDFs, one AES-GCM and one ES256 signature, all
from `cryptography`. **What makes that safe rather than brave is RFC 8291's own
worked example (Appendix A)**: `tests/test_push.py` feeds its published keys,
salt and plaintext through `encrypt` and requires the published ciphertext byte
for byte. A match cannot happen by accident.

**What a mock still cannot prove (CLAUDE.md §3 rule 2):** that Apple's, Google's
and Mozilla's push services accept this request. The probe
(`python -m core.push_probe`, dry by default) carries that to the launch pass.

**Nothing here logs.** A push endpoint is a capability URL — anyone holding it
and the keys can message the learner's phone — so it is never printed whole;
`endpoint_host` is what a log line may carry.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

#: RFC 8188 record size. One record carries the whole payload: ours are a few
#: hundred bytes, and the push services cap a message at 4096.
RECORD_SIZE = 4096
#: RFC 8030 §5.2. A reminder nobody saw in 12 hours is about a day that has
#: moved on; the push service drops it rather than delivering it late.
DEFAULT_TTL_SECONDS = 12 * 60 * 60
#: RFC 8292 §2: `exp` no more than 24 hours ahead. Twelve leaves slack for a
#: clock that is a little fast.
VAPID_LIFETIME = timedelta(hours=12)
#: The payload must fit one record with its padding delimiter and GCM tag.
MAX_PAYLOAD_BYTES = RECORD_SIZE - 17 - 86


class PushConfigError(ValueError):
    """The VAPID configuration or a subscription is unusable. Nothing was sent."""


def b64url_decode(text: str) -> bytes:
    text = text.strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    """RFC 5869 with SHA-256, one expansion block (every length here is ≤ 32)."""
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:length]


def _public_bytes(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def _private_from_raw(raw: bytes) -> ec.EllipticCurvePrivateKey:
    if len(raw) != 32:
        raise PushConfigError("a P-256 private key is 32 bytes")
    return ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())


def encrypt(
    plaintext: bytes,
    *,
    ua_public: bytes,
    auth_secret: bytes,
    salt: bytes | None = None,
    as_private: ec.EllipticCurvePrivateKey | None = None,
) -> bytes:
    """RFC 8291 `aes128gcm`: the body of one push message.

    ``salt`` and ``as_private`` exist for the RFC's test vector only; in use
    both are fresh per message, which is what the RFC requires.
    """
    if len(plaintext) > MAX_PAYLOAD_BYTES:
        raise PushConfigError(f"a push payload is at most {MAX_PAYLOAD_BYTES} bytes")
    if len(auth_secret) != 16:
        raise PushConfigError("a subscription's auth secret is 16 bytes")
    try:
        ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    except ValueError as exc:
        raise PushConfigError("a subscription's p256dh is not a P-256 point") from exc

    salt = os.urandom(16) if salt is None else salt
    as_private = as_private or ec.generate_private_key(ec.SECP256R1())
    as_public = _public_bytes(as_private.public_key())
    ecdh_secret = as_private.exchange(ec.ECDH(), ua_key)

    # RFC 8291 §3.4: the auth secret and both public keys are mixed in first.
    ikm = _hkdf(
        auth_secret, ecdh_secret, b"WebPush: info\x00" + ua_public + as_public, 32
    )
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)

    # One record, so it is the last one: the delimiter is 0x02 (RFC 8188 §2).
    ciphertext = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    header = (
        salt
        + RECORD_SIZE.to_bytes(4, "big")
        + len(as_public).to_bytes(1, "big")
        + as_public
    )
    return header + ciphertext


@dataclass(frozen=True)
class Vapid:
    """The application server's identity (RFC 8292). From `.env`, never committed."""

    private_key: str  # base64url, the raw 32-byte scalar
    public_key: str  # base64url, the uncompressed 65-byte point
    subject: str  # `mailto:` or `https:` — Apple refuses anything else

    def check(self) -> None:
        """Refuse a key pair that does not match, before any learner is messaged."""
        if not (self.subject.startswith("mailto:") or self.subject.startswith("https:")):
            raise PushConfigError("VAPID_SUBJECT must start with mailto: or https:")
        private = _private_from_raw(b64url_decode(self.private_key))
        if _public_bytes(private.public_key()) != b64url_decode(self.public_key):
            raise PushConfigError("VAPID_PUBLIC_KEY is not the private key's public half")


def generate_vapid_keys() -> tuple[str, str]:
    """A fresh (private, public) pair, both base64url. The operator's, at launch."""
    private = ec.generate_private_key(ec.SECP256R1())
    raw = private.private_numbers().private_value.to_bytes(32, "big")
    return b64url_encode(raw), b64url_encode(_public_bytes(private.public_key()))


def vapid_authorization(endpoint: str, vapid: Vapid, *, now: datetime) -> str:
    """The `Authorization: vapid t=…, k=…` header for one push service origin."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    parts = urlsplit(endpoint)
    audience = f"{parts.scheme}://{parts.netloc}"
    header = b64url_encode(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = b64url_encode(
        json.dumps(
            {
                "aud": audience,
                "exp": int((now + VAPID_LIFETIME).timestamp()),
                "sub": vapid.subject,
            },
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{claims}".encode("ascii")
    private = _private_from_raw(b64url_decode(vapid.private_key))
    der = private.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    signature = b64url_encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={header}.{claims}.{signature}, k={vapid.public_key}"


@dataclass(frozen=True)
class Subscription:
    """A browser's push subscription, as `PushSubscription.toJSON()` gives it."""

    endpoint: str
    p256dh: str
    auth: str


@dataclass(frozen=True)
class PushRequest:
    """Everything `push_api.send` needs, and nothing it has to decide."""

    endpoint: str
    headers: dict[str, str]
    body: bytes


def endpoint_host(endpoint: str) -> str:
    """What a log line may say about an endpoint: its host, never its path."""
    return urlsplit(endpoint).netloc or "?"


def build_request(
    subscription: Subscription,
    message: dict[str, str],
    vapid: Vapid,
    *,
    now: datetime,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> PushRequest:
    """One push: the JSON message encrypted for this subscription, and signed."""
    if urlsplit(subscription.endpoint).scheme != "https":
        raise PushConfigError("a push endpoint is https")
    body = encrypt(
        json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        ua_public=b64url_decode(subscription.p256dh),
        auth_secret=b64url_decode(subscription.auth),
    )
    return PushRequest(
        endpoint=subscription.endpoint,
        headers={
            "Authorization": vapid_authorization(subscription.endpoint, vapid, now=now),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(ttl_seconds),
            # RFC 8030 §5.3. A reminder is not urgent; `normal` lets a phone in
            # low-power mode batch it rather than wake for it.
            "Urgency": "normal",
        },
        body=body,
    )


def main(argv: list[str] | None = None) -> int:
    """`python -m core.push keys` — a fresh VAPID pair for `.env`. Local, free,
    and it writes nothing: the operator pastes the three lines."""
    import argparse

    parser = argparse.ArgumentParser(description="Web Push (VAPID) key generation.")
    parser.add_argument("command", choices=["keys"])
    parser.parse_args(argv)
    private, public = generate_vapid_keys()
    print("# Web Push (W20). Paste into /home/bot/english-bot/.env. Never commit.")
    print(f"VAPID_PRIVATE_KEY={private}")
    print(f"VAPID_PUBLIC_KEY={public}")
    print("VAPID_SUBJECT=mailto:<the operator's address>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
