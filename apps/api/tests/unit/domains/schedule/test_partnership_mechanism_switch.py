"""Unit test: switching away from fixed_partner clears all Partnerships;
switching back is a fresh auto-pairing. PairHistory is untouched by either
direction (spec FR-024)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Partnership
from app.domains.schedule.service import (
    auto_pair_on_enter_fixed_partner,
    clear_partnerships_on_exit,
    get_pair_count,
)


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Mechanism Switch Test",
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
async def test_switch_out_clears_partnerships(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    p1, p2 = (
        await _make_roster_entry(db_session, group),
        await _make_roster_entry(db_session, group),
    )
    db_session.add(Partnership(group_id=group.id, player_a_id=p1.id, player_b_id=p2.id))
    db_session.add(_pair_history_row(group, p1, p2))
    await db_session.commit()

    await clear_partnerships_on_exit(db_session, group)
    await db_session.commit()

    result = await db_session.execute(select(Partnership).where(Partnership.group_id == group.id))
    assert result.scalars().all() == []

    # PairHistory MUST survive the switch (FR-024).
    count = await get_pair_count(db_session, group.id, p1.id, p2.id)
    assert count == 1


@pytest.mark.asyncio
async def test_switch_back_is_a_fresh_pairing(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    p1, p2 = (
        await _make_roster_entry(db_session, group),
        await _make_roster_entry(db_session, group),
    )
    await auto_pair_on_enter_fixed_partner(db_session, group)
    await db_session.commit()
    await clear_partnerships_on_exit(db_session, group)
    await db_session.commit()

    await auto_pair_on_enter_fixed_partner(db_session, group)
    await db_session.commit()

    result = await db_session.execute(select(Partnership).where(Partnership.group_id == group.id))
    partnerships = result.scalars().all()
    assert len(partnerships) == 1
    assert {partnerships[0].player_a_id, partnerships[0].player_b_id} == {p1.id, p2.id}


def _pair_history_row(group: Group, a: RosterEntry, b: RosterEntry) -> object:
    from app.domains.schedule.models import PairHistory

    lo, hi = sorted((a.id, b.id))
    return PairHistory(group_id=group.id, player_lo_id=lo, player_hi_id=hi, pair_count=1)
