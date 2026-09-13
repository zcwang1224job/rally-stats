"""group scoreboard scoring enabled

Revision ID: 28d799ad1f93
Revises: 8a1f2c9d4e6b
Create Date: 2026-09-13 19:49:43.979010

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '28d799ad1f93'
down_revision: str | None = '8a1f2c9d4e6b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'groups',
        sa.Column(
            'scoreboard_scoring_enabled',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column('groups', 'scoreboard_scoring_enabled')
