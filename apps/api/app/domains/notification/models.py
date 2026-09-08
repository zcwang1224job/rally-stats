"""Notification — per specs/012-realtime-notifications/data-model.md.
`type` + `source_id` is a deliberate multi-polymorphic pair (no DB-level FK
on `source_id` — it points at a different table depending on `type`; today
only `"friend_request"` exists, pointing at `friend_requests.id`) so future
notification types (e.g. group invitations) don't require a schema change
(research.md #5). Rows are permanent once created — `read_at` only ever
moves from `NULL` to a timestamp, never back (FR-012/FR-005)."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    # "friend_request" (only value today) — source_id points at friend_requests.id
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
