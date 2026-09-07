"""Unit test: mark_all_read() (FR-008) and mark_notification_read()
(FR-007) — idempotency, scoping to the calling member, and the
NOTIFICATION_NOT_FOUND error for a notification that doesn't belong to
the caller."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.friend.service import create_friend_request
from app.domains.member.models import Member
from app.domains.member.service import register
from app.domains.notification.service import (
    get_unread_count,
    list_notifications,
    mark_all_read,
    mark_notification_read,
)

pytestmark = pytest.mark.asyncio


async def _verified(session: AsyncSession, email: str, nickname: str) -> Member:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()
    return member


async def test_mark_all_read_marks_every_unread_and_is_idempotent(
    db_session: AsyncSession,
) -> None:
    b = await _verified(db_session, "notif-markall-b@example.com", "B")
    a1 = await _verified(db_session, "notif-markall-a1@example.com", "A1")
    a2 = await _verified(db_session, "notif-markall-a2@example.com", "A2")
    await create_friend_request(db_session, a1.id, b.user_number)
    await create_friend_request(db_session, a2.id, b.user_number)

    first_call = await mark_all_read(db_session, b.id)
    assert first_call.marked_count == 2
    assert (await get_unread_count(db_session, b.id)).unread_count == 0

    second_call = await mark_all_read(db_session, b.id)
    assert second_call.marked_count == 0


async def test_mark_notification_read_is_idempotent(db_session: AsyncSession) -> None:
    b = await _verified(db_session, "notif-markone-b@example.com", "B")
    a = await _verified(db_session, "notif-markone-a@example.com", "A")
    await create_friend_request(db_session, a.id, b.user_number)
    notification_id = uuid.UUID(
        (await list_notifications(db_session, b.id)).notifications[0].notification_id
    )

    first = await mark_notification_read(db_session, b.id, notification_id)
    assert first.read_at is not None

    second = await mark_notification_read(db_session, b.id, notification_id)
    assert second.read_at is not None


async def test_mark_notification_read_rejects_foreign_notification(
    db_session: AsyncSession,
) -> None:
    b = await _verified(db_session, "notif-markforeign-b@example.com", "B")
    c = await _verified(db_session, "notif-markforeign-c@example.com", "C")
    a = await _verified(db_session, "notif-markforeign-a@example.com", "A")
    await create_friend_request(db_session, a.id, b.user_number)
    notification_id = uuid.UUID(
        (await list_notifications(db_session, b.id)).notifications[0].notification_id
    )

    with pytest.raises(ApiError) as exc_info:
        await mark_notification_read(db_session, c.id, notification_id)
    assert exc_info.value.error_code == "NOTIFICATION_NOT_FOUND"


async def test_mark_notification_read_rejects_unknown_id(db_session: AsyncSession) -> None:
    b = await _verified(db_session, "notif-markunknown-b@example.com", "B")

    with pytest.raises(ApiError) as exc_info:
        await mark_notification_read(db_session, b.id, uuid.uuid4())
    assert exc_info.value.error_code == "NOTIFICATION_NOT_FOUND"
