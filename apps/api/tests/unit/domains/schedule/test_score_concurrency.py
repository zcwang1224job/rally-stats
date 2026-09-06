"""Unit test: real concurrent +1 requests against the same in_progress
match — two independent DB connections, both increments MUST apply
(Edge Case: 兩位計分員幾乎同時對同一場地按下 +1), matching the atomic
`UPDATE ... WHERE` guarantee's addition semantics (research.md #5)."""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import apply_score_delta, create_match_with_participants
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Score Concurrency Test",
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


async def _attempt_plus_one(court_id: object, match_id: object) -> int:
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        court_result = await session.execute(select(Court).where(Court.id == court_id))
        court = court_result.scalar_one()
        result = await apply_score_delta(session, court, match_id, "A", 1)  # type: ignore[arg-type]
        await engine.dispose()
        return result.score_a


async def test_concurrent_plus_one_both_apply(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = Court(group_id=group.id, name="1號場")
    db_session.add(court)
    await db_session.commit()
    await db_session.refresh(court)

    p1 = RosterEntry(group_id=group.id, nickname="P1", status="active")
    p2 = RosterEntry(group_id=group.id, nickname="P2", status="active")
    db_session.add_all([p1, p2])
    await db_session.commit()
    await db_session.refresh(p1)
    await db_session.refresh(p2)

    match = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    results = await asyncio.gather(
        _attempt_plus_one(court.id, match.id),
        _attempt_plus_one(court.id, match.id),
    )

    assert sorted(results) == [1, 2]

    await db_session.refresh(match)
    assert match.score_a == 2
