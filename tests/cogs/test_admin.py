"""Tests for AdminCog."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord

from src.cogs.admin import AdminCog

# ---------------------------------------------------------------------------
# setup 関数テスト
# ---------------------------------------------------------------------------


class TestSetup:
    """Tests for setup function."""

    async def test_setup_adds_cog(self) -> None:
        """setup() が Bot に AdminCog を追加する。"""
        from src.cogs.admin import setup

        bot = MagicMock(spec=discord.ext.commands.Bot)
        bot.add_cog = AsyncMock()

        await setup(bot)

        bot.add_cog.assert_awaited_once()
        cog = bot.add_cog.call_args[0][0]
        assert isinstance(cog, AdminCog)
