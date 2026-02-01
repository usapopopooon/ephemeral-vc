"""Role panel cog for role assignment via buttons/reactions.

ボタンまたはリアクションでロールを付与/解除するパネル機能を提供する Cog。

機能:
  - /rolepanel create: パネル作成
  - /rolepanel add: ロール追加
  - /rolepanel remove: ロール削除
  - /rolepanel delete: パネル削除
  - /rolepanel list: パネル一覧

対応形式:
  - button: ボタン式 (推奨)
  - reaction: リアクション式
"""

import logging
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from src.database.engine import async_session
from src.services.db_service import (
    add_role_panel_item,
    delete_role_panel,
    get_all_role_panels,
    get_role_panel_by_message_id,
    get_role_panel_item_by_emoji,
    get_role_panel_items,
    get_role_panels_by_channel,
    remove_role_panel_item,
)
from src.ui.role_panel_view import (
    RolePanelCreateModal,
    RolePanelView,
    refresh_role_panel,
)

logger = logging.getLogger(__name__)


class RolePanelCog(commands.Cog):
    """ロールパネル機能を提供する Cog。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Cog 読み込み時に永続 View を登録する。"""
        async with async_session() as db_session:
            panels = await get_all_role_panels(db_session)
            for panel in panels:
                if panel.panel_type == "button":
                    items = await get_role_panel_items(db_session, panel.id)
                    view = RolePanelView(panel.id, items)
                    self.bot.add_view(view)
                    logger.debug("Registered role panel view for panel %d", panel.id)

        logger.info(
            "Loaded %d role panel views",
            len([p for p in panels if p.panel_type == "button"]),
        )

    # -------------------------------------------------------------------------
    # コマンドグループ
    # -------------------------------------------------------------------------

    rolepanel = app_commands.Group(
        name="rolepanel",
        description="ロールパネルの作成・管理",
        default_permissions=discord.Permissions(manage_roles=True),
    )

    @rolepanel.command(name="create", description="ロールパネルを作成する")
    @app_commands.describe(
        panel_type="パネルの種類 (button: ボタン式, reaction: リアクション式)",
        channel="パネルを送信するチャンネル (省略時: 現在のチャンネル)",
        remove_reaction="リアクション自動削除 (カウントを常に 1 に保つ)",
    )
    async def create(
        self,
        interaction: discord.Interaction,
        panel_type: Literal["button", "reaction"],
        channel: discord.TextChannel | None = None,
        remove_reaction: bool = False,
    ) -> None:
        """ロールパネルを作成する。"""
        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                "テキストチャンネルを指定してください。", ephemeral=True
            )
            return

        modal = RolePanelCreateModal(panel_type, target_channel.id, remove_reaction)
        await interaction.response.send_modal(modal)

    @rolepanel.command(name="add", description="ロールパネルにロールを追加する")
    @app_commands.describe(
        role="追加するロール",
        emoji="ボタン/リアクションに使う絵文字",
        label="ボタンのラベル (ボタン式のみ)",
        style="ボタンのスタイル (ボタン式のみ)",
    )
    async def add(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        emoji: str,
        label: str | None = None,
        style: Literal["primary", "secondary", "success", "danger"] = "secondary",
    ) -> None:
        """ロールパネルにロールを追加する。"""
        if interaction.channel is None:
            await interaction.response.send_message(
                "チャンネルが見つかりません。", ephemeral=True
            )
            return

        async with async_session() as db_session:
            # チャンネル内のパネルを取得
            panels = await get_role_panels_by_channel(
                db_session, str(interaction.channel.id)
            )
            if not panels:
                await interaction.response.send_message(
                    "このチャンネルにロールパネルがありません。\n"
                    "先に `/rolepanel create` でパネルを作成してください。",
                    ephemeral=True,
                )
                return

            # 最新のパネルを使用
            panel = panels[-1]

            # 既に同じ絵文字が使われていないか確認
            existing = await get_role_panel_item_by_emoji(db_session, panel.id, emoji)
            if existing:
                await interaction.response.send_message(
                    f"絵文字 {emoji} は既に使用されています。", ephemeral=True
                )
                return

            # ロールを追加
            await add_role_panel_item(
                db_session,
                panel_id=panel.id,
                role_id=str(role.id),
                emoji=emoji,
                label=label,
                style=style,
            )

            # パネルを更新
            items = await get_role_panel_items(db_session, panel.id)
            channel = (
                interaction.guild.get_channel(int(panel.channel_id))
                if interaction.guild
                else None
            )
            if isinstance(channel, discord.TextChannel):
                await refresh_role_panel(channel, panel, items, self.bot)

        await interaction.response.send_message(
            f"ロール {role.mention} ({emoji}) を追加しました。",
            ephemeral=True,
        )

    @rolepanel.command(name="remove", description="ロールパネルからロールを削除する")
    @app_commands.describe(emoji="削除するロールの絵文字")
    async def remove(
        self,
        interaction: discord.Interaction,
        emoji: str,
    ) -> None:
        """ロールパネルからロールを削除する。"""
        if interaction.channel is None:
            await interaction.response.send_message(
                "チャンネルが見つかりません。", ephemeral=True
            )
            return

        async with async_session() as db_session:
            panels = await get_role_panels_by_channel(
                db_session, str(interaction.channel.id)
            )
            if not panels:
                await interaction.response.send_message(
                    "このチャンネルにロールパネルがありません。", ephemeral=True
                )
                return

            panel = panels[-1]

            # ロールを削除
            success = await remove_role_panel_item(db_session, panel.id, emoji)
            if not success:
                await interaction.response.send_message(
                    f"絵文字 {emoji} のロールが見つかりません。", ephemeral=True
                )
                return

            # パネルを更新
            items = await get_role_panel_items(db_session, panel.id)
            channel = (
                interaction.guild.get_channel(int(panel.channel_id))
                if interaction.guild
                else None
            )
            if isinstance(channel, discord.TextChannel):
                await refresh_role_panel(channel, panel, items, self.bot)

        await interaction.response.send_message(
            f"ロール ({emoji}) を削除しました。", ephemeral=True
        )

    @rolepanel.command(name="delete", description="ロールパネルを削除する")
    async def delete(self, interaction: discord.Interaction) -> None:
        """ロールパネルを削除する。"""
        if interaction.channel is None:
            await interaction.response.send_message(
                "チャンネルが見つかりません。", ephemeral=True
            )
            return

        async with async_session() as db_session:
            panels = await get_role_panels_by_channel(
                db_session, str(interaction.channel.id)
            )
            if not panels:
                await interaction.response.send_message(
                    "このチャンネルにロールパネルがありません。", ephemeral=True
                )
                return

            panel = panels[-1]

            # Discord 上のメッセージを削除
            if panel.message_id and interaction.guild:
                channel = interaction.guild.get_channel(int(panel.channel_id))
                if isinstance(channel, discord.TextChannel):
                    try:
                        msg = await channel.fetch_message(int(panel.message_id))
                        await msg.delete()
                    except discord.HTTPException:
                        pass  # メッセージが既に削除されている場合は無視

            # DB からパネルを削除
            await delete_role_panel(db_session, panel.id)

        await interaction.response.send_message(
            "ロールパネルを削除しました。", ephemeral=True
        )

    @rolepanel.command(name="list", description="ロールパネルの一覧を表示する")
    async def list_panels(self, interaction: discord.Interaction) -> None:
        """ロールパネルの一覧を表示する。"""
        if interaction.guild is None:
            await interaction.response.send_message(
                "サーバー内でのみ使用できます。", ephemeral=True
            )
            return

        from src.services.db_service import get_role_panels_by_guild

        async with async_session() as db_session:
            panels = await get_role_panels_by_guild(
                db_session, str(interaction.guild.id)
            )
            if not panels:
                await interaction.response.send_message(
                    "このサーバーにロールパネルはありません。", ephemeral=True
                )
                return

            embed = discord.Embed(
                title="ロールパネル一覧",
                color=discord.Color.blue(),
            )

            for panel in panels:
                items = await get_role_panel_items(db_session, panel.id)
                channel = interaction.guild.get_channel(int(panel.channel_id))
                channel_mention = (
                    channel.mention if channel else f"(不明: {panel.channel_id})"
                )

                role_count = len(items)
                embed.add_field(
                    name=f"{panel.title} ({panel.panel_type})",
                    value=f"チャンネル: {channel_mention}\nロール数: {role_count}",
                    inline=False,
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------------------------------------------------------------------------
    # リアクションイベント
    # -------------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        """リアクション追加イベント。リアクション式ロールパネル用。"""
        await self._handle_reaction(payload, "add")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        """リアクション削除イベント。リアクション式ロールパネル用。"""
        await self._handle_reaction(payload, "remove")

    async def _handle_reaction(
        self, payload: discord.RawReactionActionEvent, action: str
    ) -> None:
        """リアクションイベントを処理する。"""
        # Bot 自身のリアクションは無視
        if payload.user_id == self.bot.user.id:  # type: ignore[union-attr]
            return

        async with async_session() as db_session:
            # パネルを取得
            panel = await get_role_panel_by_message_id(
                db_session, str(payload.message_id)
            )
            if panel is None or panel.panel_type != "reaction":
                return

            # 絵文字からロールを取得
            emoji_str = str(payload.emoji)
            item = await get_role_panel_item_by_emoji(db_session, panel.id, emoji_str)
            if item is None:
                return

            # remove_reaction モードの情報を保持
            remove_reaction_mode = panel.remove_reaction

        # ギルドとメンバーを取得
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        if guild is None:
            return

        member = guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.HTTPException:
                return

        if member.bot:
            return

        role = guild.get_role(int(item.role_id))
        if role is None:
            logger.warning("Role %s not found for panel %d", item.role_id, panel.id)
            return

        try:
            if remove_reaction_mode:
                # リアクション自動削除モード: 追加時のみトグル動作
                if action == "add":
                    # ユーザーのリアクションを削除してカウントを 1 に保つ
                    channel = guild.get_channel(payload.channel_id)
                    if isinstance(channel, discord.TextChannel):
                        try:
                            msg = await channel.fetch_message(payload.message_id)
                            await msg.remove_reaction(payload.emoji, member)
                        except discord.HTTPException:
                            pass  # 削除失敗は無視

                    # ロールをトグル
                    if role in member.roles:
                        await member.remove_roles(
                            role, reason="ロールパネル (リアクション) から解除"
                        )
                        logger.debug(
                            "Removed role %s from user %s via reaction (toggle)",
                            role.name,
                            member.display_name,
                        )
                    else:
                        await member.add_roles(
                            role, reason="ロールパネル (リアクション) から付与"
                        )
                        logger.debug(
                            "Added role %s to user %s via reaction (toggle)",
                            role.name,
                            member.display_name,
                        )
                # remove イベントは無視 (Bot がリアクションを削除しただけ)
            else:
                # 通常モード: リアクション追加で付与、削除で解除
                if action == "add":
                    if role not in member.roles:
                        await member.add_roles(
                            role, reason="ロールパネル (リアクション) から付与"
                        )
                        logger.debug(
                            "Added role %s to user %s via reaction",
                            role.name,
                            member.display_name,
                        )
                else:  # remove
                    if role in member.roles:
                        await member.remove_roles(
                            role, reason="ロールパネル (リアクション) から解除"
                        )
                        logger.debug(
                            "Removed role %s from user %s via reaction",
                            role.name,
                            member.display_name,
                        )
        except discord.Forbidden:
            logger.warning("No permission to modify role %s", role.name)
        except discord.HTTPException as e:
            logger.error("Failed to modify role: %s", e)


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する。"""
    await bot.add_cog(RolePanelCog(bot))
