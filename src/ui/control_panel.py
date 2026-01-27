"""Control panel UI components for voice channels."""

from typing import Any

import discord

from src.core.permissions import is_owner
from src.core.validators import validate_channel_name, validate_user_limit
from src.database.engine import async_session
from src.database.models import VoiceSession
from src.services.db_service import get_voice_session, update_voice_session


def create_control_panel_embed(
    session: VoiceSession, owner: discord.Member
) -> discord.Embed:
    """Create the control panel embed."""
    embed = discord.Embed(
        title="Voice Channel Controls",
        description=f"Owner: {owner.mention}",
        color=discord.Color.blue(),
    )

    lock_status = "Locked" if session.is_locked else "Unlocked"
    limit_status = str(session.user_limit) if session.user_limit > 0 else "Unlimited"

    embed.add_field(name="Status", value=lock_status, inline=True)
    embed.add_field(name="User Limit", value=limit_status, inline=True)

    return embed


# =============================================================================
# Modals
# =============================================================================


class RenameModal(discord.ui.Modal, title="Rename Channel"):
    """Modal for renaming the voice channel."""

    name: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="New Channel Name",
        placeholder="Enter new channel name...",
        min_length=1,
        max_length=100,
    )

    def __init__(self, session_id: int) -> None:
        super().__init__()
        self.session_id = session_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle modal submission."""
        new_name = str(self.name.value)

        if not validate_channel_name(new_name):
            await interaction.response.send_message(
                "Invalid channel name.", ephemeral=True
            )
            return

        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                await interaction.response.send_message(
                    "Session not found.", ephemeral=True
                )
                return

            if not is_owner(voice_session.owner_id, interaction.user.id):
                await interaction.response.send_message(
                    "Only the owner can rename this channel.", ephemeral=True
                )
                return

            channel = interaction.channel
            if isinstance(channel, discord.VoiceChannel):
                await channel.edit(name=new_name)

            await update_voice_session(db_session, voice_session, name=new_name)

        await interaction.response.send_message(
            f"Channel renamed to **{new_name}**.", ephemeral=True
        )


class UserLimitModal(discord.ui.Modal, title="Change User Limit"):
    """Modal for changing the user limit."""

    limit: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="User Limit (0-99, 0 = unlimited)",
        placeholder="Enter a number between 0 and 99...",
        min_length=1,
        max_length=2,
    )

    def __init__(self, session_id: int) -> None:
        super().__init__()
        self.session_id = session_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle modal submission."""
        try:
            new_limit = int(self.limit.value)
        except ValueError:
            await interaction.response.send_message(
                "Please enter a valid number.", ephemeral=True
            )
            return

        if not validate_user_limit(new_limit):
            await interaction.response.send_message(
                "Invalid user limit. Must be between 0 and 99.", ephemeral=True
            )
            return

        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                await interaction.response.send_message(
                    "Session not found.", ephemeral=True
                )
                return

            if not is_owner(voice_session.owner_id, interaction.user.id):
                await interaction.response.send_message(
                    "Only the owner can change the user limit.", ephemeral=True
                )
                return

            channel = interaction.channel
            if isinstance(channel, discord.VoiceChannel):
                await channel.edit(user_limit=new_limit)

            await update_voice_session(db_session, voice_session, user_limit=new_limit)

        limit_text = str(new_limit) if new_limit > 0 else "unlimited"
        await interaction.response.send_message(
            f"User limit set to **{limit_text}**.", ephemeral=True
        )


# =============================================================================
# Ephemeral Select Views (shown when button is clicked)
# =============================================================================


class TransferSelectView(discord.ui.View):
    """Ephemeral view with select for transferring ownership."""

    def __init__(
        self, channel: discord.VoiceChannel, owner_id: int
    ) -> None:
        super().__init__(timeout=60)
        members = [
            m for m in channel.members if m.id != owner_id
        ]
        if not members:
            return
        options = [
            discord.SelectOption(
                label=m.display_name, value=str(m.id)
            )
            for m in members[:25]
        ]
        self.add_item(TransferSelectMenu(options))


