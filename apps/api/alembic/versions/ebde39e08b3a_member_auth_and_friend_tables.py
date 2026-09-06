"""member auth and friend tables

Revision ID: ebde39e08b3a
Revises: 066e515aeffd
Create Date: 2026-09-01 10:28:40.768938

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ebde39e08b3a'
down_revision: Union[str, None] = '066e515aeffd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('members', sa.Column('email', sa.String(length=255), nullable=False))
    op.add_column('members', sa.Column('password_hash', sa.String(length=255), nullable=False))
    op.add_column('members', sa.Column('user_number', sa.String(length=8), nullable=False))
    op.add_column(
        'members',
        sa.Column(
            'verification_status', sa.String(length=16), nullable=False, server_default='unverified'
        ),
    )
    op.add_column(
        'members', sa.Column('token_version', sa.Integer(), nullable=False, server_default='0')
    )
    op.create_index('ux_members_email', 'members', ['email'], unique=True)
    op.create_index(
        'ux_members_user_number_ci', 'members', [sa.text('LOWER(user_number)')], unique=True
    )

    op.create_table(
        'email_verification_tokens',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('member_id', sa.UUID(), nullable=False),
        sa.Column('token', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('used_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ux_evt_token', 'email_verification_tokens', ['token'], unique=True)

    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('member_id', sa.UUID(), nullable=False),
        sa.Column('token', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('used_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ux_prt_token', 'password_reset_tokens', ['token'], unique=True)

    op.create_table(
        'friend_requests',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('requester_id', sa.UUID(), nullable=False),
        sa.Column('addressee_id', sa.UUID(), nullable=False),
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
        sa.CheckConstraint('requester_id <> addressee_id', name='ck_friend_request_distinct_members'),
        sa.ForeignKeyConstraint(['requester_id'], ['members.id']),
        sa.ForeignKeyConstraint(['addressee_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ux_friend_requests_pending_pair',
        'friend_requests',
        [sa.text('LEAST(requester_id, addressee_id)'), sa.text('GREATEST(requester_id, addressee_id)')],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_table('friend_requests')
    op.drop_table('password_reset_tokens')
    op.drop_table('email_verification_tokens')
    op.drop_index('ux_members_user_number_ci', table_name='members')
    op.drop_index('ux_members_email', table_name='members')
    op.drop_column('members', 'token_version')
    op.drop_column('members', 'verification_status')
    op.drop_column('members', 'user_number')
    op.drop_column('members', 'password_hash')
    op.drop_column('members', 'email')
