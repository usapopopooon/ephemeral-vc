"""SQLAlchemy database models."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Lobby(Base):
    """Lobby VC configuration. One server can have multiple lobbies."""

    __tablename__ = "lobbies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    lobby_channel_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    category_id: Mapped[str | None] = mapped_column(String, nullable=True)
    default_user_limit: Mapped[int] = mapped_column(Integer, default=0)

    sessions: Mapped[list["VoiceSession"]] = relationship(
        "VoiceSession", back_populates="lobby", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Lobby(id={self.id}, guild_id={self.guild_id}, "
            f"channel_id={self.lobby_channel_id})>"
        )


class VoiceSession(Base):
    """Currently active voice channel session."""

    __tablename__ = "voice_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lobby_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lobbies.id"), nullable=False
    )
    channel_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    user_limit: Mapped[int] = mapped_column(Integer, default=0)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    text_channel_id: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    lobby: Mapped["Lobby"] = relationship("Lobby", back_populates="sessions")

    def __repr__(self) -> str:
        return (
            f"<VoiceSession(id={self.id}, channel_id={self.channel_id}, "
            f"owner_id={self.owner_id})>"
        )
