"""Unit test: partnership side effects of members joining/leaving (spec
FR-022/023)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Partnership
from app.domains.schedule.service import handle_member_joined, handle_member_left


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Partnership Membership Test",
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
async def test_new_member_pairs_with_existing_unpaired(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    unpaired = await _make_roster_entry(db_session, group)
    new_member = await _make_roster_entry(db_session, group)

    await handle_member_joined(db_session, group, new_member)
    await db_session.commit()

    result = await db_session.execute(select(Partnership).where(Partnership.group_id == group.id))
    partnerships = result.scalars().all()
    assert len(partnerships) == 1
    assert {partnerships[0].player_a_id, partnerships[0].player_b_id} == {
        unpaired.id,
        new_member.id,
    }


@pytest.mark.asyncio
async def test_new_member_becomes_unpaired_when_everyone_already_paired(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    p1 = await _make_roster_entry(db_session, group)
    p2 = await _make_roster_entry(db_session, group)
    db_session.add(Partnership(group_id=group.id, player_a_id=p1.id, player_b_id=p2.id))
    await db_session.commit()
    new_member = await _make_roster_entry(db_session, group)

    await handle_member_joined(db_session, group, new_member)
    await db_session.commit()

    result = await db_session.execute(select(Partnership).where(Partnership.group_id == group.id))
    partnerships = result.scalars().all()
    assert len(partnerships) == 1  # unchanged — new member stays unpaired


@pytest.mark.asyncio
async def test_leaving_partner_dissolves_partnership(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    p1 = await _make_roster_entry(db_session, group)
    p2 = await _make_roster_entry(db_session, group)
    db_session.add(Partnership(group_id=group.id, player_a_id=p1.id, player_b_id=p2.id))
    await db_session.commit()

    await handle_member_left(db_session, group, p1, new_status="left")
    await db_session.commit()

    result = await db_session.execute(select(Partnership).where(Partnership.group_id == group.id))
    assert result.scalars().all() == []
    await db_session.refresh(p1)
    assert p1.status == "left"
