"""Bad-input paths for S1 onboarding: polite re-ask, no advance, no crash."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app import texts
from app.handlers import onboarding as ob


def _text_update(text: str) -> MagicMock:
    update = MagicMock()
    update.message = AsyncMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock(id=1)
    update.effective_message = update.message
    update.callback_query = None
    return update


def _context() -> MagicMock:
    context = MagicMock()
    context.user_data = {}
    context.application.bot_data = {}
    return context


def test_name_single_space_reasks_and_stays() -> None:
    async def run() -> None:
        update = _text_update(" ")
        context = _context()
        state = await ob.receive_name(update, context)
        assert state == ob.NAME
        update.message.reply_text.assert_awaited_once_with(texts.ONBOARD_INVALID_NAME)
        assert "name" not in context.user_data.get("onboarding", {})

    asyncio.run(run())


def test_efset_abc_and_150_reask_and_stay() -> None:
    async def run() -> None:
        context = _context()
        for bad in ("abc", "150"):
            update = _text_update(bad)
            state = await ob.receive_efset_text(update, context)
            assert state == ob.EFSET, bad
            update.message.reply_text.assert_awaited()
            args, kwargs = update.message.reply_text.await_args
            assert args[0] == texts.ONBOARD_INVALID_EFSET
            assert "reply_markup" in kwargs
            assert context.user_data.get("onboarding", {}).get("efset_baseline") is None
            assert context.user_data.get("onboarding", {}).get("cefr_level") is None

    asyncio.run(run())


def test_morning_other_25_00_and_8pm_reask_and_stay() -> None:
    async def run() -> None:
        context = _context()
        for bad in ("25:00", "8pm"):
            update = _text_update(bad)
            state = await ob.receive_morning_other(update, context)
            assert state == ob.MORNING_OTHER, bad
            update.message.reply_text.assert_awaited_once_with(texts.ONBOARD_INVALID_TIME)
            assert "morning_time" not in context.user_data.get("onboarding", {})

    asyncio.run(run())
