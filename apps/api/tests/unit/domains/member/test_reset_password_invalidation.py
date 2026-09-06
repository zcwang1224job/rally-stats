"""Unit test: reset_password() success also marks verified and bumps
token_version (FR-014/015 — all devices' sessions invalidated)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import PasswordResetToken
from app.domains.member.security import verify_password
from app.domains.member.service import forgot_password, register, reset_password

pytestmark = pytest.mark.asyncio


async def test_reset_password_marks_verified_and_bumps_token_version(
    db_session: AsyncSession,
) -> None:
    member = await register(db_session, "invalidate@example.com", "abc12345")
    starting_version = member.token_version
    await forgot_password(db_session, "invalidate@example.com")

    result = await db_session.execute(
        select(PasswordResetToken).where(PasswordResetToken.member_id == member.id)
    )
    token = result.scalar_one()

    updated_member = await reset_password(db_session, token.token, "newpass123")

    assert updated_member.verification_status == "verified"
    assert updated_member.token_version == starting_version + 1
    assert verify_password("newpass123", updated_member.password_hash)


async def test_reset_password_updates_password_hash(db_session: AsyncSession) -> None:
    member = await register(db_session, "invalidate2@example.com", "abc12345")
    await forgot_password(db_session, "invalidate2@example.com")

    result = await db_session.execute(
        select(PasswordResetToken).where(PasswordResetToken.member_id == member.id)
    )
    token = result.scalar_one()

    updated_member = await reset_password(db_session, token.token, "newpass123")

    assert not verify_password("abc12345", updated_member.password_hash)
