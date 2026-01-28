"""Shared pytest fixtures."""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.constants import DEFAULT_TEST_DATABASE_URL_SYNC
from src.database.models import Base, Lobby

TEST_DATABASE_URL_SYNC = os.environ.get(
    "TEST_DATABASE_URL_SYNC",
    DEFAULT_TEST_DATABASE_URL_SYNC,
)


@pytest.fixture
def db_session() -> Session:
    """Create a PostgreSQL session for testing."""
    engine = create_engine(TEST_DATABASE_URL_SYNC)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        # Create a test lobby
        lobby = Lobby(guild_id="123456789", lobby_channel_id="987654321")
        session.add(lobby)
        session.commit()
        yield session
