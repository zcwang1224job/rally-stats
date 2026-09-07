"""Unit test: invalidate_pending_invites_for_group()/
invalidate_pending_invites_for_member_pair() — FR-014, Edge Cases (group
disbanded / friendship dissolved while an invite is pending)."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group_invite.models import GroupInvite
from app.domains.group_invite.service import (
    decline_invite,
    invalidate_pending_invites_for_group,
    invalidate_pending_invites_for_member_pair,
    send_invite,
)
from tests.unit.domains.group_invite._helpers import (
    become_friends,
    member_created_group,
    verified_member,
)

pytestmark = pytest.mark.asyncio


async def test_invalidate_for_group_transitions_pending_invites(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "inval-a1@example.com", "A")
    b = await verified_member(db_session, "inval-b1@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)

    await invalidate_pending_invites_for_group(db_session, group.id)
    await db_session.commit()

    invite = (
        await db_session.execute(
            select(GroupInvite).where(GroupInvite.id == uuid.UUID(sent.invite_id))
        )
    ).scalar_one()
    assert invite.status == "invalidated"


async def test_invalidate_for_group_leaves_terminal_invites_untouched(
    db_session: AsyncSession,
) -> None:
    a = await verified_member(db_session, "inval-a2@example.com", "A")
    b = await verified_member(db_session, "inval-b2@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)
    await decline_invite(db_session, b.id, uuid.UUID(sent.invite_id))

    await invalidate_pending_invites_for_group(db_session, group.id)
    await db_session.commit()

    invite = (
        await db_session.execute(
            select(GroupInvite).where(GroupInvite.id == uuid.UUID(sent.invite_id))
        )
    ).scalar_one()
    assert invite.status == "declined"


async def test_invalidate_for_member_pair_transitions_pending_invite(
    db_session: AsyncSession,
) -> None:
    a = await verified_member(db_session, "inval-a3@example.com", "A")
    b = await verified_member(db_session, "inval-b3@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)

    await invalidate_pending_invites_for_member_pair(db_session, b.id, a.id)  # reversed order
    await db_session.commit()

    invite = (
        await db_session.execute(
            select(GroupInvite).where(GroupInvite.id == uuid.UUID(sent.invite_id))
        )
    ).scalar_one()
    assert invite.status == "invalidated"


async def test_invalidate_for_member_pair_ignores_unrelated_pair(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "inval-a4@example.com", "A")
    b = await verified_member(db_session, "inval-b4@example.com", "B")
    stranger = await verified_member(db_session, "inval-c4@example.com", "C")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)

    await invalidate_pending_invites_for_member_pair(db_session, a.id, stranger.id)
    await db_session.commit()

    invite = (
        await db_session.execute(
            select(GroupInvite).where(GroupInvite.id == uuid.UUID(sent.invite_id))
        )
    ).scalar_one()
    assert invite.status == "pending"
