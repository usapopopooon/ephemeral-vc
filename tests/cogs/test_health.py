"""Tests for HealthCog (heartbeat monitoring)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord.ext import commands

from src.cogs.health import HealthCog

# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _make_cog(*, latency: float = 0.05, guild_count: int = 3) -> HealthCog:
    """Create a HealthCog with a mock bot.

    Args:
        latency: Bot の WebSocket レイテンシ (秒)
        guild_count: Bot が参加しているサーバー数
    """
    bot = MagicMock(spec=commands.Bot)
    bot.latency = latency
    bot.guilds = [MagicMock()] * guild_count
    bot.wait_until_ready = AsyncMock()
    return HealthCog(bot)


# ---------------------------------------------------------------------------
# _build_embed テスト
# ---------------------------------------------------------------------------


class TestBuildEmbed:
    """Tests for _build_embed."""

    def test_healthy_embed_is_green(self) -> None:
        """200ms 未満のレイテンシは緑色の Embed を返す。"""
        cog = _make_cog()
        embed = cog._build_embed(
            status="Healthy",
            uptime_str="1h 0m 0s",
            latency_ms=50,
            guild_count=3,
        )
        assert embed.color == discord.Color.green()
        assert "Healthy" in (embed.title or "")

    def test_degraded_embed_is_yellow(self) -> None:
        """200〜500ms のレイテンシは黄色の Embed を返す。"""
        cog = _make_cog()
        embed = cog._build_embed(
            status="Degraded",
            uptime_str="0h 5m 0s",
            latency_ms=300,
            guild_count=1,
        )
        assert embed.color == discord.Color.yellow()

    def test_unhealthy_embed_is_red(self) -> None:
        """500ms 以上のレイテンシは赤色の Embed を返す。"""
        cog = _make_cog()
        embed = cog._build_embed(
            status="Unhealthy",
            uptime_str="0h 0m 10s",
            latency_ms=600,
            guild_count=0,
        )
        assert embed.color == discord.Color.red()

    def test_embed_has_required_fields(self) -> None:
        """Embed に Uptime, Latency, Guilds フィールドがある。"""
        cog = _make_cog()
        embed = cog._build_embed(
            status="Healthy",
            uptime_str="2h 30m 15s",
            latency_ms=100,
            guild_count=5,
        )
        field_names = [f.name for f in embed.fields]
        assert "Uptime" in field_names
        assert "Latency" in field_names
        assert "Guilds" in field_names

    def test_embed_has_footer_with_boot_time(self) -> None:
        """Embed のフッターに Boot 時刻が含まれる。"""
        cog = _make_cog()
        embed = cog._build_embed(
            status="Healthy",
            uptime_str="0h 0m 0s",
            latency_ms=10,
            guild_count=1,
        )
        assert embed.footer is not None
        assert "Boot" in (embed.footer.text or "")


# ---------------------------------------------------------------------------
# _heartbeat テスト
# ---------------------------------------------------------------------------


class TestHeartbeat:
    """Tests for _heartbeat loop body."""

    async def test_sends_embed_when_channel_configured(self) -> None:
        """health_channel_id が設定されていれば Embed を送信する。"""
        cog = _make_cog(latency=0.1, guild_count=2)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        cog.bot.get_channel = MagicMock(return_value=mock_channel)

        with patch("src.cogs.health.settings") as mock_settings:
            mock_settings.health_channel_id = 12345
            await cog._heartbeat()  # type: ignore[misc]

            mock_channel.send.assert_awaited_once()
            kwargs = mock_channel.send.call_args[1]
            assert isinstance(kwargs["embed"], discord.Embed)

    async def test_skips_send_when_channel_not_configured(self) -> None:
        """health_channel_id が 0 なら送信しない。"""
        cog = _make_cog()

        cog.bot.get_channel = MagicMock(return_value=None)

        with patch("src.cogs.health.settings") as mock_settings:
            mock_settings.health_channel_id = 0
            await cog._heartbeat()  # type: ignore[misc]

            cog.bot.get_channel.assert_not_called()

    async def test_skips_send_when_channel_not_found(self) -> None:
        """チャンネルが見つからない場合は送信しない。"""
        cog = _make_cog()

        cog.bot.get_channel = MagicMock(return_value=None)

        with patch("src.cogs.health.settings") as mock_settings:
            mock_settings.health_channel_id = 99999
            await cog._heartbeat()  # type: ignore[misc]

            cog.bot.get_channel.assert_called_once_with(99999)

    async def test_skips_non_text_channel(self) -> None:
        """テキストチャンネル以外には送信しない。"""
        cog = _make_cog()

        voice_channel = MagicMock(spec=discord.VoiceChannel)
        voice_channel.send = AsyncMock()
        cog.bot.get_channel = MagicMock(return_value=voice_channel)

        with patch("src.cogs.health.settings") as mock_settings:
            mock_settings.health_channel_id = 12345
            await cog._heartbeat()  # type: ignore[misc]

            # VoiceChannel なので send は呼ばれない
            voice_channel.send.assert_not_awaited()

    async def test_status_healthy_under_200ms(self) -> None:
        """200ms 未満は Healthy ステータス。"""
        cog = _make_cog(latency=0.1)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        cog.bot.get_channel = MagicMock(return_value=mock_channel)

        with patch("src.cogs.health.settings") as mock_settings:
            mock_settings.health_channel_id = 1
            await cog._heartbeat()  # type: ignore[misc]

            embed = mock_channel.send.call_args[1]["embed"]
            assert "Healthy" in (embed.title or "")

    async def test_status_degraded_200_to_500ms(self) -> None:
        """200〜500ms は Degraded ステータス。"""
        cog = _make_cog(latency=0.3)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        cog.bot.get_channel = MagicMock(return_value=mock_channel)

        with patch("src.cogs.health.settings") as mock_settings:
            mock_settings.health_channel_id = 1
            await cog._heartbeat()  # type: ignore[misc]

            embed = mock_channel.send.call_args[1]["embed"]
            assert "Degraded" in (embed.title or "")

    async def test_status_unhealthy_over_500ms(self) -> None:
        """500ms 以上は Unhealthy ステータス。"""
        cog = _make_cog(latency=0.6)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        cog.bot.get_channel = MagicMock(return_value=mock_channel)

        with patch("src.cogs.health.settings") as mock_settings:
            mock_settings.health_channel_id = 1
            await cog._heartbeat()  # type: ignore[misc]

            embed = mock_channel.send.call_args[1]["embed"]
            assert "Unhealthy" in (embed.title or "")


# ---------------------------------------------------------------------------
# cog_load / cog_unload テスト
# ---------------------------------------------------------------------------


class TestCogLifecycle:
    """Tests for cog_load and cog_unload."""

    async def test_cog_load_starts_heartbeat(self) -> None:
        """cog_load でハートビートループが開始される。"""
        cog = _make_cog()
        with patch.object(cog._heartbeat, "start") as mock_start:
            await cog.cog_load()
            mock_start.assert_called_once()

    async def test_cog_unload_cancels_heartbeat(self) -> None:
        """cog_unload でハートビートループが停止される。"""
        cog = _make_cog()
        with patch.object(cog._heartbeat, "cancel") as mock_cancel:
            await cog.cog_unload()
            mock_cancel.assert_called_once()
