"""Unit test: email_verification_tokens lifecycle — issuance at
registration, expiry, used_at marking, already-used/expired errors."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.member.models import EmailVerificationToken
from app.domains.member.service import register, verify_email

pytestmark = pytest.mark.asyncio


async def _get_token(session: AsyncSession, member_id: object) -> EmailVerificationToken:
    result = await session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.member_id == member_id)
    )
    return result.scalar_one()


async def test_register_issues_verification_token(db_session: AsyncSession) -> None:
    member = await register(db_session, "verify@example.com", "abc12345")
    token = await _get_token(db_session, member.id)
    assert token.used_at is None
    assert token.expires_at > datetime.now(UTC)


async def test_verify_email_marks_verified_and_consumes_token(db_session: AsyncSession) -> None:
    member = await register(db_session, "verify2@example.com", "abc12345")
    token = await _get_token(db_session, member.id)

    verified_member = await verify_email(db_session, token.token)
    assert verified_member.verification_status == "verified"

    await db_session.refresh(token)
    assert token.used_at is not None


async def test_verify_email_rejects_unknown_token(db_session: AsyncSession) -> None:
    with pytest.raises(ApiError) as exc_info:
        await verify_email(db_session, uuid.uuid4())
    assert exc_info.value.error_code == "VERIFICATION_TOKEN_INVALID"


async def test_verify_email_rejects_already_used_token(db_session: AsyncSession) -> None:
    member = await register(db_session, "verify3@example.com", "abc12345")
    token = await _get_token(db_session, member.id)
    await verify_email(db_session, token.token)

    with pytest.raises(ApiError) as exc_info:
        await verify_email(db_session, token.token)
    assert exc_info.value.error_code == "VERIFICATION_TOKEN_ALREADY_USED"


async def test_verify_email_rejects_expired_token(db_session: AsyncSession) -> None:
    member = await register(db_session, "verify4@example.com", "abc12345")
    token = await _get_token(db_session, member.id)
    token.expires_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await verify_email(db_session, token.token)
    assert exc_info.value.error_code == "VERIFICATION_TOKEN_EXPIRED"
