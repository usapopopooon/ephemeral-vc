"""add is_enabled to bump_reminders and make remind_at nullable

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # is_enabled カラムを追加 (デフォルト True)
    op.add_column(
        "bump_reminders",
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )
    # remind_at を nullable に変更
    op.alter_column(
        "bump_reminders",
        "remind_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )


def downgrade() -> None:
    # remind_at を not null に戻す (null の場合はデフォルト値を設定)
    op.execute(
        "UPDATE bump_reminders SET remind_at = NOW() WHERE remind_at IS NULL"
    )
    op.alter_column(
        "bump_reminders",
        "remind_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    # is_enabled カラムを削除
    op.drop_column("bump_reminders", "is_enabled")
