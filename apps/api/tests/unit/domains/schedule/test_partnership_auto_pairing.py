"""Unit test: switching into fixed_partner auto-pairs by join order, odd
member count leaves the latest joiner unpaired (spec FR-020)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Partnership
from app.domains.schedule.service import auto_pair_on_enter_fixed_partner


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Partnership Auto Pairing Test",
        max_members=8,
        match_mode="doubles",
        scheduling_mechanism="fixed_partner",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_roster_entry(session: AsyncSession, group: Group) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname="P", status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@pytest.mark.asyncio
async def test_even_count_pairs_everyone(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entries = [await _make_roster_entry(db_session, group) for _ in range(4)]

    await auto_pair_on_enter_fixed_partner(db_session, group)
    await db_session.commit()

    result = await db_session.execute(select(Partnership).where(Partnership.group_id == group.id))
    partnerships = result.scalars().all()
    assert len(partnerships) == 2
    paired_ids = {p.player_a_id for p in partnerships} | {p.player_b_id for p in partnerships}
    assert paired_ids == {e.id for e in entries}


@pytest.mark.asyncio
async def test_odd_count_leaves_last_joiner_unpaired(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entries = [await _make_roster_entry(db_session, group) for _ in range(3)]

    await auto_pair_on_enter_fixed_partner(db_session, group)
    await db_session.commit()

    result = await db_session.execute(select(Partnership).where(Partnership.group_id == group.id))
    partnerships = result.scalars().all()
    assert len(partnerships) == 1
    paired_ids = {partnerships[0].player_a_id, partnerships[0].player_b_id}
    assert entries[2].id not in paired_ids  # latest joiner unpaired
    assert entries[0].id in paired_ids
    assert entries[1].id in paired_ids
