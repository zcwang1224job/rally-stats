"""group invite table

Revision ID: b740e0fbe798
Revises: cc86c6121d63
Create Date: 2026-09-07 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b740e0fbe798'
down_revision: Union[str, None] = 'cc86c6121d63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'group_invites',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('group_id', sa.UUID(), nullable=False),
        sa.Column('inviter_member_id', sa.UUID(), nullable=False),
        sa.Column('invitee_member_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column(
            'created_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.ForeignKeyConstraint(['inviter_member_id'], ['members.id']),
        sa.ForeignKeyConstraint(['invitee_member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ux_group_invites_pending_invitee',
        'group_invites',
        ['group_id', 'invitee_member_id'],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        'ix_group_invites_group_invitee_created',
        'group_invites',
        ['group_id', 'invitee_member_id', sa.text('created_at DESC')],
    )


def downgrade() -> None:
    op.drop_index('ix_group_invites_group_invitee_created', table_name='group_invites')
    op.drop_index('ux_group_invites_pending_invitee', table_name='group_invites')
    op.drop_table('group_invites')
