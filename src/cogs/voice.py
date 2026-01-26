"""Voice channel event handlers."""

import contextlib

import discord
from discord.ext import commands

from src.database.engine import async_session
from src.services.db_service import (
    create_voice_session,
    delete_voice_session,
    get_lobby_by_channel_id,
    get_voice_session,
)
from src.ui.control_panel import ControlPanelView, create_control_panel_embed

# Default voice region for new channels
DEFAULT_RTC_REGION = "japan"


class VoiceCog(commands.Cog):
    """Cog for voice channel management."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Handle voice state updates."""
        # Handle lobby join (only VoiceChannel, not StageChannel)
        if (
            after.channel
            and after.channel != before.channel
            and isinstance(after.channel, discord.VoiceChannel)
        ):
            await self._handle_lobby_join(member, after.channel)

        # Handle ephemeral channel leave (check if empty)
        if (
            before.channel
            and before.channel != after.channel
            and isinstance(before.channel, discord.VoiceChannel)
        ):
            await self._handle_channel_leave(before.channel)

    async def _handle_lobby_join(
        self, member: discord.Member, channel: discord.VoiceChannel
    ) -> None:
        """Handle a member joining a lobby channel."""
        print(f"_handle_lobby_join called: {member} joined {channel.name} (ID: {channel.id})")
        async with async_session() as session:
            lobby = await get_lobby_by_channel_id(session, str(channel.id))
            print(f"Lobby lookup result: {lobby}")
            if not lobby:
                print(f"Channel {channel.id} is not a registered lobby")
                return  # Not a lobby channel

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
            channel_name = "new-channel"
            new_channel = await guild.create_voice_channel(
                name=channel_name,
                category=category,
                user_limit=lobby.default_user_limit,
                rtc_region=DEFAULT_RTC_REGION,
            )

            # Create database record
            voice_session = await create_voice_session(
                session,
                lobby_id=lobby.id,
                channel_id=str(new_channel.id),
                owner_id=str(member.id),
                name=channel_name,
                user_limit=lobby.default_user_limit,
            )

            # Set text chat permissions: only owner can read messages
            await new_channel.set_permissions(
                guild.default_role, read_message_history=False
            )
            await new_channel.set_permissions(
                member, read_message_history=True
            )

            # Move member to new channel
            try:
                await member.move_to(new_channel)
                print(f"Moved {member} to {new_channel.name}")
            except discord.HTTPException as e:
                # Failed to move, clean up
                print(f"Failed to move {member}: {e}")
                await new_channel.delete()
                await delete_voice_session(session, str(new_channel.id))
                return

            # Send control panel to the channel's text chat
            embed = create_control_panel_embed(voice_session, member)
            view = ControlPanelView(
                voice_session.id, voice_session.is_locked, voice_session.is_hidden
            )
            self.bot.add_view(view)

            await new_channel.send(embed=embed, view=view)

    async def _handle_channel_leave(self, channel: discord.VoiceChannel) -> None:
        """Handle a member leaving a channel - delete if empty."""
        # Check if channel is empty
        if len(channel.members) > 0:
            return

        async with async_session() as session:
            voice_session = await get_voice_session(session, str(channel.id))
            if not voice_session:
                return  # Not an ephemeral channel

            # Delete the channel (may already be deleted)
            with contextlib.suppress(discord.HTTPException):
                await channel.delete(reason="Ephemeral VC: All members left")

            # Delete database record
            await delete_voice_session(session, str(channel.id))


async def setup(bot: commands.Bot) -> None:
    """Setup function for loading the cog."""
    await bot.add_cog(VoiceCog(bot))
