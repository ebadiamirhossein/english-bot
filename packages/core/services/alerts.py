"""Operator alerts + global PTB error handler (S18).

Throttling is file-backed under RUNTIME_DIR so restarts during a sticky
outage do not re-flood the shared operator/learner chat. Alerts never
increment bot_message_counts — PRD §7 rule 9 caps learning messages.
"""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from app import texts
from app.config import load_settings

logger = logging.getLogger(__name__)

ALERT_COOLDOWN = timedelta(minutes=15)
TELEGRAM_MAX_MESSAGE = 4096
TRACEBACK_BUDGET = 2500


def _throttle_path() -> Path:
    return Path(load_settings().alert_throttle_file)


def _load_throttle(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            logger.error("Alert throttle file is not a JSON object: %s", path)
            return {}
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Alert throttle file unreadable (%s): %s", path, exc)
        return {}


def _save_throttle(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def should_send_alert(
    key: str,
    *,
    now: datetime,
    path: Path | None = None,
    cooldown: timedelta = ALERT_COOLDOWN,
) -> tuple[bool, int]:
    """Return (send_now, suppressed_count_for_message).

    When send_now is False, increments suppressed and returns the new count.
    When True, returns the suppressed count accumulated since the previous
    send (then resets suppressed to 0 in the file).
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    throttle_file = path or _throttle_path()
    data = _load_throttle(throttle_file)
    entry = data.get(key)
    if not isinstance(entry, dict):
        entry = {}
    last_raw = entry.get("last_sent")
    suppressed = int(entry.get("suppressed", 0) or 0)
    if last_raw:
        try:
            last_sent = datetime.fromisoformat(str(last_raw))
            if last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=timezone.utc)
            if now - last_sent < cooldown:
                suppressed += 1
                data[key] = {
                    "last_sent": last_sent.isoformat(),
                    "suppressed": suppressed,
                }
                _save_throttle(throttle_file, data)
                return False, suppressed
        except (TypeError, ValueError):
            logger.error("Bad last_sent in throttle for key=%s", key)

    # Send: report prior suppressed, then reset.
    prior = suppressed
    data[key] = {"last_sent": now.isoformat(), "suppressed": 0}
    _save_throttle(throttle_file, data)
    return True, prior


def format_alert(
    *,
    handler: str,
    user_id: int | None,
    exc: BaseException,
    tb: str,
    suppressed: int = 0,
) -> str:
    """Build an operator alert under Telegram's message limit."""
    header = (
        f"Unhandled {type(exc).__name__} in {handler}\n"
        f"user_id={user_id if user_id is not None else 'n/a'}\n"
        f"{type(exc).__name__}: {exc}"
    )
    if suppressed:
        header += f"\nsuppressed={suppressed}"
    body = tb.strip() or "(no traceback)"
    if len(body) > TRACEBACK_BUDGET:
        body = body[: TRACEBACK_BUDGET - 3] + "..."
    text = f"{header}\n\n{body}"
    if len(text) > TELEGRAM_MAX_MESSAGE:
        text = text[: TELEGRAM_MAX_MESSAGE - 3] + "..."
    return text


async def notify_operator(
    app: Any,
    *,
    key: str,
    text: str,
    now: datetime | None = None,
    path: Path | None = None,
) -> bool:
    """Send a throttled alert to OPERATOR_TELEGRAM_ID. Never touches message ceiling.

    Returns True if a Telegram message was sent. Appends suppressed=N when
    prior duplicates were held during the cooldown.
    """
    instant = now or datetime.now(timezone.utc)
    settings = load_settings()
    operator_id = settings.operator_telegram_id
    if operator_id is None:
        logger.error(
            "OPERATOR_TELEGRAM_ID unset — alert suppressed key=%s text=%s",
            key,
            text[:200],
        )
        return False

    send, suppressed = should_send_alert(key, now=instant, path=path)
    if not send:
        logger.warning(
            "Operator alert throttled key=%s suppressed=%s", key, suppressed
        )
        return False

    body = text
    if suppressed:
        body = f"{text}\nsuppressed={suppressed}"
    if len(body) > TELEGRAM_MAX_MESSAGE:
        body = body[: TELEGRAM_MAX_MESSAGE - 3] + "..."

    try:
        await app.bot.send_message(chat_id=operator_id, text=body)
    except Exception:
        logger.exception("Failed to send operator alert key=%s", key)
        return False
    return True


def _handler_name(context: ContextTypes.DEFAULT_TYPE) -> str:
    handler = getattr(context, "handler", None)
    if handler is None:
        return "unknown"
    callback = getattr(handler, "callback", None)
    if callback is not None:
        name = getattr(callback, "__name__", None)
        if name:
            return str(name)
        return type(callback).__name__
    return type(handler).__name__


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global PTB error handler: soft to user, throttled alert to operator."""
    exc = context.error
    if exc is None:
        return
    handler = _handler_name(context)
    user_id: int | None = None
    chat = None
    if isinstance(update, Update):
        if update.effective_user is not None:
            user_id = update.effective_user.id
        chat = update.effective_chat

    logger.exception(
        "Unhandled exception handler=%s user_id=%s",
        handler,
        user_id,
        exc_info=exc,
    )

    if chat is not None:
        try:
            await context.bot.send_message(
                chat_id=chat.id, text=texts.SOFT_UNHANDLED
            )
        except Exception:
            logger.exception(
                "Failed soft reply after unhandled error user_id=%s", user_id
            )

    tb = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    # Peek prior suppressed for the alert body, then notify_operator applies
    # the same throttle key. To avoid double-counting, format without
    # suppressed and let notify_operator append it.
    key = f"{type(exc).__name__}|{handler}"
    alert = format_alert(
        handler=handler,
        user_id=user_id,
        exc=exc,
        tb=tb,
        suppressed=0,
    )
    await notify_operator(context.application, key=key, text=alert)
