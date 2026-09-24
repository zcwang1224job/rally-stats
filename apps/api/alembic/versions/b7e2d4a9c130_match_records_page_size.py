"""match_records_page_size system_config default

Revision ID: b7e2d4a9c130
Revises: c3d9a1f6e205
Create Date: 2026-09-22 00:00:00.000000

A member's match records (their own 對戰紀錄, a friend's records, one of
我的團's history) get their own, shorter page size: each row is a tall
scorecard. Same key/value/description shape as 8a1f2c9d4e6b's rows.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e2d4a9c130'
down_revision: Union[str, None] = 'c3d9a1f6e205'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO system_config (key, value, description) VALUES "
        "('match_records_page_size', '10', '對戰紀錄（本人、好友、我的團歷史）每頁比賽筆數') "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM system_config WHERE key = 'match_records_page_size'")
