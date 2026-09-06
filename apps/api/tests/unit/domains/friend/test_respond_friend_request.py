"""Unit test: respond_friend_request() only lets the addressee accept/reject
(FR-040) — a non-addressee gets FRIEND_REQUEST_NOT_FOUND, never a hint that
the request exists."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.friend.service import create_friend_request, respond_friend_request
from app.domains.member.models import Member
from app.domains.member.service import register

pytestmark = pytest.mark.asyncio


async def _verified(session: AsyncSession, email: str, nickname: str) -> Member:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()
    return member


async def test_addressee_can_accept(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "responda1@example.com", "A")
    b = await _verified(db_session, "respondb1@example.com", "B")
    created = await create_friend_request(db_session, a.id, b.user_number)

    result = await respond_friend_request(
        db_session, b.id, uuid.UUID(created.friend_request_id), accept=True
    )
    assert result.status == "accepted"


async def test_addressee_can_reject(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "responda2@example.com", "A")
    b = await _verified(db_session, "respondb2@example.com", "B")
    created = await create_friend_request(db_session, a.id, b.user_number)

    result = await respond_friend_request(
        db_session, b.id, uuid.UUID(created.friend_request_id), accept=False
    )
    assert result.status == "rejected"


async def test_requester_cannot_respond_to_own_request(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "responda3@example.com", "A")
    b = await _verified(db_session, "respondb3@example.com", "B")
    created = await create_friend_request(db_session, a.id, b.user_number)

    with pytest.raises(ApiError) as exc_info:
        await respond_friend_request(
            db_session, a.id, uuid.UUID(created.friend_request_id), accept=True
        )
    assert exc_info.value.error_code == "FRIEND_REQUEST_NOT_FOUND"


async def test_unrelated_member_cannot_respond(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "responda4@example.com", "A")
    b = await _verified(db_session, "respondb4@example.com", "B")
    stranger = await _verified(db_session, "respondc4@example.com", "C")
    created = await create_friend_request(db_session, a.id, b.user_number)

    with pytest.raises(ApiError) as exc_info:
        await respond_friend_request(
            db_session, stranger.id, uuid.UUID(created.friend_request_id), accept=True
        )
    assert exc_info.value.error_code == "FRIEND_REQUEST_NOT_FOUND"


async def test_already_responded_request_cannot_be_responded_to_again(
    db_session: AsyncSession,
) -> None:
    a = await _verified(db_session, "responda5@example.com", "A")
    b = await _verified(db_session, "respondb5@example.com", "B")
    created = await create_friend_request(db_session, a.id, b.user_number)
    await respond_friend_request(
        db_session, b.id, uuid.UUID(created.friend_request_id), accept=True
    )

    with pytest.raises(ApiError) as exc_info:
        await respond_friend_request(
            db_session, b.id, uuid.UUID(created.friend_request_id), accept=False
        )
    assert exc_info.value.error_code == "FRIEND_REQUEST_NOT_PENDING"
