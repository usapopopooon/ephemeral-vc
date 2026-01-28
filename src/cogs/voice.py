"""Voice channel event handlers.

一時 VC (Ephemeral Voice Channel) のコアロジック。
ユーザーがロビーに参加すると新しい VC を作成し、
全員が退出すると自動削除する。オーナー退出時は自動引き継ぎを行う。

フロー:
  1. ユーザーがロビー VC に参加
  2. 新しい VC を作成し、ユーザーをそこに移動
  3. コントロールパネル (Embed + ボタン) を送信
  4. ユーザーが退出 → 全員いなくなったら VC を削除
  5. オーナーが退出 → 最も長くいるメンバーにオーナーを引き継ぎ
"""

from __future__ import annotations

import contextlib
import time

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.engine import async_session
from src.database.models import VoiceSession
from src.services.db_service import (
    add_voice_session_member,
    create_lobby,
    create_voice_session,
    delete_lobby,
    delete_voice_session,
    get_lobbies_by_guild,
    get_lobby_by_channel_id,
    get_voice_session,
    get_voice_session_members_ordered,
    remove_voice_session_member,
    update_voice_session,
)
from src.ui.control_panel import (
    ControlPanelView,
    create_control_panel_embed,
    repost_panel,
)

# デフォルトの VC リージョン (サーバー地域)。"japan" = 東京リージョン
DEFAULT_RTC_REGION = "japan"


