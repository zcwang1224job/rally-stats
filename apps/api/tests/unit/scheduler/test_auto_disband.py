"""Unit test: last_activity_at > 1hr sweep logic (spec FR-036, research.md #4)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.scheduler.auto_disband import sweep_idle_groups
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.asyncio


async def _sweep(db_session: AsyncSession) -> None:
    # Build a session factory bound to *this* test's running event loop
    # (asyncpg connections are loop-bound; see auto_disband.py docstring),
    # and reuse db_session's live transaction connection so the sweep sees
    # data this test just wrote before its own fixture-level commit.
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    await sweep_idle_groups(session_factory=factory)
    await engine.dispose()


async def _make_group(session: AsyncSession, last_activity_at: datetime) -> Group:
    group = Group(
        name="Idle Test",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
        last_activity_at=last_activity_at,
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def test_idle_group_over_1hr_is_disbanded(db_session: AsyncSession) -> None:
    idle_group = await _make_group(db_session, datetime.now(UTC) - timedelta(minutes=61))
    await _sweep(db_session)
    await db_session.refresh(idle_group)
    assert idle_group.status == "disbanded"


async def test_active_group_under_1hr_is_not_disbanded(db_session: AsyncSession) -> None:
    active_group = await _make_group(db_session, datetime.now(UTC) - timedelta(minutes=10))
    await _sweep(db_session)
    await db_session.refresh(active_group)
    assert active_group.status == "active"


async def test_sweep_only_touches_active_groups_past_cutoff(db_session: AsyncSession) -> None:
    idle = await _make_group(db_session, datetime.now(UTC) - timedelta(minutes=90))
    fresh = await _make_group(db_session, datetime.now(UTC) - timedelta(minutes=1))
    idle_id, fresh_id = idle.id, fresh.id
    await _sweep(db_session)

    # The sweep wrote through a separate session/connection, so db_session's
    # identity map still holds the pre-sweep cached objects for idle/fresh —
    # expire them to force a fresh read of the committed rows.
    db_session.expire_all()
    result = await db_session.execute(select(Group).where(Group.id.in_([idle_id, fresh_id])))
    statuses = {g.id: g.status for g in result.scalars().all()}
    assert statuses[idle_id] == "disbanded"
    assert statuses[fresh_id] == "active"
