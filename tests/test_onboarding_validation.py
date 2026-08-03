"""Bad-input paths for S1b onboarding: in-place re-render, no advance, no crash.

Adapted from S1: free-text now lands in NAME_OTHER / EFSET_SCORE / MORNING_OTHER
and invalid input edits the wizard message (never a separate error bubble).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from telegram.error import BadRequest

from app import texts
from app.handlers import onboarding as ob


def _text_update(text: str) -> MagicMock:
    update = MagicMock()
    update.message = AsyncMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.effective_message = update.message
    update.effective_user = MagicMock(id=1)
    update.callback_query = None
    return update


def _context(*, wizard: bool = True) -> MagicMock:
    context = MagicMock()
    context.user_data = {
        "onboarding": {},
        "wizard_state": ob.NAME,
    }
    if wizard:
        context.user_data["wizard_message_id"] = 42
        context.user_data["wizard_chat_id"] = 7
    context.bot = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    context.application.bot_data = {}
    return context


def test_name_other_single_space_reasks_and_stays() -> None:
    async def run() -> None:
        update = _text_update(" ")
        context = _context()
        context.user_data["wizard_state"] = ob.NAME_OTHER
        state = await ob.receive_name_other(update, context)
        assert state == ob.NAME_OTHER
        context.bot.edit_message_text.assert_awaited()
        args_kwargs = context.bot.edit_message_text.await_args
        text = args_kwargs.kwargs.get("text") or args_kwargs.args[0]
        assert texts.ONBOARD_INVALID_NAME in text
        assert "name" not in context.user_data.get("onboarding", {})
        update.message.reply_text.assert_not_awaited()

    asyncio.run(run())


def test_efset_score_abc_and_150_reask_and_stay() -> None:
    async def run() -> None:
        context = _context()
        context.user_data["wizard_state"] = ob.EFSET_SCORE
        for bad in ("abc", "150"):
            context.bot.edit_message_text.reset_mock()
            update = _text_update(bad)
            state = await ob.receive_efset_score(update, context)
            assert state == ob.EFSET_SCORE, bad
            context.bot.edit_message_text.assert_awaited()
            args_kwargs = context.bot.edit_message_text.await_args
            text = args_kwargs.kwargs.get("text") or args_kwargs.args[0]
            assert texts.ONBOARD_INVALID_EFSET in text
            assert context.user_data.get("onboarding", {}).get("efset_baseline") is None
            assert context.user_data.get("onboarding", {}).get("cefr_level") is None
            update.message.reply_text.assert_not_awaited()

    asyncio.run(run())


def test_morning_other_25_00_and_8pm_reask_and_stay() -> None:
    async def run() -> None:
        context = _context()
        context.user_data["wizard_state"] = ob.MORNING_OTHER
        for bad in ("25:00", "8pm"):
            context.bot.edit_message_text.reset_mock()
            update = _text_update(bad)
            state = await ob.receive_morning_other(update, context)
            assert state == ob.MORNING_OTHER, bad
            context.bot.edit_message_text.assert_awaited()
            args_kwargs = context.bot.edit_message_text.await_args
            text = args_kwargs.kwargs.get("text") or args_kwargs.args[0]
            assert texts.ONBOARD_INVALID_TIME in text
            assert "morning_time" not in context.user_data.get("onboarding", {})
            update.message.reply_text.assert_not_awaited()

    asyncio.run(run())


def test_edit_ignores_message_not_modified() -> None:
    async def run() -> None:
        context = _context()
        context.bot.edit_message_text = AsyncMock(
            side_effect=BadRequest("Message is not modified: specified new message content and reply markup are exactly the same")
        )
        await ob._safe_edit_message_text(
            context,
            chat_id=7,
            message_id=42,
            text="same",
            reply_markup=None,
        )

    asyncio.run(run())
