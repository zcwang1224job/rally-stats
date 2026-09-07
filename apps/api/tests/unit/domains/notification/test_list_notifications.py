"""Unit test: list_notifications() — newest-first ordering, correct
read/unread reflection, and that listing itself never mutates read_at
(FR-004/005/013)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.friend.service import create_friend_request
from app.domains.member.models import Member
from app.domains.member.service import register
from app.domains.notification.service import list_notifications, mark_notification_read

pytestmark = pytest.mark.asyncio


async def _verified(session: AsyncSession, email: str, nickname: str) -> Member:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()
    return member


async def test_list_is_newest_first_and_reflects_read_state(db_session: AsyncSession) -> None:
    b = await _verified(db_session, "notif-list-b@example.com", "B")
    requester_1 = await _verified(db_session, "notif-list-r1@example.com", "R1")
    requester_2 = await _verified(db_session, "notif-list-r2@example.com", "R2")

    first = await create_friend_request(db_session, requester_1.id, b.user_number)
    second = await create_friend_request(db_session, requester_2.id, b.user_number)

    response = await list_notifications(db_session, b.id)

    assert response.unread_count == 2
    assert len(response.notifications) == 2
    # Newest (second) first.
    assert response.notifications[0].friend_request is not None
    assert response.notifications[0].friend_request.friend_request_id == second.friend_request_id
    assert response.notifications[0].read is False
    assert response.notifications[1].friend_request is not None
    assert response.notifications[1].friend_request.friend_request_id == first.friend_request_id
    assert response.notifications[1].read is False


async def test_listing_does_not_mark_anything_as_read(db_session: AsyncSession) -> None:
    b = await _verified(db_session, "notif-list-noop-b@example.com", "B")
    a = await _verified(db_session, "notif-list-noop-a@example.com", "A")
    await create_friend_request(db_session, a.id, b.user_number)

    await list_notifications(db_session, b.id)
    await list_notifications(db_session, b.id)

    response = await list_notifications(db_session, b.id)
    assert response.unread_count == 1
    assert response.notifications[0].read is False


async def test_list_reflects_read_state_after_marking_read(db_session: AsyncSession) -> None:
    b = await _verified(db_session, "notif-list-read-b@example.com", "B")
    a = await _verified(db_session, "notif-list-read-a@example.com", "A")
    await create_friend_request(db_session, a.id, b.user_number)
    unread_notification = (await list_notifications(db_session, b.id)).notifications[0]

    await mark_notification_read(
        db_session, b.id, uuid.UUID(unread_notification.notification_id)
    )

    response = await list_notifications(db_session, b.id)
    assert response.unread_count == 0
    assert response.notifications[0].read is True
