"""Tests for database service."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database.models import Base
from src.services.db_service import (
    create_lobby,
    create_voice_session,
    delete_lobby,
    delete_voice_session,
    get_all_voice_sessions,
    get_lobbies_by_guild,
    get_lobby_by_channel_id,
    get_voice_session,
    update_voice_session,
)


@pytest.fixture
async def db_session() -> AsyncSession:
    """Create an in-memory SQLite async session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session


class TestLobbyOperations:
    """Tests for lobby database operations."""

    async def test_create_lobby(self, db_session: AsyncSession) -> None:
        """Test creating a lobby."""
        lobby = await create_lobby(
            db_session,
            guild_id="123",
            lobby_channel_id="456",
            category_id="789",
            default_user_limit=10,
        )
        assert lobby.id is not None
        assert lobby.guild_id == "123"
        assert lobby.lobby_channel_id == "456"
        assert lobby.category_id == "789"
        assert lobby.default_user_limit == 10

    async def test_get_lobby_by_channel_id(self, db_session: AsyncSession) -> None:
        """Test getting a lobby by channel ID."""
        await create_lobby(db_session, guild_id="123", lobby_channel_id="456")

        lobby = await get_lobby_by_channel_id(db_session, "456")
        assert lobby is not None
        assert lobby.guild_id == "123"

    async def test_get_lobby_by_channel_id_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting a non-existent lobby."""
        lobby = await get_lobby_by_channel_id(db_session, "nonexistent")
        assert lobby is None

    async def test_get_lobbies_by_guild(self, db_session: AsyncSession) -> None:
        """Test getting all lobbies for a guild."""
        await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        await create_lobby(db_session, guild_id="123", lobby_channel_id="789")
        await create_lobby(db_session, guild_id="999", lobby_channel_id="111")

        lobbies = await get_lobbies_by_guild(db_session, "123")
        assert len(lobbies) == 2

    async def test_delete_lobby(self, db_session: AsyncSession) -> None:
        """Test deleting a lobby."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")

        result = await delete_lobby(db_session, lobby.id)
        assert result is True

        found = await get_lobby_by_channel_id(db_session, "456")
        assert found is None

    async def test_delete_lobby_not_found(self, db_session: AsyncSession) -> None:
        """Test deleting a non-existent lobby."""
        result = await delete_lobby(db_session, 99999)
        assert result is False


class TestVoiceSessionOperations:
    """Tests for voice session database operations."""

    async def test_create_voice_session(self, db_session: AsyncSession) -> None:
        """Test creating a voice session."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")

        session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
            user_limit=5,
        )

        assert session.id is not None
        assert session.channel_id == "789"
        assert session.owner_id == "111"
        assert session.name == "Test Channel"
        assert session.user_limit == 5

    async def test_get_voice_session(self, db_session: AsyncSession) -> None:
        """Test getting a voice session."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        found = await get_voice_session(db_session, "789")
        assert found is not None
        assert found.owner_id == "111"

    async def test_get_voice_session_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting a non-existent voice session."""
        found = await get_voice_session(db_session, "nonexistent")
        assert found is None

    async def test_get_all_voice_sessions(self, db_session: AsyncSession) -> None:
        """Test getting all voice sessions."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Channel 1",
        )
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="790",
            owner_id="222",
            name="Channel 2",
        )

        sessions = await get_all_voice_sessions(db_session)
        assert len(sessions) == 2

    async def test_update_voice_session(self, db_session: AsyncSession) -> None:
        """Test updating a voice session."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        updated = await update_voice_session(
            db_session,
            session,
            name="New Name",
            user_limit=10,
            is_locked=True,
            is_hidden=True,
            owner_id="222",
        )

        assert updated.name == "New Name"
        assert updated.user_limit == 10
        assert updated.is_locked is True
        assert updated.is_hidden is True
        assert updated.owner_id == "222"

    async def test_update_voice_session_name_only(
        self, db_session: AsyncSession
    ) -> None:
        """Test updating only the name."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Original",
        )

        updated = await update_voice_session(
            db_session, session, name="Renamed"
        )

        assert updated.name == "Renamed"
        assert updated.owner_id == "111"
        assert updated.is_locked is False

    async def test_update_voice_session_owner_only(
        self, db_session: AsyncSession
    ) -> None:
        """Test updating only the owner_id."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test",
        )

        updated = await update_voice_session(
            db_session, session, owner_id="222"
        )

        assert updated.owner_id == "222"
        assert updated.name == "Test"

    async def test_update_voice_session_no_changes(
        self, db_session: AsyncSession
    ) -> None:
        """Test updating with no fields changed."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test",
        )

        updated = await update_voice_session(db_session, session)

        assert updated.name == "Test"
        assert updated.owner_id == "111"

    async def test_update_voice_session_text_channel_id(
        self, db_session: AsyncSession
    ) -> None:
        """Test setting text_channel_id."""
        lobby = await create_lobby(
            db_session, guild_id="123", lobby_channel_id="456"
        )
        session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test",
        )
        assert session.text_channel_id is None

        updated = await update_voice_session(
            db_session, session, text_channel_id="999"
        )
        assert updated.text_channel_id == "999"

    async def test_update_voice_session_clear_text_channel_id(
        self, db_session: AsyncSession
    ) -> None:
        """Test clearing text_channel_id."""
        lobby = await create_lobby(
            db_session, guild_id="123", lobby_channel_id="456"
        )
        session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test",
        )
        await update_voice_session(
            db_session, session, text_channel_id="999"
        )

        updated = await update_voice_session(
            db_session, session, text_channel_id=None
        )
        assert updated.text_channel_id is None

    async def test_delete_voice_session(self, db_session: AsyncSession) -> None:
        """Test deleting a voice session."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        result = await delete_voice_session(db_session, "789")
        assert result is True

        found = await get_voice_session(db_session, "789")
        assert found is None

    async def test_delete_voice_session_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting a non-existent voice session."""
        result = await delete_voice_session(db_session, "nonexistent")
        assert result is False

    async def test_voice_session_default_values(
        self, db_session: AsyncSession
    ) -> None:
        """Test that default values are set correctly."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        assert session.is_locked is False
        assert session.is_hidden is False
        assert session.user_limit == 0
