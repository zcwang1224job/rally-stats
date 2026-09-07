"""Unit test: sending a friend request creates exactly one Notification row
for the addressee (research.md #4), and the DB-level uniqueness constraint
(type, source_id, member_id) prevents duplicates."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.friend.service import create_friend_request
from app.domains.member.models import Member
from app.domains.member.service import register
from app.domains.notification.models import Notification

pytestmark = pytest.mark.asyncio


async def _verified(session: AsyncSession, email: str, nickname: str) -> Member:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()
    return member


async def test_creating_friend_request_creates_one_notification(
    db_session: AsyncSession,
) -> None:
    a = await _verified(db_session, "notif-create-a@example.com", "A")
    b = await _verified(db_session, "notif-create-b@example.com", "B")

    response = await create_friend_request(db_session, a.id, b.user_number)

    result = await db_session.execute(select(Notification).where(Notification.member_id == b.id))
    notifications = list(result.scalars())
    assert len(notifications) == 1
    assert notifications[0].type == "friend_request"
    assert str(notifications[0].source_id) == response.friend_request_id
    assert notifications[0].read_at is None


async def test_duplicate_type_source_member_rejected_at_db_level(
    db_session: AsyncSession,
) -> None:
    """Bypasses the service layer entirely to prove the DB constraint
    itself (not just application logic) enforces the rule."""
    a = await _verified(db_session, "notif-dup-a@example.com", "A")
    b = await _verified(db_session, "notif-dup-b@example.com", "B")

    response = await create_friend_request(db_session, a.id, b.user_number)

    db_session.add(
        Notification(
            member_id=b.id,
            type="friend_request",
            source_id=uuid.UUID(response.friend_request_id),
        )
    )
    with pytest.raises(Exception):  # noqa: B017 - asserting the raw DB IntegrityError surfaces
        await db_session.commit()
