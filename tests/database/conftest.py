"""Database test fixtures with factory helpers."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from faker import Faker
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.constants import DEFAULT_TEST_DATABASE_URL
from src.database.models import Base, Lobby, VoiceSession
from src.services.db_service import create_lobby, create_voice_session

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

    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
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
async def voice_session(
    db_session: AsyncSession, lobby: Lobby
) -> VoiceSession:
    """テスト用 VoiceSession を1つ作成して返す。"""
    return await create_voice_session(
        db_session,
        lobby_id=lobby.id,
        channel_id=snowflake(),
        owner_id=snowflake(),
        name=fake.word(),
    )
