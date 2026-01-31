"""Tests for main entry point."""

from __future__ import annotations

import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ===========================================================================
# _setup_logging テスト
# ===========================================================================


class TestSetupLogging:
    """Tests for _setup_logging function."""

    def test_invalid_log_level_uses_info(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """無効な LOG_LEVEL の場合は INFO を使用して警告を出力する。"""
        import importlib
        import os

        # 既存の環境変数を保存
        original = os.environ.get("LOG_LEVEL")

        try:
            # 無効なログレベルを設定
            os.environ["LOG_LEVEL"] = "INVALID_LEVEL"

            # モジュールを再読み込みして _setup_logging を再実行
            import src.main

            importlib.reload(src.main)

            # 警告が出力されていることを確認
            captured = capsys.readouterr()
            assert "Warning: Invalid LOG_LEVEL" in captured.out
            assert "INVALID_LEVEL" in captured.out
        finally:
            # 環境変数を元に戻す
            if original is None:
                os.environ.pop("LOG_LEVEL", None)
            else:
                os.environ["LOG_LEVEL"] = original

            # モジュールを再読み込み
            import src.main

            importlib.reload(src.main)


# ===========================================================================
# _handle_shutdown_signal テスト
# ===========================================================================


class TestHandleShutdownSignalValueError:
    """_handle_shutdown_signal の ValueError ハンドリングテスト。"""

    def test_invalid_signal_number_uses_string(self) -> None:
        """無効なシグナル番号の場合は文字列として使用する。"""
        import src.main as main_module
        from src.main import _handle_shutdown_signal

        main_module._bot = None

        # 無効なシグナル番号 (999 は通常存在しない)
        with patch("src.main.logger") as mock_logger:
            _handle_shutdown_signal(999, None)

            # ログに "999" が含まれることを確認
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0]
            assert "999" in call_args[1]


