"""member view round history and left_at

Revision ID: adbd1ac0296c
Revises: ebde39e08b3a
Create Date: 2026-09-01 20:04:22.725177

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'adbd1ac0296c'
down_revision: str | None = 'ebde39e08b3a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'roster_entries', sa.Column('left_at', postgresql.TIMESTAMP(timezone=True), nullable=True)
    )

    op.create_table(
        'round_history',
        sa.Column('group_id', sa.UUID(), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.PrimaryKeyConstraint('group_id', 'round_number'),
    )


def downgrade() -> None:
    op.drop_table('round_history')
    op.drop_column('roster_entries', 'left_at')
