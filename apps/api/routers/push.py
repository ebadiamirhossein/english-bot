"""W20's routes: turn reminders on or off for THIS browser. PRD §10.

    GET  /push/key          the VAPID public key, or null when push is not set up
    POST /push/subscribe    store this browser's subscription      → {on: true}
    POST /push/unsubscribe  forget it                              → {on: false}
    POST /push/state        is this browser subscribed?            → {on: bool}

Each parses, authorises, calls **one** service function and serialises
(CLAUDE.md §2). **Plain `def`** (standing rule 6 / #7): they block on a pool
checkout.

**The endpoint is always in a JSON body, never the URL** — it is a capability
URL, and a URL is what access logs keep. `state` is a POST for that reason and
no other. Log lines carry the user id and the route, never the endpoint.

**No route here sends a push.** Sending is the worker's (`core.services.push`),
on its own clock; the probe is the only other door, and it is the operator's.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from apps.api.deps import get_settings, rate_limit, require_current_user
from apps.api.routers.cards import require_json
from apps.api.schemas import (
    PushEndpointIn,
    PushKeyOut,
    PushStateOut,
    PushSubscriptionIn,
)
from core.config import Settings
from core.push import Subscription
from core.services import push as push_service
from core.services.auth import AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(tags=["push"])

# A learner toggles reminders a handful of times a year; the menu reads the
# state each time it opens. The ceiling guards a stolen session, not cost.
_LIMIT = Depends(rate_limit("push", per_client=120, overall=600, window_seconds=3600))


@router.get("/push/key", response_model=PushKeyOut, dependencies=[_LIMIT])
def key(
    session: AuthenticatedUser = Depends(require_current_user),
    settings: Settings = Depends(get_settings),
) -> PushKeyOut:
    """Null means the reminder control is not drawn at all."""
    return PushKeyOut(public_key=push_service.public_key(settings))


@router.post(
    "/push/subscribe",
    response_model=PushStateOut,
    dependencies=[Depends(require_json), _LIMIT],
)
def subscribe(
    body: PushSubscriptionIn,
    session: AuthenticatedUser = Depends(require_current_user),
) -> PushStateOut:
    push_service.save_subscription(
        session.id,
        Subscription(endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth),
    )
    logger.info("push subscribe user_id=%s", session.id)
    return PushStateOut(on=True)


@router.post(
    "/push/unsubscribe",
    response_model=PushStateOut,
    dependencies=[Depends(require_json), _LIMIT],
)
def unsubscribe(
    body: PushEndpointIn,
    session: AuthenticatedUser = Depends(require_current_user),
) -> PushStateOut:
    push_service.delete_subscription(session.id, body.endpoint)
    logger.info("push unsubscribe user_id=%s", session.id)
    return PushStateOut(on=False)


@router.post(
    "/push/state",
    response_model=PushStateOut,
    dependencies=[Depends(require_json), _LIMIT],
)
def state(
    body: PushEndpointIn,
    session: AuthenticatedUser = Depends(require_current_user),
) -> PushStateOut:
    return PushStateOut(on=push_service.has_subscription(session.id, body.endpoint))
