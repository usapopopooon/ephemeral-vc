"""Tests for database engine module."""

from __future__ import annotations

import ssl
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.database.models import Base

from .conftest import TEST_DATABASE_URL

# ===========================================================================
# Heroku / SSL configuration テスト
# ===========================================================================


class TestSSLConfiguration:
    """SSL 設定のテスト。"""

    def test_get_connect_args_without_ssl(self) -> None:
        """DATABASE_REQUIRE_SSL が設定されていない場合、空の dict を返す。"""
        with patch.dict("os.environ", {}, clear=True):
            # モジュールを再読み込みして環境変数の変更を反映
            import importlib

            import src.database.engine as engine_module

            importlib.reload(engine_module)

            # SSL なしの場合は空の dict
            result = engine_module._get_connect_args()
            assert result == {}

    def test_get_connect_args_with_ssl(self) -> None:
        """DATABASE_REQUIRE_SSL=true の場合、SSL コンテキストを返す。"""
        with patch.dict("os.environ", {"DATABASE_REQUIRE_SSL": "true"}):
            import importlib

            import src.database.engine as engine_module

            importlib.reload(engine_module)

            result = engine_module._get_connect_args()
            assert "ssl" in result
            assert isinstance(result["ssl"], ssl.SSLContext)

    def test_get_connect_args_ssl_context_settings(self) -> None:
        """SSL コンテキストが正しく設定されている。"""
        with patch.dict("os.environ", {"DATABASE_REQUIRE_SSL": "true"}):
            import importlib

            import src.database.engine as engine_module

            importlib.reload(engine_module)

            result = engine_module._get_connect_args()
            ssl_ctx = result["ssl"]
            # Heroku の自己署名証明書のため検証をスキップ
            assert ssl_ctx.check_hostname is False
            assert ssl_ctx.verify_mode == ssl.CERT_NONE


class TestConnectionPoolConfiguration:
    """コネクションプール設定のテスト。"""

    def test_default_pool_size(self) -> None:
        """デフォルトのプールサイズが設定される。"""
        with patch.dict("os.environ", {}, clear=True):
            import importlib

            import src.database.engine as engine_module

            importlib.reload(engine_module)

            assert engine_module.POOL_SIZE == 5
            assert engine_module.MAX_OVERFLOW == 10

    def test_custom_pool_size(self) -> None:
        """環境変数でプールサイズをカスタマイズできる。"""
        with patch.dict("os.environ", {"DB_POOL_SIZE": "10", "DB_MAX_OVERFLOW": "20"}):
            import importlib

            import src.database.engine as engine_module

            importlib.reload(engine_module)

            assert engine_module.POOL_SIZE == 10
            assert engine_module.MAX_OVERFLOW == 20


class TestParseIntEnv:
    """_parse_int_env 関数のテスト (Linux 互換性)。"""

    def test_returns_value_when_valid_integer(self) -> None:
        """有効な整数値の場合、その値を返す。"""
        with patch.dict("os.environ", {"TEST_VAR": "42"}):
            import importlib

            import src.database.engine as engine_module

            importlib.reload(engine_module)

            result = engine_module._parse_int_env("TEST_VAR", 10)
            assert result == 42

    def test_returns_default_when_env_not_set(self) -> None:
        """環境変数が設定されていない場合、デフォルト値を返す。"""
        with patch.dict("os.environ", {}, clear=True):
            import importlib

            import src.database.engine as engine_module

            importlib.reload(engine_module)

            result = engine_module._parse_int_env("NONEXISTENT_VAR", 99)
            assert result == 99

    def test_returns_default_when_empty_string(self) -> None:
        """空文字列の場合、デフォルト値を返す。"""
        with patch.dict("os.environ", {"TEST_VAR": ""}):
            import importlib

            import src.database.engine as engine_module

            importlib.reload(engine_module)

            result = engine_module._parse_int_env("TEST_VAR", 77)
            assert result == 77

    def test_returns_default_when_whitespace_only(self) -> None:
        """空白のみの場合、デフォルト値を返す。"""
        with patch.dict("os.environ", {"TEST_VAR": "   "}):
            import importlib

            import src.database.engine as engine_module

            importlib.reload(engine_module)

            result = engine_module._parse_int_env("TEST_VAR", 55)
            assert result == 55

    def test_returns_default_when_invalid_value(self) -> None:
        """無効な値の場合、デフォルト値を返す (警告ログ出力)。"""
        with patch.dict("os.environ", {"TEST_VAR": "not_a_number"}):
            import importlib

            import src.database.engine as engine_module

            importlib.reload(engine_module)

            result = engine_module._parse_int_env("TEST_VAR", 33)
            assert result == 33

    def test_returns_default_when_float_value(self) -> None:
        """浮動小数点の場合、デフォルト値を返す。"""
        with patch.dict("os.environ", {"TEST_VAR": "3.14"}):
            import importlib

            import src.database.engine as engine_module

            importlib.reload(engine_module)

            result = engine_module._parse_int_env("TEST_VAR", 11)
            assert result == 11

    def test_handles_negative_values(self) -> None:
        """負の値も正しくパースされる。"""
        with patch.dict("os.environ", {"TEST_VAR": "-5"}):
            import importlib

            import src.database.engine as engine_module

            importlib.reload(engine_module)

            result = engine_module._parse_int_env("TEST_VAR", 10)
            assert result == -5

    def test_strips_whitespace(self) -> None:
        """前後の空白は除去される。"""
        with patch.dict("os.environ", {"TEST_VAR": "  42  "}):
            import importlib

            import src.database.engine as engine_module

            importlib.reload(engine_module)

            result = engine_module._parse_int_env("TEST_VAR", 10)
            assert result == 42


# ===========================================================================
# init_db テスト
# ===========================================================================


class TestInitDb:
    """Tests for init_db()."""

    @patch("src.database.engine.engine")
    async def test_creates_all_tables(self, mock_engine: MagicMock) -> None:
        """Base.metadata.create_all が呼ばれる。"""
        from src.database.engine import init_db

        mock_conn = AsyncMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)

        await init_db()

        mock_conn.run_sync.assert_awaited_once()

    async def test_idempotent(self) -> None:
        """init_db を2回呼んでもエラーにならない (冪等性)。"""
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)

            # 1回目: テーブル作成
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # 2回目: 既存テーブルがあっても問題なし
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    async def test_tables_exist_after_init(self) -> None:
        """init_db 後にテーブルが実際に存在する。"""
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)

            from sqlalchemy import inspect as sa_inspect

            async with engine.connect() as conn:
                tables = await conn.run_sync(
                    lambda sync_conn: sa_inspect(sync_conn).get_table_names()
                )

            assert "lobbies" in tables
            assert "voice_sessions" in tables
        finally:
            await engine.dispose()


# ===========================================================================
# get_session テスト
# ===========================================================================


class TestGetSession:
    """Tests for get_session()."""

    @patch("src.database.engine.async_session")
    async def test_returns_session(self, mock_factory: MagicMock) -> None:
        """AsyncSession が返される。"""
        from src.database.engine import get_session

        mock_session = AsyncMock(spec=AsyncSession)
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await get_session()

        assert result is mock_session
