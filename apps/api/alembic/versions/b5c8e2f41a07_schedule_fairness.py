"""schedule_fairness

Revision ID: b5c8e2f41a07
Revises: e7a41c9b3d52
Create Date: 2026-09-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b5c8e2f41a07'
down_revision: Union[str, None] = 'e7a41c9b3d52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Hand-written, same as the other recent migrations (autogenerate picks
    # up unrelated model/DB drift).
    #
    # DEPLOY ORDER: run this BEFORE the backend that maps these columns — the
    # API container does not run migrations on start.

    # Opt-in "a freed court immediately gets the next 4 waiting players"
    # mode for fair_rotation doubles. Off for every existing group.
    op.add_column(
        'groups',
        sa.Column(
            'continuous_rotation', sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )

    # Call-up order of a round's queued matches. Replaces the old trick of
    # rewriting matches.created_at to encode that order.
    op.add_column('matches', sa.Column('queue_position', sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE matches AS m
        SET queue_position = ordered.position
        FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY group_id, round_number ORDER BY created_at, id
                   ) - 1 AS position
            FROM matches
            WHERE status = 'queued'
        ) AS ordered
        WHERE m.id = ordered.id
        """
    )

    # pair_history now separates teammates from opponents, and counts a
    # match when it takes a court instead of when it is planned. The old
    # rows counted planned matches that were later abandoned unplayed, so
    # rebuild the whole table from matches that actually started. It is
    # derived data only; nothing else references it.
    op.add_column(
        'pair_history',
        sa.Column('teammate_count', sa.Integer(), nullable=False, server_default='0'),
    )
    op.execute('DELETE FROM pair_history')
    op.execute(
        """
        INSERT INTO pair_history (group_id, player_lo_id, player_hi_id, pair_count, teammate_count)
        SELECT m.group_id,
               a.roster_entry_id,
               b.roster_entry_id,
               COUNT(*),
               COUNT(*) FILTER (WHERE a.team = b.team)
        FROM matches AS m
        JOIN match_participants AS a ON a.match_id = m.id
        JOIN match_participants AS b
          ON b.match_id = m.id AND a.roster_entry_id < b.roster_entry_id
        WHERE m.started_at IS NOT NULL
        GROUP BY m.group_id, a.roster_entry_id, b.roster_entry_id
        """
    )


def downgrade() -> None:
    op.drop_column('pair_history', 'teammate_count')
    op.drop_column('matches', 'queue_position')
    op.drop_column('groups', 'continuous_rotation')
