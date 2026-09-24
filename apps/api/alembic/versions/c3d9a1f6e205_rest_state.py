"""rest_state

Revision ID: c3d9a1f6e205
Revises: b5c8e2f41a07
Create Date: 2026-09-19 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c3d9a1f6e205'
down_revision: Union[str, None] = 'b5c8e2f41a07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Hand-written, same as the other recent migrations.
    #
    # DEPLOY ORDER: run this BEFORE the backend that maps these columns — the
    # API container does not run migrations on start.

    # 037-rest-ready-toggle: NULL = ready, a timestamp = resting since then.
    # Every existing player starts ready, so scheduling is unchanged.
    op.add_column(
        'roster_entries',
        sa.Column('resting_since', postgresql.TIMESTAMP(timezone=True), nullable=True),
    )
    # Matches a returning player is treated as having played, for scheduling
    # priority only (research.md Decision 4). Never read by any record.
    op.add_column(
        'roster_entries',
        sa.Column('played_credit', sa.Integer(), nullable=False, server_default='0'),
    )

    # Finished rest periods, so "matches sat out" can leave them out
    # (research.md Decision 3). The ongoing one lives in resting_since.
    op.create_table(
        'roster_rest_periods',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'roster_entry_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('roster_entries.id'),
            nullable=False,
        ),
        sa.Column(
            'group_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('groups.id'), nullable=False
        ),
        sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('ended_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint('ended_at >= started_at', name='ck_roster_rest_periods_order'),
    )
    op.create_index(
        'ix_roster_rest_periods_roster_entry_id', 'roster_rest_periods', ['roster_entry_id']
    )
    op.create_index('ix_roster_rest_periods_group_id', 'roster_rest_periods', ['group_id'])


def downgrade() -> None:
    op.drop_index('ix_roster_rest_periods_group_id', table_name='roster_rest_periods')
    op.drop_index('ix_roster_rest_periods_roster_entry_id', table_name='roster_rest_periods')
    op.drop_table('roster_rest_periods')
    op.drop_column('roster_entries', 'played_credit')
    op.drop_column('roster_entries', 'resting_since')
