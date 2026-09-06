"""Unit test: FR-004 Email uniqueness (case-insensitive after FR-006
normalization) rejects duplicate registration."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def test_register_creates_member_with_lowercased_email(db_session: AsyncSession) -> None:
    member = await register(db_session, "MixedCase@Example.com", "abc12345")
    assert member.email == "mixedcase@example.com"
    assert member.verification_status == "unverified"


async def test_register_rejects_duplicate_email(db_session: AsyncSession) -> None:
    await register(db_session, "dup@example.com", "abc12345")

    with pytest.raises(ApiError) as exc_info:
        await register(db_session, "dup@example.com", "abc12345")
    assert exc_info.value.error_code == "EMAIL_ALREADY_REGISTERED"


async def test_register_rejects_duplicate_email_different_case(db_session: AsyncSession) -> None:
    await register(db_session, "case@example.com", "abc12345")

    with pytest.raises(ApiError) as exc_info:
        await register(db_session, "CASE@EXAMPLE.COM", "abc12345")
    assert exc_info.value.error_code == "EMAIL_ALREADY_REGISTERED"


async def test_register_assigns_unique_user_number(db_session: AsyncSession) -> None:
    member = await register(db_session, "usernum@example.com", "abc12345")
    assert len(member.user_number) == 8
