"""Unit test: accept_invite() — FR-006/007 (skip-password join success),
FR-013 (capacity-full leaves the invite pending and notifies the inviter),
authorization boundaries."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group_invite.models import GroupInvite
from app.domains.group_invite.service import accept_invite, decline_invite, send_invite
from app.domains.member.models import Member
from app.domains.notification.models import Notification
from tests.unit.domains.group_invite._helpers import (
    become_friends,
    member_created_group,
    verified_member,
)

pytestmark = pytest.mark.asyncio


async def test_accept_invite_joins_and_skips_password_even_when_group_has_one(
    db_session: AsyncSession,
) -> None:
    a = await verified_member(db_session, "accept-a1@example.com", "A")
    b = await verified_member(db_session, "accept-b1@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a, password="secret123")
    sent = await send_invite(db_session, group, a.id, b.id)

    response = await accept_invite(db_session, b, uuid.UUID(sent.invite_id))

    assert response.group_id == str(group.id)
    assert response.nickname == "B"
    invite = (
        await db_session.execute(
            select(GroupInvite).where(GroupInvite.id == uuid.UUID(sent.invite_id))
        )
    ).scalar_one()
    assert invite.status == "accepted"


async def test_accept_invite_rejects_non_pending(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "accept-a2@example.com", "A")
    b = await verified_member(db_session, "accept-b2@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)
    await decline_invite(db_session, b.id, uuid.UUID(sent.invite_id))

    with pytest.raises(ApiError) as exc_info:
        await accept_invite(db_session, b, uuid.UUID(sent.invite_id))
    assert exc_info.value.error_code == "GROUP_INVITE_NOT_PENDING"


async def test_accept_invite_rejects_non_invitee(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "accept-a3@example.com", "A")
    b = await verified_member(db_session, "accept-b3@example.com", "B")
    stranger = await verified_member(db_session, "accept-c3@example.com", "C")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)

    with pytest.raises(ApiError) as exc_info:
        await accept_invite(db_session, stranger, uuid.UUID(sent.invite_id))
    assert exc_info.value.error_code == "GROUP_INVITE_NOT_FOUND"


async def test_accept_invite_full_group_stays_pending_and_notifies_inviter(
    db_session: AsyncSession,
) -> None:
    a = await verified_member(db_session, "accept-a4@example.com", "A")
    b = await verified_member(db_session, "accept-b4@example.com", "B")
    filler = await verified_member(db_session, "accept-filler4@example.com", "Filler")
    await become_friends(db_session, a, b)
    # max_members=2, singles: creator (a) is the only pre-existing member —
    # fill the remaining single seat before b tries to accept.
    group = await member_created_group(db_session, a, max_members=2, match_mode="singles")
    await become_friends(db_session, a, filler)
    from app.domains.group.service import join_group

    await join_group(db_session, group, member=filler, password=None, nickname=None)
    sent = await send_invite(db_session, group, a.id, b.id)

    with pytest.raises(ApiError) as exc_info:
        await accept_invite(db_session, b, uuid.UUID(sent.invite_id))
    assert exc_info.value.error_code == "GROUP_FULL"

    invite = (
        await db_session.execute(
            select(GroupInvite).where(GroupInvite.id == uuid.UUID(sent.invite_id))
        )
    ).scalar_one()
    assert invite.status == "pending"

    notifications = list(
        (
            await db_session.execute(
                select(Notification).where(
                    Notification.member_id == a.id,
                    Notification.type == "group_invite_capacity_full",
                )
            )
        ).scalars()
    )
    assert len(notifications) == 1
    assert notifications[0].source_id == invite.id


async def test_accept_invite_repeated_capacity_full_does_not_duplicate_notification(
    db_session: AsyncSession,
) -> None:
    """The DB's uq_notifications_type_source_member index caps this at one
    notification per invite per inviter across repeat failed attempts —
    a second failed accept on the same invite MUST NOT raise or duplicate."""
    a = await verified_member(db_session, "accept-a5@example.com", "A")
    b = await verified_member(db_session, "accept-b5@example.com", "B")
    filler = await verified_member(db_session, "accept-filler5@example.com", "Filler")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a, max_members=2, match_mode="singles")
    await become_friends(db_session, a, filler)
    from app.domains.group.service import join_group

    await join_group(db_session, group, member=filler, password=None, nickname=None)
    sent = await send_invite(db_session, group, a.id, b.id)
    a_id = a.id

    for _ in range(2):
        # A failed accept attempt's `_notify_inviter_capacity_full` may roll
        # back this shared session (on the second attempt's duplicate-key
        # IntegrityError) — re-fetch `b` fresh each iteration rather than
        # reusing the same expired-then-detached ORM instance across calls
        # (a test-only artifact of sharing one session across service calls;
        # a real request gets its own fresh session per call).
        b = (await db_session.execute(select(Member).where(Member.id == b.id))).scalar_one()
        with pytest.raises(ApiError) as exc_info:
            await accept_invite(db_session, b, uuid.UUID(sent.invite_id))
        assert exc_info.value.error_code == "GROUP_FULL"

    notifications = list(
        (
            await db_session.execute(
                select(Notification).where(
                    Notification.member_id == a_id,
                    Notification.type == "group_invite_capacity_full",
                )
            )
        ).scalars()
    )
    assert len(notifications) == 1
