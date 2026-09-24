"""shot_placement_ending_type

Revision ID: e7a41c9b3d52
Revises: d0c14187b0e3
Create Date: 2026-09-18 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e7a41c9b3d52'
down_revision: Union[str, None] = 'd0c14187b0e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 035-point-ending-type: hand-written, same as 030/031's migrations —
    # autogenerate picks up a large amount of unrelated model/DB metadata
    # drift. One nullable column, no default, no backfill: every row written
    # before this feature stays NULL ("not recorded"). Inferring a value for
    # old rows from their landing would only ever produce errors (out, serve
    # fault) and never winners, skewing every old match's ratio.
    #
    # DEPLOY ORDER: run this BEFORE the backend that maps the column. The
    # API container does not run migrations on start, and once the column is
    # on the ORM model every read of shot_placement_records selects it — a
    # backend ahead of this migration breaks match details, the dashboard and
    # detailed-mode "-1", not just the new feature.
    op.add_column(
        'shot_placement_records',
        sa.Column('ending_type', sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('shot_placement_records', 'ending_type')
