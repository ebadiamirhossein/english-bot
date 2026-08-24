"""Passkey enrolment, sign-in, sessions, claim tokens and rate limits.

Every query that touches the auth columns or the five ``auth_*`` tables lives
here. Nothing in this module knows about HTTP: it takes and returns ``bytes``,
``str``, dataclasses and an explicit ``now``.

**Why every function takes ``now``.** CLAUDE.md §3 rule 6 — a test must not
depend on the wall clock. Expiry logic is exactly where that creeps in, so the
clock is a parameter and the SQL compares against ``%(now)s`` rather than
``NOW()`` everywhere an expiry is involved. A test can then place itself 31 days
ahead without sleeping and without freezing global time.

**Why nothing is cached in module state.** ``english-api`` runs
``uvicorn --workers 2``. A module-level challenge cache works perfectly on one
laptop process and fails roughly half of all real ceremonies, because begin and
finish land on different processes. Challenges, sessions and rate-limit counters
are all rows.

**Approval is never re-implemented here.** ``access_control.is_approved`` is the
single predicate; see ``_require_enrollable`` and ``resolve_session``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from core import passkeys
from core.config import Settings, load_settings
from core.db import connection
from core.services.access_control import is_approved

logger = logging.getLogger(__name__)

# A ceremony must finish inside this window. The browser's own timeout is a
# hint; this is the rule.
CHALLENGE_TTL = timedelta(minutes=5)

# Consumed and expired challenges are swept after this. Nothing reads them.
CHALLENGE_SWEEP_AFTER = timedelta(hours=1)

# Long past the sliding window, so a live session is never in reach of the
# sweep. See the note in _sweep_sessions.
SESSION_SWEEP_AFTER = timedelta(days=90)

RATE_LIMIT_SWEEP_AFTER = timedelta(days=1)

# The session is slid at most once a day: a write on every request would be one
# UPDATE per page view for no benefit.
SESSION_SLIDE_WHEN_REMAINING_BELOW = timedelta(days=29)

# 256 bits from the CSPRNG, for both session and claim tokens. Stored as a plain
# SHA-256 digest rather than under a slow KDF: these are not human-chosen
# passwords, so there is no dictionary to slow down, and a KDF would add latency
# to every authenticated request while defending against nothing the digest does
# not already cover.
TOKEN_BYTES = 32


class EnrolmentRefused(Exception):
    """First enrolment was refused.

    Deliberately carries no reason. Unknown address, unclaimed-but-unapproved
    user, already-enrolled account and bad claim token must be indistinguishable
    from outside, or the route becomes an oracle for which addresses exist and
    which accounts are already taken.
    """


class AuthenticationFailed(Exception):
    """An assertion did not produce a session. Carries no client-facing reason."""


@dataclass(frozen=True)
class AuthenticatedUser:
    """A resolved session.

    Carries ``id`` -- the internal ``users.id`` -- and deliberately not a
    Telegram id. Before W4b this field was ``telegram_user_id``, which meant the
    API could not represent a learner who had never used Telegram.
    """

    id: int
    name: str
    expires_at: datetime
    # True when this resolution slid the expiry, so the caller re-sets the
    # cookie. The caller is apps/api/deps.py::get_current_user and nowhere else.
    renewed: bool = False


@dataclass(frozen=True)
class IssuedSession:
    """A freshly minted session. ``raw_token`` exists only here and in the cookie."""

    raw_token: str
    user: AuthenticatedUser


@dataclass(frozen=True)
class StoredPasskey:
    """One credential, as the owner sees it. No key material."""

    credential_id: bytes
    nickname: str | None
    created_at: datetime
    last_used_at: datetime | None
    backed_up: bool | None


@dataclass(frozen=True)
class ClaimTokenRecord:
    """An outstanding or spent claim token. Never carries the token itself."""

    user_id: int
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None


def _digest(raw: str) -> bytes:
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def normalise_email(email: str) -> str:
    """Trim and lowercase. Exact match after that — no Gmail dot-folding.

    The address is whatever the operator set; inventing equivalences here would
    mean an address the operator can read in the table does not match what the
    learner types, or worse, that two different addresses collide.
    """
    return email.strip().lower()


# --- registration -------------------------------------------------------------


def begin_registration(
    *, email: str, claim_token: str, now: datetime, settings: Settings | None = None
) -> str:
    """Options JSON for a first enrolment, or ``EnrolmentRefused``.

    Four conditions, all required:

    1. ``auth_email`` matches a ``users`` row;
    2. that row has never enrolled (``auth_user_id IS NULL``);
    3. **the user is approved** — checked here and not only at sign-in, because
       otherwise a revoked or never-approved learner enrols successfully and
       fails at their first sign-in, after a credential has been written and a
       single-use claim token burned;
    4. a valid, unused, unexpired claim token belongs to that same row.

    The token is *verified* here and *consumed* in :func:`finish_registration`,
    so a cancelled Face ID prompt does not burn it.
    """
    cfg = settings or load_settings()
    address = normalise_email(email)

    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, name
              FROM users
             WHERE auth_email = %(email)s
               AND auth_user_id IS NULL
            """,
            {"email": address},
        ).fetchone()
        if row is None:
            raise EnrolmentRefused()
        user_id = int(row["id"])

        if not is_approved(user_id):
            raise EnrolmentRefused()

        token_row = conn.execute(
            """
            SELECT 1
              FROM auth_claim_tokens
             WHERE token_hash = %(hash)s
               AND user_id = %(user_id)s
               AND used_at IS NULL
               AND expires_at > %(now)s
            """,
            {"hash": _digest(claim_token), "user_id": user_id, "now": now},
        ).fetchone()
        if token_row is None:
            raise EnrolmentRefused()

        handle = uuid.uuid4()
        challenge = passkeys.new_challenge()
        _sweep_challenges(conn, now)
        conn.execute(
            """
            INSERT INTO auth_challenges
                (challenge, ceremony, user_id, auth_user_id, expires_at)
            VALUES (%(challenge)s, 'registration', %(user_id)s, %(handle)s,
                    %(expires)s)
            """,
            {
                "challenge": challenge,
                "user_id": user_id,
                "handle": str(handle),
                "expires": now + CHALLENGE_TTL,
            },
        )
        conn.commit()

    return passkeys.registration_options_json(
        rp_id=cfg.webauthn_rp_id,
        rp_name=cfg.webauthn_rp_name,
        user_handle=handle.bytes,
        # Shown in the passkey picker. Read from the row at runtime — no address
        # appears in this repo.
        user_name=address,
        user_display_name=str(row["name"]),
        challenge=challenge,
        exclude_credential_ids=(),
    )


