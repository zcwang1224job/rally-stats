"""Unit test: Round-complete detection — `completed` and `abandoned` both
count as terminal (spec FR-028)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import create_match_with_participants, round_is_complete


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Round Completion Test",
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


async def _make_roster_entry(session: AsyncSession, group: Group) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname="P", status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@pytest.mark.asyncio
async def test_round_incomplete_when_match_in_progress(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1 = await _make_roster_entry(db_session, group)

    p2 = await _make_roster_entry(db_session, group)
    await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    assert await round_is_complete(db_session, group.id, 1) is False


@pytest.mark.asyncio
async def test_round_incomplete_when_match_queued(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    p1 = await _make_roster_entry(db_session, group)

    p2 = await _make_roster_entry(db_session, group)
    await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    assert await round_is_complete(db_session, group.id, 1) is False


@pytest.mark.asyncio
async def test_round_complete_when_all_completed_or_abandoned(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1, p2, p3, p4 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    m1 = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    m2 = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="in_progress",
        team_a=[p3.id], team_b=[p4.id],
    )
    m1.status = "completed"
    m2.status = "abandoned"
    await db_session.commit()

    assert await round_is_complete(db_session, group.id, 1) is True


@pytest.mark.asyncio
async def test_round_complete_with_no_matches_at_all(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    assert await round_is_complete(db_session, group.id, 99) is True
