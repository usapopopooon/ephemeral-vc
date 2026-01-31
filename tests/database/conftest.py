"""Database test fixtures with factory helpers."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from faker import Faker
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.constants import DEFAULT_TEST_DATABASE_URL
from src.database.models import (
    Base,
    BumpConfig,
    BumpReminder,
    Lobby,
    StickyMessage,
    VoiceSession,
    VoiceSessionMember,
)
from src.services.db_service import (
    add_voice_session_member,
    create_lobby,
    create_sticky_message,
    create_voice_session,
    upsert_bump_config,
    upsert_bump_reminder,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

fake = Faker()

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    DEFAULT_TEST_DATABASE_URL,
)


def snowflake() -> str:
    """Discord snowflake 風の ID を生成する。"""
    return str(fake.random_number(digits=18, fix_len=True))


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """PostgreSQL テスト DB のセッションを提供する。"""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def lobby(db_session: AsyncSession) -> Lobby:
    """テスト用ロビーを1つ作成して返す。"""
    return await create_lobby(
        db_session,
        guild_id=snowflake(),
        lobby_channel_id=snowflake(),
    )


@pytest.fixture
async def voice_session(db_session: AsyncSession, lobby: Lobby) -> VoiceSession:
    """テスト用 VoiceSession を1つ作成して返す。"""
    return await create_voice_session(
        db_session,
        lobby_id=lobby.id,
        channel_id=snowflake(),
        owner_id=snowflake(),
        name=fake.word(),
    )


@pytest.fixture
async def voice_session_member(
    db_session: AsyncSession, voice_session: VoiceSession
) -> VoiceSessionMember:
    """テスト用 VoiceSessionMember を1つ作成して返す。"""
    return await add_voice_session_member(
        db_session,
        voice_session_id=voice_session.id,
        user_id=snowflake(),
    )


@pytest.fixture
async def bump_reminder(db_session: AsyncSession) -> BumpReminder:
    """テスト用 BumpReminder を1つ作成して返す。"""
    return await upsert_bump_reminder(
        db_session,
        guild_id=snowflake(),
        channel_id=snowflake(),
        service_name=fake.random_element(elements=["DISBOARD", "ディス速報"]),
        remind_at=datetime.now(UTC) + timedelta(hours=2),
    )


@pytest.fixture
async def bump_config(db_session: AsyncSession) -> BumpConfig:
    """テスト用 BumpConfig を1つ作成して返す。"""
    return await upsert_bump_config(
        db_session,
        guild_id=snowflake(),
        channel_id=snowflake(),
    )


@pytest.fixture
async def sticky_message(db_session: AsyncSession) -> StickyMessage:
    """テスト用 StickyMessage を1つ作成して返す。"""
    return await create_sticky_message(
        db_session,
        channel_id=snowflake(),
        guild_id=snowflake(),
        title=fake.sentence(nb_words=3),
        description=fake.paragraph(),
        color=fake.random_int(min=0, max=0xFFFFFF),
        cooldown_seconds=fake.random_int(min=1, max=60),
        message_type=fake.random_element(elements=["embed", "text"]),
    )
