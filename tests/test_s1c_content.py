"""S1c content checks: self-assessment CEFR mapping and domain drill-down table."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from apps.bot import texts
from apps.bot.handlers import onboarding as ob
from apps.bot.handlers.onboarding import self_assess_to_cefr


def test_self_assess_maps_to_cefr_and_efset_stays_null() -> None:
    expected = {"a2": "A2", "b1": "B1", "b2": "B2"}
    for key, cefr in expected.items():
        assert self_assess_to_cefr(key) == cefr

    async def run() -> None:
        for key, cefr in expected.items():
            update = MagicMock()
            update.callback_query = AsyncMock()
            update.callback_query.data = f"wiz:level:{key}"
            update.callback_query.answer = AsyncMock()
            update.effective_message = MagicMock()
            context = MagicMock()
            context.user_data = {
                "onboarding": {"efset_baseline": None},
                "wizard_message_id": 1,
                "wizard_chat_id": 1,
                "wizard_state": ob.LEVEL,
            }
            context.bot = MagicMock()
            context.bot.edit_message_text = AsyncMock()
            state = await ob.wizard_callback(update, context)
            assert state == ob.DOMAIN
            answers = context.user_data["onboarding"]
            assert answers["cefr_level"] == cefr
            assert answers["efset_baseline"] is None

    asyncio.run(run())


def test_domain_drilldown_min_four_specifics_and_label_width() -> None:
    category_keys = {key for key, _label in texts.DOMAIN_CATEGORIES}
    assert category_keys == set(texts.DOMAIN_SPECIFICS.keys())
    for cat, specifics in texts.DOMAIN_SPECIFICS.items():
        assert len(specifics) >= 4, f"{cat} has fewer than 4 specifics"
        for _key, label in specifics:
            assert len(label) <= 20, f"{cat}/{label!r} exceeds 20 chars ({len(label)})"
