"""Evening reading delivery (S9a).

Sends title+body only. Questions are stored unsent for S9c.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app import texts
from app.llm import LLMError, chat
from app.services.interests import select_topic
from app.services.reading import (
    ReadingValidationError,
    persist_and_send,
    validate_reading_payload,
)
from app.services.sessions import (
    has_reading_session_on,
    increment_bot_messages,
    local_today,
    under_message_ceiling,
)
from app.services.users import get_user

logger = logging.getLogger(__name__)

HANDLER_NAME = "reading"
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "reading.txt"
_prompt_template: str | None = None


def init_reading_prompt() -> None:
    """Load the reading system prompt from disk (call once at boot)."""
    global _prompt_template
    _prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")


def _system_prompt(
    *,
    cefr_level: str,
    native_language: str,
    topic: str,
    track: str,
) -> str:
    if _prompt_template is None:
        init_reading_prompt()
    assert _prompt_template is not None
    return _prompt_template.format(
        cefr_level=cefr_level,
        native_language=native_language,
        topic=topic,
        track=track,
    )


def _generate(
    *,
    cefr_level: str,
    native_language: str,
    topic: str,
    track: str,
    chat_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    system = _system_prompt(
        cefr_level=cefr_level,
        native_language=native_language,
        topic=topic,
        track=track,
    )
    call = chat_fn or chat
    result = call(
        [{"role": "user", "content": "Generate today's reading passage."}],
        system=system,
        json_mode=True,
        max_tokens=4000,
    )
    if not isinstance(result, dict):
        raise LLMError("reading response was not a JSON object")
    return result


def _user_timezone(user_id: int) -> str:
    from app.db import connection

    with connection() as conn:
        row = conn.execute(
            """
            SELECT timezone FROM users WHERE telegram_user_id = %s
            """,
            (user_id,),
        ).fetchone()
    if row is None or not row["timezone"]:
        return "Europe/Vilnius"
    return str(row["timezone"])


async def deliver_evening(
    app: Any,
    user_id: int,
    *,
    now: datetime,
    chat_fn: Callable[..., Any] | None = None,
) -> str:
    """Deliver one reading for ``user_id``. Returns action taken."""
    bot = app.bot
    tz = _user_timezone(user_id)
    day = local_today(tz, now)

    if has_reading_session_on(user_id, day):
        return "skipped_existing"

    if not under_message_ceiling(user_id, day):
        logger.warning(
            "reading skip user_id=%s reason=ceiling_reached day=%s",
            user_id,
            day,
        )
        return "skipped_ceiling"

    user = get_user(user_id)
    if user is None:
        logger.warning(
            "reading skip user_id=%s reason=user_not_found",
            user_id,
        )
        return "skipped_no_user"

    topic_row = select_topic(user_id, user.track_weights, day)
    if topic_row is None:
        logger.warning(
            "reading skip user_id=%s reason=no_interests",
            user_id,
        )
        return "skipped_no_interests"

    raw: dict[str, Any] | None = None
    payload = None
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            # Off the event loop — sync chat() must not block JobQueue ticks.
            raw = await asyncio.to_thread(
                _generate,
                cefr_level=user.cefr_level,
                native_language=user.native_language,
                topic=topic_row.topic,
                track=topic_row.track,
                chat_fn=chat_fn,
            )
            payload = validate_reading_payload(raw)
            break
        except LLMError as exc:
            last_err = exc
            logger.warning(
                "reading LLM failure user_id=%s attempt=%s: %s",
                user_id,
                attempt + 1,
                exc,
            )
        except ReadingValidationError as exc:
            last_err = exc
            logger.warning(
                "reading validation failure user_id=%s attempt=%s: %s",
                user_id,
                attempt + 1,
                exc,
            )
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            logger.warning(
                "reading generation failure user_id=%s attempt=%s: %s",
                user_id,
                attempt + 1,
                exc,
            )

    if payload is None:
        reason = "llm_failure" if isinstance(last_err, LLMError) else "validation_failure"
        if last_err is not None and not isinstance(
            last_err, (LLMError, ReadingValidationError)
        ):
            reason = "generation_failure"
        logger.warning(
            "reading skip user_id=%s reason=%s after_retry detail=%s",
            user_id,
            reason,
            last_err,
        )
        return f"skipped_{reason}"

    message_text = texts.READING_DELIVERY.format(
        title=payload.title,
        body=payload.body,
    )

    async def _send() -> None:
        await bot.send_message(chat_id=user_id, text=message_text)

    try:
        await persist_and_send(
            user_id=user_id,
            local_date=day,
            topic=topic_row.topic,
            track=topic_row.track,
            cefr_level=user.cefr_level,
            payload=payload,
            send=_send,
        )
    except Exception:
        logger.exception(
            "reading send/persist failed user_id=%s — rolled back",
            user_id,
        )
        return "skipped_send_failed"

    increment_bot_messages(user_id, day)
    return "reading"