def finish_registration(
    *,
    credential: dict,
    claim_token: str,
    now: datetime,
    settings: Settings | None = None,
) -> IssuedSession:
    """Verify the attestation and, in one transaction, enrol the account.

    The claim token is consumed *here*: if anything below it rolls back, the
    token is unused again.
    """
    cfg = settings or load_settings()

    pending = _consume_challenge(credential, "registration", now)
    user_id = pending["user_id"]
    handle = pending["auth_user_id"]
    if user_id is None or handle is None:
        raise AuthenticationFailed()

    try:
        registered = passkeys.verify_registration(
            credential=credential,
            expected_challenge=pending["challenge"],
            expected_rp_id=cfg.webauthn_rp_id,
            expected_origin=cfg.webauthn_origin,
        )
    except passkeys.PasskeyError as exc:
        raise AuthenticationFailed() from exc

    with connection() as conn:
        spent = conn.execute(
            """
            UPDATE auth_claim_tokens
               SET used_at = %(now)s, used_credential_id = %(cid)s
             WHERE token_hash = %(hash)s
               AND user_id = %(user_id)s
               AND used_at IS NULL
               AND expires_at > %(now)s
            RETURNING user_id
            """,
            {
                "hash": _digest(claim_token),
                "user_id": user_id,
                "cid": registered.credential_id,
                "now": now,
            },
        ).fetchone()
        if spent is None:
            conn.rollback()
            raise AuthenticationFailed()

        bound = conn.execute(
            """
            UPDATE users
               SET auth_user_id = %(handle)s
             WHERE id = %(user_id)s
               AND auth_user_id IS NULL
            RETURNING name
            """,
            {"handle": handle, "user_id": user_id},
        ).fetchone()
        if bound is None:
            conn.rollback()
            raise AuthenticationFailed()

        _insert_credential(conn, user_id, registered)
        session = _issue_session(
            conn, user_id, str(bound["name"]), registered.credential_id, now, cfg
        )
        conn.commit()

    logger.info("Enrolled user_id=%s", user_id)
    return session


