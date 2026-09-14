"""member allow_friend_invite_from_match_pages

Revision ID: c1d2e3f4a5b6
Revises: a3f7e9c2b1d4
Create Date: 2026-09-14 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: str | None = 'a3f7e9c2b1d4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'members',
        sa.Column(
            'allow_friend_invite_from_match_pages',
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column('members', 'allow_friend_invite_from_match_pages')
