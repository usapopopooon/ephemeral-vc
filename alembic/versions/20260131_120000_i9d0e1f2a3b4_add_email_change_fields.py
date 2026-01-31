"""Add pending_email, email_change_token, email_change_token_expires_at to admin_users.

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
Create Date: 2026-01-31 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "i9d0e1f2a3b4"
down_revision: str | None = "h8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("pending_email", sa.String(), nullable=True),
    )
    op.add_column(
        "admin_users",
        sa.Column("email_change_token", sa.String(), nullable=True),
    )
    op.add_column(
        "admin_users",
        sa.Column(
            "email_change_token_expires_at", sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("admin_users", "email_change_token_expires_at")
    op.drop_column("admin_users", "email_change_token")
    op.drop_column("admin_users", "pending_email")