class TransferSelectMenu(discord.ui.Select[Any]):
    """Transfer ownership select menu."""

    def __init__(self, options: list[discord.SelectOption]) -> None:
        super().__init__(
            placeholder="Select new owner...", options=options
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle selection."""
        channel = interaction.channel
        if not isinstance(channel, discord.VoiceChannel):
            return

        guild = interaction.guild
        if not guild:
            return

        new_owner = guild.get_member(int(self.values[0]))
        if not new_owner:
            await interaction.response.edit_message(
                content="Member not found.", view=None
            )
            return

        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                await interaction.response.edit_message(
                    content="Session not found.", view=None
                )
                return

            if isinstance(interaction.user, discord.Member):
                await channel.set_permissions(
                    interaction.user,
                    read_message_history=None,
                )
            await channel.set_permissions(
                new_owner, read_message_history=True
            )

            await update_voice_session(
                db_session,
                voice_session,
                owner_id=str(new_owner.id),
            )

        await interaction.response.edit_message(
            content=f"Ownership transferred to {new_owner.mention}.",
            view=None,
        )


class KickSelectView(discord.ui.View):
    """Ephemeral view with user select for kicking."""

    def __init__(self) -> None:
        super().__init__(timeout=60)

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select user to kick...")
    async def select_user(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect[Any]
    ) -> None:
        """Handle user selection."""
        user_to_kick = select.values[0]
        channel = interaction.channel

        if not isinstance(channel, discord.VoiceChannel):
            return

        if not (
            isinstance(user_to_kick, discord.Member)
            and user_to_kick.voice
            and user_to_kick.voice.channel == channel
        ):
            await interaction.response.edit_message(
                content=f"{user_to_kick.mention} is not in this channel.", view=None
            )
            return

        await user_to_kick.move_to(None)
        await interaction.response.edit_message(
            content=f"{user_to_kick.mention} has been kicked.", view=None
        )


class BlockSelectView(discord.ui.View):
    """Ephemeral view with user select for blocking."""

    def __init__(self) -> None:
        super().__init__(timeout=60)

    @discord.ui.select(
        cls=discord.ui.UserSelect, placeholder="Select user to block..."
    )
    async def select_user(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect[Any]
    ) -> None:
        """Handle user selection."""
        user_to_block = select.values[0]
        channel = interaction.channel

        if not isinstance(channel, discord.VoiceChannel):
            return

        if not isinstance(user_to_block, discord.Member):
            return

        await channel.set_permissions(user_to_block, connect=False)

        if (
            isinstance(user_to_block, discord.Member)
            and user_to_block.voice
            and user_to_block.voice.channel == channel
        ):
            await user_to_block.move_to(None)

        await interaction.response.edit_message(
            content=f"{user_to_block.mention} has been blocked.", view=None
        )


class AllowSelectView(discord.ui.View):
    """Ephemeral view with user select for allowing."""

    def __init__(self) -> None:
        super().__init__(timeout=60)

    @discord.ui.select(
        cls=discord.ui.UserSelect, placeholder="Select user to allow..."
    )
    async def select_user(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect[Any]
    ) -> None:
        """Handle user selection."""
        user_to_allow = select.values[0]
        channel = interaction.channel

        if not isinstance(channel, discord.VoiceChannel):
            return

        if not isinstance(user_to_allow, discord.Member):
            return

        await channel.set_permissions(user_to_allow, connect=True)
        await interaction.response.edit_message(
            content=f"{user_to_allow.mention} has been allowed.", view=None
        )


class RegionSelectView(discord.ui.View):
    """Ephemeral view with region select."""

    REGIONS = [
        ("Automatic", "auto"),
        ("Japan", "japan"),
        ("Singapore", "singapore"),
        ("Hong Kong", "hongkong"),
        ("Sydney", "sydney"),
        ("India", "india"),
        ("US West", "us-west"),
        ("US East", "us-east"),
        ("US Central", "us-central"),
        ("US South", "us-south"),
        ("Europe", "europe"),
        ("Brazil", "brazil"),
        ("South Africa", "southafrica"),
        ("Russia", "russia"),
    ]

    def __init__(self) -> None:
        super().__init__(timeout=60)
        options = [
            discord.SelectOption(label=label, value=value)
            for label, value in self.REGIONS
        ]
        self.add_item(RegionSelectMenu(options))


class RegionSelectMenu(discord.ui.Select[Any]):
    """Region select menu."""

    def __init__(self, options: list[discord.SelectOption]) -> None:
        super().__init__(placeholder="Select region...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle selection."""
        selected = self.values[0]
        region = None if selected == "auto" else selected
        channel = interaction.channel

        if isinstance(channel, discord.VoiceChannel):
            await channel.edit(rtc_region=region)

        region_name = selected if selected != "auto" else "Automatic"
        await interaction.response.edit_message(
            content=f"Region changed to **{region_name}**.", view=None
        )


# =============================================================================
# Main Control Panel View
# =============================================================================


class ControlPanelView(discord.ui.View):
    """Main control panel view with buttons only."""

    def __init__(
        self, session_id: int, is_locked: bool = False, is_hidden: bool = False
    ) -> None:
        super().__init__(timeout=None)
        self.session_id = session_id

        if is_locked:
            self.lock_button.label = "Unlock"
            self.lock_button.emoji = "🔓"

        if is_hidden:
            self.hide_button.label = "Unhide"
            self.hide_button.emoji = "👁️"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the user is the owner before allowing any interaction."""
        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                await interaction.response.send_message(
                    "Session not found.", ephemeral=True
                )
                return False

            if not is_owner(voice_session.owner_id, interaction.user.id):
                await interaction.response.send_message(
                    "Only the channel owner can use this control panel.",
                    ephemeral=True,
                )
                return False

        return True

    # Row 0
    @discord.ui.button(
        label="Rename",
        emoji="🏷️",
        style=discord.ButtonStyle.secondary,
        custom_id="rename_button",
        row=0,
    )
    async def rename_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """Handle rename button click."""
        await interaction.response.send_modal(RenameModal(self.session_id))

    @discord.ui.button(
        label="Limit",
        emoji="👥",
        style=discord.ButtonStyle.secondary,
        custom_id="limit_button",
        row=0,
    )
    async def limit_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """Handle limit button click."""
        await interaction.response.send_modal(UserLimitModal(self.session_id))

    # Row 1
    @discord.ui.button(
        label="Lock",
        emoji="🔒",
        style=discord.ButtonStyle.secondary,
        custom_id="lock_button",
        row=1,
    )
    async def lock_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Handle lock/unlock button click."""
        channel = interaction.channel
        if not isinstance(channel, discord.VoiceChannel) or not interaction.guild:
            return

        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                return

            new_locked_state = not voice_session.is_locked

            if new_locked_state:
                await channel.set_permissions(
                    interaction.guild.default_role, connect=False
                )
                if isinstance(interaction.user, discord.Member):
                    await channel.set_permissions(
                        interaction.user,
                        connect=True,
                        speak=True,
                        stream=True,
                        move_members=True,
                        mute_members=True,
                        deafen_members=True,
                    )
                button.label = "Unlock"
                button.emoji = "🔓"
            else:
                await channel.set_permissions(
                    interaction.guild.default_role, overwrite=None
                )
                button.label = "Lock"
                button.emoji = "🔒"

            await update_voice_session(
                db_session, voice_session, is_locked=new_locked_state
            )

        status = "locked" if new_locked_state else "unlocked"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"Channel has been **{status}**.", ephemeral=True
        )

    @discord.ui.button(
        label="Region",
        emoji="🌏",
        style=discord.ButtonStyle.secondary,
        custom_id="region_button",
        row=1,
    )
    async def region_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """Handle region button click."""
        await interaction.response.send_message(
            "Select a region:", view=RegionSelectView(), ephemeral=True
        )

    @discord.ui.button(
        label="Hide",
        emoji="🙈",
        style=discord.ButtonStyle.secondary,
        custom_id="hide_button",
        row=1,
    )
    async def hide_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Handle hide/unhide button click."""
        channel = interaction.channel
        if not isinstance(channel, discord.VoiceChannel) or not interaction.guild:
            return

        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                return

            new_hidden_state = not voice_session.is_hidden

            if new_hidden_state:
                # Hide: deny @everyone view_channel, allow current members
                await channel.set_permissions(
                    interaction.guild.default_role, view_channel=False
                )
                # Allow all current members to see the channel
                for member in channel.members:
                    await channel.set_permissions(member, view_channel=True)
                button.label = "Unhide"
                button.emoji = "👁️"
            else:
                # Unhide: remove @everyone view_channel override
                await channel.set_permissions(
                    interaction.guild.default_role, view_channel=None
                )
                button.label = "Hide"
                button.emoji = "🙈"

            await update_voice_session(
                db_session, voice_session, is_hidden=new_hidden_state
            )

        status = "hidden" if new_hidden_state else "visible"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"Channel is now **{status}**.", ephemeral=True
        )

    # Row 2
    @discord.ui.button(
        label="Transfer",
        emoji="👑",
        style=discord.ButtonStyle.secondary,
        custom_id="transfer_button",
        row=2,
    )
    async def transfer_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """Handle transfer button click."""
        channel = interaction.channel
        if not isinstance(channel, discord.VoiceChannel):
            return

        view = TransferSelectView(channel, interaction.user.id)
        if not view.children:
            await interaction.response.send_message(
                "No other members in this channel.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Select new owner:", view=view, ephemeral=True
        )

    @discord.ui.button(
        label="Kick",
        emoji="👟",
        style=discord.ButtonStyle.secondary,
        custom_id="kick_button",
        row=2,
    )
    async def kick_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """Handle kick button click."""
        await interaction.response.send_message(
            "Select user to kick:", view=KickSelectView(), ephemeral=True
        )

    # Row 3
    @discord.ui.button(
        label="Block",
        emoji="🚫",
        style=discord.ButtonStyle.danger,
        custom_id="block_button",
        row=3,
    )
    async def block_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """Handle block button click."""
        await interaction.response.send_message(
            "Select user to block:", view=BlockSelectView(), ephemeral=True
        )

    @discord.ui.button(
        label="Allow",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="allow_button",
        row=3,
    )
    async def allow_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """Handle allow button click."""
        await interaction.response.send_message(
            "Select user to allow:", view=AllowSelectView(), ephemeral=True
        )
