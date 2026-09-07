"""Unit test: list_invitable_friends() — research.md #8's combined
already_member/invite-status view (FR-001, FR-004, FR-009)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.service import join_group, leave_group
from app.domains.group_invite.service import (
    accept_invite,
    decline_invite,
    list_invitable_friends,
    send_invite,
)
from tests.unit.domains.group_invite._helpers import (
    become_friends,
    member_created_group,
    verified_member,
)

pytestmark = pytest.mark.asyncio


async def test_not_invited_and_already_member_statuses(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "list-a1@example.com", "A")
    b = await verified_member(db_session, "list-b1@example.com", "B")
    c = await verified_member(db_session, "list-c1@example.com", "C")
    await become_friends(db_session, a, b)
    await become_friends(db_session, a, c)
    group = await member_created_group(db_session, a, max_members=8)
    await join_group(db_session, group, member=c, password=None, nickname=None)

    response = await list_invitable_friends(db_session, group)

    by_id = {f.member_id: f for f in response.friends}
    assert by_id[str(b.id)].invite_status == "not_invited"
    assert by_id[str(b.id)].invite_id is None
    assert by_id[str(c.id)].invite_status == "already_member"


async def test_pending_status_reflects_sent_invite(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "list-a2@example.com", "A")
    b = await verified_member(db_session, "list-b2@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)

    response = await list_invitable_friends(db_session, group)

    by_id = {f.member_id: f for f in response.friends}
    assert by_id[str(b.id)].invite_status == "pending"
    assert by_id[str(b.id)].invite_id == sent.invite_id


async def test_declined_then_reinvited_reflects_latest_status(db_session: AsyncSession) -> None:
    """FR-008: declining does not permanently block re-invites — the list
    must reflect the MOST RECENT invite, not the first one ever sent."""
    a = await verified_member(db_session, "list-a3@example.com", "A")
    b = await verified_member(db_session, "list-b3@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    first = await send_invite(db_session, group, a.id, b.id)

    await decline_invite(db_session, b.id, uuid.UUID(first.invite_id))

    response = await list_invitable_friends(db_session, group)
    by_id = {f.member_id: f for f in response.friends}
    assert by_id[str(b.id)].invite_status == "declined"

    second = await send_invite(db_session, group, a.id, b.id)
    response_after_reinvite = await list_invitable_friends(db_session, group)
    by_id_after = {f.member_id: f for f in response_after_reinvite.friends}
    assert by_id_after[str(b.id)].invite_status == "pending"
    assert by_id_after[str(b.id)].invite_id == second.invite_id


async def test_accepted_then_left_reverts_to_not_invited_and_allows_reinvite(
    db_session: AsyncSession,
) -> None:
    """Bug report: 團長邀請好友後，對方接受後又退出，這樣組團仍然顯示已接受，
    無法再次邀請 — an accepted invite must not permanently strand the
    creator once the invitee is no longer actually in the group."""
    a = await verified_member(db_session, "list-a4@example.com", "A")
    b = await verified_member(db_session, "list-b4@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)
    accepted = await accept_invite(db_session, b, uuid.UUID(sent.invite_id))

    response_while_active = await list_invitable_friends(db_session, group)
    assert (
        next(f for f in response_while_active.friends if f.member_id == str(b.id)).invite_status
        == "already_member"
    )

    await leave_group(
        db_session,
        group,
        uuid.UUID(accepted.roster_entry_id),
        guest_session_token=None,
        member_id=b.id,
    )

    response_after_leaving = await list_invitable_friends(db_session, group)
    by_id = {f.member_id: f for f in response_after_leaving.friends}
    assert by_id[str(b.id)].invite_status == "not_invited"
    assert by_id[str(b.id)].invite_id is None

    # And re-inviting must actually succeed, not just be offered in the UI.
    reinvited = await send_invite(db_session, group, a.id, b.id)
    assert reinvited.status == "pending"
