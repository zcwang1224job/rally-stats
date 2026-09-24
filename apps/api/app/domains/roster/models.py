"""RosterEntry (Roster Entry / Player) — shared entity, first written by 001;
full lifecycle (wait_count semantics, status transitions) is owned by later specs
003/004/006 per specs/001-create-manage-group/data-model.md §4."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class RosterEntry(Base):
    __tablename__ = "roster_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False, index=True
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=True, index=True
    )
    nickname: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # active | left | kicked
    is_creator: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    joined_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    wait_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NULL = infinite (never played yet), see specs/003 FR-004
    guest_session_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True
    )
    left_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # 005-member-view FR-008: set when status transitions to left/kicked,
    # NULL while active. Never cleared once set.
    resting_since: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # 037-rest-ready-toggle: NULL = ready, otherwise resting since then —
    # left out of every "who can play next" query (research.md Decision 1).
    played_credit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # 037: matches a returning player counts as having played, for
    # scheduling priority only (research.md Decision 4). Never in records.


class RosterRestPeriod(Base):
    """037-rest-ready-toggle: a finished rest period. Matches that went on
    court during one don't count as matches the player sat out (research.md
    Decision 3). The ongoing period is `RosterEntry.resting_since`."""

    __tablename__ = "roster_rest_periods"
    __table_args__ = (
        CheckConstraint("ended_at >= started_at", name="ck_roster_rest_periods_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    roster_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_entries.id"), nullable=False, index=True
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
