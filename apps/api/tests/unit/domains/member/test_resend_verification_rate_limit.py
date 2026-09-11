"""Unit test: FR-004 resend-verification per-account 5-minute cooldown
(research.md #1/#5 — DB timestamp+count comparison, not slowapi, since this
is account-scoped rather than IP-scoped).

020-resend-verification-email revised these assertions after
`/speckit-analyze` finding I1: the original 006-member-friends design (and
this feature's first draft) based the cooldown on "the most recent
verification-email send," which included the one sent automatically at
registration — meaning a member's very first manual resend could be
rejected if attempted within the cooldown window of their own signup. The
fix: the cooldown only ever applies *between* manually-triggered resends."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.member.models import EmailVerificationToken
from app.domains.member.service import register, resend_verification

pytestmark = pytest.mark.asyncio


async def test_first_manual_resend_succeeds_immediately_after_registration(
    db_session: AsyncSession,
) -> None:
    """(a) research.md #5: a member who just registered (exactly 1 token —
    the registration one) MUST be able to resend immediately, not be
    rejected as if they'd just resent."""
    member = await register(db_session, "resend@example.com", "abc12345")

    available_at = await resend_verification(db_session, member)

    assert available_at > datetime.now(UTC)
    count_result = await db_session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.member_id == member.id)
    )
    assert len(count_result.scalars().all()) == 2


async def test_second_resend_within_cooldown_is_rejected(db_session: AsyncSession) -> None:
    """(b) once a member has manually resent once (2 tokens total), a
    second resend within 5 minutes MUST be rejected."""
    member = await register(db_session, "resend-second@example.com", "abc12345")
    await resend_verification(db_session, member)

    with pytest.raises(ApiError) as exc_info:
        await resend_verification(db_session, member)
    assert exc_info.value.error_code == "RESEND_RATE_LIMITED"


async def test_resend_after_cooldown_succeeds(db_session: AsyncSession) -> None:
    """(c) once 5 minutes have passed since the last manual resend, the
    next resend succeeds; short of that, it's still rejected."""
    member = await register(db_session, "resend2@example.com", "abc12345")
    await resend_verification(db_session, member)

    async def _shift_all_tokens_back(delta: timedelta) -> None:
        # Both the registration token AND the resend token MUST move back
        # together, preserving their relative order — otherwise the
        # untouched registration token (still effectively "now") becomes
        # the new max(created_at), silently defeating the backdate.
        result = await db_session.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.member_id == member.id)
        )
        for token in result.scalars():
            token.created_at = token.created_at - delta
        await db_session.commit()

    await _shift_all_tokens_back(timedelta(seconds=61))
    with pytest.raises(ApiError) as exc_info:
        await resend_verification(db_session, member)
    assert exc_info.value.error_code == "RESEND_RATE_LIMITED"

    await _shift_all_tokens_back(timedelta(minutes=5))
    await resend_verification(db_session, member)

    count_result = await db_session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.member_id == member.id)
    )
    assert len(count_result.scalars().all()) == 3


async def test_resend_rejects_already_verified_member(db_session: AsyncSession) -> None:
    member = await register(db_session, "resend3@example.com", "abc12345")
    member.verification_status = "verified"
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await resend_verification(db_session, member)
    assert exc_info.value.error_code == "ALREADY_VERIFIED"