# --- authentication -----------------------------------------------------------


def begin_authentication(
    *, now: datetime, settings: Settings | None = None
) -> str:
    """Options JSON for sign-in. Nothing user-specific crosses the wire."""
    cfg = settings or load_settings()
    challenge = passkeys.new_challenge()
    with connection() as conn:
        _sweep_challenges(conn, now)
        conn.execute(
            """
            INSERT INTO auth_challenges (challenge, ceremony, expires_at)
            VALUES (%(challenge)s, 'authentication', %(expires)s)
            """,
            {"challenge": challenge, "expires": now + CHALLENGE_TTL},
        )
        conn.commit()
    return passkeys.authentication_options_json(
        rp_id=cfg.webauthn_rp_id, challenge=challenge
    )


def finish_authentication(
    *, credential: dict, now: datetime, settings: Settings | None = None
) -> IssuedSession:
    """Verify an assertion and issue a session.

    The user is resolved from the assertion's **user handle**, which is what
    makes a discoverable credential work without a typed identifier.
    """
    cfg = settings or load_settings()

    pending = _consume_challenge(credential, "authentication", now)

    try:
        handle = passkeys.user_handle_from_response(credential)
        credential_id = passkeys.credential_id_from_response(credential)
    except passkeys.PasskeyError as exc:
        raise AuthenticationFailed() from exc
    if handle is None:
        raise AuthenticationFailed()
    try:
        handle_uuid = uuid.UUID(bytes=handle)
    except ValueError as exc:
        raise AuthenticationFailed() from exc

    with connection() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.name, c.public_key, c.sign_count
              FROM users u
              INNER JOIN auth_credentials c
                      ON c.user_id = u.id
             WHERE u.auth_user_id = %(handle)s
               AND c.credential_id = %(cid)s
            """,
            {"handle": str(handle_uuid), "cid": credential_id},
        ).fetchone()
        if row is None:
            # Covers both "no such handle" and "that credential belongs to
            # someone else" — one answer, no oracle.
            raise AuthenticationFailed()

        user_id = int(row["id"])
        if not is_approved(user_id):
            raise AuthenticationFailed()

        try:
            assertion = passkeys.verify_authentication(
                credential=credential,
                expected_challenge=pending["challenge"],
                expected_rp_id=cfg.webauthn_rp_id,
                expected_origin=cfg.webauthn_origin,
                public_key=bytes(row["public_key"]),
                current_sign_count=int(row["sign_count"]),
            )
        except passkeys.PasskeyError as exc:
            # Includes a sign-count regression, which py_webauthn raises on.
            raise AuthenticationFailed() from exc

        conn.execute(
            """
            UPDATE auth_credentials
               SET sign_count = %(count)s, last_used_at = %(now)s
             WHERE credential_id = %(cid)s
            """,
            {"count": assertion.new_sign_count, "cid": credential_id, "now": now},
        )
        session = _issue_session(
            conn, user_id, str(row["name"]), credential_id, now, cfg
        )
        conn.commit()

    return session


# --- adding a passkey to an enrolled account ----------------------------------


def begin_add_passkey(
    *, user_id: int, now: datetime, settings: Settings | None = None
) -> str:
    """Creation options for a second passkey. Requires an existing session.

    ``excludeCredentials`` carries the user's current credential ids so the same
    device cannot silently enrol twice.
    """
    cfg = settings or load_settings()
    challenge = passkeys.new_challenge()

    with connection() as conn:
        row = conn.execute(
            """
            SELECT name, auth_email, auth_user_id
              FROM users
             WHERE id = %(user_id)s
            """,
            {"user_id": user_id},
        ).fetchone()
        if row is None or row["auth_user_id"] is None:
            raise AuthenticationFailed()
        existing = [
            bytes(r["credential_id"])
            for r in conn.execute(
                """
                SELECT credential_id FROM auth_credentials
                 WHERE user_id = %(user_id)s
                """,
                {"user_id": user_id},
            ).fetchall()
        ]
        _sweep_challenges(conn, now)
        conn.execute(
            """
            INSERT INTO auth_challenges
                (challenge, ceremony, user_id, expires_at)
            VALUES (%(challenge)s, 'registration', %(user_id)s, %(expires)s)
            """,
            {
                "challenge": challenge,
                "user_id": user_id,
                "expires": now + CHALLENGE_TTL,
            },
        )
        conn.commit()

    return passkeys.registration_options_json(
        rp_id=cfg.webauthn_rp_id,
        rp_name=cfg.webauthn_rp_name,
        user_handle=uuid.UUID(str(row["auth_user_id"])).bytes,
        user_name=str(row["auth_email"] or row["name"]),
        user_display_name=str(row["name"]),
        challenge=challenge,
        exclude_credential_ids=tuple(existing),
    )


def finish_add_passkey(
    *,
    user_id: int,
    credential: dict,
    now: datetime,
    settings: Settings | None = None,
) -> bytes:
    """Attach a new credential to **the session's** user and to no other.

    The challenge row written at begin carries the user id; this asserts the two
    agree, so a challenge minted under one session cannot be finished under
    another.
    """
    cfg = settings or load_settings()

    pending = _consume_challenge(credential, "registration", now)
    if pending["user_id"] is None or int(pending["user_id"]) != user_id:
        raise AuthenticationFailed()
    # A challenge minted by begin_registration carries a handle and belongs to
    # the first-enrolment path; it must not be usable here.
    if pending["auth_user_id"] is not None:
        raise AuthenticationFailed()

    try:
        registered = passkeys.verify_registration(
            credential=credential,
            expected_challenge=pending["challenge"],
            expected_rp_id=cfg.webauthn_rp_id,
            expected_origin=cfg.webauthn_origin,
        )
    except passkeys.PasskeyError as exc:
        raise AuthenticationFailed() from exc

    with connection() as conn:
        _insert_credential(conn, user_id, registered)
        conn.commit()

    return registered.credential_id


def list_passkeys(*, user_id: int) -> list[StoredPasskey]:
    """The caller's own credentials. No key material, no sign counts."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT credential_id, nickname, created_at, last_used_at, backed_up
              FROM auth_credentials
             WHERE user_id = %(user_id)s
             ORDER BY created_at
            """,
            {"user_id": user_id},
        ).fetchall()
    return [
        StoredPasskey(
            credential_id=bytes(r["credential_id"]),
            nickname=r["nickname"],
            created_at=r["created_at"],
            last_used_at=r["last_used_at"],
            backed_up=r["backed_up"],
        )
        for r in rows
    ]


def delete_passkey(*, user_id: int, credential_id: bytes) -> str:
    """Remove one credential. Returns ``deleted``, ``last`` or ``missing``.

    Scoped to ``user_id``: a credential belonging to another learner is
    ``missing``, and the route answers 404 rather than 403 — a 403 would confirm
    the credential exists and turn an opaque id into an enumeration oracle.

    The count and the delete are **one transaction with ``FOR UPDATE``**. Two
    concurrent deletes each seeing two credentials would otherwise both proceed
    and leave the learner with none, and self-lockout is the recovery case with
    no self-service way back.
    """
    with connection() as conn:
        with conn.transaction():
            owned = conn.execute(
                """
                SELECT credential_id
                  FROM auth_credentials
                 WHERE user_id = %(user_id)s
                 FOR UPDATE
                """,
                {"user_id": user_id},
            ).fetchall()
            ids = {bytes(r["credential_id"]) for r in owned}
            if credential_id not in ids:
                return "missing"
            if len(ids) <= 1:
                return "last"
            conn.execute(
                """
                DELETE FROM auth_credentials
                 WHERE credential_id = %(cid)s AND user_id = %(user_id)s
                """,
                {"cid": credential_id, "user_id": user_id},
            )
    return "deleted"


# --- sessions -----------------------------------------------------------------


def resolve_session(
    *, raw_token: str, now: datetime, settings: Settings | None = None
) -> AuthenticatedUser | None:
    """The signed-in user, or ``None``. Slides the expiry at most once a day.

    Approval is re-checked on **every** request, by calling
    ``access_control.is_approved`` — never by re-writing the predicate. That is
    what makes a revocation take effect on the learner's next request everywhere,
    without anything having to remember to revoke sessions too.
    """
    cfg = settings or load_settings()
    if not raw_token:
        return None

    with connection() as conn:
        row = conn.execute(
            """
            SELECT s.token_hash, s.expires_at, u.id, u.name
              FROM auth_sessions s
              INNER JOIN users u ON u.id = s.user_id
             WHERE s.token_hash = %(hash)s
               AND s.revoked_at IS NULL
               AND s.expires_at > %(now)s
            """,
            {"hash": _digest(raw_token), "now": now},
        ).fetchone()
        if row is None:
            return None

        user_id = int(row["id"])
        if not is_approved(user_id):
            return None

        expires_at = row["expires_at"]
        renewed = False
        if expires_at - now < SESSION_SLIDE_WHEN_REMAINING_BELOW:
            expires_at = now + timedelta(days=cfg.auth_session_days)
            conn.execute(
                """
                UPDATE auth_sessions
                   SET expires_at = %(expires)s, last_seen_at = %(now)s
                 WHERE token_hash = %(hash)s
                """,
                {"expires": expires_at, "now": now, "hash": row["token_hash"]},
            )
            conn.commit()
            renewed = True

    return AuthenticatedUser(
        id=user_id,
        name=str(row["name"]),
        expires_at=expires_at,
        renewed=renewed,
    )


def revoke_session(*, raw_token: str, now: datetime) -> None:
    """Invalidate a session server-side.

    Clearing the cookie is not enough on its own: a token that leaked would
    still work. Both halves happen — this one, and the route's ``Max-Age=0``.
    """
    if not raw_token:
        return
    with connection() as conn:
        conn.execute(
            """
            UPDATE auth_sessions
               SET revoked_at = %(now)s
             WHERE token_hash = %(hash)s AND revoked_at IS NULL
            """,
            {"hash": _digest(raw_token), "now": now},
        )
        conn.commit()


def revoke_all_sessions(*, user_id: int, now: datetime) -> int:
    """Kill every session a user holds. Used by the recovery runbook."""
    with connection() as conn:
        rows = conn.execute(
            """
            UPDATE auth_sessions
               SET revoked_at = %(now)s
             WHERE user_id = %(user_id)s AND revoked_at IS NULL
            RETURNING token_hash
            """,
            {"user_id": user_id, "now": now},
        ).fetchall()
        conn.commit()
    return len(rows)


# --- claim tokens -------------------------------------------------------------


def issue_claim_token(
    *, user_id: int, now: datetime, hours: int | None = None,
    settings: Settings | None = None,
) -> str:
    """Mint a one-time enrolment token. Returns the raw value **once**.

    Only the SHA-256 digest is stored, so this return value is the only time the
    token exists in readable form. It is handed over out of band — never through
    the channel the app is reached on.
    """
    cfg = settings or load_settings()
    raw = _new_token()
    lifetime = timedelta(hours=hours or cfg.auth_claim_token_hours)
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO auth_claim_tokens (token_hash, user_id, created_at, expires_at)
            VALUES (%(hash)s, %(user_id)s, %(now)s, %(expires)s)
            """,
            {
                "hash": _digest(raw),
                "user_id": user_id,
                "now": now,
                "expires": now + lifetime,
            },
        )
        conn.commit()
    logger.info("Issued claim token user_id=%s expires_in_hours=%s", user_id,
                lifetime.total_seconds() / 3600)
    return raw


