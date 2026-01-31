"""Tests for web app lifespan handler.

Note: These tests use logger mocking to be more robust when running with
the full test suite and coverage.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch


class TestLifespanHandler:
    """lifespan ハンドラのテスト。"""

    async def test_lifespan_logs_startup_success(self) -> None:
        """起動時にログメソッドが呼ばれる。"""
        from fastapi import FastAPI

        from src.web.app import lifespan

        test_app = FastAPI()

        # ログ出力と check_database_connection をモック
        with (
            patch(
                "src.web.app.check_database_connection", new_callable=AsyncMock
            ) as mock_check_db,
            patch("src.web.app.logger") as mock_logger,
        ):
            mock_check_db.return_value = True

            async with lifespan(test_app):
                pass

            # 起動・終了のログが呼ばれる
            mock_logger.info.assert_any_call("Starting web admin application...")
            mock_logger.info.assert_any_call("Shutting down web admin application...")

    async def test_lifespan_logs_db_connection_success(self) -> None:
        """データベース接続成功時にログメソッドが呼ばれる。"""
        from fastapi import FastAPI

        from src.web.app import lifespan

        test_app = FastAPI()

        # check_database_connection が True を返すようにモック
        with (
            patch(
                "src.web.app.check_database_connection", new_callable=AsyncMock
            ) as mock_check_db,
            patch("src.web.app.logger") as mock_logger,
        ):
            mock_check_db.return_value = True

            async with lifespan(test_app):
                pass

            mock_logger.info.assert_any_call("Database connection successful")
            mock_check_db.assert_awaited_once()

    async def test_lifespan_logs_db_connection_failure(self) -> None:
        """データベース接続失敗時にエラーログが呼ばれる。"""
        from fastapi import FastAPI

        from src.web.app import lifespan

        test_app = FastAPI()

        # check_database_connection が False を返すようにモック
        with (
            patch(
                "src.web.app.check_database_connection", new_callable=AsyncMock
            ) as mock_check_db,
            patch("src.web.app.logger") as mock_logger,
        ):
            mock_check_db.return_value = False

            async with lifespan(test_app):
                pass

            # エラーログが呼ばれる
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args[0][0]
            assert "Database connection failed" in call_args
            mock_check_db.assert_awaited_once()

    async def test_lifespan_continues_on_db_failure(self) -> None:
        """データベース接続失敗時もアプリは起動を続ける。"""
        from fastapi import FastAPI

        from src.web.app import lifespan

        test_app = FastAPI()

        # check_database_connection が False を返すようにモック
        with patch(
            "src.web.app.check_database_connection", new_callable=AsyncMock
        ) as mock_check_db:
            mock_check_db.return_value = False
            # 例外が発生しないことを確認
            async with lifespan(test_app):
                pass  # 正常に完了すればOK
