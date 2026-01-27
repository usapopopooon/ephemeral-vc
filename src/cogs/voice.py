"""Voice channel event handlers."""

from __future__ import annotations

import contextlib
import time

import discord
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.engine import async_session
from src.database.models import VoiceSession
from src.services.db_service import (
    create_voice_session,
    delete_voice_session,
    get_lobby_by_channel_id,
    get_voice_session,
    update_voice_session,
)
from src.ui.control_panel import ControlPanelView, create_control_panel_embed

# Default voice region for new channels
DEFAULT_RTC_REGION = "japan"


class VoiceCog(commands.Cog):
    """Cog for voice channel management."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Track when members join ephemeral channels: {channel_id: {user_id: timestamp}}
        self._join_times: dict[int, dict[int, float]] = {}

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Handle voice state updates."""
        # Handle join (lobby creation + join tracking)
        if (
            after.channel
            and after.channel != before.channel
            and isinstance(after.channel, discord.VoiceChannel)
        ):
            await self._handle_lobby_join(member, after.channel)
            self._record_join(after.channel.id, member.id)

        # Handle ephemeral channel leave
        if (
            before.channel
            and before.channel != after.channel
            and isinstance(before.channel, discord.VoiceChannel)
        ):
            self._remove_join(before.channel.id, member.id)
            await self._handle_channel_leave(member, before.channel)

    def _record_join(self, channel_id: int, user_id: int) -> None:
        """Record when a member joins a channel."""
        channel_times = self._join_times.setdefault(channel_id, {})
        channel_times.setdefault(user_id, time.monotonic())

    def _remove_join(self, channel_id: int, user_id: int) -> None:
        """Remove a member's join record."""
        if channel_id in self._join_times:
            self._join_times[channel_id].pop(user_id, None)

    def _cleanup_channel(self, channel_id: int) -> None:
        """Clean up all join records for a channel."""
        self._join_times.pop(channel_id, None)

    def _get_longest_member(
        self, channel: discord.VoiceChannel, exclude_id: int
    ) -> discord.Member | None:
        """Get the member who has been in the channel the longest."""
        records = self._join_times.get(channel.id, {})
        remaining = [m for m in channel.members if m.id != exclude_id]
        if not remaining:
            return None
        # Sort by join time (earliest first), fallback to first member
        remaining.sort(key=lambda m: records.get(m.id, float("inf")))
        return remaining[0]

    async def _handle_lobby_join(
        self, member: discord.Member, channel: discord.VoiceChannel
    ) -> None:
        """Handle a member joining a lobby channel."""
        async with async_session() as session:
            lobby = await get_lobby_by_channel_id(
                session, str(channel.id)
            )
            if not lobby:
                return

            guild = member.guild

            # Determine category
            category = None
            if lobby.category_id:
                category = guild.get_channel(int(lobby.category_id))
                if not isinstance(category, discord.CategoryChannel):
                    category = channel.category
            else:
                category = channel.category

            # Create voice channel
            channel_name = f"{member.display_name}'s channel"
            new_channel = await guild.create_voice_channel(
                name=channel_name,
                category=category,
                user_limit=lobby.default_user_limit,
                rtc_region=DEFAULT_RTC_REGION,
            )

            # Create database record
            try:
                voice_session = await create_voice_session(
                    session,
                    lobby_id=lobby.id,
                    channel_id=str(new_channel.id),
                    owner_id=str(member.id),
                    name=channel_name,
                    user_limit=lobby.default_user_limit,
                )
            except Exception:
                await new_channel.delete()
                raise

            # Set text chat permissions: only owner can read
            await new_channel.set_permissions(
                guild.default_role, read_message_history=False
            )
            await new_channel.set_permissions(
                member, read_message_history=True
            )

            # Move member to new channel
            try:
                await member.move_to(new_channel)
            except discord.HTTPException:
                await new_channel.delete()
                await delete_voice_session(
                    session, str(new_channel.id)
                )
                return

            # Send control panel
            embed = create_control_panel_embed(voice_session, member)
            view = ControlPanelView(
                voice_session.id,
                voice_session.is_locked,
                voice_session.is_hidden,
            )
            self.bot.add_view(view)
            await new_channel.send(embed=embed, view=view)

    async def _handle_channel_leave(
        self, member: discord.Member, channel: discord.VoiceChannel
    ) -> None:
        """Handle a member leaving a channel."""
        async with async_session() as session:
            voice_session = await get_voice_session(
                session, str(channel.id)
            )
            if not voice_session:
                return  # Not an ephemeral channel

            # If channel is empty, delete it
            if len(channel.members) == 0:
                self._cleanup_channel(channel.id)
                with contextlib.suppress(discord.HTTPException):
                    await channel.delete(
                        reason="Ephemeral VC: All members left"
                    )
                await delete_voice_session(session, str(channel.id))
                return

            # If the owner left, transfer to longest-staying member
            if voice_session.owner_id == str(member.id):
                await self._transfer_ownership(
                    session, voice_session, member, channel
                )

    async def _transfer_ownership(
        self,
        session: AsyncSession,
        voice_session: VoiceSession,
        old_owner: discord.Member,
        channel: discord.VoiceChannel,
    ) -> None:
        """Transfer ownership to the longest-staying member."""
        new_owner = self._get_longest_member(channel, old_owner.id)
        if not new_owner:
            return

        # Update DB
        await update_voice_session(
            session, voice_session, owner_id=str(new_owner.id)
        )

        # Update text chat permissions
        with contextlib.suppress(discord.HTTPException):
            await channel.set_permissions(
                old_owner, read_message_history=None
            )
            await channel.set_permissions(
                new_owner, read_message_history=True
            )

        # Update control panel embed
        embed = create_control_panel_embed(voice_session, new_owner)
        async for msg in channel.history(limit=20):
            if msg.author == self.bot.user and msg.embeds:
                with contextlib.suppress(discord.HTTPException):
                    await msg.edit(embed=embed)
                break

        # Notify the channel
        with contextlib.suppress(discord.HTTPException):
            await channel.send(
                f"オーナーが退出したため、"
                f"{new_owner.mention} に引き継ぎました。"
            )


async def setup(bot: commands.Bot) -> None:
    """Setup function for loading the cog."""
    await bot.add_cog(VoiceCog(bot))