class TestMain:
    """Tests for main() function."""

    @patch("src.main.settings")
    @patch("src.main.EphemeralVCBot")
    @patch("src.main.check_database_connection_with_retry")
    async def test_starts_bot_with_token(
        self,
        mock_check_db: AsyncMock,
        mock_bot_class: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Bot が discord_token で起動される。"""
        from src.main import main

        mock_check_db.return_value = True
        mock_settings.discord_token = "test-token-123"
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot

        await main()

        mock_check_db.assert_awaited_once()
        mock_bot.start.assert_awaited_once_with("test-token-123")

    @patch("src.main.sys")
    @patch("src.main.check_database_connection_with_retry")
    async def test_exits_on_db_connection_failure(
        self,
        mock_check_db: AsyncMock,
        mock_sys: MagicMock,
    ) -> None:
        """データベース接続に失敗した場合、終了する。"""
        from src.main import main

        mock_check_db.return_value = False
        mock_sys.exit.side_effect = SystemExit(1)

        with pytest.raises(SystemExit):
            await main()

        mock_check_db.assert_awaited_once()
        mock_sys.exit.assert_called_once_with(1)

    @patch("src.main.signal.signal")
    @patch("src.main.settings")
    @patch("src.main.EphemeralVCBot")
    @patch("src.main.check_database_connection_with_retry")
    async def test_registers_signal_handlers(
        self,
        mock_check_db: AsyncMock,
        mock_bot_class: MagicMock,
        mock_settings: MagicMock,
        mock_signal: MagicMock,
    ) -> None:
        """main() がすべてのシグナルハンドラを登録する。"""
        from src.main import main

        mock_check_db.return_value = True
        mock_settings.discord_token = "test-token"
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot

        await main()

        # SIGTERM, SIGINT, SIGHUP, SIGPIPE のハンドラが登録されている
        # (Unix/macOS では 4 つ、Windows では 2 つ)
        registered_signals = {call[0][0] for call in mock_signal.call_args_list}
        assert signal.SIGTERM in registered_signals
        assert signal.SIGINT in registered_signals
        # SIGHUP と SIGPIPE は Unix/macOS のみ
        if hasattr(signal, "SIGHUP"):
            assert signal.SIGHUP in registered_signals
        if hasattr(signal, "SIGPIPE"):
            assert signal.SIGPIPE in registered_signals

    @patch("src.main.signal.signal")
    @patch("src.main.settings")
    @patch("src.main.EphemeralVCBot")
    @patch("src.main.check_database_connection_with_retry")
    async def test_handles_signal_registration_error(
        self,
        mock_check_db: AsyncMock,
        mock_bot_class: MagicMock,
        mock_settings: MagicMock,
        mock_signal: MagicMock,
    ) -> None:
        """シグナル登録エラーでもアプリは起動を続ける。"""
        from src.main import main

        mock_check_db.return_value = True
        mock_settings.discord_token = "test-token"
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot
        mock_signal.side_effect = ValueError("signal only works in main thread")

        # エラーが発生しても起動する
        await main()

        mock_bot.start.assert_awaited_once()


class TestShutdownSignalHandler:
    """シャットダウンシグナルハンドラ (SIGTERM/SIGINT) のテスト。"""

    def test_handle_sigterm_creates_shutdown_task(self) -> None:
        """SIGTERM ハンドラがシャットダウンタスクを作成する。"""
        import src.main as main_module
        from src.main import _handle_shutdown_signal

        # モックの Bot を設定
        mock_bot = AsyncMock()
        main_module._bot = mock_bot

        with patch("src.main.asyncio.create_task") as mock_create_task:
            _handle_shutdown_signal(signal.SIGTERM, None)

            # シャットダウンタスクが作成される
            mock_create_task.assert_called_once()

        # クリーンアップ
        main_module._bot = None

    def test_handle_sigint_creates_shutdown_task(self) -> None:
        """SIGINT ハンドラがシャットダウンタスクを作成する。"""
        import src.main as main_module
        from src.main import _handle_shutdown_signal

        # モックの Bot を設定
        mock_bot = AsyncMock()
        main_module._bot = mock_bot

        with patch("src.main.asyncio.create_task") as mock_create_task:
            _handle_shutdown_signal(signal.SIGINT, None)

            # シャットダウンタスクが作成される
            mock_create_task.assert_called_once()

        # クリーンアップ
        main_module._bot = None

    def test_handle_signal_does_nothing_when_no_bot(self) -> None:
        """Bot がない場合、ハンドラは何もしない。"""
        import src.main as main_module
        from src.main import _handle_shutdown_signal

        main_module._bot = None

        with patch("src.main.asyncio.create_task") as mock_create_task:
            _handle_shutdown_signal(signal.SIGTERM, None)

            # タスクは作成されない
            mock_create_task.assert_not_called()

    def test_handle_signal_with_no_event_loop(self) -> None:
        """イベントループがない場合、sys.exit で終了する。"""
        import src.main as main_module
        from src.main import _handle_shutdown_signal

        mock_bot = AsyncMock()
        main_module._bot = mock_bot

        with (
            patch("src.main.asyncio.create_task", side_effect=RuntimeError("No loop")),
            patch("src.main.sys.exit") as mock_exit,
        ):
            _handle_shutdown_signal(signal.SIGTERM, None)

            mock_exit.assert_called_once_with(0)

        # クリーンアップ
        main_module._bot = None

    async def test_shutdown_bot_closes_connection(self) -> None:
        """_shutdown_bot が Bot を閉じる。"""
        import src.main as main_module
        from src.main import _shutdown_bot

        mock_bot = AsyncMock()
        main_module._bot = mock_bot

        await _shutdown_bot()

        mock_bot.close.assert_awaited_once()

        # クリーンアップ
        main_module._bot = None

    async def test_shutdown_bot_does_nothing_when_no_bot(self) -> None:
        """Bot がない場合、_shutdown_bot は何もしない。"""
        import src.main as main_module
        from src.main import _shutdown_bot

        main_module._bot = None

        # エラーなく完了する
        await _shutdown_bot()


# ===========================================================================
# Unix/macOS 固有のシグナルハンドラテスト
# ===========================================================================


class TestUnixSignalHandlers:
    """Unix/macOS 固有のシグナルハンドラ (SIGHUP/SIGPIPE) のテスト。"""

    @pytest.mark.skipif(
        not hasattr(signal, "SIGHUP"),
        reason="SIGHUP is not available on this platform",
    )
    @patch("src.main.signal.signal")
    @patch("src.main.settings")
    @patch("src.main.EphemeralVCBot")
    @patch("src.main.check_database_connection_with_retry")
    async def test_sighup_is_ignored(
        self,
        mock_check_db: AsyncMock,
        mock_bot_class: MagicMock,
        mock_settings: MagicMock,
        mock_signal: MagicMock,
    ) -> None:
        """SIGHUP が SIG_IGN で登録される (ターミナル切断時も継続)。"""
        from src.main import main

        mock_check_db.return_value = True
        mock_settings.discord_token = "test-token"
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot

        await main()

        # SIGHUP が SIG_IGN で登録されていることを確認
        sighup_calls = [
            call for call in mock_signal.call_args_list if call[0][0] == signal.SIGHUP
        ]
        assert len(sighup_calls) == 1
        assert sighup_calls[0][0][1] == signal.SIG_IGN

    @pytest.mark.skipif(
        not hasattr(signal, "SIGPIPE"),
        reason="SIGPIPE is not available on this platform",
    )
    @patch("src.main.signal.signal")
    @patch("src.main.settings")
    @patch("src.main.EphemeralVCBot")
    @patch("src.main.check_database_connection_with_retry")
    async def test_sigpipe_is_ignored(
        self,
        mock_check_db: AsyncMock,
        mock_bot_class: MagicMock,
        mock_settings: MagicMock,
        mock_signal: MagicMock,
    ) -> None:
        """SIGPIPE が SIG_IGN で登録される (ソケット切断でもクラッシュしない)。"""
        from src.main import main

        mock_check_db.return_value = True
        mock_settings.discord_token = "test-token"
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot

        await main()

        # SIGPIPE が SIG_IGN で登録されていることを確認
        sigpipe_calls = [
            call for call in mock_signal.call_args_list if call[0][0] == signal.SIGPIPE
        ]
        assert len(sigpipe_calls) == 1
        assert sigpipe_calls[0][0][1] == signal.SIG_IGN

    @pytest.mark.skipif(
        not hasattr(signal, "SIGHUP"),
        reason="SIGHUP is not available on this platform",
    )
    @patch("src.main.signal.signal")
    @patch("src.main.settings")
    @patch("src.main.EphemeralVCBot")
    @patch("src.main.check_database_connection_with_retry")
    async def test_sighup_registration_error_does_not_crash(
        self,
        mock_check_db: AsyncMock,
        mock_bot_class: MagicMock,
        mock_settings: MagicMock,
        mock_signal: MagicMock,
    ) -> None:
        """SIGHUP の登録エラーでもアプリは起動を続ける。"""
        from src.main import main

        mock_check_db.return_value = True
        mock_settings.discord_token = "test-token"
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot

        # SIGHUP の登録時のみエラーを発生させる
        def side_effect(sig: signal.Signals, _handler: signal.Handlers) -> None:
            if sig == signal.SIGHUP:
                raise OSError("Cannot set SIGHUP handler")

        mock_signal.side_effect = side_effect

        # エラーが発生しても起動する
        await main()

        mock_bot.start.assert_awaited_once()

    @pytest.mark.skipif(
        not hasattr(signal, "SIGPIPE"),
        reason="SIGPIPE is not available on this platform",
    )
    @patch("src.main.signal.signal")
    @patch("src.main.settings")
    @patch("src.main.EphemeralVCBot")
    @patch("src.main.check_database_connection_with_retry")
    async def test_sigpipe_registration_error_does_not_crash(
        self,
        mock_check_db: AsyncMock,
        mock_bot_class: MagicMock,
        mock_settings: MagicMock,
        mock_signal: MagicMock,
    ) -> None:
        """SIGPIPE の登録エラーでもアプリは起動を続ける。"""
        from src.main import main

        mock_check_db.return_value = True
        mock_settings.discord_token = "test-token"
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot

        # SIGPIPE の登録時のみエラーを発生させる
        def side_effect(sig: signal.Signals, _handler: signal.Handlers) -> None:
            if sig == signal.SIGPIPE:
                raise OSError("Cannot set SIGPIPE handler")

        mock_signal.side_effect = side_effect

        # エラーが発生しても起動する
        await main()

        mock_bot.start.assert_awaited_once()
