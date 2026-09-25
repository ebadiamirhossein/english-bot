"""W20: `core.push` — RFC 8291 encryption and RFC 8292 VAPID — and the probe's dry run.

**Every expected value here is hardcoded or computed independently** (CLAUDE.md
§3 rule 5). The load-bearing one is RFC 8291 Appendix A: its published keys,
salt and plaintext must produce its published body, byte for byte. The VAPID
signature is checked with `cryptography`'s own verifier against the public key,
not by re-signing.

**What these cannot prove (§3 rule 2):** that a real push service accepts the
request. That is `python -m core.push_probe --live`, the operator's, at the
launch pass.

**RED DEMONSTRATIONS (2026-09-25):**
* `test_rfc8291_appendix_a_byte_for_byte` — red with the key-info prefix spelt
  `b"WebPush: info"` without its NUL (the body diverged after the header).
* `test_the_vapid_token_verifies_and_names_the_push_origin` — red with `aud` set
  to the whole endpoint rather than its origin (`'https://push.example.test/abc'
  != 'https://push.example.test'`).
* `test_a_mismatched_key_pair_is_refused_before_anything_is_sent` — red with
  `Vapid.check`'s comparison removed (DID NOT RAISE).
* `test_the_dry_probe_sends_nothing_and_prints_no_endpoint_path` — red with the
  probe printing `request.endpoint` whole (the token path appeared in stdout).
"""

from __future__ import annotations

import base64
import json
import os
import secrets
from datetime import datetime, timezone

import psycopg
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from core import push, push_probe
from core.config import load_settings

NOW = datetime(2026, 9, 25, 6, 0, tzinfo=timezone.utc)


def _d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def browser_subscription(endpoint: str = "https://push.example.test/abc") -> push.Subscription:
    """What a browser mints: a P-256 key pair and a 16-byte secret."""
    key = ec.generate_private_key(ec.SECP256R1())
    point = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return push.Subscription(endpoint=endpoint, p256dh=_e(point), auth=_e(os.urandom(16)))


def vapid() -> push.Vapid:
    private, public = push.generate_vapid_keys()
    return push.Vapid(private_key=private, public_key=public, subject="mailto:op@example.invalid")


def test_rfc8291_appendix_a_byte_for_byte() -> None:
    """The RFC's worked example, every value copied from the RFC's text."""
    body = push.encrypt(
        b"When I grow up, I want to be a watermelon",
        ua_public=_d(
            "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
        ),
        auth_secret=_d("BTBZMqHH6r4Tts7J_aSIgg"),
        salt=_d("DGv6ra1nlYgDCS1FRnbzlw"),
        as_private=ec.derive_private_key(
            int.from_bytes(_d("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"),
            ec.SECP256R1(),
        ),
    )
    assert _e(body) == (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
    )


def test_each_message_is_encrypted_afresh() -> None:
    """A fresh salt and a fresh server key per message (RFC 8291 §3.4)."""
    sub = browser_subscription()
    a = push.encrypt(b"x", ua_public=_d(sub.p256dh), auth_secret=_d(sub.auth))
    b = push.encrypt(b"x", ua_public=_d(sub.p256dh), auth_secret=_d(sub.auth))
    assert a[:16] != b[:16]
    assert a[21:86] != b[21:86]


def test_the_vapid_token_verifies_and_names_the_push_origin() -> None:
    v = vapid()
    header = push.vapid_authorization("https://push.example.test/abc?x=1", v, now=NOW)
    assert header.startswith("vapid t=") and header.endswith(f", k={v.public_key}")
    token = header[len("vapid t="):].split(",", 1)[0]
    head_b64, claims_b64, sig_b64 = token.split(".")
    assert json.loads(_d(head_b64)) == {"typ": "JWT", "alg": "ES256"}
    assert json.loads(_d(claims_b64)) == {
        "aud": "https://push.example.test",
        "exp": 1790359200,  # 2026-09-25T18:00Z: calendar.timegm((2026, 9, 25, 18, 0, 0))
        "sub": "mailto:op@example.invalid",
    }
    sig = _d(sig_b64)
    assert len(sig) == 64
    public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), _d(v.public_key))
    der = encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
    public.verify(der, f"{head_b64}.{claims_b64}".encode(), ec.ECDSA(hashes.SHA256()))
    with pytest.raises(InvalidSignature):
        public.verify(der, f"{head_b64}.{claims_b64}x".encode(), ec.ECDSA(hashes.SHA256()))


def test_a_mismatched_key_pair_is_refused_before_anything_is_sent() -> None:
    a, b = vapid(), vapid()
    push.Vapid(a.private_key, a.public_key, a.subject).check()
    with pytest.raises(push.PushConfigError, match="public half"):
        push.Vapid(a.private_key, b.public_key, a.subject).check()
    with pytest.raises(push.PushConfigError, match="mailto"):
        push.Vapid(a.private_key, a.public_key, "op@example.invalid").check()


