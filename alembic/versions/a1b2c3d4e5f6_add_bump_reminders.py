"""add bump_reminders table

Revision ID: a1b2c3d4e5f6
Revises: 6be2a413ed70
Create Date: 2026-01-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "6be2a413ed70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "bump_reminders" not in inspector.get_table_names():
        op.create_table(
            "bump_reminders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("guild_id", sa.String(), nullable=False, index=True),
            sa.Column("channel_id", sa.String(), nullable=False),
            sa.Column("service_name", sa.String(), nullable=False),
            sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("guild_id", "service_name", name="uq_guild_service"),
        )


def downgrade() -> None:
    op.drop_table("bump_reminders")
