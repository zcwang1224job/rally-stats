"""score events table

Revision ID: f3a1c9d4e7b2
Revises: 3912de8ceb6c
Create Date: 2026-09-09 10:00:00.000000

Append-only audit trail of every +1/-1 scoring action, alongside the
existing Match.score_a/score_b running totals which apply_score_delta()
still overwrites in place.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f3a1c9d4e7b2'
down_revision: Union[str, None] = '3912de8ceb6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'score_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('match_id', sa.UUID(), nullable=False),
        sa.Column('group_id', sa.UUID(), nullable=False),
        sa.Column('side', sa.String(length=1), nullable=False),
        sa.Column('delta', sa.Integer(), nullable=False),
        sa.Column('score_a', sa.Integer(), nullable=False),
        sa.Column('score_b', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column(
            'created_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_score_events_match_id', 'score_events', ['match_id'])
    op.create_index('ix_score_events_group_id', 'score_events', ['group_id'])
    op.create_index(
        'ix_score_events_match_created', 'score_events', ['match_id', 'created_at']
    )


def downgrade() -> None:
    op.drop_index('ix_score_events_match_created', table_name='score_events')
    op.drop_index('ix_score_events_group_id', table_name='score_events')
    op.drop_index('ix_score_events_match_id', table_name='score_events')
    op.drop_table('score_events')
