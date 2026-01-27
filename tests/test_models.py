"""Tests for database models."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database.models import Base, Lobby, VoiceSession


@pytest.fixture
async def db_session() -> AsyncSession:
    """Create an in-memory SQLite async session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


class TestLobbyModel:
    """Tests for the Lobby model."""

    async def test_repr(self, db_session: AsyncSession) -> None:
        """Test Lobby __repr__ output."""
        lobby = Lobby(
            guild_id="123", lobby_channel_id="456"
        )
        db_session.add(lobby)
        await db_session.commit()

        assert "guild_id=123" in repr(lobby)
        assert "channel_id=456" in repr(lobby)

    async def test_default_user_limit(self, db_session: AsyncSession) -> None:
        """Test default_user_limit defaults to 0."""
        lobby = Lobby(
            guild_id="123", lobby_channel_id="456"
        )
        db_session.add(lobby)
        await db_session.commit()

        assert lobby.default_user_limit == 0

    async def test_category_id_nullable(self, db_session: AsyncSession) -> None:
        """Test category_id can be None."""
        lobby = Lobby(
            guild_id="123", lobby_channel_id="456"
        )
        db_session.add(lobby)
        await db_session.commit()

        assert lobby.category_id is None

    async def test_category_id_set(self, db_session: AsyncSession) -> None:
        """Test category_id can be set."""
        lobby = Lobby(
            guild_id="123",
            lobby_channel_id="456",
            category_id="789",
        )
        db_session.add(lobby)
        await db_session.commit()

        assert lobby.category_id == "789"


class TestVoiceSessionModel:
    """Tests for the VoiceSession model."""

    async def test_repr(self, db_session: AsyncSession) -> None:
        """Test VoiceSession __repr__ output."""
        lobby = Lobby(
            guild_id="123", lobby_channel_id="456"
        )
        db_session.add(lobby)
        await db_session.commit()

        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test",
        )
        db_session.add(session)
        await db_session.commit()

        assert "channel_id=789" in repr(session)
        assert "owner_id=111" in repr(session)

    async def test_default_is_locked(self, db_session: AsyncSession) -> None:
        """Test is_locked defaults to False."""
        lobby = Lobby(guild_id="123", lobby_channel_id="456")
        db_session.add(lobby)
        await db_session.commit()

        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test",
        )
        db_session.add(session)
        await db_session.commit()

        assert session.is_locked is False

    async def test_default_is_hidden(self, db_session: AsyncSession) -> None:
        """Test is_hidden defaults to False."""
        lobby = Lobby(guild_id="123", lobby_channel_id="456")
        db_session.add(lobby)
        await db_session.commit()

        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test",
        )
        db_session.add(session)
        await db_session.commit()

        assert session.is_hidden is False

    async def test_default_user_limit(
        self, db_session: AsyncSession
    ) -> None:
        """Test user_limit defaults to 0."""
        lobby = Lobby(guild_id="123", lobby_channel_id="456")
        db_session.add(lobby)
        await db_session.commit()

        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test",
        )
        db_session.add(session)
        await db_session.commit()

        assert session.user_limit == 0

    async def test_created_at_auto_set(
        self, db_session: AsyncSession
    ) -> None:
        """Test created_at is automatically set."""
        lobby = Lobby(
            guild_id="123", lobby_channel_id="456"
        )
        db_session.add(lobby)
        await db_session.commit()

        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test",
        )
        db_session.add(session)
        await db_session.commit()

        assert session.created_at is not None

    async def test_created_at_has_timezone(
        self, db_session: AsyncSession
    ) -> None:
        """Test created_at is timezone-aware."""
        lobby = Lobby(guild_id="123", lobby_channel_id="456")
        db_session.add(lobby)
        await db_session.commit()

        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test",
        )
        db_session.add(session)
        await db_session.commit()

        assert session.created_at is not None
        assert session.created_at.tzinfo is not None

    async def test_cascade_delete(
        self, db_session: AsyncSession
    ) -> None:
        """Test that deleting a lobby cascades to voice sessions."""
        lobby = Lobby(
            guild_id="123", lobby_channel_id="456"
        )
        db_session.add(lobby)
        await db_session.commit()

        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test",
        )
        db_session.add(session)
        await db_session.commit()

        await db_session.delete(lobby)
        await db_session.commit()

        from sqlalchemy import select

        result = await db_session.execute(
            select(VoiceSession).where(
                VoiceSession.channel_id == "789"
            )
        )
        assert result.scalar_one_or_none() is None
