"""Unit test: manually reassigning two partners breaks their old pairs; both
old partners become unpaired (spec FR-021)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Partnership
from app.domains.schedule.service import manual_partnership_reassign


async def _make_group(session: AsyncSession, name: str = "Partnership Reassign Test") -> Group:
    group = Group(
        name=name,
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


async def _make_partnership(
    session: AsyncSession, group: Group, a: RosterEntry, b: RosterEntry
) -> Partnership:
    partnership = Partnership(group_id=group.id, player_a_id=a.id, player_b_id=b.id)
    session.add(partnership)
    await session.commit()
    return partnership


@pytest.mark.asyncio
async def test_reassign_breaks_both_old_partnerships(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    p1, p2, p3, p4 = [await _make_roster_entry(db_session, group) for _ in range(4)]
    await _make_partnership(db_session, group, p1, p2)
    await _make_partnership(db_session, group, p3, p4)

    await manual_partnership_reassign(db_session, group, p1.id, p3.id)
    await db_session.commit()

    result = await db_session.execute(select(Partnership).where(Partnership.group_id == group.id))
    partnerships = result.scalars().all()
    assert len(partnerships) == 1
    assert {partnerships[0].player_a_id, partnerships[0].player_b_id} == {p1.id, p3.id}
    # p2 and p4 are now both unpaired (no Partnership row references them).
    remaining_ids = {partnerships[0].player_a_id, partnerships[0].player_b_id}
    assert p2.id not in remaining_ids
    assert p4.id not in remaining_ids


@pytest.mark.asyncio
async def test_rejects_roster_entry_from_a_different_group(db_session: AsyncSession) -> None:
    """Security review (T078): a roster_entry_id belonging to another group
    MUST NOT be pairable into this group's Partnership table, even if it's
    active there — otherwise an admin could cross-reference another group's
    roster into their own partnerships."""
    group = await _make_group(db_session)
    other_group = await _make_group(db_session, name="Other Group")
    p1 = await _make_roster_entry(db_session, group)
    foreign = await _make_roster_entry(db_session, other_group)

    with pytest.raises(ApiError) as exc_info:
        await manual_partnership_reassign(db_session, group, p1.id, foreign.id)
    assert exc_info.value.error_code == "VALIDATION_ERROR"
