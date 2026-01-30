"""Sticky message cog.

チャンネルに常に最新位置に表示される embed メッセージを設定する。
新しいメッセージが投稿されると、古い sticky を削除して再投稿する。

仕組み:
  - /sticky set で sticky メッセージを設定
  - on_message で新規メッセージを監視
  - cooldown 経過後、古い sticky を削除して新しい sticky を投稿
  - Bot 再起動後も DB から設定を復元して動作継続
"""

from __future__ import annotations

import logging
from contextlib import suppress
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

from src.database.engine import async_session
from src.services.db_service import (
    create_sticky_message,
    delete_sticky_message,
    get_all_sticky_messages,
    get_sticky_message,
    update_sticky_message_id,
)

logger = logging.getLogger(__name__)

# デフォルトの embed 色 (Discord Blurple)
DEFAULT_COLOR = 0x5865F2


class StickyCog(commands.Cog):
    """Sticky メッセージ機能を提供する Cog。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ==========================================================================
    # メッセージ監視
    # ==========================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """新規メッセージを監視し、sticky メッセージを再投稿する。"""
        # Bot のメッセージは無視
        if message.author.bot:
            return

        # ギルドがなければ無視 (DM など)
        if not message.guild:
            return

        channel_id = str(message.channel.id)

        # sticky 設定を取得
        async with async_session() as session:
            sticky = await get_sticky_message(session, channel_id)

        if not sticky:
            return

        # cooldown チェック
        now = datetime.now(UTC)
        if sticky.last_posted_at:
            elapsed = (now - sticky.last_posted_at).total_seconds()
            if elapsed < sticky.cooldown_seconds:
                logger.info(
                    "Sticky cooldown active: channel=%s elapsed=%.1fs cooldown=%ds",
                    channel_id,
                    elapsed,
                    sticky.cooldown_seconds,
                )
                return

        # 古い sticky メッセージを削除
        if sticky.message_id:
            with suppress(discord.NotFound, discord.HTTPException):
                old_message = await message.channel.fetch_message(
                    int(sticky.message_id)
                )
                await old_message.delete()
                logger.info(
                    "Deleted old sticky message: channel=%s message_id=%s",
                    channel_id,
                    sticky.message_id,
                )

        # 新しい sticky メッセージを投稿
        embed = self._build_embed(sticky.title, sticky.description, sticky.color)
        try:
            new_message = await message.channel.send(embed=embed)
            logger.info(
                "Posted new sticky message: channel=%s message_id=%s",
                channel_id,
                new_message.id,
            )

            # DB を更新
            async with async_session() as session:
                await update_sticky_message_id(
                    session,
                    channel_id,
                    str(new_message.id),
                    last_posted_at=now,
                )
        except discord.HTTPException as e:
            logger.error("Failed to post sticky message: channel=%s error=%s",
                         channel_id, e)

    # ==========================================================================
    # ヘルパーメソッド
    # ==========================================================================

    def _build_embed(
        self, title: str, description: str, color: int | None
    ) -> discord.Embed:
        """sticky メッセージ用の Embed を作成する。"""
        return discord.Embed(
            title=title,
            description=description,
            color=color or DEFAULT_COLOR,
        )

    # ==========================================================================
    # スラッシュコマンド
    # ==========================================================================

    sticky_group = app_commands.Group(
        name="sticky",
        description="Sticky メッセージの設定",
        default_permissions=discord.Permissions(administrator=True),
    )

    @sticky_group.command(name="set", description="sticky メッセージを設定")
    @app_commands.describe(
        title="embed のタイトル",
        description="embed の説明文",
        color="embed の色 (16進数、例: FF0000)",
        cooldown="再投稿までの間隔（秒）",
    )
    async def sticky_set(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        color: str | None = None,
        cooldown: int = 5,
    ) -> None:
        """このチャンネルに sticky メッセージを設定する。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        # 色のパース
        color_int: int | None = None
        if color:
            try:
                # 0x プレフィックスや # を除去
                color_clean = color.lstrip("#").lstrip("0x")
                color_int = int(color_clean, 16)
            except ValueError:
                await interaction.response.send_message(
                    f"無効な色形式です: `{color}`\n"
                    "16進数で指定してください（例: `FF0000`, `#00FF00`）",
                    ephemeral=True,
                )
                return

        # cooldown の検証
        if cooldown < 1:
            cooldown = 1
        if cooldown > 3600:
            cooldown = 3600

        guild_id = str(interaction.guild.id)
        channel_id = str(interaction.channel_id)

        # 設定を保存
        async with async_session() as session:
            await create_sticky_message(
                session,
                channel_id=channel_id,
                guild_id=guild_id,
                title=title,
                description=description,
                color=color_int,
                cooldown_seconds=cooldown,
            )

        # embed を投稿
        embed = self._build_embed(title, description, color_int)
        await interaction.response.send_message(
            "✅ Sticky メッセージを設定しました。", ephemeral=True
        )

        # 実際の sticky メッセージを投稿
        channel = interaction.channel
        if channel and hasattr(channel, "send"):
            try:
                new_message = await channel.send(embed=embed)
                async with async_session() as session:
                    await update_sticky_message_id(
                        session,
                        channel_id,
                        str(new_message.id),
                        last_posted_at=datetime.now(UTC),
                    )
                logger.info(
                    "Sticky message set: guild=%s channel=%s title=%s",
                    guild_id,
                    channel_id,
                    title,
                )
            except discord.HTTPException as e:
                logger.error("Failed to post initial sticky message: %s", e)

    @sticky_group.command(name="remove", description="sticky メッセージを解除")
    async def sticky_remove(self, interaction: discord.Interaction) -> None:
        """このチャンネルの sticky メッセージを解除する。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        channel_id = str(interaction.channel_id)

        # 現在の sticky メッセージを削除
        async with async_session() as session:
            sticky = await get_sticky_message(session, channel_id)

        if not sticky:
            await interaction.response.send_message(
                "このチャンネルには sticky メッセージが設定されていません。",
                ephemeral=True,
            )
            return

        # メッセージを削除
        if sticky.message_id and interaction.channel:
            with suppress(discord.NotFound, discord.HTTPException):
                channel = interaction.channel
                if hasattr(channel, "fetch_message"):
                    old_message = await channel.fetch_message(int(sticky.message_id))
                    await old_message.delete()

        # DB から削除
        async with async_session() as session:
            await delete_sticky_message(session, channel_id)

        await interaction.response.send_message(
            "✅ Sticky メッセージを解除しました。", ephemeral=True
        )
        logger.info(
            "Sticky message removed: guild=%s channel=%s",
            interaction.guild.id,
            channel_id,
        )

    @sticky_group.command(name="status", description="sticky 設定を確認")
    async def sticky_status(self, interaction: discord.Interaction) -> None:
        """このチャンネルの sticky 設定を確認する。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        channel_id = str(interaction.channel_id)

        async with async_session() as session:
            sticky = await get_sticky_message(session, channel_id)

        if not sticky:
            await interaction.response.send_message(
                "このチャンネルには sticky メッセージが設定されていません。",
                ephemeral=True,
            )
            return

        color_hex = f"#{sticky.color:06X}" if sticky.color else "デフォルト"
        embed = discord.Embed(
            title="📌 Sticky メッセージ設定",
            color=sticky.color or DEFAULT_COLOR,
        )
        embed.add_field(name="タイトル", value=sticky.title, inline=False)
        embed.add_field(
            name="説明",
            value=sticky.description[:100] + "..."
            if len(sticky.description) > 100
            else sticky.description,
            inline=False,
        )
        embed.add_field(name="色", value=color_hex, inline=True)
        embed.add_field(
            name="クールダウン", value=f"{sticky.cooldown_seconds}秒", inline=True
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する関数。"""
    await bot.add_cog(StickyCog(bot))

    # Bot 起動時に全ての sticky 設定をログ出力
    async with async_session() as session:
        stickies = await get_all_sticky_messages(session)
        if stickies:
            logger.info(
                "Loaded %d sticky message configurations",
                len(stickies),
            )
