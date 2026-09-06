"""Unit test: concurrent Next Round attempts are serialized by a pessimistic
lock — a second request arriving while the first is mid-transaction gets
ROUND_GENERATION_IN_PROGRESS rather than blocking or double-generating
(spec Assumptions, research.md #8)."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.errors import ApiError
from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.schedule.service import generate_next_round
from tests.conftest import TEST_DATABASE_URL


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Next Round Locking Test",
        max_members=4,
        match_mode="singles",
        scheduling_mechanism="fair_rotation",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_court(session: AsyncSession, group: Group) -> Court:
    court = Court(group_id=group.id, name="1號場")
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


@pytest.mark.asyncio
async def test_concurrent_next_round_returns_conflict(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)

    # A separate connection holds the row lock in an open transaction,
    # simulating a first request's generate_next_round() still in flight.
    engine2 = create_async_engine(TEST_DATABASE_URL)
    async with engine2.connect() as conn2:
        await conn2.execute(text("BEGIN"))
        await conn2.execute(
            text("SELECT id FROM groups WHERE id = :id FOR UPDATE"), {"id": str(group.id)}
        )

        with pytest.raises(ApiError) as exc_info:
            await generate_next_round(db_session, group)
        assert exc_info.value.error_code == "ROUND_GENERATION_IN_PROGRESS"

        await conn2.execute(text("ROLLBACK"))
    await engine2.dispose()
