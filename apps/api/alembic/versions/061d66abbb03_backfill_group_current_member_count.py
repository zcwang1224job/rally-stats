"""backfill group current_member_count

Revision ID: 061d66abbb03
Revises: b474066439e6
Create Date: 2026-09-06 17:10:15.402087

`current_member_count` only ever had its increment (`join_group`'s atomic
`+1`) implemented — nothing decremented it on a member leaving or being
kicked, so any group with turnover has been counting cumulative joins
ever since, not currently-active members. This one-time backfill
recomputes it from the actual RosterEntry rows; the app code fix
(app/domains/schedule/service.py `handle_member_left`) keeps it correct
going forward.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '061d66abbb03'
down_revision: str | None = 'b474066439e6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE groups
            SET current_member_count = counts.active_count
            FROM (
                SELECT g.id AS group_id, COUNT(r.id) AS active_count
                FROM groups g
                LEFT JOIN roster_entries r
                    ON r.group_id = g.id AND r.status = 'active'
                GROUP BY g.id
            ) AS counts
            WHERE groups.id = counts.group_id
            """
        )
    )


def downgrade() -> None:
    # Irreversible: the pre-backfill values were wrong (that's the bug this
    # fixes) and weren't recorded anywhere, so there's nothing correct to
    # restore them to.
    pass