def list_claim_tokens() -> list[ClaimTokenRecord]:
    """Outstanding and spent tokens. Never the token, never the address."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT user_id, created_at, expires_at, used_at
              FROM auth_claim_tokens
             ORDER BY created_at DESC
            """
        ).fetchall()
    return [
        ClaimTokenRecord(
            user_id=int(r["user_id"]),
            created_at=r["created_at"],
            expires_at=r["expires_at"],
            used_at=r["used_at"],
        )
        for r in rows
    ]


def revoke_claim_tokens(*, user_id: int, now: datetime) -> int:
    """Spend every outstanding token for a user without enrolling anything."""
    with connection() as conn:
        rows = conn.execute(
            """
            UPDATE auth_claim_tokens
               SET used_at = %(now)s
             WHERE user_id = %(user_id)s AND used_at IS NULL
            RETURNING token_hash
            """,
            {"user_id": user_id, "now": now},
        ).fetchall()
        conn.commit()
    return len(rows)


def user_id_for_email(*, email: str) -> int | None:
    """Operator lookup for the CLI. Returns None when the address is unknown."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id FROM users WHERE auth_email = %(email)s
            """,
            {"email": normalise_email(email)},
        ).fetchone()
    return int(row["id"]) if row else None


# --- rate limiting ------------------------------------------------------------


