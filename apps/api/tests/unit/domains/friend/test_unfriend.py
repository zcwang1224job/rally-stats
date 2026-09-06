"""Unit test: unfriend() transitions accepted -> unfriended, permits
unlimited resend afterward, and only operates on accepted relationships
(FR-043~046)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.friend.service import (
    create_friend_request,
    get_friendship_status,
    respond_friend_request,
    unfriend,
)
from app.domains.member.models import Member
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _verified(session: AsyncSession, email: str, nickname: str) -> Member:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()
    return member


async def _become_friends(session: AsyncSession, a: Member, b: Member) -> str:
    created = await create_friend_request(session, a.id, b.user_number)
    await respond_friend_request(session, b.id, uuid.UUID(created.friend_request_id), accept=True)
    return created.friend_request_id


async def test_unfriend_transitions_to_unfriended(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "unfrienda1@example.com", "A")
    b = await _verified(db_session, "unfriendb1@example.com", "B")
    friend_request_id = await _become_friends(db_session, a, b)

    result = await unfriend(db_session, a.id, uuid.UUID(friend_request_id))

    assert result.status == "unfriended"
    assert await get_friendship_status(db_session, a.id, b.id) == "none"


async def test_unfriend_allows_unlimited_resend_afterward(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "unfrienda2@example.com", "A")
    b = await _verified(db_session, "unfriendb2@example.com", "B")
    friend_request_id = await _become_friends(db_session, a, b)
    await unfriend(db_session, a.id, uuid.UUID(friend_request_id))

    new_request = await create_friend_request(db_session, a.id, b.user_number)

    assert new_request.status == "pending"


async def test_unfriend_rejects_non_accepted_relationship(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "unfrienda3@example.com", "A")
    b = await _verified(db_session, "unfriendb3@example.com", "B")
    created = await create_friend_request(db_session, a.id, b.user_number)  # still pending

    with pytest.raises(ApiError) as exc_info:
        await unfriend(db_session, a.id, uuid.UUID(created.friend_request_id))
    assert exc_info.value.error_code == "FRIEND_REQUEST_NOT_ACCEPTED"


async def test_unfriend_rejects_unrelated_member(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "unfrienda4@example.com", "A")
    b = await _verified(db_session, "unfriendb4@example.com", "B")
    stranger = await _verified(db_session, "unfriendc4@example.com", "C")
    friend_request_id = await _become_friends(db_session, a, b)

    with pytest.raises(ApiError) as exc_info:
        await unfriend(db_session, stranger.id, uuid.UUID(friend_request_id))
    assert exc_info.value.error_code == "FRIEND_REQUEST_NOT_FOUND"
