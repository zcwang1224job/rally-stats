"""Unit test: PIN brute-force lockout (10 failed attempts -> 15min lockout,
research.md #1)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import reauth_admin

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Lockout Test",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("654321"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def test_correct_pin_succeeds(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    token, returned_group = await reauth_admin(db_session, group.group_number, "654321")
    assert token
    assert returned_group.id == group.id


async def test_wrong_pin_increments_failed_attempts(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    with pytest.raises(ApiError) as exc_info:
        await reauth_admin(db_session, group.group_number, "000000")
    assert exc_info.value.error_code == "GROUP_ADMIN_PIN_INCORRECT"
    await db_session.refresh(group)
    assert group.admin_failed_attempts == 1


async def test_tenth_failure_locks_account(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    for _ in range(10):
        with pytest.raises(ApiError):
            await reauth_admin(db_session, group.group_number, "000000")

    with pytest.raises(ApiError) as exc_info:
        await reauth_admin(db_session, group.group_number, "654321")  # even correct PIN blocked
    assert exc_info.value.error_code == "GROUP_ADMIN_LOCKED"
