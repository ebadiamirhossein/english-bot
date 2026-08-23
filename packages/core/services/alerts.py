"""Operator alerts (S18).

Channel-neutral: the caller supplies ``send``. The PTB error handler that
used to live here is now ``apps/bot/alerts.py::on_error``.

Throttling is file-backed under RUNTIME_DIR so restarts during a sticky
outage do not re-flood the shared operator/learner chat. Alerts never
increment bot_message_counts — PRD §7 rule 9 caps learning messages.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from core.config import load_settings

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
    send: Callable[[str], Awaitable[None]],
    *,
    key: str,
    text: str,
    now: datetime | None = None,
    path: Path | None = None,
) -> bool:
    """Send a throttled alert to the operator. Never touches message ceiling.

    ``send`` delivers one already-formatted string on whatever channel the
    caller owns. OPERATOR_TELEGRAM_ID still gates whether an alert is raised
    at all, so an unconfigured operator stays a logged no-op.

    Returns True if an alert was delivered. Appends suppressed=N when prior
    duplicates were held during the cooldown.
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

    # Not `send` — that name is the caller's delivery callable now.
    may_send, suppressed = should_send_alert(key, now=instant, path=path)
    if not may_send:
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
        await send(body)
    except Exception:
        logger.exception("Failed to send operator alert key=%s", key)
        return False
    return True
