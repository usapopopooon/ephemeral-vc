"""Add role_panels and role_panel_items tables.

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
Create Date: 2026-02-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "k1f2a3b4c5d6"
down_revision: str | None = "j0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # role_panels テーブル作成
    op.create_table(
        "role_panels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("guild_id", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("panel_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("color", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_role_panels_guild_id"),
        "role_panels",
        ["guild_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_role_panels_channel_id"),
        "role_panels",
        ["channel_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_role_panels_message_id"),
        "role_panels",
        ["message_id"],
        unique=False,
    )

    # role_panel_items テーブル作成
    op.create_table(
        "role_panel_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("panel_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.String(), nullable=False),
        sa.Column("emoji", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("style", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["panel_id"],
            ["role_panels.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("panel_id", "emoji", name="uq_panel_emoji"),
    )


def downgrade() -> None:
    op.drop_table("role_panel_items")
    op.drop_index(op.f("ix_role_panels_message_id"), table_name="role_panels")
    op.drop_index(op.f("ix_role_panels_channel_id"), table_name="role_panels")
    op.drop_index(op.f("ix_role_panels_guild_id"), table_name="role_panels")
    op.drop_table("role_panels")
