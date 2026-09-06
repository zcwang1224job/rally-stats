"""Unit test: search/create-request exclude unverified accounts (FR-036)
and reject targeting oneself (FR-037)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.friend.service import create_friend_request
from app.domains.member.models import Member
from app.domains.member.service import register, search_member

pytestmark = pytest.mark.asyncio


async def _verified(session: AsyncSession, email: str, nickname: str) -> Member:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()
    return member


async def test_search_excludes_unverified_account(db_session: AsyncSession) -> None:
    searcher = await _verified(db_session, "exclude1@example.com", "A")
    unverified = await register(db_session, "exclude2@example.com", "abc12345")

    with pytest.raises(ApiError) as exc_info:
        await search_member(db_session, unverified.user_number, searcher.id)
    assert exc_info.value.error_code == "MEMBER_NOT_FOUND"


async def test_search_rejects_self(db_session: AsyncSession) -> None:
    searcher = await _verified(db_session, "exclude3@example.com", "A")

    with pytest.raises(ApiError) as exc_info:
        await search_member(db_session, searcher.user_number, searcher.id)
    assert exc_info.value.error_code == "CANNOT_SEARCH_SELF"


async def test_create_friend_request_excludes_unverified_account(db_session: AsyncSession) -> None:
    requester = await _verified(db_session, "exclude4@example.com", "A")
    unverified = await register(db_session, "exclude5@example.com", "abc12345")

    with pytest.raises(ApiError) as exc_info:
        await create_friend_request(db_session, requester.id, unverified.user_number)
    assert exc_info.value.error_code == "MEMBER_NOT_FOUND"


async def test_create_friend_request_rejects_self(db_session: AsyncSession) -> None:
    requester = await _verified(db_session, "exclude6@example.com", "A")

    with pytest.raises(ApiError) as exc_info:
        await create_friend_request(db_session, requester.id, requester.user_number)
    assert exc_info.value.error_code == "CANNOT_FRIEND_SELF"
