"""add text_channel_id to voice_sessions

Revision ID: a1b2c3d4e5f6
Revises: bc395b6e2991
Create Date: 2026-01-27 19:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = 'bc395b6e2991'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'voice_sessions',
        sa.Column('text_channel_id', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('voice_sessions', 'text_channel_id')
