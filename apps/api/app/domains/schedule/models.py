"""Match, MatchParticipant, PairHistory, Partnership — per
specs/003-schedule-rotation/data-model.md §1-4."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False, index=True
    )
    court_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courts.id"), nullable=True, index=True
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    # queued | in_progress | completed | abandoned
    score_a: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_b: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winner_team: Mapped[str | None] = mapped_column(String(1), nullable=True)

    # Match Scoring Settings snapshot (copied from groups at creation time)
    target_score: Mapped[int] = mapped_column(Integer, nullable=False)
    deuce_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    cap_score: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class MatchParticipant(Base):
    __tablename__ = "match_participants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    roster_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), nullable=False, index=True
    )
    team: Mapped[str] = mapped_column(String(1), nullable=False)  # 'A' | 'B'


class PairHistory(Base):
    __tablename__ = "pair_history"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), primary_key=True
    )
    player_lo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), primary_key=True
    )
    player_hi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), primary_key=True
    )
    pair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Partnership(Base):
    __tablename__ = "partnerships"
    __table_args__ = (CheckConstraint("player_a_id <> player_b_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False, index=True
    )
    player_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), nullable=False, unique=True
    )
    player_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
