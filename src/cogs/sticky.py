"""Sticky message cog.

チャンネルに常に最新位置に表示される embed/text メッセージを設定する。
新しいメッセージが投稿されると、古い sticky を削除して再投稿する。

仕組み:
  - /sticky set で sticky メッセージを設定 (embed または text を選択)
  - on_message で新規メッセージを監視
  - delay 秒後に古い sticky を削除して新しい sticky を投稿（デバウンス方式）
  - Bot 再起動後も DB から設定を復元して動作継続
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

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


class StickyEmbedModal(discord.ui.Modal, title="Sticky メッセージ設定 (Embed)"):
    """Embed 形式の Sticky メッセージを設定するモーダル。"""

    sticky_title: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="タイトル",
        placeholder="embed のタイトルを入力...",
        max_length=256,
        required=True,
    )

    description: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="説明文",
        style=discord.TextStyle.paragraph,
        placeholder="embed の説明文を入力（改行可）...",
        max_length=4000,
        required=True,
    )

    color: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="色 (16進数、例: FF0000)",
        placeholder="省略時はデフォルト色",
        max_length=10,
        required=False,
    )

    delay: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="遅延（秒）",
        placeholder="最後のメッセージから再投稿までの遅延",
        default="5",
        max_length=4,
        required=False,
    )

    def __init__(self, cog: StickyCog) -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """モーダル送信時の処理。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        title = self.sticky_title.value
        description = self.description.value

        # 色のパース
        color_int: int | None = None
        if self.color.value:
            try:
                color_clean = self.color.value.lstrip("#").lstrip("0x")
                color_int = int(color_clean, 16)
            except ValueError:
                await interaction.response.send_message(
                    f"無効な色形式です: `{self.color.value}`\n"
                    "16進数で指定してください（例: `FF0000`, `#00FF00`）",
                    ephemeral=True,
                )
                return

        # delay のパース
        delay_seconds = 5
        if self.delay.value:
            try:
                delay_seconds = int(self.delay.value)
            except ValueError:
                await interaction.response.send_message(
                    f"無効な遅延値です: `{self.delay.value}`\n"
                    "数字を入力してください",
                    ephemeral=True,
                )
                return

        # delay の検証
        if delay_seconds < 1:
            delay_seconds = 1
        if delay_seconds > 3600:
            delay_seconds = 3600

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
                cooldown_seconds=delay_seconds,
                message_type="embed",
            )

        # embed を投稿
        embed = self.cog._build_embed(title, description, color_int)
        await interaction.response.send_message(
            "✅ Sticky メッセージ (Embed) を設定しました。", ephemeral=True
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
                    "Sticky message set (embed): guild=%s channel=%s title=%s",
                    guild_id,
                    channel_id,
                    title,
                )
            except discord.HTTPException as e:
                logger.error("Failed to post initial sticky message: %s", e)