def rate_limit_bucket(
    *, route: str, client: str, settings: Settings | None = None
) -> str:
    """The table key for one client on one route.

    A salted **hash**, never a raw address: CLAUDE.md §5 keeps personal data out
    of the record, and a digest is enough to count with. ``client="global"``
    produces the shared ceiling's key from the same function, so both halves of
    the limit are provably rows in the same table.
    """
    cfg = settings or load_settings()
    material = f"{cfg.auth_rate_limit_salt}|{client}|{route}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def check_rate_limit(
    *,
    route: str,
    client: str,
    per_client: int,
    overall: int,
    window_seconds: int,
    now: datetime,
    settings: Settings | None = None,
) -> bool:
    """Count this request against both limits. ``False`` means refuse it.

    Two limits, because either alone is weak: a per-client limit is evaded from
    many addresses, and a global-only limit lets one attacker deny sign-in to
    the two learners. Both are one row each.

    Counted in Postgres rather than in memory for the ``--workers 2`` reason at
    the top of this module.
    """
    cfg = settings or load_settings()
    cutoff = now - timedelta(seconds=window_seconds)
    allowed = True
    with connection() as conn:
        _sweep_rate_limits(conn, now)
        for who, limit in ((client, per_client), ("global", overall)):
            bucket = rate_limit_bucket(route=route, client=who, settings=cfg)
            row = conn.execute(
                """
                INSERT INTO auth_rate_limits (bucket, window_start, count)
                VALUES (%(bucket)s, %(now)s, 1)
                ON CONFLICT (bucket) DO UPDATE
                   SET count = CASE
                           WHEN auth_rate_limits.window_start < %(cutoff)s THEN 1
                           ELSE auth_rate_limits.count + 1
                       END,
                       window_start = CASE
                           WHEN auth_rate_limits.window_start < %(cutoff)s
                           THEN %(now)s
                           ELSE auth_rate_limits.window_start
                       END
                RETURNING count
                """,
                {"bucket": bucket, "now": now, "cutoff": cutoff},
            ).fetchone()
            if row is not None and int(row["count"]) > limit:
                allowed = False
        conn.commit()
    if not allowed:
        logger.warning("Rate limit hit route=%s", route)
    return allowed


