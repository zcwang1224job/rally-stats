"""Unit test: get_invite_detail() — invitee-only visibility (FR-005/010)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group_invite.service import get_invite_detail, send_invite
from tests.unit.domains.group_invite._helpers import (
    become_friends,
    member_created_group,
    verified_member,
)

pytestmark = pytest.mark.asyncio


async def test_get_invite_detail_returns_live_status(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "detail-a1@example.com", "A")
    b = await verified_member(db_session, "detail-b1@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)

    detail = await get_invite_detail(db_session, b.id, uuid.UUID(sent.invite_id))

    assert detail.status == "pending"
    assert detail.group_id == str(group.id)
    assert detail.group_name == group.name
    assert detail.inviter_nickname == "A"


async def test_get_invite_detail_rejects_non_invitee(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "detail-a2@example.com", "A")
    b = await verified_member(db_session, "detail-b2@example.com", "B")
    stranger = await verified_member(db_session, "detail-c2@example.com", "C")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)

    with pytest.raises(ApiError) as exc_info:
        await get_invite_detail(db_session, stranger.id, uuid.UUID(sent.invite_id))
    assert exc_info.value.error_code == "GROUP_INVITE_NOT_FOUND"


async def test_get_invite_detail_rejects_unknown_id(db_session: AsyncSession) -> None:
    b = await verified_member(db_session, "detail-b3@example.com", "B")

    with pytest.raises(ApiError) as exc_info:
        await get_invite_detail(db_session, b.id, uuid.uuid4())
    assert exc_info.value.error_code == "GROUP_INVITE_NOT_FOUND"
