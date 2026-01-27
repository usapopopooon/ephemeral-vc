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
        title="ボイスチャンネル設定",
        description=f"オーナー: {owner.mention}",
        color=discord.Color.blue(),
    )

    lock_status = "ロック中" if session.is_locked else "未ロック"
    limit_status = str(session.user_limit) if session.user_limit > 0 else "無制限"

    embed.add_field(name="状態", value=lock_status, inline=True)
    embed.add_field(name="人数制限", value=limit_status, inline=True)

    return embed


# =============================================================================
# Modals
# =============================================================================


class RenameModal(discord.ui.Modal, title="チャンネル名変更"):
    """Modal for renaming the voice channel."""

    name: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="新しいチャンネル名",
        placeholder="チャンネル名を入力...",
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
                "無効なチャンネル名です。", ephemeral=True
            )
            return

        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                await interaction.response.send_message(
                    "セッションが見つかりません。", ephemeral=True
                )
                return

            if not is_owner(voice_session.owner_id, interaction.user.id):
                await interaction.response.send_message(
                    "オーナーのみチャンネル名を変更できます。", ephemeral=True
                )
                return

            channel = interaction.channel
            if isinstance(channel, discord.VoiceChannel):
                await channel.edit(name=new_name)

            await update_voice_session(db_session, voice_session, name=new_name)

        await interaction.response.send_message(
            f"チャンネル名を **{new_name}** に変更しました。", ephemeral=True
        )


class UserLimitModal(discord.ui.Modal, title="人数制限変更"):
    """Modal for changing the user limit."""

    limit: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="人数制限 (0〜99、0 = 無制限)",
        placeholder="0〜99の数字を入力...",
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
                "有効な数字を入力してください。", ephemeral=True
            )
            return

        if not validate_user_limit(new_limit):
            await interaction.response.send_message(
                "無効な人数制限です。0〜99の範囲で入力してください。",
                ephemeral=True,
            )
            return

        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                await interaction.response.send_message(
                    "セッションが見つかりません。", ephemeral=True
                )
                return

            if not is_owner(voice_session.owner_id, interaction.user.id):
                await interaction.response.send_message(
                    "オーナーのみ人数制限を変更できます。", ephemeral=True
                )
                return

            channel = interaction.channel
            if isinstance(channel, discord.VoiceChannel):
                await channel.edit(user_limit=new_limit)

            await update_voice_session(db_session, voice_session, user_limit=new_limit)

        limit_text = str(new_limit) if new_limit > 0 else "無制限"
        await interaction.response.send_message(
            f"人数制限を **{limit_text}** に設定しました。", ephemeral=True
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
            placeholder="新しいオーナーを選択...", options=options
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
                content="メンバーが見つかりません。", view=None
            )
            return

        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                await interaction.response.edit_message(
                    content="セッションが見つかりません。", view=None
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
            content=f"{new_owner.mention} にオーナーを譲渡しました。",
            view=None,
        )


class KickSelectView(discord.ui.View):
    """Ephemeral view with user select for kicking."""

    def __init__(self) -> None:
        super().__init__(timeout=60)

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="キックするユーザーを選択...",
    )
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
                content=f"{user_to_kick.mention} はこのチャンネルにいません。",
                view=None,
            )
            return

        await user_to_kick.move_to(None)
        await interaction.response.edit_message(
            content=f"{user_to_kick.mention} をキックしました。", view=None
        )


class BlockSelectView(discord.ui.View):
    """Ephemeral view with user select for blocking."""

    def __init__(self) -> None:
        super().__init__(timeout=60)

    @discord.ui.select(
        cls=discord.ui.UserSelect, placeholder="ブロックするユーザーを選択..."
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
            content=f"{user_to_block.mention} をブロックしました。", view=None
        )


class AllowSelectView(discord.ui.View):
    """Ephemeral view with user select for allowing."""

    def __init__(self) -> None:
        super().__init__(timeout=60)

    @discord.ui.select(
        cls=discord.ui.UserSelect, placeholder="許可するユーザーを選択..."
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
            content=f"{user_to_allow.mention} を許可しました。", view=None
        )


