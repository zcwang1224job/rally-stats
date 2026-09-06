"""Unit test: FR-011 resend-verification per-account 60s cooldown
(research.md #6 — DB timestamp comparison, not slowapi, since this is
account-scoped rather than IP-scoped)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.member.models import EmailVerificationToken
from app.domains.member.service import register, resend_verification

pytestmark = pytest.mark.asyncio


async def test_resend_within_cooldown_is_rejected(db_session: AsyncSession) -> None:
    member = await register(db_session, "resend@example.com", "abc12345")

    with pytest.raises(ApiError) as exc_info:
        await resend_verification(db_session, member)
    assert exc_info.value.error_code == "RESEND_RATE_LIMITED"


async def test_resend_after_cooldown_succeeds(db_session: AsyncSession) -> None:
    member = await register(db_session, "resend2@example.com", "abc12345")

    result = await db_session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.member_id == member.id)
    )
    token = result.scalar_one()
    token.created_at = datetime.now(UTC) - timedelta(seconds=61)
    await db_session.commit()

    await resend_verification(db_session, member)

    count_result = await db_session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.member_id == member.id)
    )
    assert len(count_result.scalars().all()) == 2


async def test_resend_rejects_already_verified_member(db_session: AsyncSession) -> None:
    member = await register(db_session, "resend3@example.com", "abc12345")
    member.verification_status = "verified"
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await resend_verification(db_session, member)
    assert exc_info.value.error_code == "ALREADY_VERIFIED"
