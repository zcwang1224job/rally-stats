"""Unit test: password hashing round-trip, access/refresh JWT issuance and
decoding — including token_version mismatch rejection and access/refresh
type discrimination (research.md #2, #3)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.member.models import Member
from app.domains.member.security import (
    hash_password,
    issue_access_token,
    issue_refresh_token,
    refresh_access_token,
    require_member,
    verify_password,
)


async def _make_member(session: AsyncSession, email: str, user_number: str) -> Member:
    member = Member(email=email, password_hash=hash_password("abc12345"), user_number=user_number)
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


def test_hash_password_round_trip() -> None:
    hashed = hash_password("abc12345")
    assert hashed != "abc12345"
    assert verify_password("abc12345", hashed) is True
    assert verify_password("wrong-password", hashed) is False


@pytest.mark.asyncio
async def test_require_member_accepts_valid_access_token(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "a@example.com", "aB3dEfGh")

    token = issue_access_token(str(member.id), member.token_version)
    resolved = await require_member(authorization=f"Bearer {token}", session=db_session)
    assert resolved.id == member.id


@pytest.mark.asyncio
async def test_require_member_rejects_stale_token_version(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "b@example.com", "cD4eFgHi")

    stale_token = issue_access_token(str(member.id), member.token_version)
    member.token_version += 1
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await require_member(authorization=f"Bearer {stale_token}", session=db_session)
    assert exc_info.value.error_code == "MEMBER_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_require_member_rejects_refresh_token(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "c@example.com", "eF5gHiJk")

    refresh_token = issue_refresh_token(str(member.id), member.token_version)
    with pytest.raises(ApiError) as exc_info:
        await require_member(authorization=f"Bearer {refresh_token}", session=db_session)
    assert exc_info.value.error_code == "MEMBER_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_refresh_access_token_rejects_access_token(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "d@example.com", "gH6iJkLm")

    access_token = issue_access_token(str(member.id), member.token_version)
    with pytest.raises(ApiError) as exc_info:
        await refresh_access_token(db_session, access_token)
    assert exc_info.value.error_code == "REFRESH_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_refresh_access_token_issues_new_access_token(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "e@example.com", "iJ7kLmNo")

    refresh_token = issue_refresh_token(str(member.id), member.token_version)
    new_access_token = await refresh_access_token(db_session, refresh_token)
    resolved = await require_member(authorization=f"Bearer {new_access_token}", session=db_session)
    assert resolved.id == member.id
