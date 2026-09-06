"""Unit test: FR-013 (2026-09-01 clarification) — forgot_password() is a
silent no-op for an unregistered Email, never raising or otherwise revealing
whether an account exists (avoids account enumeration)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.member.models import PasswordResetToken
from app.domains.member.service import forgot_password, register

pytestmark = pytest.mark.asyncio


async def test_forgot_password_unknown_email_is_silent_noop(db_session: AsyncSession) -> None:
    await forgot_password(db_session, "nobody@example.com")

    result = await db_session.execute(select(PasswordResetToken))
    assert result.scalars().all() == []


async def test_forgot_password_known_email_issues_token(db_session: AsyncSession) -> None:
    member = await register(db_session, "known@example.com", "abc12345")
    await forgot_password(db_session, "known@example.com")

    result = await db_session.execute(
        select(PasswordResetToken).where(PasswordResetToken.member_id == member.id)
    )
    assert len(result.scalars().all()) == 1
