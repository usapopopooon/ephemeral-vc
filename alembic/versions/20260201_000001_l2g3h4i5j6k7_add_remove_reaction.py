"""Add remove_reaction column to role_panels.

Revision ID: l2g3h4i5j6k7
Revises: k1f2a3b4c5d6
Create Date: 2026-02-01 00:00:01.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "l2g3h4i5j6k7"
down_revision: str | None = "k1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # remove_reaction カラムを追加
    # True: リアクション追加でトグル、リアクション自動削除 (カウント常に 1)
    # False: リアクション追加で付与、削除で解除 (通常動作)
    op.add_column(
        "role_panels",
        sa.Column("remove_reaction", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("role_panels", "remove_reaction")
