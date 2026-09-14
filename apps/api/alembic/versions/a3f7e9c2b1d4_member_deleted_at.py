"""member deleted_at

Revision ID: a3f7e9c2b1d4
Revises: 54972280ca44
Create Date: 2026-09-14 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3f7e9c2b1d4'
down_revision: str | None = '54972280ca44'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'members',
        sa.Column('deleted_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('members', 'deleted_at')
