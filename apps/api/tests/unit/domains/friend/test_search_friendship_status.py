"""Unit test: get_friendship_status() four-state logic (FR-038)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.friend.service import (
    create_friend_request,
    get_friendship_status,
    respond_friend_request,
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


async def test_status_is_none_with_no_relationship(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "statusa1@example.com", "A")
    b = await _verified(db_session, "statusb1@example.com", "B")

    assert await get_friendship_status(db_session, a.id, b.id) == "none"


async def test_status_is_pending_outgoing_and_incoming(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "statusa2@example.com", "A")
    b = await _verified(db_session, "statusb2@example.com", "B")
    await create_friend_request(db_session, a.id, b.user_number)

    assert await get_friendship_status(db_session, a.id, b.id) == "pending_outgoing"
    assert await get_friendship_status(db_session, b.id, a.id) == "pending_incoming"


async def test_status_is_friends_after_accepted(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "statusa3@example.com", "A")
    b = await _verified(db_session, "statusb3@example.com", "B")
    created = await create_friend_request(db_session, a.id, b.user_number)
    await respond_friend_request(
        db_session, b.id, uuid.UUID(created.friend_request_id), accept=True
    )

    assert await get_friendship_status(db_session, a.id, b.id) == "friends"
    assert await get_friendship_status(db_session, b.id, a.id) == "friends"
