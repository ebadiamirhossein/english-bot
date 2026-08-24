"""Passkey routes: enrol, sign in, sign out, manage credentials.

Every route here is a **plain ``def``** (see ``apps/api/deps.py`` for why), parses,
authorises, calls **one** service function and serialises. No SQL, no business
logic — ``tests/test_core_boundary.py`` fails the commit that adds either.

Two response disciplines that are load-bearing rather than stylistic:

* **Enrolment failures are indistinguishable.** Unknown address, unapproved
  user, already-enrolled account and bad claim token all return the same body.
  Anything else makes this route an oracle for which addresses exist.
* **A credential that is not yours is 404, never 403.** A 403 confirms the
  credential exists and turns an opaque id into something enumerable.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from apps.api.deps import (
    clear_session_cookie,
    get_settings,
    rate_limit,
    require_current_user,
    session_cookie_name,
    set_session_cookie,
)
from apps.api.schemas import (
    CredentialEnvelope,
    Passkey,
    RegisterBeginRequest,
    RegisterFinishRequest,
    Session,
)
from core.config import Settings
from core.passkeys import PasskeyError, b64url_decode, b64url_encode
from core.services import auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Deliberately the only thing a refused enrolment ever says.
REFUSED = {"error": "registration_unavailable"}
UNAUTHENTICATED = {"error": "not_authenticated"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session_body(user: auth.AuthenticatedUser) -> Session:
    return Session(
        user_id=user.id,
        name=user.name,
        expires_at=user.expires_at,
    )


def _options(payload: str) -> JSONResponse:
    """Hand py_webauthn's own JSON straight through.

    Re-encoding it through pydantic would mean re-modelling the WebAuthn options
    shape, which is the thing the schema module explains we are not doing.
    """
    return JSONResponse(content=json.loads(payload))


# --- first enrolment ----------------------------------------------------------


@router.post(
    "/register/begin",
    dependencies=[Depends(rate_limit("register_begin", 5, 20, 3600))],
)
def register_begin(
    body: RegisterBeginRequest, settings: Settings = Depends(get_settings)
) -> JSONResponse:
    """Creation options for a learner claiming their account for the first time."""
    try:
        payload = auth.begin_registration(
            email=body.email,
            claim_token=body.claim_token,
            now=_now(),
            settings=settings,
        )
    except auth.EnrolmentRefused:
        return JSONResponse(status_code=400, content=REFUSED)
    return _options(payload)


@router.post(
    "/register/finish",
    dependencies=[Depends(rate_limit("register_finish", 5, 20, 3600))],
)
def register_finish(
    body: RegisterFinishRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> Session:
    """Verify the attestation, bind the account, and start a session."""
    try:
        issued = auth.finish_registration(
            credential=body.credential,
            claim_token=body.claim_token,
            now=_now(),
            settings=settings,
        )
    except (auth.AuthenticationFailed, auth.EnrolmentRefused) as exc:
        raise HTTPException(status_code=401, detail="not_authenticated") from exc
    set_session_cookie(response, settings, issued.raw_token)
    return _session_body(issued.user)


# --- sign in ------------------------------------------------------------------


@router.post(
    "/login/begin", dependencies=[Depends(rate_limit("login_begin", 10, 60, 60))]
)
def login_begin(settings: Settings = Depends(get_settings)) -> JSONResponse:
    """Request options. No body, no identifier — the passkey is discoverable."""
    return _options(auth.begin_authentication(now=_now(), settings=settings))


@router.post(
    "/login/finish", dependencies=[Depends(rate_limit("login_finish", 10, 60, 60))]
)
def login_finish(
    body: CredentialEnvelope,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> Session:
    """Verify the assertion and start a session."""
    try:
        issued = auth.finish_authentication(
            credential=body.credential, now=_now(), settings=settings
        )
    except auth.AuthenticationFailed as exc:
        raise HTTPException(status_code=401, detail="not_authenticated") from exc
    set_session_cookie(response, settings, issued.raw_token)
    return _session_body(issued.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request, settings: Settings = Depends(get_settings)
) -> Response:
    """Revoke the session **server-side** and clear the cookie.

    Both halves, always. Clearing the cookie alone would leave a live token in
    whatever captured it — which is exactly what the logout test replays to
    check. Idempotent: no session is not an error.
    """
    raw = request.cookies.get(session_cookie_name(settings), "")
    auth.revoke_session(raw_token=raw, now=_now())
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response, settings)
    return response


# --- managing passkeys --------------------------------------------------------


@router.get("/passkeys")
def list_passkeys(
    user: auth.AuthenticatedUser = Depends(require_current_user),
) -> list[Passkey]:
    """The caller's own credentials."""
    return [
        Passkey(
            id=b64url_encode(p.credential_id),
            nickname=p.nickname,
            created_at=p.created_at,
            last_used_at=p.last_used_at,
            backed_up=p.backed_up,
        )
        for p in auth.list_passkeys(user_id=user.id)
    ]


@router.post(
    "/passkeys/begin",
    dependencies=[Depends(rate_limit("passkeys_begin", 10, 40, 3600))],
)
def add_passkey_begin(
    user: auth.AuthenticatedUser = Depends(require_current_user),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Creation options for a second passkey. Requires an existing session.

    A different path from first enrolment on purpose: adding a credential to an
    account that is already enrolled is proved by *holding a session*, not by a
    claim token.
    """
    return _options(
        auth.begin_add_passkey(
            user_id=user.id, now=_now(), settings=settings
        )
    )


@router.post(
    "/passkeys/finish",
    dependencies=[Depends(rate_limit("passkeys_finish", 10, 40, 3600))],
)
def add_passkey_finish(
    body: CredentialEnvelope,
    user: auth.AuthenticatedUser = Depends(require_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Attach the new credential to **this session's** user and no other."""
    try:
        credential_id = auth.finish_add_passkey(
            user_id=user.id,
            credential=body.credential,
            now=_now(),
            settings=settings,
        )
    except auth.AuthenticationFailed as exc:
        raise HTTPException(status_code=401, detail="not_authenticated") from exc
    return {"id": b64url_encode(credential_id)}


@router.delete("/passkeys/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_passkey(
    credential_id: str,
    user: auth.AuthenticatedUser = Depends(require_current_user),
) -> Response:
    """Remove one credential.

    404 for an id that is not valid base64url, and 404 for a credential that
    belongs to someone else — a request for something that cannot exist is not a
    server fault, and a 403 would confirm existence.

    409 for the last remaining credential: removing it is self-lockout, and this
    slice has no email reset to recover from it.
    """
    try:
        raw = b64url_decode(credential_id)
    except PasskeyError:
        raise HTTPException(status_code=404, detail="not_found") from None

    outcome = auth.delete_passkey(user_id=user.id, credential_id=raw)
    if outcome == "missing":
        raise HTTPException(status_code=404, detail="not_found")
    if outcome == "last":
        raise HTTPException(status_code=409, detail="last_passkey")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
