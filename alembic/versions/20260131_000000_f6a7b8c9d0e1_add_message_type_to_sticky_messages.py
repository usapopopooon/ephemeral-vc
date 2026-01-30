"""add message_type to sticky_messages

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-01-31 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sticky_messages",
        sa.Column(
            "message_type",
            sa.String(),
            nullable=False,
            server_default="embed",
        ),
    )


def downgrade() -> None:
    op.drop_column("sticky_messages", "message_type")
