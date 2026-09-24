"""shot_placement_records

Revision ID: d0c14187b0e3
Revises: 202050aacc77
Create Date: 2026-09-16 11:11:56.447487

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd0c14187b0e3'
down_revision: Union[str, None] = '202050aacc77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 031-shot-placement-scoring: hand-trimmed from `alembic revision
    # --autogenerate` output — the autogenerate diff also picked up a large
    # amount of unrelated pre-existing model/DB metadata drift (dropped
    # tables, unrelated index churn), stripped here same as 030's migration.
    op.add_column(
        'groups',
        sa.Column('detailed_scoring_enabled', sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        'matches',
        sa.Column('detailed_scoring_enabled', sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_table(
        'shot_placement_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('score_event_id', sa.UUID(), nullable=False),
        sa.Column('match_id', sa.UUID(), nullable=False),
        sa.Column('group_id', sa.UUID(), nullable=False),
        sa.Column('roster_entry_id', sa.UUID(), nullable=True),
        sa.Column('losing_roster_entry_id', sa.UUID(), nullable=True),
        sa.Column('team', sa.String(length=1), nullable=False),
        sa.Column('landing_x', sa.Float(), nullable=True),
        sa.Column('landing_y', sa.Float(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['roster_entry_id'], ['roster_entries.id'], ),
        sa.ForeignKeyConstraint(['losing_roster_entry_id'], ['roster_entries.id'], ),
        sa.ForeignKeyConstraint(['score_event_id'], ['score_events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('score_event_id'),
    )
    op.create_index(op.f('ix_shot_placement_records_group_id'), 'shot_placement_records', ['group_id'], unique=False)
    op.create_index(op.f('ix_shot_placement_records_match_id'), 'shot_placement_records', ['match_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_shot_placement_records_match_id'), table_name='shot_placement_records')
    op.drop_index(op.f('ix_shot_placement_records_group_id'), table_name='shot_placement_records')
    op.drop_table('shot_placement_records')
    op.drop_column('matches', 'detailed_scoring_enabled')
    op.drop_column('groups', 'detailed_scoring_enabled')
