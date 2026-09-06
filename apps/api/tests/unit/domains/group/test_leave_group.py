"""Unit test: leave_group() success path — calls the existing
handle_member_left(new_status="left") convergence rules and immediately
invalidates the Guest's session token (005-member-view US4, FR-014/016)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import join_group, leave_group, resolve_active_roster_membership
from app.domains.member.models import Member

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Leave Group Test",
        max_members=8,
        match_mode="doubles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def test_leave_group_marks_entry_left(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entry, _ = await join_group(db_session, group, member=None, password=None, nickname="小美")

    updated = await leave_group(
        db_session, group, entry.id, guest_session_token=entry.guest_session_token, member_id=None
    )

    assert updated.status == "left"
    assert updated.left_at is not None


async def test_leave_group_invalidates_guest_token_immediately(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entry, _ = await join_group(db_session, group, member=None, password=None, nickname="小美")
    token = entry.guest_session_token

    await leave_group(db_session, group, entry.id, guest_session_token=token, member_id=None)

    with pytest.raises(ApiError) as exc_info:
        await resolve_active_roster_membership(
            db_session, group.id, guest_session_token=token, member_id=None
        )
    assert exc_info.value.error_code == "MEMBERSHIP_REQUIRED"


async def test_leave_group_member_identity(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    member = Member(
        email="leave-test@example.com",
        password_hash="x",
        nickname="小明",
        user_number="LV000001",
        verification_status="verified",
    )
    db_session.add(member)
    await db_session.commit()
    await db_session.refresh(member)
    entry, _ = await join_group(db_session, group, member=member, password=None, nickname=None)

    updated = await leave_group(
        db_session, group, entry.id, guest_session_token=None, member_id=member.id
    )

    assert updated.status == "left"
