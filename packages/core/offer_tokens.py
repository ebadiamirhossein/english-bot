"""A server-signed proof that something was OFFERED to this learner. **#408, #419.**

`POST /conversation/save-word` and `POST /write/keep` both write a card from a
value the client sends back, and neither could tell a word the close-out offered
from any string a client chose: #408 put *"any 1–80 character string"* into
`cards` on `/talk`, and #419 showed `/write/keep` saving `weed` and *"the person"*
through the real route. **Re-checking the value's SHAPE on the write narrows
that and cannot close it** — the offer list is computed from text that is gone
by the time the tap arrives (turns are deleted at close, §O2; a journal entry is
never stored), so the server cannot recompute what it offered.

**THE FIX THAT NEEDS NO STORED TEXT: sign the offer.** The route that makes an
offer returns an HMAC over (surface, user, the offered values); the route that
saves requires it back and refuses anything it does not verify. Nothing is
stored, nothing expires, and a token minted for one learner, one surface or one
word verifies for no other.

**THE KEY IS `AUTH_RATE_LIMIT_SALT`, WITH A DOMAIN PREFIX, AND THAT IS A
DECISION RATHER THAN A SHORTCUT.** It is already a server-only secret on the host
(`BUILD_PROGRESS.md` Environment: *Auth keys on server `.env`*), so this needs no
new variable and no deploy step; the `offer-token:v1` prefix keeps the two uses
from ever producing the same digest for the same input. **With no key the
module fails CLOSED**: `mint` returns an empty token and `verify` refuses
everything, so a host missing the secret saves nothing rather than everything.

**WHAT IT CANNOT DO, STATED:** prove the learner MEANT to keep it. A token proves
the value was offered to this learner on this surface; the tap is still theirs.
"""

from __future__ import annotations

import hashlib
import hmac

from core.config import Settings, load_settings

_DOMAIN = "offer-token:v1"
_SEP = "\x1f"
#: 128 bits of the digest, hex. Enough that guessing one is not a strategy.
TOKEN_CHARS = 32


def _key(settings: Settings | None) -> bytes:
    cfg = settings or load_settings()
    return cfg.auth_rate_limit_salt.encode("utf-8")


def _digest(key: bytes, surface: str, user_id: int, parts: tuple[str, ...]) -> str:
    message = _SEP.join((_DOMAIN, surface, str(int(user_id)), *parts)).encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()[:TOKEN_CHARS]


def mint(surface: str, user_id: int, *parts: str, settings: Settings | None = None) -> str:
    """The token for one offer. ``""`` when the server holds no key (fail closed)."""
    key = _key(settings)
    if not key:
        return ""
    return _digest(key, surface, user_id, parts)


def verify(
    surface: str, user_id: int, token: str | None, *parts: str,
    settings: Settings | None = None,
) -> bool:
    """True only for a token this server minted for exactly these values."""
    key = _key(settings)
    if not key or not token:
        return False
    return hmac.compare_digest(_digest(key, surface, user_id, parts), token)
