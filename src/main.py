"""Entry point for Ephemeral VC bot.

Bot のエントリーポイント。データベース接続の確認、シグナルハンドラの設定、
Bot の起動を行う。

Examples:
    直接実行::

        python -m src.main

    または::

        python src/main.py

See Also:
    - :class:`src.bot.EphemeralVCBot`: Bot 本体
    - :mod:`src.config`: 設定管理

Notes:
    起動前に以下を確認すること:

    - 環境変数 DISCORD_TOKEN が設定されている
    - データベースが起動している
    - Alembic マイグレーションが実行されている

    環境変数:

    - LOG_LEVEL: ログレベル (DEBUG, INFO, WARNING, ERROR, CRITICAL)。デフォルト: INFO
"""

import asyncio
import logging
import os
import signal
import sys
from types import FrameType

from src.bot import EphemeralVCBot
from src.config import settings
from src.database.engine import check_database_connection_with_retry


def _setup_logging() -> None:
    """ロギングを設定する。

    環境変数 LOG_LEVEL からログレベルを取得し、設定する。
    デフォルトは INFO。無効な値が指定された場合も INFO を使用。

    標準出力にログを出力する (Docker/systemd 環境対応)。
    """
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, None)

    if not isinstance(log_level, int):
        # 無効なログレベル名の場合は INFO を使用
        log_level = logging.INFO
        print(f"Warning: Invalid LOG_LEVEL '{log_level_name}', using INFO")

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        # Docker/systemd 環境では stdout に出力
        stream=sys.stdout,
    )


_setup_logging()
logger = logging.getLogger(__name__)

#: グローバル変数として Bot インスタンスを保持。
#:
#: シグナルハンドラから Bot にアクセスするために使用する。
#: main() 関数内で初期化され、_handle_sigterm() から参照される。
#:
#: :type: EphemeralVCBot | None
_bot: EphemeralVCBot | None = None


def _handle_shutdown_signal(signum: int, _frame: FrameType | None) -> None:
    """シャットダウンシグナルハンドラ (SIGTERM/SIGINT)。

    Heroku などのクラウド環境はシャットダウン時に SIGTERM を送信する。
    Linux で Ctrl+C を押すと SIGINT が送信される。
    このハンドラで Bot を graceful に停止する。

    Args:
        signum (int): シグナル番号 (SIGTERM=15, SIGINT=2)。
        _frame (FrameType | None): 現在のスタックフレーム。未使用。

    Returns:
        None

    Notes:
        - シグナルハンドラは同期関数でなければならない
        - asyncio.create_task() で非同期のシャットダウン処理を起動
        - _bot が None の場合は何もしない
        - イベントループが存在しない場合は RuntimeError をキャッチ

    Examples:
        シグナルハンドラの登録::

            import signal
            signal.signal(signal.SIGTERM, _handle_shutdown_signal)
            signal.signal(signal.SIGINT, _handle_shutdown_signal)

    See Also:
        - :func:`_shutdown_bot`: 実際のシャットダウン処理
        - Heroku の SIGTERM: https://devcenter.heroku.com/articles/dynos#shutdown
    """
    # シグナル名を取得 (Linux 互換性のため signal.Signals を使用)
    try:
        sig_name = signal.Signals(signum).name
    except ValueError:
        sig_name = str(signum)

    logger.info("Received %s signal, initiating graceful shutdown...", sig_name)

    if _bot is not None:
        try:
            # Bot を閉じるタスクを作成
            asyncio.create_task(_shutdown_bot())
        except RuntimeError:
            # イベントループが存在しない場合 (稀なケース)
            logger.warning("Event loop not running, forcing shutdown")
            sys.exit(0)


async def _shutdown_bot() -> None:
    """Bot を graceful に停止する。

    Bot の close() メソッドを呼び出し、Discord との接続を
    安全に切断する。Heroku の SIGTERM 受信時に呼び出される。

    Returns:
        None

    Notes:
        - _bot が None の場合は何もしない
        - close() は非同期処理のため、await が必要
        - シグナルハンドラから asyncio.create_task() で呼び出される

    Examples:
        直接呼び出し (通常は不要)::

            await _shutdown_bot()

    See Also:
        - :func:`_handle_sigterm`: シグナルハンドラ
        - :meth:`discord.Client.close`: Bot のクローズ処理
    """
    global _bot
    if _bot is not None:
        logger.info("Closing bot connection...")
        await _bot.close()
        logger.info("Bot closed successfully")


async def main() -> None:
    """Bot のメインエントリーポイント。

    データベース接続を確認し、シグナルハンドラを設定して
    Bot を起動する。

    Returns:
        None

    Raises:
        SystemExit: データベース接続に失敗した場合 (exit code: 1)。
        discord.LoginFailure: Discord トークンが無効な場合。
        discord.PrivilegedIntentsRequired: 特権 Intent が無効な場合。

    Notes:
        実行される処理:

        1. データベース接続をリトライ付きで確認
        2. シグナルハンドラを登録:
           - SIGTERM/SIGINT: graceful shutdown 用
           - SIGHUP: ターミナル切断時も動作継続 (無視)
           - SIGPIPE: ソケット切断時のクラッシュ防止 (無視)
        3. Bot を起動し、Discord に接続

    Examples:
        asyncio.run での実行::

            import asyncio
            from src.main import main

            asyncio.run(main())

        または直接実行::

            python -m src.main

    See Also:
        - :class:`src.bot.EphemeralVCBot`: Bot 本体
        - :func:`src.database.engine.check_database_connection_with_retry`: DB 確認
    """
    global _bot

    # データベース接続チェック (リトライ付き)
    if not await check_database_connection_with_retry():
        logger.error(
            "Cannot start bot: Database connection failed. "
            "Check DATABASE_URL and ensure the database is running."
        )
        sys.exit(1)

    # シグナルハンドラを設定 (Unix 系 OS)
    # SIGTERM: Heroku, Docker, systemd などからのシャットダウン要求
    # SIGINT: Ctrl+C (Linux/macOS)
    # SIGHUP: ターミナル切断時 (SSH セッション終了など)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle_shutdown_signal)
            logger.info("%s handler registered", sig.name)
        except (ValueError, OSError) as e:
            # Windows やスレッドからの呼び出しでは設定できない場合がある
            logger.warning("Could not register %s handler: %s", sig.name, e)

    # SIGHUP を無視する (Unix/macOS)
    # ターミナルが閉じられても Bot は動作を継続する
    # これは nohup や screen/tmux なしで実行した場合の安全対策
    if hasattr(signal, "SIGHUP"):
        try:
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
            logger.info("SIGHUP handler registered (ignored)")
        except (ValueError, OSError) as e:
            logger.warning("Could not register SIGHUP handler: %s", e)

    # SIGPIPE を無視する (Unix/macOS)
    # 切断されたソケットへの書き込み時にプロセスが終了するのを防ぐ
    # Python は BrokenPipeError を発生させるが、SIGPIPE がデフォルトで
    # 有効だと先にプロセスが終了してしまう
    if hasattr(signal, "SIGPIPE"):
        try:
            signal.signal(signal.SIGPIPE, signal.SIG_IGN)
            logger.info("SIGPIPE handler registered (ignored)")
        except (ValueError, OSError) as e:
            logger.warning("Could not register SIGPIPE handler: %s", e)

    _bot = EphemeralVCBot()
    async with _bot:
        await _bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
