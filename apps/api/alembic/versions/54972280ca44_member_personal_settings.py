"""member personal settings

Revision ID: 54972280ca44
Revises: 28d799ad1f93
Create Date: 2026-09-13 21:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '54972280ca44'
down_revision: str | None = '28d799ad1f93'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'members',
        sa.Column(
            'language_preference', sa.String(length=8), nullable=False, server_default='zh-TW'
        ),
    )
    op.add_column(
        'members',
        sa.Column('allow_search', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        'members',
        sa.Column(
            'share_match_records_with_friends',
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.create_table(
        'member_login_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'member_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('members.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('device_category', sa.String(length=16), nullable=False),
        sa.Column(
            'created_at',
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        'ix_member_login_records_member_id', 'member_login_records', ['member_id']
    )


def downgrade() -> None:
    op.drop_index('ix_member_login_records_member_id', table_name='member_login_records')
    op.drop_table('member_login_records')
    op.drop_column('members', 'share_match_records_with_friends')
    op.drop_column('members', 'allow_search')
    op.drop_column('members', 'language_preference')
