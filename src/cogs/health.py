"""Health monitoring cog for sending periodic heartbeat embeds."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

from src.config import settings

logger = logging.getLogger(__name__)

# Heartbeat interval in minutes
_HEARTBEAT_MINUTES = 10
_JST = timezone(timedelta(hours=9))


class HealthCog(commands.Cog):
    """Sends periodic health-check embeds to a designated channel."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._start_time = time.monotonic()
        self._boot_jst = datetime.now(_JST)

    async def cog_load(self) -> None:
        """Start the heartbeat loop when the cog is loaded."""
        self._heartbeat.start()

    async def cog_unload(self) -> None:
        """Cancel the heartbeat loop when the cog is unloaded."""
        self._heartbeat.cancel()

    # ------------------------------------------------------------------
    # Heartbeat loop
    # ------------------------------------------------------------------

    @tasks.loop(minutes=_HEARTBEAT_MINUTES)
    async def _heartbeat(self) -> None:
        uptime_sec = int(time.monotonic() - self._start_time)
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        guild_count = len(self.bot.guilds)
        latency_ms = round(self.bot.latency * 1000)

        if latency_ms < 200:
            status = "Healthy"
        elif latency_ms < 500:
            status = "Degraded"
        else:
            status = "Unhealthy"

        logger.info(
            "[Heartbeat] %s | uptime=%s latency=%dms guilds=%d",
            status, uptime_str, latency_ms, guild_count,
        )

        # Optionally send embed to Discord channel
        if settings.health_channel_id:
            channel = self.bot.get_channel(settings.health_channel_id)
            if channel is not None and isinstance(channel, discord.TextChannel):
                embed = self._build_embed(
                    status=status,
                    uptime_str=uptime_str,
                    latency_ms=latency_ms,
                    guild_count=guild_count,
                )
                await channel.send(embed=embed)

    @_heartbeat.before_loop
    async def _before_heartbeat(self) -> None:
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Embed builder
    # ------------------------------------------------------------------

    def _build_embed(
        self,
        *,
        status: str,
        uptime_str: str,
        latency_ms: int,
        guild_count: int,
    ) -> discord.Embed:
        if latency_ms < 200:
            color = discord.Color.green()
        elif latency_ms < 500:
            color = discord.Color.yellow()
        else:
            color = discord.Color.red()

        embed = discord.Embed(
            title=f"Heartbeat — {status}",
            color=color,
            timestamp=datetime.now(_JST),
        )
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(name="Latency", value=f"{latency_ms}ms", inline=True)
        embed.add_field(name="Guilds", value=str(guild_count), inline=True)
        embed.set_footer(text=f"Boot: {self._boot_jst:%Y-%m-%d %H:%M JST}")
        return embed


async def setup(bot: commands.Bot) -> None:
    """Register the HealthCog."""
    await bot.add_cog(HealthCog(bot))
