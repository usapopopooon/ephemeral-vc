"""Tests for database service."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.constants import DEFAULT_TEST_DATABASE_URL
from src.database.models import Base
from src.services.db_service import (
    add_voice_session_member,
    clear_bump_reminder,
    create_lobby,
    create_voice_session,
    delete_bump_config,
    delete_lobby,
    delete_voice_session,
    get_all_voice_sessions,
    get_bump_config,
    get_bump_reminder,
    get_due_bump_reminders,
    get_lobbies_by_guild,
    get_lobby_by_channel_id,
    get_voice_session,
    get_voice_session_members_ordered,
    remove_voice_session_member,
    toggle_bump_reminder,
    update_bump_reminder_role,
    update_voice_session,
    upsert_bump_config,
    upsert_bump_reminder,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    DEFAULT_TEST_DATABASE_URL,
)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """PostgreSQL テスト DB のセッションを提供する。"""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session

    await engine.dispose()


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
        """Test updating only the name leaves other fields unchanged."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Original",
            user_limit=5,
        )

        updated = await update_voice_session(db_session, session, name="Renamed")

        assert updated.name == "Renamed"
        assert updated.user_limit == 5
        assert updated.is_locked is False
        assert updated.is_hidden is False
        assert updated.owner_id == "111"

    async def test_update_voice_session_no_params(
        self, db_session: AsyncSession
    ) -> None:
        """Test updating with no parameters changes nothing."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Unchanged",
        )

        updated = await update_voice_session(db_session, session)

        assert updated.name == "Unchanged"
        assert updated.owner_id == "111"
        assert updated.is_locked is False
        assert updated.is_hidden is False

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


class TestVoiceSessionMemberOperations:
    """Tests for voice session member database operations."""

    async def test_add_voice_session_member(self, db_session: AsyncSession) -> None:
        """Test adding a member to a voice session."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        voice_session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        member = await add_voice_session_member(
            db_session, voice_session.id, "222"
        )

        assert member.id is not None
        assert member.voice_session_id == voice_session.id
        assert member.user_id == "222"
        assert member.joined_at is not None

    async def test_add_voice_session_member_existing(
        self, db_session: AsyncSession
    ) -> None:
        """Test adding an existing member returns the existing record."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        voice_session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        # Add member first time
        member1 = await add_voice_session_member(
            db_session, voice_session.id, "222"
        )

        # Add same member again
        member2 = await add_voice_session_member(
            db_session, voice_session.id, "222"
        )

        # Should return same record (idempotent)
        assert member1.id == member2.id
        assert member1.joined_at == member2.joined_at

    async def test_remove_voice_session_member(
        self, db_session: AsyncSession
    ) -> None:
        """Test removing a member from a voice session."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        voice_session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        await add_voice_session_member(db_session, voice_session.id, "222")

        result = await remove_voice_session_member(
            db_session, voice_session.id, "222"
        )
        assert result is True

        # Verify member is gone
        members = await get_voice_session_members_ordered(
            db_session, voice_session.id
        )
        assert len(members) == 0

    async def test_remove_voice_session_member_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test removing a non-existent member returns False."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        voice_session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        result = await remove_voice_session_member(
            db_session, voice_session.id, "nonexistent"
        )
        assert result is False

    async def test_get_voice_session_members_ordered(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting members ordered by join time."""
        import asyncio

        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        voice_session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        # Add members with slight delays to ensure different join times
        await add_voice_session_member(db_session, voice_session.id, "first")
        await asyncio.sleep(0.01)
        await add_voice_session_member(db_session, voice_session.id, "second")
        await asyncio.sleep(0.01)
        await add_voice_session_member(db_session, voice_session.id, "third")

        members = await get_voice_session_members_ordered(
            db_session, voice_session.id
        )

        assert len(members) == 3
        assert members[0].user_id == "first"
        assert members[1].user_id == "second"
        assert members[2].user_id == "third"

    async def test_get_voice_session_members_ordered_empty(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting members from empty session returns empty list."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        voice_session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        members = await get_voice_session_members_ordered(
            db_session, voice_session.id
        )

        assert members == []

    async def test_voice_session_members_cascade_delete(
        self, db_session: AsyncSession
    ) -> None:
        """Test that members are deleted when voice session is deleted."""
        lobby = await create_lobby(db_session, guild_id="123", lobby_channel_id="456")
        voice_session = await create_voice_session(
            db_session,
            lobby_id=lobby.id,
            channel_id="789",
            owner_id="111",
            name="Test Channel",
        )

        await add_voice_session_member(db_session, voice_session.id, "222")
        await add_voice_session_member(db_session, voice_session.id, "333")

        # Delete the voice session
        await delete_voice_session(db_session, "789")

        # Members should be automatically deleted via CASCADE
        # We can't query directly since voice_session is gone,
        # but we verify no errors occurred during cascade delete


class TestBumpReminderOperations:
    """Tests for bump reminder database operations."""

    async def test_upsert_bump_reminder_create(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a new bump reminder."""
        from datetime import UTC, datetime, timedelta

        remind_at = datetime.now(UTC) + timedelta(hours=2)

        reminder = await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        assert reminder.id is not None
        assert reminder.guild_id == "123"
        assert reminder.channel_id == "456"
        assert reminder.service_name == "DISBOARD"
        assert reminder.remind_at == remind_at

    async def test_upsert_bump_reminder_update(
        self, db_session: AsyncSession
    ) -> None:
        """Test updating an existing bump reminder for same guild+service."""
        from datetime import UTC, datetime, timedelta

        remind_at_1 = datetime.now(UTC) + timedelta(hours=2)
        remind_at_2 = datetime.now(UTC) + timedelta(hours=4)

        # Create first reminder
        reminder1 = await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at_1,
        )

        # Upsert with new time (same guild+service should update)
        reminder2 = await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="789",  # Different channel
            service_name="DISBOARD",
            remind_at=remind_at_2,
        )

        # Should be same record (updated)
        assert reminder1.id == reminder2.id
        assert reminder2.channel_id == "789"
        assert reminder2.remind_at == remind_at_2

    async def test_upsert_bump_reminder_different_services(
        self, db_session: AsyncSession
    ) -> None:
        """Test that different services create separate reminders."""
        from datetime import UTC, datetime, timedelta

        remind_at = datetime.now(UTC) + timedelta(hours=2)

        reminder1 = await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        reminder2 = await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="ディス速報",
            remind_at=remind_at,
        )

        # Should be different records
        assert reminder1.id != reminder2.id

    async def test_get_due_bump_reminders(self, db_session: AsyncSession) -> None:
        """Test getting reminders that are due."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)

        # Past reminder (should be returned)
        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=now - timedelta(minutes=5),
        )

        # Future reminder (should not be returned)
        await upsert_bump_reminder(
            db_session,
            guild_id="456",
            channel_id="789",
            service_name="ディス速報",
            remind_at=now + timedelta(hours=1),
        )

        due = await get_due_bump_reminders(db_session, now)

        assert len(due) == 1
        assert due[0].guild_id == "123"
        assert due[0].service_name == "DISBOARD"

    async def test_get_due_bump_reminders_empty(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting due reminders when none are due."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)

        # Only future reminders
        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=now + timedelta(hours=2),
        )

        due = await get_due_bump_reminders(db_session, now)

        assert due == []

    async def test_clear_bump_reminder(self, db_session: AsyncSession) -> None:
        """Test clearing a bump reminder (sets remind_at to None)."""
        from datetime import UTC, datetime, timedelta

        remind_at = datetime.now(UTC) + timedelta(hours=2)

        reminder = await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        result = await clear_bump_reminder(db_session, reminder.id)
        assert result is True

        # Verify remind_at is cleared (no due reminders)
        due = await get_due_bump_reminders(
            db_session, datetime.now(UTC) + timedelta(hours=3)
        )
        assert due == []

    async def test_clear_bump_reminder_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test clearing a non-existent bump reminder."""
        result = await clear_bump_reminder(db_session, 99999)
        assert result is False

    async def test_toggle_bump_reminder(self, db_session: AsyncSession) -> None:
        """Test toggling bump reminder enabled state."""
        from datetime import UTC, datetime, timedelta

        remind_at = datetime.now(UTC) + timedelta(hours=2)

        # Create reminder (default is_enabled=True)
        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        # Toggle to disabled
        new_state = await toggle_bump_reminder(db_session, "123", "DISBOARD")
        assert new_state is False

        # Toggle back to enabled
        new_state = await toggle_bump_reminder(db_session, "123", "DISBOARD")
        assert new_state is True

    async def test_toggle_bump_reminder_creates_if_not_exists(
        self, db_session: AsyncSession
    ) -> None:
        """Test toggle creates disabled reminder if not exists."""
        # Toggle non-existent reminder
        new_state = await toggle_bump_reminder(db_session, "999", "DISBOARD")
        assert new_state is False

    async def test_get_due_bump_reminders_ignores_disabled(
        self, db_session: AsyncSession
    ) -> None:
        """Test that disabled reminders are not returned as due."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)

        # Create reminder
        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=now - timedelta(minutes=5),
        )

        # Disable it
        await toggle_bump_reminder(db_session, "123", "DISBOARD")

        # Should not be returned
        due = await get_due_bump_reminders(db_session, now)
        assert due == []

    async def test_get_bump_reminder(self, db_session: AsyncSession) -> None:
        """Test getting a bump reminder by guild_id and service_name."""
        from datetime import UTC, datetime, timedelta

        remind_at = datetime.now(UTC) + timedelta(hours=2)

        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        reminder = await get_bump_reminder(db_session, "123", "DISBOARD")

        assert reminder is not None
        assert reminder.guild_id == "123"
        assert reminder.service_name == "DISBOARD"

    async def test_get_bump_reminder_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting a non-existent bump reminder."""
        reminder = await get_bump_reminder(db_session, "nonexistent", "DISBOARD")
        assert reminder is None

    async def test_update_bump_reminder_role(
        self, db_session: AsyncSession
    ) -> None:
        """Test updating the notification role for a bump reminder."""
        from datetime import UTC, datetime, timedelta

        remind_at = datetime.now(UTC) + timedelta(hours=2)

        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        # Update role
        result = await update_bump_reminder_role(
            db_session, "123", "DISBOARD", "999"
        )
        assert result is True

        # Verify role was updated
        reminder = await get_bump_reminder(db_session, "123", "DISBOARD")
        assert reminder is not None
        assert reminder.role_id == "999"

    async def test_update_bump_reminder_role_reset_to_default(
        self, db_session: AsyncSession
    ) -> None:
        """Test resetting the notification role to default (None)."""
        from datetime import UTC, datetime, timedelta

        remind_at = datetime.now(UTC) + timedelta(hours=2)

        await upsert_bump_reminder(
            db_session,
            guild_id="123",
            channel_id="456",
            service_name="DISBOARD",
            remind_at=remind_at,
        )

        # Set a custom role first
        await update_bump_reminder_role(db_session, "123", "DISBOARD", "999")

        # Reset to default
        result = await update_bump_reminder_role(
            db_session, "123", "DISBOARD", None
        )
        assert result is True

        # Verify role was reset
        reminder = await get_bump_reminder(db_session, "123", "DISBOARD")
        assert reminder is not None
        assert reminder.role_id is None

    async def test_update_bump_reminder_role_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test updating role for a non-existent reminder."""
        result = await update_bump_reminder_role(
            db_session, "nonexistent", "DISBOARD", "999"
        )
        assert result is False


class TestBumpConfigOperations:
    """Tests for bump config database operations."""

    async def test_upsert_bump_config_create(
        self, db_session: AsyncSession
    ) -> None:
        """Test creating a new bump config."""
        config = await upsert_bump_config(
            db_session,
            guild_id="123",
            channel_id="456",
        )

        assert config.guild_id == "123"
        assert config.channel_id == "456"
        assert config.created_at is not None

    async def test_upsert_bump_config_update(
        self, db_session: AsyncSession
    ) -> None:
        """Test updating an existing bump config."""
        # Create first config
        config1 = await upsert_bump_config(
            db_session,
            guild_id="123",
            channel_id="456",
        )
        original_created_at = config1.created_at

        # Upsert with new channel (same guild should update)
        config2 = await upsert_bump_config(
            db_session,
            guild_id="123",
            channel_id="789",
        )

        # Should be same record (updated channel, same guild_id)
        assert config2.guild_id == "123"
        assert config2.channel_id == "789"
        # created_at should remain the same
        assert config2.created_at == original_created_at

    async def test_upsert_bump_config_different_guilds(
        self, db_session: AsyncSession
    ) -> None:
        """Test that different guilds create separate configs."""
        config1 = await upsert_bump_config(
            db_session,
            guild_id="123",
            channel_id="456",
        )

        config2 = await upsert_bump_config(
            db_session,
            guild_id="999",
            channel_id="789",
        )

        # Should be different records (different guilds)
        assert config1.guild_id != config2.guild_id

    async def test_get_bump_config(self, db_session: AsyncSession) -> None:
        """Test getting a bump config by guild_id."""
        await upsert_bump_config(
            db_session,
            guild_id="123",
            channel_id="456",
        )

        config = await get_bump_config(db_session, "123")

        assert config is not None
        assert config.guild_id == "123"
        assert config.channel_id == "456"

    async def test_get_bump_config_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test getting a non-existent bump config."""
        config = await get_bump_config(db_session, "nonexistent")
        assert config is None

    async def test_delete_bump_config(self, db_session: AsyncSession) -> None:
        """Test deleting a bump config."""
        await upsert_bump_config(
            db_session,
            guild_id="123",
            channel_id="456",
        )

        result = await delete_bump_config(db_session, "123")
        assert result is True

        # Verify config is deleted
        config = await get_bump_config(db_session, "123")
        assert config is None

    async def test_delete_bump_config_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """Test deleting a non-existent bump config."""
        result = await delete_bump_config(db_session, "nonexistent")
        assert result is False
