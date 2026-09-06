"""schedule rotation tables

Revision ID: 066e515aeffd
Revises: 2357341bf737
Create Date: 2026-09-01 05:59:54.533574

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '066e515aeffd'
down_revision: Union[str, None] = '2357341bf737'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'matches',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('group_id', sa.UUID(), nullable=False),
        sa.Column('court_id', sa.UUID(), nullable=True),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='queued'),
        sa.Column('score_a', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('score_b', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('winner_team', sa.String(length=1), nullable=True),
        sa.Column('target_score', sa.Integer(), nullable=False),
        sa.Column('deuce_threshold', sa.Integer(), nullable=False),
        sa.Column('cap_score', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('ended_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.ForeignKeyConstraint(['court_id'], ['courts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_matches_group_round', 'matches', ['group_id', 'round_number'])
    op.create_index('ix_matches_court_status', 'matches', ['court_id', 'status'])
    op.create_index(
        'ux_matches_court_in_progress',
        'matches',
        ['court_id'],
        unique=True,
        postgresql_where=sa.text("status = 'in_progress'"),
    )

    op.create_table(
        'match_participants',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('match_id', sa.UUID(), nullable=False),
        sa.Column('roster_entry_id', sa.UUID(), nullable=False),
        sa.Column('team', sa.String(length=1), nullable=False),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['roster_entry_id'], ['roster_entries.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_match_participants_match', 'match_participants', ['match_id']
    )
    op.create_index(
        'ix_match_participants_roster', 'match_participants', ['roster_entry_id']
    )

    op.create_table(
        'pair_history',
        sa.Column('group_id', sa.UUID(), nullable=False),
        sa.Column('player_lo_id', sa.UUID(), nullable=False),
        sa.Column('player_hi_id', sa.UUID(), nullable=False),
        sa.Column('pair_count', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.ForeignKeyConstraint(['player_lo_id'], ['roster_entries.id']),
        sa.ForeignKeyConstraint(['player_hi_id'], ['roster_entries.id']),
        sa.PrimaryKeyConstraint('group_id', 'player_lo_id', 'player_hi_id'),
    )

    op.create_table(
        'partnerships',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('group_id', sa.UUID(), nullable=False),
        sa.Column('player_a_id', sa.UUID(), nullable=False),
        sa.Column('player_b_id', sa.UUID(), nullable=False),
        sa.Column(
            'created_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.CheckConstraint('player_a_id <> player_b_id', name='ck_partnership_distinct_players'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.ForeignKeyConstraint(['player_a_id'], ['roster_entries.id']),
        sa.ForeignKeyConstraint(['player_b_id'], ['roster_entries.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ux_partnership_player_a', 'partnerships', ['player_a_id'], unique=True
    )
    op.create_index(
        'ux_partnership_player_b', 'partnerships', ['player_b_id'], unique=True
    )


def downgrade() -> None:
    op.drop_table('partnerships')
    op.drop_table('pair_history')
    op.drop_table('match_participants')
    op.drop_table('matches')
