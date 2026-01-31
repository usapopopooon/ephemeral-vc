"""Health monitoring cog for sending periodic heartbeat embeds.

Bot の死活監視を行う Cog。discord.py の tasks.loop を使い、
定期的にハートビート Embed を Discord チャンネルに送信する。

仕組み:
  - 10分ごとにハートビートを送信
  - Uptime (稼働時間)、Latency (遅延)、Guilds (サーバー数) を表示
  - レイテンシに応じて Embed の色が変わる (緑/黄/赤)
  - ログにも出力されるので Heroku logs 等でも確認可能

注意:
  Bot 自身がハートビートを送る仕組みなので、Bot がフリーズすると通知も止まる。
  「通知が来ない = 死んだかもしれない」は人間が判断する必要がある。
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

from src.config import settings

# ロガーの取得。__name__ でモジュールパスがロガー名になる
# (例: "src.cogs.health")
logger = logging.getLogger(__name__)

# ハートビートの送信間隔 (分)
_HEARTBEAT_MINUTES = 10

# 日本標準時 (JST = UTC+9)。Boot 時刻の表示に使う
_JST = timezone(timedelta(hours=9))


class HealthCog(commands.Cog):
    """定期的にハートビート Embed を送信する死活監視 Cog。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Bot 起動時刻を記録 (Uptime 計算用)
        # time.monotonic() はシステム起動からの秒数。時計変更に影響されない。
        self._start_time = time.monotonic()
        # Boot 時刻を JST で記録 (Embed のフッターに表示)
        self._boot_jst = datetime.now(_JST)

    async def cog_load(self) -> None:
        """Cog が読み込まれたときに呼ばれる。ハートビートループを開始する。

        __init__ でタスクを開始するのは NG。Bot がまだ Discord に
        接続していない状態でタスクが走ってしまう。cog_load なら安全。
        """
        self._heartbeat.start()

    async def cog_unload(self) -> None:
        """Cog がアンロードされたときに呼ばれる。ループを停止する。"""
        self._heartbeat.cancel()

    # ------------------------------------------------------------------
    # Heartbeat loop
    # ------------------------------------------------------------------

    @tasks.loop(minutes=_HEARTBEAT_MINUTES)
    async def _heartbeat(self) -> None:
        """10分ごとに実行されるハートビート処理。

        @tasks.loop(minutes=10) を付けるだけで、自動的に繰り返し実行される。
        seconds, hours でも指定可能。
        """
        # --- Uptime の計算 ---
        # 現在時刻 - 起動時刻 = 稼働秒数
        uptime_sec = int(time.monotonic() - self._start_time)
        # divmod: 割り算の商と余りを同時に取得する Python 組み込み関数
        hours, remainder = divmod(uptime_sec, 3600)  # 3600秒 = 1時間
        minutes, seconds = divmod(remainder, 60)  # 60秒 = 1分
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        # --- Bot の状態を取得 ---
        guild_count = len(self.bot.guilds)  # 参加しているサーバー数
        # bot.latency: Discord WebSocket の往復遅延 (秒単位)
        latency_ms = round(self.bot.latency * 1000)  # ミリ秒に変換

        # --- ステータスの判定 ---
        # レイテンシに基づいて健全性を判定する
        if latency_ms < 200:
            status = "Healthy"  # 正常 (200ms 未満)
        elif latency_ms < 500:
            status = "Degraded"  # 低下 (200〜500ms)
        else:
            status = "Unhealthy"  # 異常 (500ms 以上)

        # --- ログ出力 ---
        # Heroku logs や Datadog でも確認できるようにログに出力
        logger.info(
            "[Heartbeat] %s | uptime=%s latency=%dms guilds=%d",
            status,
            uptime_str,
            latency_ms,
            guild_count,
        )

        # --- Discord チャンネルに Embed を送信 ---
        # health_channel_id が 0 (未設定) の場合はスキップ
        if settings.health_channel_id:
            channel = self.bot.get_channel(settings.health_channel_id)
            if channel is None:
                logger.warning(
                    "Health channel %d not found in cache",
                    settings.health_channel_id,
                )
            elif not isinstance(channel, discord.TextChannel):
                logger.warning(
                    "Health channel %d is not a TextChannel (type=%s)",
                    settings.health_channel_id,
                    type(channel).__name__,
                )
            else:
                embed = self._build_embed(
                    status=status,
                    uptime_str=uptime_str,
                    latency_ms=latency_ms,
                    guild_count=guild_count,
                )
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException as e:
                    logger.error(
                        "Failed to send heartbeat to channel %d: %s",
                        settings.health_channel_id,
                        e,
                    )

    @_heartbeat.before_loop
    async def _before_heartbeat(self) -> None:
        """ハートビートループ開始前に1回だけ呼ばれる準備用フック。

        wait_until_ready() で Bot の Discord 接続完了を待つ。
        接続完了後、デプロイ (起動) 通知を送信する。
        tasks.loop は before_loop 完了後に即座に初回実行されるので、
        ここでタスク本体を手動で呼ぶと二重実行になるので注意。
        """
        await self.bot.wait_until_ready()

        # --- デプロイ (起動) 通知 ---
        if settings.health_channel_id:
            channel = self.bot.get_channel(settings.health_channel_id)
            if channel is None:
                logger.warning(
                    "Health channel %d not found for deploy notification",
                    settings.health_channel_id,
                )
            elif isinstance(channel, discord.TextChannel):
                embed = self._build_deploy_embed()
                try:
                    await channel.send(embed=embed)
                    logger.info(
                        "Deploy notification sent to channel %d",
                        settings.health_channel_id,
                    )
                except discord.HTTPException as e:
                    logger.error(
                        "Failed to send deploy notification to channel %d: %s",
                        settings.health_channel_id,
                        e,
                    )
            else:
                logger.warning(
                    "Health channel %d is not a TextChannel for deploy notification",
                    settings.health_channel_id,
                )

    # ------------------------------------------------------------------
    # Embed builder
    # ------------------------------------------------------------------

    def _build_deploy_embed(self) -> discord.Embed:
        """デプロイ (起動) 通知用の Embed を組み立てる。

        ハートビート Embed (緑/黄/赤) と区別するため、青色を使用する。
        Bot 起動時に1回だけ送信される。
        """
        guild_count = len(self.bot.guilds)
        embed = discord.Embed(
            title="\U0001f680 Deploy Complete",
            color=discord.Color.blue(),
            timestamp=datetime.now(UTC),
        )
        embed.add_field(
            name="Boot",
            value=f"{self._boot_jst:%Y-%m-%d %H:%M JST}",
            inline=True,
        )
        embed.add_field(name="Guilds", value=str(guild_count), inline=True)
        return embed

    def _build_embed(
        self,
        *,
        status: str,
        uptime_str: str,
        latency_ms: int,
        guild_count: int,
    ) -> discord.Embed:
        """ハートビート用の Embed を組み立てる。

        レイテンシに応じて色が変わる:
          - 緑 (green): 200ms 未満 — 正常
          - 黄 (yellow): 200〜500ms — 低下
          - 赤 (red): 500ms 以上 — 異常
        """
        # Embed の色を決定
        if latency_ms < 200:
            color = discord.Color.green()
        elif latency_ms < 500:
            color = discord.Color.yellow()
        else:
            color = discord.Color.red()

        # Embed を組み立てる
        embed = discord.Embed(
            title=f"Heartbeat — {status}",
            color=color,
            # timestamp: Embed の右下に表示される時刻。
            # UTC で渡すと Discord がユーザーのローカル時刻に変換してくれる。
            timestamp=datetime.now(UTC),
        )
        # add_field: Embed にフィールド (名前: 値) を追加
        # inline=True で横並びに表示される
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(name="Latency", value=f"{latency_ms}ms", inline=True)
        embed.add_field(name="Guilds", value=str(guild_count), inline=True)
        # set_footer: Embed の最下部に小さいテキストを表示
        embed.set_footer(text=f"Boot: {self._boot_jst:%Y-%m-%d %H:%M JST}")
        return embed


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する関数。bot.load_extension() から呼ばれる。"""
    await bot.add_cog(HealthCog(bot))
