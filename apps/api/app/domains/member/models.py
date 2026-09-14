"""Member — full account entity per specs/006-member-friends/data-model.md §1.
Originally created by 001 as a minimal stub (id/nickname/created_at) for FK
references (created_by_member_id, roster_entries.member_id); 006 extends it
with authentication fields. EmailVerificationToken/PasswordResetToken are
1:1-per-request lifecycle tokens for FR-007~015."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class Member(Base):
    __tablename__ = "members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # NULL = 尚未完成首次暱稱設定 (FR-012)
    user_number: Mapped[str] = mapped_column(String(8), nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unverified"
    )
    # unverified | verified
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    # 022-member-personal-settings / 024-add-english-language: the allow-list
    # lives in code (schemas.SUPPORTED_LANGUAGES, currently "zh-TW"/"en"),
    # not a DB CHECK constraint, so a future language needs no migration.
    language_preference: Mapped[str] = mapped_column(
        String(8), nullable=False, default="zh-TW", server_default="zh-TW"
    )
    allow_search: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    share_match_records_with_friends: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    # 025-delete-account: NULL = active account. Non-NULL = this account has
    # been deleted (anonymized in place, row kept — see service.delete_account()).
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class MemberLoginRecord(Base):
    """022-member-personal-settings data-model.md §2: one row per *active*
    login (Email+password submission) — token refresh MUST NOT create a row
    (FR-007). Append-only except for the retention trim in
    `service.record_login()` (research.md #2), which keeps at most 50 rows
    per member. MUST NOT gain an IP/geolocation column (FR-007)."""

    __tablename__ = "member_login_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_category: Mapped[str] = mapped_column(String(16), nullable=False)
    # "desktop" | "mobile" | "unknown"
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
