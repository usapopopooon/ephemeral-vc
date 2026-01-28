"""add role_id to bump_reminders

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-01-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # role_id カラムを追加 (nullable、None ならデフォルトロールを使用)
    op.add_column(
        "bump_reminders",
        sa.Column("role_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    # role_id カラムを削除
    op.drop_column("bump_reminders", "role_id")
