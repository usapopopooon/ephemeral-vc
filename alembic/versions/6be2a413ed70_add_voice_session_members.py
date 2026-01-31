"""add voice_session_members table

Revision ID: 6be2a413ed70
Revises: bc395b6e2991
Create Date: 2026-01-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6be2a413ed70"
down_revision: str | None = "bc395b6e2991"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "voice_session_members" not in inspector.get_table_names():
        op.create_table(
            "voice_session_members",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "voice_session_id",
                sa.Integer(),
                sa.ForeignKey("voice_sessions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column(
                "joined_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint("voice_session_id", "user_id", name="uq_session_user"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "voice_session_members" in inspector.get_table_names():
        op.drop_table("voice_session_members")