# --- internals ----------------------------------------------------------------


def _consume_challenge(credential: dict, ceremony: str, now: datetime) -> dict:
    """Atomically spend the challenge the response claims to answer.

    **One statement, not a SELECT then an UPDATE.** Two concurrent finishes
    against one challenge would otherwise both pass, which is the whole point of
    a challenge being single-use.

    **On its own connection, committed immediately, before any verification.**
    If this shared the caller's transaction, a failed signature check would roll
    the consumption back and leave the challenge replayable for the rest of its
    five minutes. A challenge is spent by being *answered*, not by being answered
    correctly. The claim token is the opposite — spent only on success — which is
    why the two are deliberately in different transactions.
    """
    try:
        challenge = _challenge_from_response(credential)
    except passkeys.PasskeyError as exc:
        raise AuthenticationFailed() from exc

    with connection() as conn:
        row = conn.execute(
            """
            UPDATE auth_challenges
               SET consumed_at = %(now)s
             WHERE challenge = %(challenge)s
               AND ceremony = %(ceremony)s
               AND consumed_at IS NULL
               AND expires_at > %(now)s
            RETURNING challenge, user_id, auth_user_id
            """,
            {"challenge": challenge, "ceremony": ceremony, "now": now},
        ).fetchone()
        conn.commit()
    if row is None:
        raise AuthenticationFailed()
    return {
        "challenge": bytes(row["challenge"]),
        "user_id": row["user_id"],
        "auth_user_id": row["auth_user_id"],
    }


