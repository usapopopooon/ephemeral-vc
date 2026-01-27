"""Tests for configuration settings."""

import os

# Set dummy token before importing Settings to avoid module-level error
os.environ.setdefault("DISCORD_TOKEN", "test-token")

from src.config import Settings  # noqa: E402


class TestAsyncDatabaseUrl:
    """Tests for async_database_url property."""

    def test_sqlite_url_unchanged(self) -> None:
        """Test that SQLite URLs are not modified."""
        s = Settings(
            discord_token="test",
            database_url="sqlite+aiosqlite:///data/test.db",
        )
        assert s.async_database_url == "sqlite+aiosqlite:///data/test.db"

    def test_heroku_postgres_url_converted(self) -> None:
        """Test Heroku postgres:// is converted to postgresql+asyncpg://."""
        s = Settings(
            discord_token="test",
            database_url="postgres://user:pass@host:5432/db",
        )
        assert s.async_database_url == (
            "postgresql+asyncpg://user:pass@host:5432/db"
        )

    def test_postgresql_url_converted(self) -> None:
        """Test postgresql:// is converted to postgresql+asyncpg://."""
        s = Settings(
            discord_token="test",
            database_url="postgresql://user:pass@host:5432/db",
        )
        assert s.async_database_url == (
            "postgresql+asyncpg://user:pass@host:5432/db"
        )

    def test_already_async_url_unchanged(self) -> None:
        """Test that postgresql+asyncpg:// URLs are not modified."""
        s = Settings(
            discord_token="test",
            database_url="postgresql+asyncpg://user:pass@host:5432/db",
        )
        assert s.async_database_url == (
            "postgresql+asyncpg://user:pass@host:5432/db"
        )

    def test_default_database_url(self) -> None:
        """Test the default database URL."""
        s = Settings(discord_token="test")
        assert s.database_url == "sqlite+aiosqlite:///data/ephemeral_vc.db"
