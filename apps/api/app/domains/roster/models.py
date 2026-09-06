"""RosterEntry (Roster Entry / Player) — shared entity, first written by 001;
full lifecycle (wait_count semantics, status transitions) is owned by later specs
003/004/006 per specs/001-create-manage-group/data-model.md §4."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
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
        UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=True
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
