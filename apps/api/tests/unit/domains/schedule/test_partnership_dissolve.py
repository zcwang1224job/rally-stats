"""Unit test: explicitly dissolving a partnership — the gap `pick two people
to swap` (manual_partnership_reassign) can't cover on its own: when the only
active members left are the two people in one existing partnership, there is
no third person to swap with, so that pair could never be turned into two
unpaired singles before this."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Partnership
from app.domains.schedule.service import dissolve_partnership


async def _make_group(
    session: AsyncSession,
    name: str = "Partnership Dissolve Test",
    scheduling_mechanism: str = "fixed_partner",
) -> Group:
    group = Group(
        name=name,
        max_members=8,
        match_mode="doubles",
        scheduling_mechanism=scheduling_mechanism,
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


async def _make_partnership(
    session: AsyncSession, group: Group, a: RosterEntry, b: RosterEntry
) -> Partnership:
    partnership = Partnership(group_id=group.id, player_a_id=a.id, player_b_id=b.id)
    session.add(partnership)
    await session.commit()
    return partnership


@pytest.mark.asyncio
async def test_dissolve_removes_the_only_remaining_pair(db_session: AsyncSession) -> None:
    """The exact edge case reported: only two active members left, already
    partnered with each other, no third person to swap with."""
    group = await _make_group(db_session)
    p1, p2 = [await _make_roster_entry(db_session, group) for _ in range(2)]
    await _make_partnership(db_session, group, p1, p2)

    await dissolve_partnership(db_session, group, p1.id)
    await db_session.commit()

    result = await db_session.execute(select(Partnership).where(Partnership.group_id == group.id))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_dissolve_via_either_side_of_the_pair(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    p1, p2, p3, p4 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    await _make_partnership(db_session, group, p1, p2)
    await _make_partnership(db_session, group, p3, p4)

    await dissolve_partnership(db_session, group, p2.id)
    await db_session.commit()

    result = await db_session.execute(select(Partnership).where(Partnership.group_id == group.id))
    partnerships = result.scalars().all()
    assert len(partnerships) == 1
    assert {partnerships[0].player_a_id, partnerships[0].player_b_id} == {p3.id, p4.id}


@pytest.mark.asyncio
async def test_dissolve_rejects_member_with_no_partnership(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    p1 = await _make_roster_entry(db_session, group)

    with pytest.raises(ApiError) as exc_info:
        await dissolve_partnership(db_session, group, p1.id)
    assert exc_info.value.error_code == "PARTNERSHIP_NOT_FOUND"


@pytest.mark.asyncio
async def test_dissolve_rejects_non_fixed_partner_group(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, scheduling_mechanism="auto")
    p1 = await _make_roster_entry(db_session, group)

    with pytest.raises(ApiError) as exc_info:
        await dissolve_partnership(db_session, group, p1.id)
    assert exc_info.value.error_code == "SCHEDULING_MECHANISM_MISMATCH"
