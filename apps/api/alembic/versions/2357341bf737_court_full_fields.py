"""court full fields

Revision ID: 2357341bf737
Revises: 75776930b757
Create Date: 2026-09-01 00:43:38.369211

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2357341bf737'
down_revision: Union[str, None] = '75776930b757'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('courts', sa.Column('name', sa.String(length=20), nullable=False))
    op.add_column('courts', sa.Column('scoreboard_token', sa.UUID(), nullable=False))
    op.add_column('courts', sa.Column('control_panel_token', sa.UUID(), nullable=False))
    op.add_column(
        'courts',
        sa.Column('scoreboard_link_version', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'courts',
        sa.Column('control_panel_link_version', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'courts',
        sa.Column(
            'created_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_unique_constraint('ux_courts_scoreboard_token', 'courts', ['scoreboard_token'])
    op.create_unique_constraint('ux_courts_control_panel_token', 'courts', ['control_panel_token'])
    op.create_index(
        'ux_courts_group_name_active',
        'courts',
        ['group_id', 'name'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('ux_courts_group_name_active', table_name='courts')
    op.drop_constraint('ux_courts_control_panel_token', 'courts', type_='unique')
    op.drop_constraint('ux_courts_scoreboard_token', 'courts', type_='unique')
    op.drop_column('courts', 'created_at')
    op.drop_column('courts', 'control_panel_link_version')
    op.drop_column('courts', 'scoreboard_link_version')
    op.drop_column('courts', 'control_panel_token')
    op.drop_column('courts', 'scoreboard_token')
    op.drop_column('courts', 'name')
