"""Unit test: Guest join nickname format validation (FR-004) and duplicate
nickname tolerance (FR-020)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import join_group

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Join Validation Test",
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


async def test_guest_join_rejects_blank_nickname(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    with pytest.raises(ApiError) as exc_info:
        await join_group(db_session, group, member=None, password=None, nickname="   ")
    assert exc_info.value.error_code == "NICKNAME_REQUIRED_FOR_GUEST"


async def test_guest_join_rejects_missing_nickname(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    with pytest.raises(ApiError) as exc_info:
        await join_group(db_session, group, member=None, password=None, nickname=None)
    assert exc_info.value.error_code == "NICKNAME_REQUIRED_FOR_GUEST"


async def test_guest_join_rejects_nickname_too_long(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    with pytest.raises(ApiError) as exc_info:
        await join_group(
            db_session, group, member=None, password=None, nickname="a" * 21
        )
    assert exc_info.value.error_code == "NICKNAME_REQUIRED_FOR_GUEST"


async def test_duplicate_nickname_allowed(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    first, _ = await join_group(db_session, group, member=None, password=None, nickname="小明")
    second, _ = await join_group(db_session, group, member=None, password=None, nickname="小明")
    assert first.nickname == second.nickname == "小明"
    assert first.id != second.id
