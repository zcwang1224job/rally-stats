"""Unit test: send_invite() — FR-001~004, FR-012."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.schemas import CreateGroupRequest
from app.domains.group.service import create_group
from app.domains.group_invite.models import GroupInvite
from app.domains.group_invite.service import send_invite
from app.domains.notification.models import Notification
from tests.unit.domains.group_invite._helpers import (
    become_friends,
    member_created_group,
    verified_member,
)

pytestmark = pytest.mark.asyncio


async def test_send_invite_creates_pending_invite_and_notifies_invitee(
    db_session: AsyncSession,
) -> None:
    a = await verified_member(db_session, "send-a1@example.com", "A")
    b = await verified_member(db_session, "send-b1@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)

    response = await send_invite(db_session, group, a.id, b.id)

    assert response.status == "pending"
    invite = (
        await db_session.execute(
            select(GroupInvite).where(GroupInvite.id == uuid.UUID(response.invite_id))
        )
    ).scalar_one()
    assert invite.group_id == group.id
    assert invite.inviter_member_id == a.id
    assert invite.invitee_member_id == b.id

    notifications = list(
        (
            await db_session.execute(
                select(Notification).where(
                    Notification.member_id == b.id, Notification.type == "group_invite"
                )
            )
        ).scalars()
    )
    assert len(notifications) == 1
    assert notifications[0].source_id == invite.id


async def test_send_invite_rejects_non_friend(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "send-a2@example.com", "A")
    b = await verified_member(db_session, "send-b2@example.com", "B")
    group = await member_created_group(db_session, a)

    with pytest.raises(ApiError) as exc_info:
        await send_invite(db_session, group, a.id, b.id)
    assert exc_info.value.error_code == "NOT_FRIENDS"


async def test_send_invite_rejects_duplicate_pending(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "send-a3@example.com", "A")
    b = await verified_member(db_session, "send-b3@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    await send_invite(db_session, group, a.id, b.id)

    with pytest.raises(ApiError) as exc_info:
        await send_invite(db_session, group, a.id, b.id)
    assert exc_info.value.error_code == "INVITE_ALREADY_PENDING"


async def test_send_invite_rejects_already_group_member(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "send-a4@example.com", "A")
    b = await verified_member(db_session, "send-b4@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    from app.domains.group.service import join_group

    await join_group(db_session, group, member=b, password=None, nickname=None)

    with pytest.raises(ApiError) as exc_info:
        await send_invite(db_session, group, a.id, b.id)
    assert exc_info.value.error_code == "ALREADY_GROUP_MEMBER"


async def test_send_invite_rejects_anonymous_group(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "send-a5@example.com", "A")
    b = await verified_member(db_session, "send-b5@example.com", "B")
    await become_friends(db_session, a, b)
    payload = CreateGroupRequest(
        name="Anon Group",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
        creator_nickname="匿名",
    )
    group, _roster_entry, _admin_pin, _guest_token = await create_group(
        db_session, payload, member=None
    )

    with pytest.raises(ApiError) as exc_info:
        await send_invite(db_session, group, a.id, b.id)
    assert exc_info.value.error_code == "GROUP_NOT_MEMBER_CREATED"
