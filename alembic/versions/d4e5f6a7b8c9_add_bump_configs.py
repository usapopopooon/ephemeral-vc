"""add bump_configs table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-01-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "bump_configs" not in inspector.get_table_names():
        # bump_configs テーブルを作成 (ギルドごとの bump 監視設定)
        op.create_table(
            "bump_configs",
            sa.Column("guild_id", sa.String(), nullable=False),
            sa.Column("channel_id", sa.String(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("guild_id"),
        )


def downgrade() -> None:
    # bump_configs テーブルを削除
    op.drop_table("bump_configs")
