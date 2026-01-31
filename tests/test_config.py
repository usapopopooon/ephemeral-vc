"""Tests for configuration settings."""

from __future__ import annotations

import os

import pytest

# モジュールレベルのエラーを回避するため、Settings インポート前にダミートークンを設定
os.environ.setdefault("DISCORD_TOKEN", "test-token")

from src.config import Settings  # noqa: E402
from src.constants import DEFAULT_DATABASE_URL  # noqa: E402


class TestAsyncDatabaseUrl:
    """Tests for async_database_url property."""

    def test_heroku_postgres_url_converted(self) -> None:
        """Test Heroku postgres:// is converted to postgresql+asyncpg://."""
        s = Settings(
            discord_token="test",
            database_url="postgres://user:pass@host:5432/db",
        )
        assert s.async_database_url == ("postgresql+asyncpg://user:pass@host:5432/db")

    def test_postgresql_url_converted(self) -> None:
        """Test postgresql:// is converted to postgresql+asyncpg://."""
        s = Settings(
            discord_token="test",
            database_url="postgresql://user:pass@host:5432/db",
        )
        assert s.async_database_url == ("postgresql+asyncpg://user:pass@host:5432/db")

    def test_already_async_url_unchanged(self) -> None:
        """Test that postgresql+asyncpg:// URLs are not modified."""
        s = Settings(
            discord_token="test",
            database_url="postgresql+asyncpg://user:pass@host:5432/db",
        )
        assert s.async_database_url == ("postgresql+asyncpg://user:pass@host:5432/db")

    def test_default_database_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test the default database URL."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        s = Settings(discord_token="test", _env_file=None)  # type: ignore[call-arg]
        assert s.database_url == DEFAULT_DATABASE_URL

    def test_url_with_query_params(self) -> None:
        """クエリパラメータ付き URL が正しく変換される。"""
        s = Settings(
            discord_token="test",
            database_url="postgres://u:p@host/db?sslmode=require",
        )
        assert s.async_database_url == (
            "postgresql+asyncpg://u:p@host/db?sslmode=require"
        )

    def test_url_with_special_chars_in_password(self) -> None:
        """パスワードに特殊文字を含む URL が変換される。"""
        s = Settings(
            discord_token="test",
            database_url="postgresql://user:p%40ss@host:5432/db",
        )
        assert s.async_database_url == ("postgresql+asyncpg://user:p%40ss@host:5432/db")

    def test_url_without_port(self) -> None:
        """ポート省略の URL が変換される。"""
        s = Settings(
            discord_token="test",
            database_url="postgres://user@host/db",
        )
        assert s.async_database_url == "postgresql+asyncpg://user@host/db"

    def test_url_only_first_occurrence_replaced(self) -> None:
        """URL 先頭の postgres:// のみ置換される。"""
        s = Settings(
            discord_token="test",
            database_url="postgres://user@postgres/db",
        )
        assert s.async_database_url == ("postgresql+asyncpg://user@postgres/db")

    def test_async_url_preserves_path(self) -> None:
        """データベース名やパスが保持される。"""
        s = Settings(
            discord_token="test",
            database_url="postgresql://u:p@host:5432/my_long_db_name",
        )
        assert "my_long_db_name" in s.async_database_url


class TestHealthChannelId:
    """health_channel_id フィールドのテスト。"""

    def test_default_is_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """デフォルトは 0。"""
        monkeypatch.delenv("HEALTH_CHANNEL_ID", raising=False)
        s = Settings(
            discord_token="test",
            database_url="postgresql+asyncpg://x@y/z",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert s.health_channel_id == 0

    def test_custom_channel_id(self) -> None:
        """カスタム値を設定できる。"""
        s = Settings(
            discord_token="test",
            database_url="postgresql+asyncpg://x@y/z",
            health_channel_id=123456789,
        )
        assert s.health_channel_id == 123456789


class TestSettingsValidation:
    """Settings バリデーションのテスト。"""

    def test_discord_token_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """discord_token がないと ValidationError。"""
        from pydantic import ValidationError

        monkeypatch.delenv("DISCORD_TOKEN", raising=False)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_all_fields_set(self) -> None:
        """全フィールド明示指定で作成できる。"""
        s = Settings(
            discord_token="tok",
            database_url="postgresql+asyncpg://u@h/d",
            health_channel_id=42,
        )
        assert s.discord_token == "tok"
        assert s.database_url == "postgresql+asyncpg://u@h/d"
        assert s.health_channel_id == 42
