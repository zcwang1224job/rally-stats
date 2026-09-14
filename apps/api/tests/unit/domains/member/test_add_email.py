"""Unit test: `add_email()` — contracts/account-recovery-api.md
`POST /members/me/email` (FR-013)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.member.models import EmailVerificationToken, Member
from app.domains.member.security import hash_password
from app.domains.member.service import add_email, register

pytestmark = pytest.mark.asyncio


async def _make_email_less_member(session: AsyncSession, user_number: str) -> Member:
    member = Member(email=None, password_hash=hash_password("abc12345"), user_number=user_number)
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def test_add_email_success_sends_verification_email(db_session: AsyncSession) -> None:
    member = await _make_email_less_member(db_session, "aB3dEfGh")

    await add_email(db_session, member, "NewEmail@Example.com")

    await db_session.refresh(member)
    assert member.email == "newemail@example.com"

    token = (
        await db_session.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.member_id == member.id)
        )
    ).scalar_one_or_none()
    assert token is not None


async def test_add_email_already_set_is_rejected(db_session: AsyncSession) -> None:
    member = await register(db_session, "alreadyset@example.com", "abc12345")

    with pytest.raises(ApiError) as exc_info:
        await add_email(db_session, member, "another@example.com")
    assert exc_info.value.error_code == "EMAIL_ALREADY_SET"


async def test_add_email_collision_is_rejected(db_session: AsyncSession) -> None:
    await register(db_session, "taken@example.com", "abc12345")
    member = await _make_email_less_member(db_session, "cD4eFgHi")

    with pytest.raises(ApiError) as exc_info:
        await add_email(db_session, member, "taken@example.com")
    assert exc_info.value.error_code == "EMAIL_ALREADY_REGISTERED"

    await db_session.refresh(member)
    assert member.email is None
