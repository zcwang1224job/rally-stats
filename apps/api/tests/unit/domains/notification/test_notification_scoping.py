"""Unit test: a notification is only ever visible to its actual recipient
(FR-009) — neither the requester nor an unrelated third member sees it or
has their own unread count affected."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.friend.service import create_friend_request
from app.domains.member.models import Member
from app.domains.member.service import register
from app.domains.notification.service import get_unread_count

pytestmark = pytest.mark.asyncio


async def _verified(session: AsyncSession, email: str, nickname: str) -> Member:
    member = await register(session, email, "abc12345")
    member.verification_status = "verified"
    member.nickname = nickname
    await session.commit()
    return member


async def test_only_the_addressee_has_an_unread_notification(db_session: AsyncSession) -> None:
    a = await _verified(db_session, "notif-scope-a@example.com", "A")
    b = await _verified(db_session, "notif-scope-b@example.com", "B")
    c = await _verified(db_session, "notif-scope-c@example.com", "C")

    await create_friend_request(db_session, a.id, b.user_number)

    assert (await get_unread_count(db_session, b.id)).unread_count == 1
    assert (await get_unread_count(db_session, a.id)).unread_count == 0
    assert (await get_unread_count(db_session, c.id)).unread_count == 0
