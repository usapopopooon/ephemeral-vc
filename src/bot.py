"""Discord bot class definition.

Bot 本体のクラス定義。起動時の初期化処理（DB・Cog・View の復元）を担う。
"""

import discord
from discord.ext import commands

from src.database.engine import async_session, init_db
from src.services.db_service import get_all_voice_sessions
from src.ui.control_panel import ControlPanelView


class EphemeralVCBot(commands.Bot):
    """Ephemeral VC の Bot 本体。

    commands.Bot を継承し、以下を追加:
      - setup_hook: 起動前に DB 初期化・Cog 読み込み・View 復元・コマンド同期
      - on_ready: 起動完了時のステータス設定とログ出力
    """

    def __init__(self) -> None:
        # --- Intents (Bot が受け取るイベントの種類) を設定 ---
        # Discord は Bot が必要なイベントだけ受け取るよう Intents で制御する。
        # Developer Portal の Bot 設定でも同じ Intents を有効にする必要がある。
        intents = discord.Intents.default()
        intents.voice_states = True  # ボイスチャンネルの参加/退出イベントを受け取る
        intents.guilds = True  # サーバー情報 (ギルド) を取得する
        intents.members = True  # メンバー情報を取得する (特権 Intent、要 Portal 有効化)

        # command_prefix: テキストコマンドの接頭辞 (例: !help)
        # この Bot ではスラッシュコマンドを使うので、テキストコマンドはほぼ使わない
        super().__init__(
            command_prefix="!",
            intents=intents,
        )

    async def setup_hook(self) -> None:
        """Bot 起動前に呼ばれるフック。DB・Cog・View の初期化を行う。

        discord.py が内部的に呼び出す。ここで行う処理:
          1. DB テーブルの作成 (初回起動時)
          2. Cog (機能モジュール) の読み込み
          3. Bot 再起動時にボタンが効くよう View を復元
          4. スラッシュコマンドを Discord サーバーに同期
        """
        # 1. データベース初期化 — テーブルが無ければ作成する
        await init_db()

        # 2. Cog の読み込み — 各機能を独立したファイル (Cog) に分けている
        #    voice: ボイスチャンネルの作成・削除・オーナー引き継ぎ
        #    admin: /lobby コマンドでロビーVC を作成
        #    health: 定期的にハートビートを送る死活監視
        await self.load_extension("src.cogs.voice")
        await self.load_extension("src.cogs.admin")
        await self.load_extension("src.cogs.health")

        # 3. 永続 View の復元
        #    discord.py の View (ボタン等) は Bot が再起動すると動かなくなる。
        #    DB に保存されているセッション情報から View を再登録することで、
        #    再起動後もボタンが押せるようにする。
        async with async_session() as session:
            sessions = await get_all_voice_sessions(session)
            for voice_session in sessions:
                # NSFW 状態は DB に保存していないため、チャンネルから取得する
                # setup_hook 時点ではキャッシュが空の場合があるため、
                # 取得できなければデフォルト値 False を使う
                is_nsfw = False
                channel = self.get_channel(int(voice_session.channel_id))
                if isinstance(channel, discord.VoiceChannel):
                    is_nsfw = channel.nsfw
                view = ControlPanelView(
                    voice_session.id,
                    voice_session.is_locked,
                    voice_session.is_hidden,
                    is_nsfw,
                )
                # add_view() で Bot にビューを登録する。
                # custom_id が一致するボタンのクリックイベントが届くようになる。
                self.add_view(view)

        # 4. スラッシュコマンドの同期
        #    tree.sync() で Bot のスラッシュコマンドを Discord に登録する。
        #    これを呼ばないとスラッシュコマンドが表示されない。
        await self.tree.sync()

    async def on_ready(self) -> None:
        """Bot が Discord に接続完了したときに呼ばれる。

        ここでは Bot のステータス (「〜をプレイ中」) を設定する。
        注意: on_ready は再接続時にも呼ばれることがある。
        """
        # Bot のステータスを「お菓子を食べています」に設定
        # discord.Game = 「〜をプレイ中」タイプのアクティビティ
        activity = discord.Game(name="お菓子を食べています")
        await self.change_presence(activity=activity)

        if self.user:
            print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")