def test_the_request_carries_what_rfc8030_and_apple_require() -> None:
    req = push.build_request(
        browser_subscription(), {"title": "t", "body": "b", "url": "/session"}, vapid(), now=NOW
    )
    assert req.headers["Content-Encoding"] == "aes128gcm"
    assert req.headers["TTL"] == "43200"
    assert req.headers["Urgency"] == "normal"
    assert req.headers["Authorization"].startswith("vapid t=")
    # salt(16) + rs(4) + idlen(1) + key(65) + ciphertext(payload + delimiter + 16 tag)
    payload = json.dumps({"title": "t", "body": "b", "url": "/session"}, separators=(",", ":"))
    assert len(req.body) == 86 + len(payload) + 1 + 16
    assert int.from_bytes(req.body[16:20], "big") == 4096


def test_a_plain_http_endpoint_or_a_bad_key_is_refused() -> None:
    with pytest.raises(push.PushConfigError, match="https"):
        push.build_request(browser_subscription("http://push.example.test/a"), {}, vapid(), now=NOW)
    bad = push.Subscription("https://push.example.test/a", "A" * 87, _e(os.urandom(16)))
    with pytest.raises(push.PushConfigError, match="P-256"):
        push.build_request(bad, {}, vapid(), now=NOW)


def test_a_log_line_may_carry_the_host_and_never_the_path() -> None:
    assert push.endpoint_host("https://web.push.apple.com/QGuQ-secret-token") == "web.push.apple.com"


def test_generated_keys_have_the_lengths_the_browser_and_031_expect() -> None:
    private, public = push.generate_vapid_keys()
    assert len(_d(private)) == 32 and len(_d(public)) == 65 and _d(public)[0] == 4
    push.Vapid(private, public, "mailto:a@b.c").check()


# ── the probe ────────────────────────────────────────────────────────────────


@pytest.fixture
def probe_learner(monkeypatch):
    v = vapid()
    monkeypatch.setenv("VAPID_PRIVATE_KEY", v.private_key)
    monkeypatch.setenv("VAPID_PUBLIC_KEY", v.public_key)
    monkeypatch.setenv("VAPID_SUBJECT", v.subject)
    with psycopg.connect(load_settings().database_url) as db:
        user_id = db.execute(
            "INSERT INTO users (name, native_language, auth_email, onboarded) "
            "VALUES ('w20-probe', 'fa', %s, TRUE) RETURNING id",
            (f"w20-{secrets.token_hex(6)}@example.invalid",),
        ).fetchone()[0]
        sub = browser_subscription(f"https://push.example.test/SECRET-{secrets.token_hex(8)}")
        db.execute(
            "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (%s,%s,%s,%s)",
            (user_id, sub.endpoint, sub.p256dh, sub.auth),
        )
        db.commit()
        try:
            yield user_id
        finally:
            db.execute("DELETE FROM users WHERE id = %s", (user_id,))
            db.commit()


def test_the_dry_probe_sends_nothing_and_prints_no_endpoint_path(
    probe_learner, monkeypatch, capsys
) -> None:
    def _no_network(*_a, **_k):
        raise AssertionError("the dry probe reached the network")

    monkeypatch.setattr("core.push_api.httpx.post", _no_network)
    monkeypatch.setattr("builtins.input", _no_network)
    assert push_probe.main(["--user", str(probe_learner)]) == 0
    out = capsys.readouterr().out
    assert "calls --live will make: 1" in out
    assert "POST https://push.example.test/…" in out
    assert "SECRET-" not in out
    assert '"aud": "https://push.example.test"' in out
    assert "DRY: nothing was sent." in out


def test_what_a_push_says_carries_no_number_and_no_banned_phrase() -> None:
    """A push is the one message the app sends unasked (CLAUDE.md §4): no count,
    no day number, no guilt. The four strings are quoted here, not imported, so
    an edit to `core/copy.py` has to be made twice to pass. Red, 2026-09-25,
    with `PUSH_NUDGE_SECOND` temporarily *"You missed 2 days — catch up?"*: the
    quoted equality fired first; `offenders` fed that same string separately
    reported `missed`, and the digit check is plain `str.isdigit`."""
    from core import copy
    from core.copy_rules import BANNED, offenders

    strings = {
        "PUSH_TITLE": copy.PUSH_TITLE,
        "PUSH_REMINDER": copy.PUSH_REMINDER,
        "PUSH_NUDGE_FIRST": copy.PUSH_NUDGE_FIRST,
        "PUSH_NUDGE_SECOND": copy.PUSH_NUDGE_SECOND,
    }
    assert strings == {
        "PUSH_TITLE": "Today’s session",
        "PUSH_REMINDER": "It’s ready whenever you are.",
        "PUSH_NUDGE_FIRST": "Today’s session is still here whenever you have a few minutes.",
        "PUSH_NUDGE_SECOND": "Short on time? One part of today’s session still counts.",
    }
    assert offenders(strings, BANNED) == []
    assert not any(ch.isdigit() for text in strings.values() for ch in text)
