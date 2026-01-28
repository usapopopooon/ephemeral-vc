"""Bump reminder cog for DISBOARD and ディス速報.

DISBOARD/ディス速報の bump 成功を検知し、2時間後にリマインドを送信する。

仕組み:
  - on_message で DISBOARD/ディス速報 Bot のメッセージを監視
  - bump 成功 Embed を検知したら DB にリマインダーを保存
  - 30秒ごとのループタスクで送信予定時刻を過ぎたリマインダーをチェック
  - Server Bumper ロールにメンションして通知
  - 通知の有効/無効をボタンで切り替え可能

注意:
  - Bot 再起動後もリマインダーは DB に保存されているため継続して動作する
  - bump_channel_id が 0 の場合は機能が無効化される
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.database.engine import async_session
from src.services.db_service import (
    clear_bump_reminder,
    delete_bump_config,
    get_bump_config,
    get_bump_reminder,
    get_due_bump_reminders,
    toggle_bump_reminder,
    update_bump_reminder_role,
    upsert_bump_config,
    upsert_bump_reminder,
)

logger = logging.getLogger(__name__)

# DISBOARD Bot の ID
DISBOARD_BOT_ID = 302050872383242240

# ディス速報 Bot の ID
DISSOKU_BOT_ID = 761562078095867916

# bump 成功を判定するキーワード
DISBOARD_SUCCESS_KEYWORD = "表示順をアップ"
DISSOKU_SUCCESS_KEYWORD = "アップ"

# リマインダーの送信間隔 (bump から何時間後か)
REMINDER_HOURS = 2

# リマインダーチェック間隔 (秒)
REMINDER_CHECK_INTERVAL_SECONDS = 30

# リマインド対象のロール名
TARGET_ROLE_NAME = "Server Bumper"


# =============================================================================
# 通知設定用 View
# =============================================================================


class BumpRoleSelectMenu(discord.ui.RoleSelect["BumpRoleSelectView"]):
    """通知先ロールを選択するセレクトメニュー。"""

    def __init__(
        self,
        guild_id: str,
        service_name: str,
        current_role_id: str | None = None,
    ) -> None:
        # 現在のロールがある場合はデフォルト値として設定
        default_values: list[discord.SelectDefaultValue] = []
        if current_role_id:
            default_values = [
                discord.SelectDefaultValue(
                    id=int(current_role_id),
                    type=discord.SelectDefaultValueType.role,
                )
            ]

        super().__init__(
            placeholder="通知先ロールを選択...",
            min_values=1,
            max_values=1,
            default_values=default_values,
        )
        self.guild_id = guild_id
        self.service_name = service_name

    async def callback(self, interaction: discord.Interaction) -> None:
        """ロール選択時のコールバック。"""
        if not self.values:
            return

        selected_role = self.values[0]

        async with async_session() as session:
            await update_bump_reminder_role(
                session, self.guild_id, self.service_name, str(selected_role.id)
            )

        await interaction.response.edit_message(
            content=f"通知先ロールを **{selected_role.name}** に変更しました。",
            view=None,
        )
        logger.info(
            "Bump notification role changed: guild=%s service=%s role=%s",
            self.guild_id,
            self.service_name,
            selected_role.name,
        )


class BumpRoleSelectView(discord.ui.View):
    """ロール選択メニューを含む View。"""

    def __init__(
        self,
        guild_id: str,
        service_name: str,
        current_role_id: str | None = None,
    ) -> None:
        super().__init__(timeout=60)
        self.add_item(BumpRoleSelectMenu(guild_id, service_name, current_role_id))

    @discord.ui.button(label="デフォルトに戻す", style=discord.ButtonStyle.secondary)
    async def reset_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[BumpRoleSelectView],
    ) -> None:
        """ロールをデフォルト (Server Bumper) に戻す。"""
        guild_id = str(interaction.guild_id) if interaction.guild_id else ""
        # service_name はメニューから取得 (順序は実装依存なので型で探す)
        menu = None
        for child in self.children:
            if isinstance(child, BumpRoleSelectMenu):
                menu = child
                break
        if menu is None:
            return
        service_name = menu.service_name

        async with async_session() as session:
            await update_bump_reminder_role(session, guild_id, service_name, None)

        msg = f"通知先ロールを **{TARGET_ROLE_NAME}** (デフォルト) に戻しました。"
        await interaction.response.edit_message(content=msg, view=None)
        logger.info(
            "Bump notification role reset to default: guild=%s service=%s",
            guild_id,
            service_name,
        )


class BumpNotificationView(discord.ui.View):
    """bump 通知の設定を変更するボタンを持つ View。

    Bot 再起動後もボタンが動作するよう、timeout=None で永続化する。
    """

    def __init__(self, guild_id: str, service_name: str, is_enabled: bool) -> None:
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.service_name = service_name
        self._update_toggle_button(is_enabled)
        self._update_role_button()

    def _update_toggle_button(self, is_enabled: bool) -> None:
        """トグルボタンの表示を現在の状態に合わせて更新する。"""
        self.toggle_button.label = (
            "通知を無効にする" if is_enabled else "通知を有効にする"
        )
        self.toggle_button.style = (
            discord.ButtonStyle.secondary if is_enabled else discord.ButtonStyle.success
        )
        # custom_id を状態に関係なく固定 (guild_id と service_name で識別)
        self.toggle_button.custom_id = (
            f"bump_toggle:{self.guild_id}:{self.service_name}"
        )

    def _update_role_button(self) -> None:
        """ロール変更ボタンの custom_id を設定する。"""
        self.role_button.custom_id = (
            f"bump_role:{self.guild_id}:{self.service_name}"
        )

    @discord.ui.button(label="通知を無効にする", style=discord.ButtonStyle.secondary)
    async def toggle_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[BumpNotificationView],
    ) -> None:
        """通知の有効/無効を切り替える。"""
        async with async_session() as session:
            new_state = await toggle_bump_reminder(
                session, self.guild_id, self.service_name
            )

        self._update_toggle_button(new_state)

        status = "有効" if new_state else "無効"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"**{self.service_name}** の通知を **{status}** にしました。",
            ephemeral=True,
        )
        logger.info(
            "Bump notification toggled: guild=%s service=%s enabled=%s",
            self.guild_id,
            self.service_name,
            new_state,
        )

    @discord.ui.button(label="通知ロールを変更", style=discord.ButtonStyle.primary)
    async def role_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[BumpNotificationView],
    ) -> None:
        """通知先ロールの変更メニューを表示する。"""
        # 現在の設定を取得
        current_role_id: str | None = None
        async with async_session() as session:
            reminder = await get_bump_reminder(
                session, self.guild_id, self.service_name
            )
            if reminder:
                current_role_id = reminder.role_id

        view = BumpRoleSelectView(
            self.guild_id, self.service_name, current_role_id
        )
        await interaction.response.send_message(
            f"**{self.service_name}** の通知先ロールを選択してください。",
            view=view,
            ephemeral=True,
        )


class BumpCog(commands.Cog):
    """DISBOARD/ディス速報の bump リマインダー機能を提供する Cog。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Cog が読み込まれたときに呼ばれる。リマインダーチェックループを開始する。"""
        self._reminder_check.start()
        logger.info("Bump reminder cog loaded, reminder check loop started")

    async def cog_unload(self) -> None:
        """Cog がアンロードされたときに呼ばれる。ループを停止する。"""
        if self._reminder_check.is_running():
            self._reminder_check.cancel()

    # ==========================================================================
    # メッセージ監視
    # ==========================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """メッセージを監視し、bump 成功を検知する。

        DISBOARD/ディス速報 Bot からのメッセージで、設定されたチャンネルかつ
        bump 成功の Embed が含まれていれば、リマインダーを登録する。
        """
        # ギルドがなければ無視 (DM など)
        if not message.guild:
            return

        # DISBOARD/ディス速報 Bot 以外は無視
        if message.author.id not in (DISBOARD_BOT_ID, DISSOKU_BOT_ID):
            return

        # Embed がなければ無視
        if not message.embeds:
            return

        guild_id = str(message.guild.id)

        # このギルドの bump 監視設定を確認
        async with async_session() as session:
            config = await get_bump_config(session, guild_id)

        # 設定がないか、設定されたチャンネルでなければ無視
        if not config or config.channel_id != str(message.channel.id):
            return

        # bump 成功かどうかを判定
        service_name = self._detect_bump_success(message)
        if not service_name:
            return

        # bump 実行者を取得
        user = self._get_bump_user(message)
        if not user:
            logger.debug("Could not determine bump user for %s", service_name)
            return

        # Server Bumper ロールを持っているか確認
        if not self._has_target_role(user):
            logger.debug(
                "User %s does not have %s role, skipping reminder",
                user.name,
                TARGET_ROLE_NAME,
            )
            return

        # リマインダーを DB に保存
        remind_at = datetime.now(UTC) + timedelta(hours=REMINDER_HOURS)
        async with async_session() as session:
            reminder = await upsert_bump_reminder(
                session,
                guild_id=guild_id,
                channel_id=str(message.channel.id),
                service_name=service_name,
                remind_at=remind_at,
            )
            is_enabled = reminder.is_enabled

        # bump 検知の確認 Embed を送信
        embed = self._build_detection_embed(service_name, user, remind_at, is_enabled)
        view = BumpNotificationView(guild_id, service_name, is_enabled)
        self.bot.add_view(view)

        try:
            await message.channel.send(embed=embed, view=view)
        except discord.HTTPException as e:
            logger.warning("Failed to send bump detection embed: %s", e)

        logger.info(
            "Bump detected: service=%s user=%s remind_at=%s is_enabled=%s",
            service_name,
            user.name,
            remind_at.isoformat(),
            is_enabled,
        )

    def _detect_bump_success(self, message: discord.Message) -> str | None:
        """メッセージから bump 成功を検知し、サービス名を返す。

        Returns:
            サービス名 ("DISBOARD" or "ディス速報")。検知できなければ None
        """
        for embed in message.embeds:
            description = embed.description or ""

            if (
                message.author.id == DISBOARD_BOT_ID
                and DISBOARD_SUCCESS_KEYWORD in description
            ):
                return "DISBOARD"

            if (
                message.author.id == DISSOKU_BOT_ID
                and DISSOKU_SUCCESS_KEYWORD in description
            ):
                return "ディス速報"

        return None

    def _get_bump_user(self, message: discord.Message) -> discord.Member | None:
        """bump を実行したユーザーを取得する。

        message.interaction から取得を試み、失敗したら None を返す。
        """
        # スラッシュコマンドの場合、interaction.user に実行者がいる
        if message.interaction and message.interaction.user:
            user = message.interaction.user
            # Member でない場合は guild から取得し直す
            if isinstance(user, discord.Member):
                return user
            if message.guild:
                return message.guild.get_member(user.id)
        return None

    def _has_target_role(self, member: discord.Member) -> bool:
        """メンバーが Server Bumper ロールを持っているか確認する。"""
        return any(role.name == TARGET_ROLE_NAME for role in member.roles)

    async def _find_recent_bump(
        self, channel: discord.TextChannel, limit: int = 100
    ) -> tuple[str, datetime] | None:
        """チャンネルの履歴から最近の bump 成功メッセージを探す。

        Args:
            channel: 検索対象のチャンネル
            limit: 検索するメッセージ数の上限

        Returns:
            (サービス名, bump時刻) のタプル。見つからなければ None
        """
        try:
            async for message in channel.history(limit=limit):
                # DISBOARD/ディス速報 Bot 以外は無視
                if message.author.id not in (DISBOARD_BOT_ID, DISSOKU_BOT_ID):
                    continue

                # bump 成功かどうかを判定
                service_name = self._detect_bump_success(message)
                if service_name:
                    return (service_name, message.created_at)

        except discord.HTTPException as e:
            logger.warning("Failed to search channel history: %s", e)

        return None

    # ==========================================================================
    # Embed 生成
    # ==========================================================================

    def _build_detection_embed(
        self,
        service_name: str,
        user: discord.Member,
        remind_at: datetime,
        is_enabled: bool,
    ) -> discord.Embed:
        """bump 検知時の確認 Embed を生成する。

        Args:
            service_name: サービス名 ("DISBOARD" または "ディス速報")
            user: bump を実行したユーザー
            remind_at: リマインド予定時刻
            is_enabled: 通知が有効かどうか

        Returns:
            確認用の Embed
        """
        # Discord タイムスタンプ形式
        ts = int(remind_at.timestamp())
        time_absolute = f"<t:{ts}:t>"  # 短い時刻表示 (例: 21:30)
        time_relative = f"<t:{ts}:R>"  # 相対時間表示 (例: 2時間後)

        if is_enabled:
            description = (
                f"{user.mention} さんが **{service_name}** を bump しました！\n\n"
                f"次の bump リマインドは {time_absolute}（{time_relative}）"
                f"に送信します。"
            )
        else:
            description = (
                f"{user.mention} さんが **{service_name}** を bump しました！\n\n"
                f"通知は現在 **無効** です。"
            )

        embed = discord.Embed(
            title="Bump 検知",
            description=description,
            color=discord.Color.green(),
            timestamp=datetime.now(UTC),
        )
        embed.set_footer(text=service_name)
        return embed

    def _build_reminder_embed(self, service_name: str) -> discord.Embed:
        """bump リマインダーの Embed を生成する。

        Args:
            service_name: サービス名 ("DISBOARD" または "ディス速報")

        Returns:
            リマインダー用の Embed
        """
        embed = discord.Embed(
            title="Bump リマインダー",
            description=(
                f"**{service_name}** の bump ができるようになりました！\n\n"
                f"サーバーを上位に表示させるために bump しましょう。"
            ),
            color=discord.Color.blue(),
            timestamp=datetime.now(UTC),
        )
        embed.set_footer(text=service_name)
        return embed

    # ==========================================================================
    # リマインダーチェックループ
    # ==========================================================================

    @tasks.loop(seconds=REMINDER_CHECK_INTERVAL_SECONDS)
    async def _reminder_check(self) -> None:
        """30秒ごとに実行されるリマインダーチェック処理。

        DB から送信予定時刻を過ぎたリマインダーを取得し、
        対象チャンネルに Server Bumper ロールをメンションして通知する。
        """
        now = datetime.now(UTC)

        async with async_session() as session:
            due_reminders = await get_due_bump_reminders(session, now)

            for reminder in due_reminders:
                await self._send_reminder(reminder)
                await clear_bump_reminder(session, reminder.id)

    @_reminder_check.before_loop
    async def _before_reminder_check(self) -> None:
        """リマインダーチェックループ開始前に Bot の接続完了を待つ。"""
        await self.bot.wait_until_ready()

    async def _send_reminder(self, reminder: BumpReminder) -> None:
        """リマインダー通知を送信する。

        Args:
            reminder: 送信する BumpReminder オブジェクト
        """
        channel = self.bot.get_channel(int(reminder.channel_id))
        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                "Reminder channel %s not found or not a text channel",
                reminder.channel_id,
            )
            return

        guild = channel.guild
        role: discord.Role | None = None

        # カスタムロールが設定されている場合はそれを使用
        if reminder.role_id:
            role = guild.get_role(int(reminder.role_id))
            if not role:
                logger.warning(
                    "Custom role %s not found in guild %s",
                    reminder.role_id,
                    guild.name,
                )

        # カスタムロールがない場合はデフォルトの Server Bumper ロールを使用
        if not role:
            role = discord.utils.get(guild.roles, name=TARGET_ROLE_NAME)

        if role:
            mention = role.mention
        else:
            # ロールが見つからない場合は @here で代用
            mention = "@here"
            logger.warning(
                "Role '%s' not found in guild %s, using @here instead",
                TARGET_ROLE_NAME,
                guild.name,
            )

        # リマインダー Embed を送信
        embed = self._build_reminder_embed(reminder.service_name)
        view = BumpNotificationView(
            reminder.guild_id, reminder.service_name, reminder.is_enabled
        )
        self.bot.add_view(view)

        try:
            await channel.send(content=mention, embed=embed, view=view)
            logger.info(
                "Sent bump reminder: guild=%s service=%s",
                reminder.guild_id,
                reminder.service_name,
            )
        except discord.HTTPException as e:
            logger.error("Failed to send bump reminder: %s", e)

    # ==========================================================================
    # スラッシュコマンド
    # ==========================================================================

    bump_group = app_commands.Group(
        name="bump",
        description="Bump リマインダーの設定",
        default_permissions=discord.Permissions(administrator=True),
    )

    @bump_group.command(name="setup", description="このチャンネルでbump監視を開始")
    async def bump_setup(self, interaction: discord.Interaction) -> None:
        """このチャンネルを bump 監視チャンネルとして設定する。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)
        channel_id = str(interaction.channel_id)

        # 設定を保存
        async with async_session() as session:
            await upsert_bump_config(session, guild_id, channel_id)

        # チャンネルの履歴から最近の bump を探す
        channel = interaction.channel
        recent_bump_info: str | None = None

        if isinstance(channel, discord.TextChannel):
            result = await self._find_recent_bump(channel)
            if result:
                service_name, bump_time = result
                remind_at = bump_time + timedelta(hours=REMINDER_HOURS)
                now = datetime.now(UTC)

                if remind_at > now:
                    # 次の bump まで待機中 → リマインダーを作成
                    async with async_session() as session:
                        await upsert_bump_reminder(
                            session,
                            guild_id=guild_id,
                            channel_id=channel_id,
                            service_name=service_name,
                            remind_at=remind_at,
                        )
                    ts = int(remind_at.timestamp())
                    recent_bump_info = (
                        f"\n\n**📊 直近の bump を検出:**\n"
                        f"サービス: **{service_name}**\n"
                        f"次の bump 可能時刻: <t:{ts}:t>（<t:{ts}:R>）\n"
                        f"リマインダーを自動設定しました。"
                    )
                else:
                    # 既に bump 可能
                    recent_bump_info = (
                        f"\n\n**📊 直近の bump を検出:**\n"
                        f"サービス: **{service_name}**\n"
                        f"✅ 現在 bump 可能です！"
                    )

        base_description = (
            f"監視チャンネル: <#{channel_id}>\n\n"
            "DISBOARD (`/bump`) または ディス速報 (`/dissoku up`) の "
            "bump 成功を検知し、2時間後にリマインドを送信します。"
        )

        embed = discord.Embed(
            title="Bump 監視を開始しました",
            description=base_description + (recent_bump_info or ""),
            color=discord.Color.green(),
            timestamp=datetime.now(UTC),
        )
        embed.set_footer(text="Bump リマインダー")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(
            "Bump monitoring enabled: guild=%s channel=%s",
            guild_id,
            channel_id,
        )

    @bump_group.command(name="status", description="bump 監視の設定状況を確認する")
    async def bump_status(self, interaction: discord.Interaction) -> None:
        """現在の bump 監視設定を表示する。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)

        async with async_session() as session:
            config = await get_bump_config(session, guild_id)

        if config:
            # Discord タイムスタンプ形式で設定日時を表示
            ts = int(config.created_at.timestamp())
            embed = discord.Embed(
                title="Bump 監視設定",
                description=(
                    f"**監視チャンネル:** <#{config.channel_id}>\n"
                    f"**設定日時:** <t:{ts}:F>"
                ),
                color=discord.Color.blue(),
            )
            embed.set_footer(text="Bump リマインダー")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="Bump 監視設定",
                description=(
                    "このサーバーでは bump 監視が設定されていません。\n\n"
                    "`/bump setup` で設定してください。"
                ),
                color=discord.Color.greyple(),
            )
            embed.set_footer(text="Bump リマインダー")
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @bump_group.command(name="disable", description="bump 監視を停止する")
    async def bump_disable(self, interaction: discord.Interaction) -> None:
        """bump 監視を停止する。"""
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)

        async with async_session() as session:
            deleted = await delete_bump_config(session, guild_id)

        if deleted:
            embed = discord.Embed(
                title="Bump 監視を停止しました",
                description="このサーバーでの bump 監視を無効にしました。",
                color=discord.Color.orange(),
                timestamp=datetime.now(UTC),
            )
            embed.set_footer(text="Bump リマインダー")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info("Bump monitoring disabled: guild=%s", guild_id)
        else:
            embed = discord.Embed(
                title="Bump 監視",
                description="bump 監視は既に無効になっています。",
                color=discord.Color.greyple(),
            )
            embed.set_footer(text="Bump リマインダー")
            await interaction.response.send_message(embed=embed, ephemeral=True)


# BumpReminder の型ヒント用 (circular import 回避)
from src.database.models import BumpReminder  # noqa: E402, F401


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する関数。bot.load_extension() から呼ばれる。"""
    # 永続 View の登録 (Bot 再起動後もボタンが動作するように)
    # 注: 実際のデータは DB から取得するため、ここではダミーの View を登録
    # discord.py は custom_id のプレフィックスでマッチングする
    bot.add_view(BumpNotificationView("0", "DISBOARD", True))
    bot.add_view(BumpNotificationView("0", "ディス速報", True))

    await bot.add_cog(BumpCog(bot))
