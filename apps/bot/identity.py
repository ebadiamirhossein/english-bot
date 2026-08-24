"""The bot's edge: where a Telegram id stops being an identity.

Since W4b, every service in ``packages/core`` takes ``user_id`` meaning
``users.id``. Telegram ids enter the system here and nowhere else.

**This is the only module in ``apps/bot`` that may read ``effective_user.id`` or
``from_user.id`` as an identity**, and ``tests/test_identity_boundary.py``
enforces that by parsing the tree. Reading ``effective_chat.id`` for a *delivery
address* is a different thing and stays where it is -- identity is who the
learner is, an address is where a message goes, and conflating the two is what
made ``chat_id=user_id`` read as correct for two years.

The rule is structural rather than advisory because the failure it prevents is
silent. A Telegram id passed into a service returns "no rows" instead of
raising, so the feature simply stops working for everyone, with a green test
suite. That is how free correction died three times.

Resolution happens **once per update**, in ``gate_unapproved`` at group -1, which
already had to look at ``effective_user`` to decide whether to let the update
through. The result is stashed on ``context.user_data``; this module reads the
stash and falls back to a query only for job-invoked paths that never passed
through the gate.
"""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update

from core.services import identity

logger = logging.getLogger(__name__)

# The stash key. Namespaced so it cannot collide with a conversation handler's
# own user_data, which is a shared dict.
USER_ID_KEY = "_identity_user_id"


def stash_user_id(update: Update, context: Any) -> int | None:
    """Resolve this update's learner once and remember it. Called by the gate.

    Returns ``None`` for somebody approved who has not onboarded yet -- there is
    genuinely no ``users`` row, and the onboarding handlers are precisely the
    ones that must work without one.
    """
    user = update.effective_user
    if user is None:
        return None
    user_id = identity.user_id_for_telegram(user.id)
    store = getattr(context, "user_data", None)
    if store is not None:
        store[USER_ID_KEY] = user_id
    return user_id


def bot_user_id(update: Update, context: Any) -> int | None:
    """This update's internal user id, or ``None`` if there is no ``users`` row.

    Prefers the value the gate stashed. The fallback query exists for paths the
    gate never saw -- a job building an Update by hand, or a test dispatching a
    single handler directly -- and lives here so there is still only one place
    the translation is written.
    """
    store = getattr(context, "user_data", None)
    if store is not None and USER_ID_KEY in store:
        return store[USER_ID_KEY]
    user = update.effective_user
    if user is None:
        return None
    user_id = identity.user_id_for_telegram(user.id)
    if store is not None:
        store[USER_ID_KEY] = user_id
    return user_id


def telegram_id_of(update: Update) -> int | None:
    """The raw Telegram id, for the handful of things that genuinely need it.

    Operator checks compare against ``OPERATOR_TELEGRAM_ID``, and access
    requests exist before any ``users`` row -- both are about the Telegram
    account itself, not about a learner. Named explicitly so those uses are
    visible rather than indistinguishable from an identity lookup.
    """
    user = update.effective_user
    return None if user is None else user.id


def telegram_chat_id(user_id: int) -> int:
    """Where to send this learner a Telegram message.

    Raises for a learner with no Telegram account. Callers in the delivery path
    check :func:`has_telegram_channel` first and skip -- see known issue #95,
    which is about making that skip loud at W20 rather than silent.
    """
    address = identity.telegram_address_for_user(user_id)
    if address is None:
        raise identity.UnknownTelegramUser(
            f"user_id={user_id} has no telegram address"
        )
    return address


def telegram_address_or_none(user_id: int) -> int | None:
    """This learner's Telegram chat id, or ``None`` if they have no Telegram.

    What every delivery entry point calls first. Returning ``None`` rather than
    raising is deliberate: a web-only learner is a normal state, not an error,
    and a delivery pass must carry on to the next person.
    """
    return identity.telegram_address_for_user(user_id)


def has_telegram_channel(user_id: int) -> bool:
    """False for a web-only learner, who cannot be reached by this bot at all."""
    return telegram_address_or_none(user_id) is not None
