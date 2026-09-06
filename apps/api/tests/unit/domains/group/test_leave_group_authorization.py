"""Unit test: leave_group() authorization — a caller can only leave via
their own roster_entry_id; a mismatched Guest token or Member identity is
rejected the same way as a nonexistent entry (005-member-view US4,
research.md #7, contracts/member-view-api.md)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import join_group, leave_group

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Leave Group Auth Test",
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


async def test_wrong_guest_token_rejected(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entry, _ = await join_group(db_session, group, member=None, password=None, nickname="小美")

    with pytest.raises(ApiError) as exc_info:
        await leave_group(
            db_session,
            group,
            entry.id,
            guest_session_token="not-the-right-token",
            member_id=None,
        )
    assert exc_info.value.error_code == "ROSTER_ENTRY_NOT_FOUND"
    assert exc_info.value.status_code == 404


async def test_neither_guest_token_nor_member_rejected(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entry, _ = await join_group(db_session, group, member=None, password=None, nickname="小美")

    with pytest.raises(ApiError) as exc_info:
        await leave_group(db_session, group, entry.id, guest_session_token=None, member_id=None)
    assert exc_info.value.error_code == "ROSTER_ENTRY_NOT_FOUND"


async def test_nonexistent_roster_entry_rejected(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)

    with pytest.raises(ApiError) as exc_info:
        await leave_group(
            db_session, group, uuid.uuid4(), guest_session_token="whatever", member_id=None
        )
    assert exc_info.value.error_code == "ROSTER_ENTRY_NOT_FOUND"


async def test_already_left_entry_rejected(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entry, _ = await join_group(db_session, group, member=None, password=None, nickname="小美")
    entry.status = "left"
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await leave_group(
            db_session,
            group,
            entry.id,
            guest_session_token=entry.guest_session_token,
            member_id=None,
        )
    assert exc_info.value.error_code == "ROSTER_ENTRY_NOT_FOUND"