class StickyTextModal(discord.ui.Modal, title="Sticky メッセージ設定 (テキスト)"):
    """テキスト形式の Sticky メッセージを設定するモーダル。"""

    content: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="メッセージ内容",
        style=discord.TextStyle.paragraph,
        placeholder="スティッキーするテキストを入力（改行可）...",
        max_length=2000,
        required=True,
    )

    delay: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="遅延（秒）",
        placeholder="最後のメッセージから再投稿までの遅延",
        default="5",
        max_length=4,
        required=False,
    )

    def __init__(self, cog: StickyCog) -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """モーダル送信時の処理。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        content = self.content.value

        # delay のパース
        delay_seconds = 5
        if self.delay.value:
            try:
                delay_seconds = int(self.delay.value)
            except ValueError:
                await interaction.response.send_message(
                    f"無効な遅延値です: `{self.delay.value}`\n"
                    "数字を入力してください",
                    ephemeral=True,
                )
                return

        # delay の検証
        if delay_seconds < 1:
            delay_seconds = 1
        if delay_seconds > 3600:
            delay_seconds = 3600

        guild_id = str(interaction.guild.id)
        channel_id = str(interaction.channel_id)

        # 設定を保存 (title は空文字、color は None)
        async with async_session() as session:
            await create_sticky_message(
                session,
                channel_id=channel_id,
                guild_id=guild_id,
                title="",
                description=content,
                color=None,
                cooldown_seconds=delay_seconds,
                message_type="text",
            )

        await interaction.response.send_message(
            "✅ Sticky メッセージ (テキスト) を設定しました。", ephemeral=True
        )

        # 実際の sticky メッセージを投稿
        channel = interaction.channel
        if channel and hasattr(channel, "send"):
            try:
                new_message = await channel.send(content)
                async with async_session() as session:
                    await update_sticky_message_id(
                        session,
                        channel_id,
                        str(new_message.id),
                        last_posted_at=datetime.now(UTC),
                    )
                logger.info(
                    "Sticky message set (text): guild=%s channel=%s",
                    guild_id,
                    channel_id,
                )
            except discord.HTTPException as e:
                logger.error("Failed to post initial sticky message: %s", e)


class StickyTypeSelect(discord.ui.Select[discord.ui.View]):
    """Sticky メッセージの種類を選択するセレクトメニュー。"""

    def __init__(self, cog: StickyCog) -> None:
        self.cog = cog
        options = [
            discord.SelectOption(
                label="Embed",
                description="タイトル・説明文・色を設定できる装飾付きメッセージ",
                value="embed",
            ),
            discord.SelectOption(
                label="テキスト",
                description="シンプルなテキストメッセージ",
                value="text",
            ),
        ]
        super().__init__(
            placeholder="メッセージの種類を選択...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """選択時のコールバック。"""
        selected = self.values[0]
        if selected == "embed":
            await interaction.response.send_modal(StickyEmbedModal(self.cog))
        else:
            await interaction.response.send_modal(StickyTextModal(self.cog))


class StickyTypeView(discord.ui.View):
    """Sticky メッセージの種類を選択する View。"""

    def __init__(self, cog: StickyCog) -> None:
        super().__init__(timeout=60)
        self.add_item(StickyTypeSelect(cog))


# 後方互換性のためのエイリアス
StickySetModal = StickyEmbedModal


class StickyCog(commands.Cog):
    """Sticky メッセージ機能を提供する Cog。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # チャンネルごとの遅延再投稿タスクを管理
        self._pending_tasks: dict[str, asyncio.Task[None]] = {}

    async def cog_unload(self) -> None:
        """Cog がアンロードされる際に、保留中のタスクをキャンセルする。"""
        for task in self._pending_tasks.values():
            task.cancel()
        self._pending_tasks.clear()

    # ==========================================================================
    # メッセージ監視
    # ==========================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """新規メッセージを監視し、sticky メッセージの再投稿をスケジュールする。"""
        # 自分自身のメッセージは無視（無限ループ防止）
        # 他のボットや他のユーザーのメッセージは sticky を再投稿するトリガーとなる
        if self.bot.user and message.author.id == self.bot.user.id:
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

        # 既存のタスクをキャンセル（デバウンス）
        if channel_id in self._pending_tasks:
            self._pending_tasks[channel_id].cancel()
            with suppress(asyncio.CancelledError):
                await self._pending_tasks[channel_id]

        # 遅延後に再投稿するタスクをスケジュール
        task = asyncio.create_task(
            self._delayed_repost(message.channel, channel_id, sticky.cooldown_seconds)
        )
        self._pending_tasks[channel_id] = task

        logger.debug(
            "Scheduled sticky repost: channel=%s delay=%ds",
            channel_id,
            sticky.cooldown_seconds,
        )

    async def _delayed_repost(
        self,
        channel: discord.abc.Messageable,
        channel_id: str,
        delay_seconds: int,
    ) -> None:
        """指定秒数後に sticky メッセージを再投稿する。"""
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            # キャンセルされた場合は何もしない
            return
        finally:
            # タスク管理から削除
            self._pending_tasks.pop(channel_id, None)

        # 再度 sticky 設定を取得（削除されている可能性があるため）
        async with async_session() as session:
            sticky = await get_sticky_message(session, channel_id)

        if not sticky:
            return

        # 古い sticky メッセージを確認・削除
        # メッセージが既に削除されている場合は再投稿せず、DB からも削除
        if not sticky.message_id:
            logger.info(
                "No message_id for sticky, removing config: channel=%s",
                channel_id,
            )
            async with async_session() as session:
                await delete_sticky_message(session, channel_id)
            return

        if hasattr(channel, "fetch_message"):
            try:
                old_message = await channel.fetch_message(int(sticky.message_id))
                await old_message.delete()
                logger.info(
                    "Deleted old sticky message: channel=%s message_id=%s",
                    channel_id,
                    sticky.message_id,
                )
            except discord.NotFound:
                # メッセージが既に削除されている場合は再投稿せず、DB からも削除
                logger.info(
                    "Sticky message already deleted, removing config: channel=%s",
                    channel_id,
                )
                async with async_session() as session:
                    await delete_sticky_message(session, channel_id)
                return
            except discord.HTTPException as e:
                logger.warning(
                    "Failed to fetch/delete old sticky message: channel=%s error=%s",
                    channel_id,
                    e,
                )
                # 取得・削除に失敗した場合も再投稿せず、DB からも削除
                async with async_session() as session:
                    await delete_sticky_message(session, channel_id)
                return

        # 新しい sticky メッセージを投稿
        try:
            if sticky.message_type == "text":
                new_message = await channel.send(sticky.description)
            else:
                embed = self._build_embed(
                    sticky.title, sticky.description, sticky.color
                )
                new_message = await channel.send(embed=embed)
            logger.info(
                "Posted new sticky message (%s): channel=%s message_id=%s",
                sticky.message_type,
                channel_id,
                new_message.id,
            )

            # DB を更新
            now = datetime.now(UTC)
            async with async_session() as session:
                await update_sticky_message_id(
                    session,
                    channel_id,
                    str(new_message.id),
                    last_posted_at=now,
                )
        except discord.HTTPException as e:
            logger.error(
                "Failed to post sticky message: channel=%s error=%s", channel_id, e
            )

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
    async def sticky_set(self, interaction: discord.Interaction) -> None:
        """このチャンネルに sticky メッセージを設定する。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        view = StickyTypeView(self)
        await interaction.response.send_message(
            "Sticky メッセージの種類を選択してください:",
            view=view,
            ephemeral=True,
        )

    @sticky_group.command(name="remove", description="sticky メッセージを解除")
    async def sticky_remove(self, interaction: discord.Interaction) -> None:
        """このチャンネルの sticky メッセージを解除する。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        channel_id = str(interaction.channel_id)

        # 保留中のタスクをキャンセル
        if channel_id in self._pending_tasks:
            self._pending_tasks[channel_id].cancel()
            self._pending_tasks.pop(channel_id, None)

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

        message_type_display = "Embed" if sticky.message_type == "embed" else "テキスト"
        color_hex = f"#{sticky.color:06X}" if sticky.color else "デフォルト"
        embed = discord.Embed(
            title="📌 Sticky メッセージ設定",
            color=sticky.color or DEFAULT_COLOR,
        )
        embed.add_field(name="種類", value=message_type_display, inline=True)
        embed.add_field(name="遅延", value=f"{sticky.cooldown_seconds}秒", inline=True)
        if sticky.message_type == "embed":
            embed.add_field(name="タイトル", value=sticky.title, inline=False)
            embed.add_field(name="色", value=color_hex, inline=True)
        embed.add_field(
            name="内容",
            value=sticky.description[:100] + "..."
            if len(sticky.description) > 100
            else sticky.description,
            inline=False,
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
