"""score serve records

Revision ID: 202050aacc77
Revises: d4e5f6a7b8c9
Create Date: 2026-09-15 22:24:20.334441

030-score-serve-record: three nullable "serve state" columns on `matches`
(serving_team, team_a_reference_server_id, team_b_reference_server_id) plus
a new `score_serve_records` table — one immutable snapshot row per +1
ScoreEvent (never for -1), per specs/030-score-serve-record/data-model.md.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '202050aacc77'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('matches', sa.Column('serving_team', sa.String(length=1), nullable=True))
    op.add_column('matches', sa.Column('team_a_reference_server_id', sa.UUID(), nullable=True))
    op.add_column('matches', sa.Column('team_b_reference_server_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_matches_team_a_reference_server_id_roster_entries',
        'matches', 'roster_entries', ['team_a_reference_server_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_matches_team_b_reference_server_id_roster_entries',
        'matches', 'roster_entries', ['team_b_reference_server_id'], ['id'],
    )

    op.create_table(
        'score_serve_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('score_event_id', sa.UUID(), nullable=False),
        sa.Column('match_id', sa.UUID(), nullable=False),
        sa.Column('group_id', sa.UUID(), nullable=False),
        sa.Column('server_roster_entry_id', sa.UUID(), nullable=False),
        sa.Column('server_team', sa.String(length=1), nullable=False),
        sa.Column('team_a_right_roster_entry_id', sa.UUID(), nullable=True),
        sa.Column('team_a_left_roster_entry_id', sa.UUID(), nullable=True),
        sa.Column('team_b_right_roster_entry_id', sa.UUID(), nullable=True),
        sa.Column('team_b_left_roster_entry_id', sa.UUID(), nullable=True),
        sa.Column(
            'created_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['score_event_id'], ['score_events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.ForeignKeyConstraint(['server_roster_entry_id'], ['roster_entries.id']),
        sa.ForeignKeyConstraint(['team_a_right_roster_entry_id'], ['roster_entries.id']),
        sa.ForeignKeyConstraint(['team_a_left_roster_entry_id'], ['roster_entries.id']),
        sa.ForeignKeyConstraint(['team_b_right_roster_entry_id'], ['roster_entries.id']),
        sa.ForeignKeyConstraint(['team_b_left_roster_entry_id'], ['roster_entries.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('score_event_id'),
    )
    op.create_index('ix_score_serve_records_match_id', 'score_serve_records', ['match_id'])
    op.create_index('ix_score_serve_records_group_id', 'score_serve_records', ['group_id'])


def downgrade() -> None:
    op.drop_index('ix_score_serve_records_group_id', table_name='score_serve_records')
    op.drop_index('ix_score_serve_records_match_id', table_name='score_serve_records')
    op.drop_table('score_serve_records')

    op.drop_constraint(
        'fk_matches_team_b_reference_server_id_roster_entries', 'matches', type_='foreignkey'
    )
    op.drop_constraint(
        'fk_matches_team_a_reference_server_id_roster_entries', 'matches', type_='foreignkey'
    )
    op.drop_column('matches', 'team_b_reference_server_id')
    op.drop_column('matches', 'team_a_reference_server_id')
    op.drop_column('matches', 'serving_team')
