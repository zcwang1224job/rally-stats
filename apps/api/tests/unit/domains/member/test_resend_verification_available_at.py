"""Unit test: 020-resend-verification-email's
`get_resend_verification_available_at()` — read-only cooldown-status
counterpart to `resend_verification()`'s write-path check. Per
research.md #5 (fixing `/speckit-analyze` finding I1): a member's first-ever
manual resend MUST NOT be treated as cooling down just because the
registration-time verification email was sent recently."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import EmailVerificationToken
from app.domains.member.service import get_resend_verification_available_at, register

pytestmark = pytest.mark.asyncio


async def test_verified_member_always_returns_none(db_session: AsyncSession) -> None:
    member = await register(db_session, "avail-verified@example.com", "abc12345")
    member.verification_status = "verified"
    await db_session.commit()

    result = await get_resend_verification_available_at(db_session, member)

    assert result is None


async def test_no_tokens_at_all_returns_none(db_session: AsyncSession) -> None:
    """Defensive case — in practice every member has at least the
    registration-issued token, but the function MUST NOT crash if that
    invariant is ever violated."""
    member = await register(db_session, "avail-notoken@example.com", "abc12345")
    await db_session.execute(
        EmailVerificationToken.__table__.delete().where(
            EmailVerificationToken.member_id == member.id
        )
    )
    await db_session.commit()

    result = await get_resend_verification_available_at(db_session, member)

    assert result is None


async def test_only_registration_token_returns_none_regardless_of_recency(
    db_session: AsyncSession,
) -> None:
    """research.md #5: exactly 1 token (the registration one, even if
    created seconds ago) means "never manually resent yet" — MUST return
    `None`, not a future timestamp."""
    member = await register(db_session, "avail-onlyreg@example.com", "abc12345")

    result = await get_resend_verification_available_at(db_session, member)

    assert result is None


async def test_two_tokens_within_cooldown_returns_future_timestamp(
    db_session: AsyncSession,
) -> None:
    member = await register(db_session, "avail-cooling@example.com", "abc12345")
    second_token = EmailVerificationToken(
        member_id=member.id, expires_at=datetime.now(UTC) + timedelta(hours=24)
    )
    db_session.add(second_token)
    await db_session.commit()
    await db_session.refresh(second_token)

    result = await get_resend_verification_available_at(db_session, member)

    assert result is not None
    assert result > datetime.now(UTC)
    assert result == second_token.created_at + timedelta(minutes=5)


async def test_two_tokens_after_cooldown_elapsed_returns_none(db_session: AsyncSession) -> None:
    member = await register(db_session, "avail-elapsed@example.com", "abc12345")
    second_token = EmailVerificationToken(
        member_id=member.id, expires_at=datetime.now(UTC) + timedelta(hours=24)
    )
    db_session.add(second_token)
    await db_session.commit()
    await db_session.refresh(second_token)

    # Shift BOTH tokens (registration + resend) back together, preserving
    # their relative order — otherwise the untouched registration token
    # (still effectively "now") would silently become the new
    # max(created_at) and defeat the backdate.
    result_tokens = await db_session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.member_id == member.id)
    )
    delta = timedelta(minutes=5, seconds=1)
    for token in result_tokens.scalars():
        token.created_at = token.created_at - delta
    await db_session.commit()

    result = await get_resend_verification_available_at(db_session, member)

    assert result is None
