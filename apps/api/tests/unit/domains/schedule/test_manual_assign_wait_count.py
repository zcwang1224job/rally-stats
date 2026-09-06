"""Unit test: manual assignment never queues (FR-015) and zeroes the
assigned participants' wait_count immediately (FR-014)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import manual_assign


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Manual Wait Count Test",
        max_members=4,
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


async def _make_court(session: AsyncSession, group: Group) -> Court:
    court = Court(group_id=group.id, name="1號場")
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


async def _make_roster_entry(session: AsyncSession, group: Group) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname="P", status="active", wait_count=None)
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@pytest.mark.asyncio
async def test_manual_assign_creates_in_progress_directly(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1 = await _make_roster_entry(db_session, group)
    p2 = await _make_roster_entry(db_session, group)

    match = await manual_assign(db_session, group, court, team_a=[p1.id], team_b=[p2.id])
    await db_session.commit()

    assert match.status == "in_progress"
    assert match.court_id == court.id


@pytest.mark.asyncio
async def test_manual_assign_zeroes_participant_wait_count(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    p1 = await _make_roster_entry(db_session, group)
    p2 = await _make_roster_entry(db_session, group)

    await manual_assign(db_session, group, court, team_a=[p1.id], team_b=[p2.id])
    await db_session.commit()

    await db_session.refresh(p1)
    await db_session.refresh(p2)
    assert p1.wait_count == 0
    assert p2.wait_count == 0
