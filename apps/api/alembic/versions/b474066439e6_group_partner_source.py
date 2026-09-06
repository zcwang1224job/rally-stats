"""group partner_source

Revision ID: b474066439e6
Revises: adbd1ac0296c
Create Date: 2026-09-02 17:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b474066439e6'
down_revision: str | None = 'adbd1ac0296c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'groups',
        sa.Column('partner_source', sa.String(), nullable=False, server_default='manual'),
    )


def downgrade() -> None:
    op.drop_column('groups', 'partner_source')
