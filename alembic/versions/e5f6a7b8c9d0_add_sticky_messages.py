"""add sticky_messages table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-01-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "sticky_messages" not in inspector.get_table_names():
        # sticky_messages テーブルを作成
        op.create_table(
            "sticky_messages",
            sa.Column("channel_id", sa.String(), nullable=False),
            sa.Column("guild_id", sa.String(), nullable=False),
            sa.Column("message_id", sa.String(), nullable=True),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column("color", sa.Integer(), nullable=True),
            sa.Column("cooldown_seconds", sa.Integer(), nullable=False, default=5),
            sa.Column("last_posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("channel_id"),
        )
        op.create_index(
            "ix_sticky_messages_guild_id",
            "sticky_messages",
            ["guild_id"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "sticky_messages" in inspector.get_table_names():
        op.drop_index("ix_sticky_messages_guild_id", table_name="sticky_messages")
        op.drop_table("sticky_messages")
