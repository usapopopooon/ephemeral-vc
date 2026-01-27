"""Database service functions with side effects."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Lobby, VoiceSession

_UNSET: Any = object()


async def get_lobby_by_channel_id(
    session: AsyncSession, channel_id: str
) -> Lobby | None:
    """Get a lobby by its channel ID.

    Args:
        session: Database session
        channel_id: The lobby channel ID

    Returns:
        The Lobby if found, None otherwise
    """
    result = await session.execute(
        select(Lobby).where(Lobby.lobby_channel_id == channel_id)
    )
    return result.scalar_one_or_none()


async def get_lobbies_by_guild(session: AsyncSession, guild_id: str) -> list[Lobby]:
    """Get all lobbies for a guild.

    Args:
        session: Database session
        guild_id: The guild ID

    Returns:
        List of lobbies
    """
    result = await session.execute(select(Lobby).where(Lobby.guild_id == guild_id))
    return list(result.scalars().all())


async def create_lobby(
    session: AsyncSession,
    guild_id: str,
    lobby_channel_id: str,
    category_id: str | None = None,
    default_user_limit: int = 0,
) -> Lobby:
    """Create a new lobby.

    Args:
        session: Database session
        guild_id: The guild ID
        lobby_channel_id: The lobby channel ID
        category_id: Optional category ID for created channels
        default_user_limit: Default user limit for created channels

    Returns:
        The created Lobby
    """
    lobby = Lobby(
        guild_id=guild_id,
        lobby_channel_id=lobby_channel_id,
        category_id=category_id,
        default_user_limit=default_user_limit,
    )
    session.add(lobby)
    await session.commit()
    await session.refresh(lobby)
    return lobby


async def delete_lobby(session: AsyncSession, lobby_id: int) -> bool:
    """Delete a lobby.

    Args:
        session: Database session
        lobby_id: The lobby ID

    Returns:
        True if deleted, False if not found
    """
    result = await session.execute(select(Lobby).where(Lobby.id == lobby_id))
    lobby = result.scalar_one_or_none()
    if lobby:
        await session.delete(lobby)
        await session.commit()
        return True
    return False


async def get_voice_session(
    session: AsyncSession, channel_id: str
) -> VoiceSession | None:
    """Get a voice session by channel ID.

    Args:
        session: Database session
        channel_id: The voice channel ID

    Returns:
        The VoiceSession if found, None otherwise
    """
    result = await session.execute(
        select(VoiceSession).where(VoiceSession.channel_id == channel_id)
    )
    return result.scalar_one_or_none()


async def get_all_voice_sessions(session: AsyncSession) -> list[VoiceSession]:
    """Get all active voice sessions.

    Args:
        session: Database session

    Returns:
        List of all voice sessions
    """
    result = await session.execute(select(VoiceSession))
    return list(result.scalars().all())


async def create_voice_session(
    session: AsyncSession,
    lobby_id: int,
    channel_id: str,
    owner_id: str,
    name: str,
    user_limit: int = 0,
) -> VoiceSession:
    """Create a new voice session.

    Args:
        session: Database session
        lobby_id: The parent lobby ID
        channel_id: The created voice channel ID
        owner_id: The owner's user ID
        name: The channel name
        user_limit: The user limit

    Returns:
        The created VoiceSession
    """
    voice_session = VoiceSession(
        lobby_id=lobby_id,
        channel_id=channel_id,
        owner_id=owner_id,
        name=name,
        user_limit=user_limit,
    )
    session.add(voice_session)
    await session.commit()
    await session.refresh(voice_session)
    return voice_session


async def update_voice_session(
    session: AsyncSession,
    voice_session: VoiceSession,
    *,
    name: str | None = None,
    user_limit: int | None = None,
    is_locked: bool | None = None,
    is_hidden: bool | None = None,
    owner_id: str | None = None,
    text_channel_id: str | None = _UNSET,
) -> VoiceSession:
    """Update a voice session.

    Args:
        session: Database session
        voice_session: The voice session to update
        name: New channel name
        user_limit: New user limit
        is_locked: New lock state
        is_hidden: New hidden state
        owner_id: New owner ID
        text_channel_id: New text channel ID (None to clear)

    Returns:
        The updated VoiceSession
    """
    if name is not None:
        voice_session.name = name
    if user_limit is not None:
        voice_session.user_limit = user_limit
    if is_locked is not None:
        voice_session.is_locked = is_locked
    if is_hidden is not None:
        voice_session.is_hidden = is_hidden
    if owner_id is not None:
        voice_session.owner_id = owner_id
    if text_channel_id is not _UNSET:
        voice_session.text_channel_id = text_channel_id

    await session.commit()
    await session.refresh(voice_session)
    return voice_session


async def delete_voice_session(session: AsyncSession, channel_id: str) -> bool:
    """Delete a voice session.

    Args:
        session: Database session
        channel_id: The voice channel ID

    Returns:
        True if deleted, False if not found
    """
    result = await session.execute(
        select(VoiceSession).where(VoiceSession.channel_id == channel_id)
    )
    voice_session = result.scalar_one_or_none()
    if voice_session:
        await session.delete(voice_session)
        await session.commit()
        return True
    return False
