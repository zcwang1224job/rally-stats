"""Unit test: after a rejection, the requester can send a brand-new request
— a new row is created, the old 'rejected' row is left untouched (FR-042)."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.friend.models import FriendRequest
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


async def test_resend_after_rejection_creates_a_new_row(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "resenda1@example.com", "A")
    b = await _verified(db_session, "resendb1@example.com", "B")
    first = await create_friend_request(db_session, a.id, b.user_number)
    await respond_friend_request(db_session, b.id, uuid.UUID(first.friend_request_id), accept=False)

    second = await create_friend_request(db_session, a.id, b.user_number)

    assert second.friend_request_id != first.friend_request_id
    assert second.status == "pending"

    result = await db_session.execute(
        select(FriendRequest).where(FriendRequest.id == uuid.UUID(first.friend_request_id))
    )
    original_row = result.scalar_one()
    assert original_row.status == "rejected"
