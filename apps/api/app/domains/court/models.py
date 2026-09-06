"""Court — full field set per specs/002-court-management/data-model.md §1.
(001 only needed a minimal stub — id/group_id/deleted_at — for its disband flow.)"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class Court(Base):
    __tablename__ = "courts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(20), nullable=False)

    scoreboard_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4, unique=True
    )
    control_panel_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4, unique=True
    )
    # Independent optimistic-lock versions — regenerating one link MUST NOT
    # conflict with a concurrent regeneration of the other (spec FR-036).
    scoreboard_link_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    control_panel_link_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
