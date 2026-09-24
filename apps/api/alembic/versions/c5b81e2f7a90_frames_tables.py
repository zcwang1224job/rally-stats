"""frames sport type tables (043)

Revision ID: c5b81e2f7a90
Revises: a3f0c2d91e47
Create Date: 2026-09-24 00:00:00.000000

The frames plugin's own tables (spec 043 data-model §7): finished frames and
in-frame points, each keyed by its spine event in `score_events` with
ON DELETE CASCADE. Owned by app/sports/types/frames; core never queries them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c5b81e2f7a90'
down_revision: Union[str, None] = 'a3f0c2d91e47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _spine_key() -> sa.Column[object]:
    return sa.Column(
        "score_event_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("score_events.id", ondelete="CASCADE"),
        primary_key=True,
    )


def _match_id() -> sa.Column[object]:
    return sa.Column(
        "match_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
    )


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at",
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def upgrade() -> None:
    op.create_table(
        "frames_frame_results",
        _spine_key(),
        _match_id(),
        sa.Column("frame_no", sa.SmallInteger(), nullable=False),
        sa.Column("winner_team", sa.String(1), nullable=False),
        sa.Column("score_a", sa.SmallInteger(), nullable=True),
        sa.Column("score_b", sa.SmallInteger(), nullable=True),
        sa.Column("ended_by", sa.String(8), nullable=False),
        _created_at(),
        sa.UniqueConstraint("match_id", "frame_no", name="uq_frames_result_frame"),
    )
    op.create_index("ix_frames_frame_results_match_id", "frames_frame_results", ["match_id"])
    op.create_table(
        "frames_frame_points",
        _spine_key(),
        _match_id(),
        sa.Column("frame_no", sa.SmallInteger(), nullable=False),
        sa.Column("side", sa.String(1), nullable=False),
        sa.Column("delta", sa.SmallInteger(), nullable=False),
        sa.Column("frame_score_a", sa.SmallInteger(), nullable=False),
        sa.Column("frame_score_b", sa.SmallInteger(), nullable=False),
        _created_at(),
    )
    op.create_index("ix_frames_frame_points_match_id", "frames_frame_points", ["match_id"])


def downgrade() -> None:
    op.drop_index("ix_frames_frame_points_match_id", table_name="frames_frame_points")
    op.drop_table("frames_frame_points")
    op.drop_index("ix_frames_frame_results_match_id", table_name="frames_frame_results")
    op.drop_table("frames_frame_results")
