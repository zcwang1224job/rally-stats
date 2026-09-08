"""group disbanded_at

Revision ID: 476c536c7b0f
Revises: b740e0fbe798
Create Date: 2026-09-08 21:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '476c536c7b0f'
down_revision: str | None = 'b740e0fbe798'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'groups',
        sa.Column('disbanded_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('groups', 'disbanded_at')