class BitrateSelectView(discord.ui.View):
    """Ephemeral view with bitrate select."""

    BITRATES = [
        ("8 kbps", "8000"),
        ("16 kbps", "16000"),
        ("32 kbps", "32000"),
        ("64 kbps", "64000"),
        ("96 kbps", "96000"),
        ("128 kbps", "128000"),
        ("256 kbps", "256000"),
        ("384 kbps", "384000"),
    ]

    def __init__(self) -> None:
        super().__init__(timeout=60)
        options = [
            discord.SelectOption(label=label, value=value)
            for label, value in self.BITRATES
        ]
        self.add_item(BitrateSelectMenu(options))


class BitrateSelectMenu(discord.ui.Select[Any]):
    """Bitrate select menu."""

    def __init__(self, options: list[discord.SelectOption]) -> None:
        super().__init__(
            placeholder="ビットレートを選択...", options=options
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle selection."""
        bitrate = int(self.values[0])
        channel = interaction.channel

        if isinstance(channel, discord.VoiceChannel):
            try:
                await channel.edit(bitrate=bitrate)
            except discord.HTTPException:
                await interaction.response.edit_message(
                    content="このサーバーのブーストレベルでは"
                    "利用できないビットレートです。",
                    view=None,
                )
                return

        label = f"{bitrate // 1000} kbps"
        await interaction.response.edit_message(
            content=f"ビットレートを **{label}** に変更しました。",
            view=None,
        )


class RegionSelectView(discord.ui.View):
    """Ephemeral view with region select."""

    REGIONS = [
        ("自動", "auto"),
        ("日本", "japan"),
        ("シンガポール", "singapore"),
        ("香港", "hongkong"),
        ("シドニー", "sydney"),
        ("インド", "india"),
        ("米国西部", "us-west"),
        ("米国東部", "us-east"),
        ("米国中部", "us-central"),
        ("米国南部", "us-south"),
        ("ヨーロッパ", "europe"),
        ("ブラジル", "brazil"),
        ("南アフリカ", "southafrica"),
        ("ロシア", "russia"),
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
        super().__init__(placeholder="リージョンを選択...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle selection."""
        selected = self.values[0]
        region = None if selected == "auto" else selected
        channel = interaction.channel

        if isinstance(channel, discord.VoiceChannel):
            await channel.edit(rtc_region=region)

        region_name = selected if selected != "auto" else "自動"
        await interaction.response.edit_message(
            content=f"リージョンを **{region_name}** に変更しました。",
            view=None,
        )


# =============================================================================
# Main Control Panel View
# =============================================================================


class ControlPanelView(discord.ui.View):
    """Main control panel view with buttons only."""

    def __init__(
        self,
        session_id: int,
        is_locked: bool = False,
        is_hidden: bool = False,
        is_nsfw: bool = False,
    ) -> None:
        super().__init__(timeout=None)
        self.session_id = session_id

        if is_locked:
            self.lock_button.label = "解除"
            self.lock_button.emoji = "🔓"

        if is_hidden:
            self.hide_button.label = "表示"
            self.hide_button.emoji = "👁️"

        if is_nsfw:
            self.nsfw_button.label = "制限解除"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the user is the owner before allowing any interaction."""
        async with async_session() as db_session:
            voice_session = await get_voice_session(
                db_session, str(interaction.channel_id)
            )
            if not voice_session:
                await interaction.response.send_message(
                    "セッションが見つかりません。", ephemeral=True
                )
                return False

            if not is_owner(voice_session.owner_id, interaction.user.id):
                await interaction.response.send_message(
                    "チャンネルオーナーのみ操作できます。",
                    ephemeral=True,
                )
                return False

        return True

    # Row 0: チャンネル設定①
    @discord.ui.button(
        label="名前変更",
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
        label="人数制限",
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

    # Row 1: チャンネル設定②
    @discord.ui.button(
        label="ビットレート",
        emoji="🔊",
        style=discord.ButtonStyle.secondary,
        custom_id="bitrate_button",
        row=1,
    )
    async def bitrate_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """Handle bitrate button click."""
        await interaction.response.send_message(
            "ビットレートを選択:",
            view=BitrateSelectView(),
            ephemeral=True,
        )

    @discord.ui.button(
        label="リージョン",
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
            "リージョンを選択:", view=RegionSelectView(), ephemeral=True
        )

    # Row 2: 状態トグル
    @discord.ui.button(
        label="ロック",
        emoji="🔒",
        style=discord.ButtonStyle.secondary,
        custom_id="lock_button",
        row=2,
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
                button.label = "解除"
                button.emoji = "🔓"
            else:
                await channel.set_permissions(
                    interaction.guild.default_role, overwrite=None
                )
                button.label = "ロック"
                button.emoji = "🔒"

            await update_voice_session(
                db_session, voice_session, is_locked=new_locked_state
            )

        status = "ロック" if new_locked_state else "ロック解除"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"チャンネルを **{status}** しました。", ephemeral=True
        )

    @discord.ui.button(
        label="非表示",
        emoji="🙈",
        style=discord.ButtonStyle.secondary,
        custom_id="hide_button",
        row=2,
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
                button.label = "表示"
                button.emoji = "👁️"
            else:
                # Unhide: remove @everyone view_channel override
                await channel.set_permissions(
                    interaction.guild.default_role, view_channel=None
                )
                button.label = "非表示"
                button.emoji = "🙈"

            await update_voice_session(
                db_session, voice_session, is_hidden=new_hidden_state
            )

        status = "非表示" if new_hidden_state else "表示"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"チャンネルを **{status}** にしました。", ephemeral=True
        )

    @discord.ui.button(
        label="年齢制限",
        emoji="🔞",
        style=discord.ButtonStyle.secondary,
        custom_id="nsfw_button",
        row=2,
    )
    async def nsfw_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Handle NSFW toggle button click."""
        channel = interaction.channel
        if not isinstance(channel, discord.VoiceChannel):
            return

        new_nsfw = not channel.nsfw

        await channel.edit(nsfw=new_nsfw)

        if new_nsfw:
            button.label = "制限解除"
        else:
            button.label = "年齢制限"

        await interaction.response.edit_message(view=self)
        status = "年齢制限を設定" if new_nsfw else "年齢制限を解除"
        await interaction.followup.send(
            f"チャンネルの **{status}** しました。", ephemeral=True
        )

    # Row 3: メンバー管理①
    @discord.ui.button(
        label="譲渡",
        emoji="👑",
        style=discord.ButtonStyle.secondary,
        custom_id="transfer_button",
        row=3,
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
                "他にメンバーがいません。",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "新しいオーナーを選択:", view=view, ephemeral=True
        )

    @discord.ui.button(
        label="キック",
        emoji="👟",
        style=discord.ButtonStyle.secondary,
        custom_id="kick_button",
        row=3,
    )
    async def kick_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """Handle kick button click."""
        await interaction.response.send_message(
            "キックするユーザーを選択:", view=KickSelectView(), ephemeral=True
        )

    # Row 4: メンバー管理②
    @discord.ui.button(
        label="ブロック",
        emoji="🚫",
        style=discord.ButtonStyle.secondary,
        custom_id="block_button",
        row=4,
    )
    async def block_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """Handle block button click."""
        await interaction.response.send_message(
            "ブロックするユーザーを選択:", view=BlockSelectView(), ephemeral=True
        )

    @discord.ui.button(
        label="許可",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="allow_button",
        row=4,
    )
    async def allow_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[Any]
    ) -> None:
        """Handle allow button click."""
        await interaction.response.send_message(
            "許可するユーザーを選択:", view=AllowSelectView(), ephemeral=True
        )