class VoiceCog(commands.Cog):
    """ボイスチャンネルの作成・削除・オーナー管理を行う Cog。

    Cog = discord.py の機能モジュール。関連するイベントハンドラや
    コマンドをまとめて管理できる。bot.load_extension() で読み込む。
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # --- 参加時刻のメモリキャッシュ ---
        # DB 読み込み頻度を減らすためのキャッシュ。
        # 構造: {チャンネルID: {ユーザーID: 参加時刻(monotonic)}}
        # time.monotonic() はシステム起動からの秒数で、時計の変更に影響されない。
        #
        # 注意: Bot 再起動時にキャッシュは消えるが、DB にも保存されているため
        # _get_longest_member_from_db() で正確な順序を取得できる。
        self._join_times: dict[int, dict[int, float]] = {}

    # ==========================================================================
    # イベントリスナー
    # ==========================================================================

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """ボイスチャンネルの状態変化を監視する。

        discord.py が自動的に呼び出すイベントハンドラ。
        以下の場合に発火する:
          - VC に参加した
          - VC から退出した
          - VC を移動した (退出 + 参加 の2回発火)
          - ミュート/スピーカーオフなどの状態変化

        Args:
            member: 状態が変わったメンバー
            before: 変更前の状態 (before.channel = 以前いたチャンネル)
            after: 変更後の状態 (after.channel = 今いるチャンネル)
        """
        # --- 参加処理 ---
        # after.channel が存在し、かつ before と異なる = 新しいチャンネルに参加した
        if (
            after.channel
            and after.channel != before.channel
            and isinstance(after.channel, discord.VoiceChannel)
        ):
            # ロビーに参加した場合は一時 VC を作成する
            await self._handle_lobby_join(member, after.channel)
            # ロック/人数制限のチェック (違反者はキック)
            if await self._enforce_channel_restrictions(member, after.channel):
                # キックされた場合は以降の処理をスキップ
                return
            # 参加時刻を記録 (キャッシュ + DB)
            self._record_join_cache(after.channel.id, member.id)
            await self._record_join_to_db(after.channel.id, member.id)

        # --- 退出処理 ---
        # before.channel が存在し、かつ after と異なる = チャンネルから退出した
        if (
            before.channel
            and before.channel != after.channel
            and isinstance(before.channel, discord.VoiceChannel)
        ):
            # 参加時刻の記録を削除 (キャッシュ + DB)
            self._remove_join_cache(before.channel.id, member.id)
            await self._remove_join_from_db(before.channel.id, member.id)
            # 一時 VC の退出処理 (空なら削除、オーナー退出なら引き継ぎ)
            await self._handle_channel_leave(member, before.channel)

    @commands.Cog.listener()
    async def on_guild_channel_delete(
        self, channel: discord.abc.GuildChannel
    ) -> None:
        """Discord 上でチャンネルが削除されたときに呼ばれるリスナー。

        管理者が手動で一時 VC を削除した場合、on_voice_state_update は
        発火しないため、DB にレコードが残ってしまう (孤立レコード)。
        このリスナーで削除されたチャンネルの DB レコードをクリーンアップする。
        """
        if not isinstance(channel, discord.VoiceChannel):
            return
        # メモリキャッシュの参加記録を削除
        self._cleanup_channel_cache(channel.id)
        # DB のレコードをクリーンアップ (存在しなくても安全)
        async with async_session() as session:
            await delete_voice_session(session, str(channel.id))
            # ロビーとして登録されていた場合、そのレコードも削除
            lobby = await get_lobby_by_channel_id(session, str(channel.id))
            if lobby:
                await delete_lobby(session, lobby.id)

    # ==========================================================================
    # 参加時刻の追跡ヘルパー
    # ==========================================================================

    def _record_join_cache(self, channel_id: int, user_id: int) -> None:
        """メンバーの参加時刻をメモリキャッシュに記録する。

        setdefault() を使い、既に記録がある場合は上書きしない。
        """
        channel_times = self._join_times.setdefault(channel_id, {})
        channel_times.setdefault(user_id, time.monotonic())

    def _remove_join_cache(self, channel_id: int, user_id: int) -> None:
        """メンバーの参加記録をメモリキャッシュから削除する。"""
        if channel_id in self._join_times:
            self._join_times[channel_id].pop(user_id, None)

    def _cleanup_channel_cache(self, channel_id: int) -> None:
        """チャンネルの全参加記録をメモリキャッシュから削除する。"""
        self._join_times.pop(channel_id, None)

    async def _record_join_to_db(self, channel_id: int, user_id: int) -> None:
        """メンバーの参加時刻を DB に記録する。

        チャンネルが一時 VC の場合のみ記録する。
        """
        async with async_session() as session:
            voice_session = await get_voice_session(session, str(channel_id))
            if voice_session:
                await add_voice_session_member(
                    session, voice_session.id, str(user_id)
                )

    async def _remove_join_from_db(self, channel_id: int, user_id: int) -> None:
        """メンバーの参加記録を DB から削除する。

        チャンネルが一時 VC の場合のみ削除する。
        """
        async with async_session() as session:
            voice_session = await get_voice_session(session, str(channel_id))
            if voice_session:
                await remove_voice_session_member(
                    session, voice_session.id, str(user_id)
                )

    async def _get_longest_member(
        self,
        session: AsyncSession,
        voice_session: VoiceSession,
        channel: discord.VoiceChannel,
        exclude_id: int,
    ) -> discord.Member | None:
        """チャンネル内で最も長く滞在しているメンバーを取得する。

        DB から参加時刻の順序を取得するため、Bot 再起動後も正確に動作する。
        Bot ユーザーは候補から除外する。

        Args:
            session: DB セッション
            voice_session: 対象の VoiceSession
            channel: 対象のボイスチャンネル
            exclude_id: 除外するユーザー ID (退出するオーナー)

        Returns:
            最も長く滞在しているメンバー。誰もいなければ None
        """
        # DB から参加順にソートされたメンバーリストを取得
        db_members = await get_voice_session_members_ordered(session, voice_session.id)

        # チャンネルに実際にいるメンバーの ID セット (Bot 除外、退出者除外)
        present_ids = {
            m.id for m in channel.members if m.id != exclude_id and not m.bot
        }

        # DB の順序を維持しながら、実際にいるメンバーのみをフィルタ
        for db_member in db_members:
            user_id = int(db_member.user_id)
            if user_id in present_ids:
                # guild.get_member() で discord.Member オブジェクトを取得
                member = channel.guild.get_member(user_id)
                if member:
                    return member

        # DB に記録がない場合のフォールバック (キャッシュを使用)
        records = self._join_times.get(channel.id, {})
        remaining = [m for m in channel.members if m.id != exclude_id and not m.bot]
        if not remaining:
            return None
        remaining.sort(key=lambda m: (records.get(m.id, float("inf")), m.id))
        return remaining[0]

    # ==========================================================================
    # 入室制限の強制
    # ==========================================================================

    async def _enforce_channel_restrictions(
        self, member: discord.Member, channel: discord.VoiceChannel
    ) -> bool:
        """一時 VC のロック/人数制限を強制する。

        「メンバーを移動」権限を持つユーザーは Discord の仕様上、
        connect=False のチャンネルにも入室できてしまう。
        このメソッドでは、Administrator 権限を持たないユーザーが
        制限を回避して入室した場合にキックする。

        Args:
            member: 参加したメンバー
            channel: 参加先のボイスチャンネル

        Returns:
            True: キックした (呼び出し元で後続処理をスキップすべき)
            False: キックしなかった (正常な入室)
        """
        # Bot 自身は除外
        if member.bot:
            return False

        # Administrator 権限を持つユーザーは制限なし
        if member.guild_permissions.administrator:
            return False

        async with async_session() as session:
            voice_session = await get_voice_session(session, str(channel.id))
            if not voice_session:
                # 一時 VC ではない (ロビーなど)
                return False

            # オーナーは制限なし
            if str(member.id) == voice_session.owner_id:
                return False

            should_kick = False
            reason = ""

            # --- ロックチェック ---
            if voice_session.is_locked:
                # チャンネル権限で明示的に connect=True が設定されているか確認
                overwrites = channel.overwrites_for(member)
                if overwrites.connect is not True:
                    # 許可されていない → キック
                    should_kick = True
                    reason = "ロックされているため"

            # --- 人数制限チェック ---
            # ロックで既にキック対象なら重複チェック不要
            if not should_kick and voice_session.user_limit > 0:
                # 現在の人数 (参加者本人を含む)
                current_count = len([m for m in channel.members if not m.bot])
                if current_count > voice_session.user_limit:
                    # チャンネル権限で明示的に connect=True が設定されているか確認
                    overwrites = channel.overwrites_for(member)
                    if overwrites.connect is not True:
                        should_kick = True
                        reason = "人数制限を超えているため"

            if should_kick:
                # キック実行
                with contextlib.suppress(discord.HTTPException):
                    await member.move_to(None)
                # チャンネルに通知
                with contextlib.suppress(discord.HTTPException):
                    await channel.send(
                        f"⚠️ {member.mention} は{reason}入室できません。"
                    )
                # DM で本人に通知
                with contextlib.suppress(discord.HTTPException, discord.Forbidden):
                    await member.send(
                        f"⚠️ **{channel.name}** は{reason}入室できませんでした。"
                    )
                return True

        return False

    # ==========================================================================
    # ロビー参加処理
    # ==========================================================================

    async def _handle_lobby_join(
        self, member: discord.Member, channel: discord.VoiceChannel
    ) -> None:
        """ロビー VC に参加したメンバーの処理を行う。

        処理の流れ:
          1. 参加したチャンネルがロビーか DB で確認
          2. ロビーなら新しい VC を作成
          3. DB にセッション情報を記録
          4. テキストチャット権限を設定 (オーナーのみ閲覧可)
          5. メンバーを新しい VC に移動
          6. コントロールパネル (Embed + ボタン) を送信
        """
        async with async_session() as session:
            # DB からロビー情報を取得。ロビーでなければ何もしない
            lobby = await get_lobby_by_channel_id(
                session, str(channel.id)
            )
            if not lobby:
                return

            guild = member.guild

            # --- カテゴリの決定 ---
            # ロビーにカテゴリ ID が設定されていればそれを使う。
            # なければロビー自体のカテゴリを使う (同じカテゴリに作成)。
            category = None
            if lobby.category_id:
                category = guild.get_channel(int(lobby.category_id))
                if not isinstance(category, discord.CategoryChannel):
                    category = channel.category
            else:
                category = channel.category

            # --- VC の作成 ---
            # チャンネル名は「ユーザー名's channel」形式
            channel_name = f"{member.display_name}'s channel"
            new_channel = await guild.create_voice_channel(
                name=channel_name,
                category=category,
                user_limit=lobby.default_user_limit,
                rtc_region=DEFAULT_RTC_REGION,  # リージョンを日本に固定
            )

            # --- DB にセッション記録 ---
            # VC 作成に成功したら、DB にセッション情報を保存する。
            # 失敗した場合は作成した VC を削除してクリーンアップ。
            try:
                voice_session = await create_voice_session(
                    session,
                    lobby_id=lobby.id,
                    channel_id=str(new_channel.id),
                    owner_id=str(member.id),
                    name=channel_name,
                    user_limit=lobby.default_user_limit,
                )
                # オーナーを最初のメンバーとして DB に登録
                await add_voice_session_member(
                    session, voice_session.id, str(member.id)
                )
            except Exception:
                await new_channel.delete()
                raise

            # --- チャンネル初期化 ---
            # DB セッション作成後の全操作をまとめてエラーハンドリングする。
            # set_permissions, move_to, send のいずれかが失敗した場合、
            # 不完全なチャンネルと DB レコードを両方クリーンアップする。
            try:
                # テキストチャット権限の設定
                # VC 内のテキストチャットはデフォルトでオーナーのみ閲覧可にする
                await new_channel.set_permissions(
                    guild.default_role, read_message_history=False
                )
                await new_channel.set_permissions(
                    member, read_message_history=True
                )

                # メンバーをロビーから新しい VC に移動
                await member.move_to(new_channel)

                # コントロールパネル (Embed + ボタン) を送信
                embed = create_control_panel_embed(voice_session, member)
                view = ControlPanelView(
                    voice_session.id,
                    voice_session.is_locked,
                    voice_session.is_hidden,
                )
                self.bot.add_view(view)
                panel_msg = await new_channel.send(
                    embed=embed, view=view
                )

                # コントロールパネルをピン留めする。
                # _transfer_ownership で pins() から確実に見つけられるようにする。
                with contextlib.suppress(discord.HTTPException):
                    await panel_msg.pin()

            except discord.HTTPException:
                # いずれかの Discord API 呼び出しが失敗した場合、
                # チャンネルと DB レコードを両方削除してクリーンアップ
                with contextlib.suppress(discord.HTTPException):
                    await new_channel.delete()
                await delete_voice_session(
                    session, str(new_channel.id)
                )
                return

    # ==========================================================================
    # 退出処理
    # ==========================================================================

    async def _handle_channel_leave(
        self, member: discord.Member, channel: discord.VoiceChannel
    ) -> None:
        """一時 VC からメンバーが退出したときの処理。

        処理の流れ:
          1. DB でこのチャンネルが一時 VC か確認
          2. チャンネルが空なら削除
          3. オーナーが退出した場合は最も長くいるメンバーに引き継ぎ
        """
        async with async_session() as session:
            voice_session = await get_voice_session(
                session, str(channel.id)
            )
            if not voice_session:
                return  # 一時 VC ではない (ロビー等) → 何もしない

            # --- 全員退出 → チャンネル削除 ---
            if len(channel.members) == 0:
                # 参加記録をクリーンアップ (キャッシュのみ。DB は CASCADE で自動削除)
                self._cleanup_channel_cache(channel.id)
                # チャンネルを削除 (Discord API エラーは無視)
                # contextlib.suppress: 指定した例外を無視する Python 標準ライブラリ
                with contextlib.suppress(discord.HTTPException):
                    await channel.delete(
                        reason="Ephemeral VC: All members left"
                    )
                # DB からセッション記録を削除
                await delete_voice_session(session, str(channel.id))
                return

            # --- オーナー退出 → 引き継ぎ ---
            if voice_session.owner_id == str(member.id):
                await self._transfer_ownership(
                    session, voice_session, member, channel
                )

    async def _find_panel_message(
        self, channel: discord.VoiceChannel
    ) -> discord.Message | None:
        """コントロールパネルのメッセージを探す。

        ピン留めメッセージを優先的に検索し、見つからなければ
        チャンネル履歴から Bot の Embed メッセージを探す。

        Returns:
            見つかったメッセージ。見つからなければ None
        """
        # ピン留めメッセージから探す (通常はここで見つかる)
        with contextlib.suppress(discord.HTTPException):
            pins = await channel.pins()
            for pinned in pins:
                if pinned.author == self.bot.user and pinned.embeds:
                    return pinned

        # フォールバック: 履歴から探す (ピン留め前の古いセッション等)
        with contextlib.suppress(discord.HTTPException):
            async for hist_msg in channel.history(limit=50):
                if hist_msg.author == self.bot.user and hist_msg.embeds:
                    return hist_msg

        return None

    async def _transfer_ownership(
        self,
        session: AsyncSession,
        voice_session: VoiceSession,
        old_owner: discord.Member,
        channel: discord.VoiceChannel,
    ) -> None:
        """オーナー権限を最も長く滞在しているメンバーに引き継ぐ。

        以下を行う:
          1. 引き継ぎ先メンバーを特定 (Bot は除外)
          2. DB のオーナー ID を更新
          3. テキストチャット権限を移行
          4. コントロールパネルの Embed を更新
          5. チャンネルに通知メッセージを送信
        """
        # 最も長く滞在しているメンバーを取得 (Bot は除外)
        # DB から参加時刻順を取得するため、再起動後も正確
        new_owner = await self._get_longest_member(
            session, voice_session, channel, old_owner.id
        )
        if not new_owner:
            return  # 人間のメンバーが誰もいない

        # DB のオーナー ID を新オーナーに更新
        await update_voice_session(
            session, voice_session, owner_id=str(new_owner.id)
        )

        # テキストチャット権限を移行
        # 旧オーナー: read_message_history=None → ロール設定に戻す (= 読めなくなる)
        # 新オーナー: read_message_history=True → 読めるようにする
        with contextlib.suppress(discord.HTTPException):
            await channel.set_permissions(
                old_owner, read_message_history=None
            )
            await channel.set_permissions(
                new_owner, read_message_history=True
            )

        # コントロールパネルを再投稿 (旧パネル削除 → 新パネル送信 → ピン留め)
        await repost_panel(channel, self.bot)

        # チャンネルに引き継ぎ通知を送信
        with contextlib.suppress(discord.HTTPException):
            await channel.send(
                f"オーナーが退出したため、"
                f"{new_owner.mention} に引き継ぎました。"
            )


    # ==========================================================================
    # スラッシュコマンド (/vc グループ)
    # ==========================================================================

    vc_group = app_commands.Group(
        name="vc",
        description="一時 VC の管理コマンド",
    )

    @vc_group.command(name="lobby", description="ロビーVCを作成します")
    @app_commands.default_permissions(administrator=True)
    async def vc_lobby(self, interaction: discord.Interaction) -> None:
        """ロビー VC を作成するスラッシュコマンド。

        処理の流れ:
          1. サーバー内でのみ実行可能かチェック
          2. 「参加して作成」という名前の VC を新規作成
          3. DB にロビーとして登録
          4. 管理者に完了メッセージを表示
        """
        # DM (ダイレクトメッセージ) からの実行を拒否
        if not interaction.guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        # --- 重複チェック ---
        # 1サーバーにつきロビーは1つまで
        async with async_session() as session:
            existing = await get_lobbies_by_guild(
                session, str(interaction.guild_id)
            )
            if existing:
                await interaction.response.send_message(
                    "このサーバーには既にロビーが存在します。",
                    ephemeral=True,
                )
                return

        # --- VC の作成 ---
        try:
            lobby_channel = await interaction.guild.create_voice_channel(
                name="参加して作成",
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"VCの作成に失敗しました: {e}", ephemeral=True
            )
            return

        # --- DB にロビーとして登録 ---
        async with async_session() as session:
            await create_lobby(
                session,
                guild_id=str(interaction.guild_id),
                lobby_channel_id=str(lobby_channel.id),
                category_id=None,
                default_user_limit=0,
            )

        await interaction.response.send_message(
            f"ロビー **{lobby_channel.name}** を作成しました！\n"
            f"お好みのカテゴリに手動で移動してください。",
            ephemeral=True,
        )

    @vc_group.command(name="panel", description="コントロールパネルを再投稿します")
    @app_commands.checks.cooldown(1, 30)
    async def vc_panel(self, interaction: discord.Interaction) -> None:
        """コントロールパネルの Embed + ボタンを再投稿するスラッシュコマンド。

        旧パネルメッセージを削除し、新しいパネルを送信する。
        一時 VC 内であれば誰でも実行可能。
        """
        channel = interaction.channel
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message(
                "一時 VC 内で使用してください。", ephemeral=True
            )
            return

        async with async_session() as session:
            voice_session = await get_voice_session(
                session, str(channel.id)
            )
            if not voice_session:
                await interaction.response.send_message(
                    "一時 VC が見つかりません。", ephemeral=True
                )
                return

        await repost_panel(channel, self.bot)
        await interaction.response.send_message(
            "コントロールパネルを再投稿しました。", ephemeral=True
        )

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """スラッシュコマンドのエラーハンドラ。クールダウン中の通知を行う。"""
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"クールダウン中です。{error.retry_after:.0f}秒後に再実行できます。",
                ephemeral=True,
            )
            return
        raise error


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する関数。bot.load_extension() から呼ばれる。"""
    await bot.add_cog(VoiceCog(bot))
