"""Discord bot class definition.

Bot 本体のクラス定義。起動時の初期化処理（DB・Cog・View の復元）を担う。

Examples:
    基本的な使い方::

        from src.bot import EphemeralVCBot
        from src.config import settings

        bot = EphemeralVCBot()
        async with bot:
            await bot.start(settings.discord_token)

See Also:
    - :mod:`src.main`: エントリーポイント
    - :mod:`src.cogs`: 各機能 Cog
    - discord.py: https://discordpy.readthedocs.io/

Notes:
    - 起動前に Alembic マイグレーションを実行すること
    - Discord Developer Portal で必要な Intents を有効化すること
"""

import logging

import discord
from discord.ext import commands

from src.database.engine import async_session
from src.services.db_service import get_all_voice_sessions
from src.ui.control_panel import ControlPanelView

logger = logging.getLogger(__name__)


class EphemeralVCBot(commands.Bot):
    """Ephemeral VC の Bot 本体。

    discord.py の commands.Bot を継承し、一時ボイスチャンネル機能、
    bump リマインダー、sticky メッセージなどの機能を提供する。

    Attributes:
        command_prefix (str): テキストコマンドの接頭辞 ("!")。
            この Bot ではスラッシュコマンドを主に使用。
        intents (discord.Intents): Bot が受け取るイベントの種類。

    Notes:
        必要な Intents:

        - voice_states: ボイスチャンネルの参加/退出イベント
        - guilds: サーバー情報 (ギルド) の取得
        - members: メンバー情報の取得 (特権 Intent、Portal 有効化必須)
        - message_content: メッセージ内容の取得 (bump 検知用)

    Examples:
        Bot の起動::

            bot = EphemeralVCBot()
            async with bot:
                await bot.start(settings.discord_token)

        コンテキストマネージャーなしでの使用::

            bot = EphemeralVCBot()
            try:
                await bot.start(settings.discord_token)
            finally:
                await bot.close()

    See Also:
        - :meth:`setup_hook`: 起動前の初期化処理
        - :meth:`on_ready`: 起動完了時の処理
        - :class:`discord.ext.commands.Bot`: 基底クラス
    """

    def __init__(self) -> None:
        """Bot インスタンスを初期化する。

        Intents を設定し、親クラスを初期化する。
        Discord Developer Portal の Bot 設定で同じ Intents を
        有効にする必要がある。

        Notes:
            設定される Intents:

            - voice_states: ボイスチャンネルの参加/退出イベント
            - guilds: サーバー情報の取得
            - members: メンバー情報の取得 (特権 Intent)
            - message_content: メッセージ内容の取得 (bump 検知用)

            アクティビティ (プレゼンス):

            - 「お菓子を食べています」をプレイ中として表示
            - コンストラクタで設定することで接続直後から表示される

        Raises:
            discord.LoginFailure: トークンが無効な場合 (start() 時)。
            discord.PrivilegedIntentsRequired: 特権 Intent が無効な場合。

        See Also:
            - Discord Developer Portal: https://discord.com/developers/applications
        """
        # --- Intents (Bot が受け取るイベントの種類) を設定 ---
        # Discord は Bot が必要なイベントだけ受け取るよう Intents で制御する。
        # Developer Portal の Bot 設定でも同じ Intents を有効にする必要がある。
        intents = discord.Intents.default()
        intents.voice_states = True  # ボイスチャンネルの参加/退出イベントを受け取る
        intents.guilds = True  # サーバー情報 (ギルド) を取得する
        intents.members = True  # メンバー情報を取得する (特権 Intent、要 Portal 有効化)
        intents.message_content = True  # メッセージ内容を取得する (bump 検知用)

        # --- アクティビティ (プレゼンス) を設定 ---
        # discord.Game = 「〜をプレイ中」タイプのアクティビティ
        # コンストラクタで設定することで、接続直後から表示される
        activity = discord.Game(name="お菓子を食べています")

        # command_prefix: テキストコマンドの接頭辞 (例: !help)
        # この Bot ではスラッシュコマンドを使うので、テキストコマンドはほぼ使わない
        super().__init__(
            command_prefix="!",
            intents=intents,
            activity=activity,
        )

    async def setup_hook(self) -> None:
        """Bot 起動前に呼ばれるフック。Cog・View の初期化を行う。

        discord.py が内部的に呼び出す。Cog の読み込み、
        永続 View の復元、スラッシュコマンドの同期を行う。

        Returns:
            None

        Raises:
            discord.ExtensionError: Cog の読み込みに失敗した場合。
            sqlalchemy.exc.OperationalError: DB 接続に失敗した場合。
            discord.HTTPException: Discord API へのリクエストに失敗した場合。

        Notes:
            実行される処理:

            1. Cog (機能モジュール) の読み込み
               - voice: ボイスチャンネル管理
               - admin: /lobby コマンド
               - health: 死活監視
               - bump: bump リマインダー
               - sticky: sticky メッセージ

            2. 永続 View の復元
               - DB から VoiceSession を取得し、ControlPanelView を再登録

            3. スラッシュコマンドの同期
               - tree.sync() で Discord にコマンドを登録

        Examples:
            setup_hook は自動で呼ばれるため、直接呼び出す必要はない::

                bot = EphemeralVCBot()
                async with bot:
                    # setup_hook() が自動で呼ばれる
                    await bot.start(token)

        See Also:
            - :meth:`on_ready`: 起動完了時の処理
            - :class:`src.ui.control_panel.ControlPanelView`: コントロールパネル
        """
        # 1. Cog の読み込み — 各機能を独立したファイル (Cog) に分けている
        #    voice: ボイスチャンネルの作成・削除・オーナー引き継ぎ
        #    admin: /lobby コマンドでロビーVC を作成
        #    health: 定期的にハートビートを送る死活監視
        #    bump: bump リマインダー
        #    sticky: sticky メッセージ
        extensions = [
            "src.cogs.voice",
            "src.cogs.admin",
            "src.cogs.health",
            "src.cogs.bump",
            "src.cogs.sticky",
            "src.cogs.role_panel",
        ]
        for ext in extensions:
            try:
                await self.load_extension(ext)
                logger.info("Loaded extension: %s", ext)
            except commands.ExtensionError as e:
                logger.exception("Failed to load extension %s: %s", ext, e)
                raise  # 起動時に Cog 読み込みに失敗したら例外を上げて停止

        # 2. 永続 View の復元
        #    discord.py の View (ボタン等) は Bot が再起動すると動かなくなる。
        #    DB に保存されているセッション情報から View を再登録することで、
        #    再起動後もボタンが押せるようにする。
        async with async_session() as session:
            sessions = await get_all_voice_sessions(session)
            logger.info("Restoring %d persistent views from database", len(sessions))
            for voice_session in sessions:
                # NSFW 状態は DB に保存していないため、チャンネルから取得する
                # setup_hook 時点ではキャッシュが空の場合があるため、
                # 取得できなければデフォルト値 False を使う
                is_nsfw = False
                channel = self.get_channel(int(voice_session.channel_id))
                if channel is None:
                    logger.debug(
                        "Channel %s not in cache for session %d, using NSFW=False",
                        voice_session.channel_id,
                        voice_session.id,
                    )
                elif isinstance(channel, discord.VoiceChannel):
                    is_nsfw = channel.nsfw
                else:
                    logger.warning(
                        "Channel %s is not a VoiceChannel (type=%s) for session %d",
                        voice_session.channel_id,
                        type(channel).__name__,
                        voice_session.id,
                    )
                view = ControlPanelView(
                    voice_session.id,
                    voice_session.is_locked,
                    voice_session.is_hidden,
                    is_nsfw,
                )
                # add_view() で Bot にビューを登録する。
                # custom_id が一致するボタンのクリックイベントが届くようになる。
                self.add_view(view)

        # 3. スラッシュコマンドの同期
        #    tree.sync() で Bot のスラッシュコマンドを Discord に登録する。
        #    これを呼ばないとスラッシュコマンドが表示されない。
        try:
            synced = await self.tree.sync()
            logger.info("Synced %d slash commands", len(synced))
        except discord.HTTPException as e:
            logger.exception("Failed to sync slash commands: %s", e)
            raise

    async def on_ready(self) -> None:
        """Bot が Discord に接続完了したときに呼ばれる。

        Bot のステータス (プレゼンス) を再設定し、起動ログを出力する。

        Returns:
            None

        Notes:
            - on_ready は再接続時にも呼ばれることがある
            - 冪等な処理のみを行うこと (何度呼ばれても問題ない処理)
            - ステータスは「お菓子を食べています」に設定される
            - アクティビティはコンストラクタでも設定されているが、
              再接続時にリセットされる可能性があるため、ここでも再設定する

        Examples:
            on_ready は自動で呼ばれるため、直接呼び出す必要はない::

                # Discord 接続完了時に自動実行される
                # Logged in as BotName (ID: 123456789)
                # ------

        See Also:
            - :meth:`setup_hook`: 起動前の初期化処理
            - :meth:`discord.Client.change_presence`: プレゼンス変更
        """
        # Bot のステータスを「お菓子を食べています」に設定
        # discord.Game = 「〜をプレイ中」タイプのアクティビティ
        activity = discord.Game(name="お菓子を食べています")
        await self.change_presence(activity=activity)

        if self.user:
            print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")
