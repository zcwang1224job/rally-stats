"""Unit test: cancel_invite() — the creator withdrawing a pending invite
before the invitee answers, and the accept path that must then refuse."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group_invite.service import (
    accept_invite,
    cancel_invite,
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


async def test_cancel_invite_transitions_to_cancelled(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "cancel-a1@example.com", "A")
    b = await verified_member(db_session, "cancel-b1@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)

    response = await cancel_invite(db_session, group.id, uuid.UUID(sent.invite_id))

    assert response.invite_id == sent.invite_id
    assert response.status == "cancelled"


async def test_cancelled_invite_cannot_be_accepted(db_session: AsyncSession) -> None:
    """The bug report's actual ask: the friend taps 接受邀請 after the
    creator withdrew it, and does NOT get into the group."""
    a = await verified_member(db_session, "cancel-a2@example.com", "A")
    b = await verified_member(db_session, "cancel-b2@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)
    await cancel_invite(db_session, group.id, uuid.UUID(sent.invite_id))

    with pytest.raises(ApiError) as exc_info:
        await accept_invite(db_session, b, uuid.UUID(sent.invite_id))
    assert exc_info.value.error_code == "GROUP_INVITE_CANCELLED"
    assert exc_info.value.status_code == 409


async def test_cancelled_invite_cannot_be_declined(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "cancel-a3@example.com", "A")
    b = await verified_member(db_session, "cancel-b3@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)
    await cancel_invite(db_session, group.id, uuid.UUID(sent.invite_id))

    with pytest.raises(ApiError) as exc_info:
        await decline_invite(db_session, b.id, uuid.UUID(sent.invite_id))
    assert exc_info.value.error_code == "GROUP_INVITE_NOT_PENDING"


async def test_cancel_invite_rejects_already_accepted(db_session: AsyncSession) -> None:
    """The race the other way round: the invitee got in first, so the
    creator's cancel must not retroactively undo a real membership."""
    a = await verified_member(db_session, "cancel-a4@example.com", "A")
    b = await verified_member(db_session, "cancel-b4@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)
    await accept_invite(db_session, b, uuid.UUID(sent.invite_id))

    with pytest.raises(ApiError) as exc_info:
        await cancel_invite(db_session, group.id, uuid.UUID(sent.invite_id))
    assert exc_info.value.error_code == "GROUP_INVITE_NOT_PENDING"


async def test_cancel_invite_is_not_repeatable(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "cancel-a5@example.com", "A")
    b = await verified_member(db_session, "cancel-b5@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)
    await cancel_invite(db_session, group.id, uuid.UUID(sent.invite_id))

    with pytest.raises(ApiError) as exc_info:
        await cancel_invite(db_session, group.id, uuid.UUID(sent.invite_id))
    assert exc_info.value.error_code == "GROUP_INVITE_NOT_PENDING"


async def test_cancel_invite_rejects_other_groups_invite(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "cancel-a6@example.com", "A")
    b = await verified_member(db_session, "cancel-b6@example.com", "B")
    c = await verified_member(db_session, "cancel-c6@example.com", "C")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    # A second creator's group — the `require_admin` token that reaches
    # `cancel_invite` is always scoped to one group, so this stands in for
    # "another group's admin tries to cancel my invite".
    other_group = await member_created_group(db_session, c, name="Other Group")
    sent = await send_invite(db_session, group, a.id, b.id)

    with pytest.raises(ApiError) as exc_info:
        await cancel_invite(db_session, other_group.id, uuid.UUID(sent.invite_id))
    assert exc_info.value.error_code == "GROUP_INVITE_NOT_FOUND"


async def test_cancel_invite_rejects_unknown_invite(db_session: AsyncSession) -> None:
    a = await verified_member(db_session, "cancel-a7@example.com", "A")
    group = await member_created_group(db_session, a)

    with pytest.raises(ApiError) as exc_info:
        await cancel_invite(db_session, group.id, uuid.uuid4())
    assert exc_info.value.error_code == "GROUP_INVITE_NOT_FOUND"


async def test_cancelled_friend_is_listed_as_cancelled_and_re_invitable(
    db_session: AsyncSession,
) -> None:
    a = await verified_member(db_session, "cancel-a8@example.com", "A")
    b = await verified_member(db_session, "cancel-b8@example.com", "B")
    await become_friends(db_session, a, b)
    group = await member_created_group(db_session, a)
    sent = await send_invite(db_session, group, a.id, b.id)
    await cancel_invite(db_session, group.id, uuid.UUID(sent.invite_id))

    listed = await list_invitable_friends(db_session, group)
    row = next(f for f in listed.friends if f.member_id == str(b.id))
    assert row.invite_status == "cancelled"
    assert row.invite_id == sent.invite_id

    # The partial unique index only covers `pending`, so a fresh invite is
    # a brand-new row rather than an INVITE_ALREADY_PENDING conflict.
    resent = await send_invite(db_session, group, a.id, b.id)
    assert resent.invite_id != sent.invite_id
    assert resent.status == "pending"

    listed_again = await list_invitable_friends(db_session, group)
    row_again = next(f for f in listed_again.friends if f.member_id == str(b.id))
    assert row_again.invite_status == "pending"
    assert row_again.invite_id == resent.invite_id
