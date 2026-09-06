"""Unit test: password_reset_tokens lifecycle — 1-hour expiry, used_at,
already-used/expired errors."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.member.models import PasswordResetToken
from app.domains.member.service import forgot_password, register, reset_password

pytestmark = pytest.mark.asyncio


async def _get_token(session: AsyncSession, member_id: object) -> PasswordResetToken:
    result = await session.execute(
        select(PasswordResetToken).where(PasswordResetToken.member_id == member_id)
    )
    return result.scalar_one()


async def test_forgot_password_issues_token_with_one_hour_expiry(
    db_session: AsyncSession,
) -> None:
    member = await register(db_session, "reset1@example.com", "abc12345")
    await forgot_password(db_session, "reset1@example.com")

    token = await _get_token(db_session, member.id)
    assert token.used_at is None
    delta = token.expires_at - datetime.now(UTC)
    assert timedelta(minutes=55) < delta <= timedelta(hours=1)


async def test_reset_password_consumes_token(db_session: AsyncSession) -> None:
    member = await register(db_session, "reset2@example.com", "abc12345")
    await forgot_password(db_session, "reset2@example.com")
    token = await _get_token(db_session, member.id)

    await reset_password(db_session, token.token, "newpass123")

    await db_session.refresh(token)
    assert token.used_at is not None


async def test_reset_password_rejects_already_used_token(db_session: AsyncSession) -> None:
    member = await register(db_session, "reset3@example.com", "abc12345")
    await forgot_password(db_session, "reset3@example.com")
    token = await _get_token(db_session, member.id)
    await reset_password(db_session, token.token, "newpass123")

    with pytest.raises(ApiError) as exc_info:
        await reset_password(db_session, token.token, "anotherpass123")
    assert exc_info.value.error_code == "RESET_TOKEN_ALREADY_USED"


async def test_reset_password_rejects_expired_token(db_session: AsyncSession) -> None:
    member = await register(db_session, "reset4@example.com", "abc12345")
    await forgot_password(db_session, "reset4@example.com")
    token = await _get_token(db_session, member.id)
    token.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await reset_password(db_session, token.token, "newpass123")
    assert exc_info.value.error_code == "RESET_TOKEN_EXPIRED"


async def test_reset_password_rejects_unknown_token(db_session: AsyncSession) -> None:
    with pytest.raises(ApiError) as exc_info:
        await reset_password(db_session, uuid.uuid4(), "newpass123")
    assert exc_info.value.error_code == "RESET_TOKEN_INVALID"
