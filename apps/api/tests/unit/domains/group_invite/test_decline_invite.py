"""Unit test: decline_invite() — FR-008."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group_invite.service import decline_invite, send_invite
from tests.unit.domains.group_invite._helpers import (
    become_friends,
    member_created_group,
    verified_member,
)

pytestmark = pytest.mark.asyncio


async def test_decline_invite_transitions_to_declined(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "decline-a1@example.com", "A")
    b = await verified_member(db_session, "decline-b1@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)

    response = await decline_invite(db_session, b.id, uuid.UUID(sent.invite_id))

    assert response.status == "declined"


async def test_decline_invite_rejects_non_pending(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "decline-a2@example.com", "A")
    b = await verified_member(db_session, "decline-b2@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)
    await decline_invite(db_session, b.id, uuid.UUID(sent.invite_id))

    with pytest.raises(ApiError) as exc_info:
        await decline_invite(db_session, b.id, uuid.UUID(sent.invite_id))
    assert exc_info.value.error_code == "GROUP_INVITE_NOT_PENDING"


async def test_decline_invite_rejects_non_invitee(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "decline-a3@example.com", "A")
    b = await verified_member(db_session, "decline-b3@example.com", "B")
    stranger = await verified_member(db_session, "decline-c3@example.com", "C")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)

    with pytest.raises(ApiError) as exc_info:
        await decline_invite(db_session, stranger.id, uuid.UUID(sent.invite_id))
    assert exc_info.value.error_code == "GROUP_INVITE_NOT_FOUND"
