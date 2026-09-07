"""notification table

Revision ID: cc86c6121d63
Revises: 061d66abbb03
Create Date: 2026-09-07 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'cc86c6121d63'
down_revision: Union[str, None] = '061d66abbb03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('member_id', sa.UUID(), nullable=False),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('source_id', sa.UUID(), nullable=False),
        sa.Column('read_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_notifications_member_created',
        'notifications',
        ['member_id', sa.text('created_at DESC')],
    )
    op.create_index(
        'ix_notifications_member_unread',
        'notifications',
        ['member_id'],
        postgresql_where=sa.text('read_at IS NULL'),
    )
    op.create_index(
        'uq_notifications_type_source_member',
        'notifications',
        ['type', 'source_id', 'member_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_notifications_type_source_member', table_name='notifications')
    op.drop_index('ix_notifications_member_unread', table_name='notifications')
    op.drop_index('ix_notifications_member_created', table_name='notifications')
    op.drop_table('notifications')