def _challenge_from_response(credential: dict) -> bytes:
    """The challenge the authenticator signed, out of clientDataJSON.

    Read from the response rather than tracked in a cookie or a body field: the
    value in ``clientDataJSON`` is the one the signature covers, so looking the
    row up by it means a response can only ever spend the challenge it actually
    answers.
    """
    response = credential.get("response")
    if not isinstance(response, dict):
        raise passkeys.PasskeyError("response is missing")
    client_data = response.get("clientDataJSON")
    if not isinstance(client_data, str):
        raise passkeys.PasskeyError("clientDataJSON is missing")
    try:
        parsed = json.loads(passkeys.b64url_decode(client_data))
        return passkeys.b64url_decode(parsed["challenge"])
    except passkeys.PasskeyError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise passkeys.PasskeyError("clientDataJSON is unreadable") from exc


def _insert_credential(conn, user_id: int, registered) -> None:
    conn.execute(
        """
        INSERT INTO auth_credentials
            (credential_id, user_id, public_key, sign_count, transports,
             aaguid, credential_device_type, backed_up)
        VALUES (%(cid)s, %(user_id)s, %(key)s, %(count)s, %(transports)s,
                %(aaguid)s, %(device_type)s, %(backed_up)s)
        """,
        {
            "cid": registered.credential_id,
            "user_id": user_id,
            "key": registered.public_key,
            "count": registered.sign_count,
            "transports": list(registered.transports),
            "aaguid": registered.aaguid,
            "device_type": registered.credential_device_type,
            "backed_up": registered.backed_up,
        },
    )


def _issue_session(
    conn,
    user_id: int,
    name: str,
    credential_id: bytes,
    now: datetime,
    cfg: Settings,
) -> IssuedSession:
    raw = _new_token()
    expires_at = now + timedelta(days=cfg.auth_session_days)
    _sweep_sessions(conn, now)
    conn.execute(
        """
        INSERT INTO auth_sessions
            (token_hash, user_id, credential_id, created_at, expires_at,
             last_seen_at)
        VALUES (%(hash)s, %(user_id)s, %(cid)s, %(now)s, %(expires)s, %(now)s)
        """,
        {
            "hash": _digest(raw),
            "user_id": user_id,
            "cid": credential_id,
            "now": now,
            "expires": expires_at,
        },
    )
    return IssuedSession(
        raw_token=raw,
        user=AuthenticatedUser(
            id=user_id, name=name, expires_at=expires_at
        ),
    )


def _sweep_challenges(conn, now: datetime) -> None:
    conn.execute(
        "DELETE FROM auth_challenges WHERE expires_at < %(cutoff)s",
        {"cutoff": now - CHALLENGE_SWEEP_AFTER},
    )


def _sweep_sessions(conn, now: datetime) -> None:
    """Drop long-dead rows.

    The cutoff is far past the sliding window, so nothing live is ever in reach.
    The volume at two learners never matters; leaving one table swept and the
    others unswept is what would read as an oversight rather than a decision.
    """
    conn.execute(
        "DELETE FROM auth_sessions WHERE expires_at < %(cutoff)s",
        {"cutoff": now - SESSION_SWEEP_AFTER},
    )


def _sweep_rate_limits(conn, now: datetime) -> None:
    conn.execute(
        "DELETE FROM auth_rate_limits WHERE window_start < %(cutoff)s",
        {"cutoff": now - RATE_LIMIT_SWEEP_AFTER},
    )
