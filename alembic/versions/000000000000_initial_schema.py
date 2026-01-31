"""initial schema

Revision ID: 000000000000
Revises:
Create Date: 2026-01-31 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "000000000000"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # lobbies テーブル
    op.create_table(
        "lobbies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("guild_id", sa.String(), nullable=False),
        sa.Column("lobby_channel_id", sa.String(), nullable=False),
        sa.Column("category_id", sa.String(), nullable=True),
        sa.Column(
            "default_user_limit", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lobbies_guild_id"), "lobbies", ["guild_id"], unique=False)
    op.create_index(
        op.f("ix_lobbies_lobby_channel_id"),
        "lobbies",
        ["lobby_channel_id"],
        unique=True,
    )

    # voice_sessions テーブル
    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lobby_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("user_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lobby_id"], ["lobbies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_voice_sessions_channel_id"),
        "voice_sessions",
        ["channel_id"],
        unique=True,
    )

    # voice_session_members テーブル
    op.create_table(
        "voice_session_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("voice_session_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["voice_session_id"], ["voice_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("voice_session_id", "user_id", name="uq_session_user"),
    )
    op.create_index(
        op.f("ix_voice_session_members_user_id"),
        "voice_session_members",
        ["user_id"],
        unique=False,
    )

    # bump_reminders テーブル
    op.create_table(
        "bump_reminders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("guild_id", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("service_name", sa.String(), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id", "service_name", name="uq_guild_service"),
    )
    op.create_index(
        op.f("ix_bump_reminders_guild_id"), "bump_reminders", ["guild_id"], unique=False
    )

    # bump_configs テーブル
    op.create_table(
        "bump_configs",
        sa.Column("guild_id", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("guild_id"),
    )

    # sticky_messages テーブル
    op.create_table(
        "sticky_messages",
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("guild_id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("color", sa.Integer(), nullable=True),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("last_posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("channel_id"),
    )
    op.create_index(
        op.f("ix_sticky_messages_guild_id"),
        "sticky_messages",
        ["guild_id"],
        unique=False,
    )


def downgrade() -> None:
    # テーブルが存在する場合のみ削除 (増分マイグレーションとの重複を安全に処理)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "sticky_messages" in tables:
        op.drop_table("sticky_messages")
    if "bump_configs" in tables:
        op.drop_table("bump_configs")
    if "bump_reminders" in tables:
        op.drop_table("bump_reminders")
    if "voice_session_members" in tables:
        op.drop_table("voice_session_members")
    if "voice_sessions" in tables:
        op.drop_table("voice_sessions")
    if "lobbies" in tables:
        op.drop_table("lobbies")
