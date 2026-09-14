"""member oauth identities

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-09-14 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: str | None = 'c1d2e3f4a5b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 027-google-line-oauth-login data-model.md §1: a LINE-only account may
    # have no email (FR-004), and any OAuth-only account has no password.
    op.alter_column('members', 'email', existing_type=sa.String(length=255), nullable=True)
    op.alter_column(
        'members', 'password_hash', existing_type=sa.String(length=255), nullable=True
    )

    # Replace the plain unique index with a partial one so multiple NULL
    # emails can coexist while any non-NULL email stays globally unique.
    op.drop_index('ux_members_email', table_name='members')
    op.create_index(
        'ux_members_email',
        'members',
        ['email'],
        unique=True,
        postgresql_where=sa.text('email IS NOT NULL'),
    )

    op.create_table(
        'member_oauth_identities',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('member_id', sa.UUID(), nullable=False),
        sa.Column('provider', sa.String(length=16), nullable=False),
        sa.Column('provider_user_id', sa.String(length=255), nullable=False),
        sa.Column('email_at_link', sa.String(length=255), nullable=True),
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
        'ix_member_oauth_identities_member_id', 'member_oauth_identities', ['member_id']
    )
    op.create_unique_constraint(
        'ux_member_oauth_identities_provider_user',
        'member_oauth_identities',
        ['provider', 'provider_user_id'],
    )
    op.create_unique_constraint(
        'ux_member_oauth_identities_member_provider',
        'member_oauth_identities',
        ['member_id', 'provider'],
    )


def downgrade() -> None:
    op.drop_table('member_oauth_identities')
    op.drop_index('ux_members_email', table_name='members')
    op.create_index('ux_members_email', 'members', ['email'], unique=True)
    op.alter_column(
        'members', 'password_hash', existing_type=sa.String(length=255), nullable=False
    )
    op.alter_column('members', 'email', existing_type=sa.String(length=255), nullable=False)
