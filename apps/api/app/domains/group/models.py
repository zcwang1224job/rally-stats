"""Group entity — includes embedded Match Scoring Settings and Admin Credential
fields, per specs/001-create-manage-group/data-model.md §1–3."""

import uuid
from datetime import datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Sequence,
    String,
    Time,
)
from sqlalchemy.dialects.postgresql import BYTEA, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

group_number_seq = Sequence("group_number_seq", start=100000, increment=1)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    group_number: Mapped[int] = mapped_column(
        BigInteger,
        group_number_seq,
        server_default=group_number_seq.next_value(),
        nullable=False,
        unique=True,
    )
    name: Mapped[str] = mapped_column(String(30), nullable=False)

    password_ciphertext: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    password_nonce: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)

    max_members: Mapped[int] = mapped_column(Integer, nullable=False)
    match_mode: Mapped[str] = mapped_column(String(8), nullable=False)  # singles | doubles
    scheduling_mechanism: Mapped[str] = mapped_column(String(16), nullable=False)
    # fair_rotation | fixed_partner | individual_mixed | manual

    activity_time_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    activity_time_end: Mapped[time | None] = mapped_column(Time, nullable=True)

    current_member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # active | disbanded

    last_activity_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_by_member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=True
    )

    admin_pin_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    admin_failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    admin_locked_until: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    admin_token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    base_settings_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    join_link_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    all_courts_link_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    join_link_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4, unique=True
    )
    all_courts_control_panel_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4, unique=True
    )

    # Match Scoring Settings (embedded, see data-model.md §2)
    scoring_mode: Mapped[str] = mapped_column(String(8), nullable=False, default="21pt")
    # 21pt | 15pt | custom
    target_score: Mapped[int] = mapped_column(Integer, nullable=False, default=21)
    deuce_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    cap_score: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    current_round_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    auto_next_round: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 011-round-robin-scheduling: only meaningful when scheduling_mechanism ==
    # "fixed_partner" — "manual" reads the partnerships table (existing
    # admin-configured pairs); "auto" recomputes teams fresh each round
    # without ever writing to partnerships (research.md #6).
    partner_source: Mapped[str] = mapped_column(String(8), nullable=False, default="manual")
    # manual | auto


class RoundHistory(Base):
    """005-member-view research.md #1/#2: written once per round generated
    (including round 1) by 003's `generate_next_round()`, read-only for this
    feature's "已離開" (left) state determination."""

    __tablename__ = "round_history"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), primary_key=True
    )
    round_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
