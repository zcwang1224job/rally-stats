"""GroupInvite — a single-row five-state state machine per
specs/013-group-invite-friends/data-model.md: pending -> accepted /
declined / invalidated / cancelled. `pending` is the only non-terminal
state; the other four are terminal and never transition further.
`cancelled` is the creator withdrawing the invite before the invitee
answers (so a later accept hits the same `GROUP_INVITE_NOT_PENDING` guard
as any other terminal state); `invalidated` stays reserved for the system
retiring an invite (group disbanded / friendship dissolved). `inviter_member_id` is a
denormalized copy of `Group.created_by_member_id` (query convenience, not a
second source of truth — always written from that same value at creation
time)."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class GroupInvite(Base):
    __tablename__ = "group_invites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False, index=True
    )
    inviter_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=False, index=True
    )
    invitee_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # pending | accepted | declined | invalidated | cancelled
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
