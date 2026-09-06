"""Unit test: join_group() raises GROUP_FULL for an already-full group
(single-request scenario; the real concurrency guarantee is tested
separately in test_join_capacity_concurrency.py, US3)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import join_group
from app.domains.roster.models import RosterEntry

pytestmark = pytest.mark.asyncio


async def _make_full_group(session: AsyncSession, name: str) -> Group:
    group = Group(
        name=name,
        max_members=1,
        match_mode="singles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def test_join_full_group_raises_group_full(db_session: AsyncSession) -> None:
    group = await _make_full_group(db_session, "Full Group Test")

    with pytest.raises(ApiError) as exc_info:
        await join_group(db_session, group, member=None, password=None, nickname="小美")
    assert exc_info.value.error_code == "GROUP_FULL"


async def test_join_full_group_does_not_create_roster_entry(db_session: AsyncSession) -> None:
    group = await _make_full_group(db_session, "Full Group No Write Test")

    with pytest.raises(ApiError):
        await join_group(db_session, group, member=None, password=None, nickname="小美")

    result = await db_session.execute(
        select(RosterEntry).where(RosterEntry.group_id == group.id)
    )
    assert result.scalars().all() == []
