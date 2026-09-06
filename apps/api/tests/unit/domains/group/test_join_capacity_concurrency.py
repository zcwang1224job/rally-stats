"""Unit test: real concurrent join requests against a group with exactly one
remaining slot — the atomic `UPDATE ... WHERE current_member_count <
max_members` guarantee (research.md #5) must let exactly one succeed, never
both, without any application-level locking (US3, SC-002)."""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import join_group
from tests.conftest import TEST_DATABASE_URL


async def _make_group_with_one_slot_left(session: AsyncSession) -> Group:
    group = Group(
        name="Concurrency Test",
        max_members=2,
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


async def _attempt_join(group_id: object, nickname: str) -> str:
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(select(Group).where(Group.id == group_id))
        group = result.scalar_one()
        try:
            await join_group(session, group, member=None, password=None, nickname=nickname)
            return "success"
        except ApiError as exc:
            return exc.error_code
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_only_one_concurrent_join_succeeds(db_session: AsyncSession) -> None:
    group = await _make_group_with_one_slot_left(db_session)

    results = await asyncio.gather(
        _attempt_join(group.id, "甲"),
        _attempt_join(group.id, "乙"),
    )

    assert sorted(results) == ["GROUP_FULL", "success"]

    await db_session.refresh(group)
    assert group.current_member_count == group.max_members == 2
