"""Tables the frames sport type owns (spec 043 data-model §7). Both hang off
the match event spine (`score_events`) and go with it on delete, so undoing
an action or deleting a match never needs this plugin's help."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class FrameResult(Base):
    """One finished frame. Its row is keyed by the spine `point` (+1 to the
    winner) that the frame's end added to the match score."""

    __tablename__ = "frames_frame_results"
    __table_args__ = (UniqueConstraint("match_id", "frame_no", name="uq_frames_result_frame"),)

    score_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("score_events.id", ondelete="CASCADE"),
        primary_key=True,
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    frame_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    winner_team: Mapped[str] = mapped_column(String(1), nullable=False)  # A | B
    # In-frame score when kept (frame_scoring_enabled), else NULL.
    score_a: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    score_b: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    ended_by: Mapped[str] = mapped_column(String(8), nullable=False)  # target | manual
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class FramePoint(Base):
    """One in-frame point (+1 / -1), keyed by its own `frames.frame_point`
    spine event (delta 0 — it never changes the match score)."""

    __tablename__ = "frames_frame_points"

    score_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("score_events.id", ondelete="CASCADE"),
        primary_key=True,
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    frame_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    side: Mapped[str] = mapped_column(String(1), nullable=False)
    delta: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    frame_score_a: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    frame_score_b: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
