"""Unit test: wait_count batch update — selected participants reset to 0,
every other active roster entry incremented by 1, NULL treated as 0 first
(spec FR-007, research.md #9)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import apply_wait_count_updates


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Wait Count Test",
        max_members=8,
        match_mode="doubles",
        scheduling_mechanism="fair_rotation",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_roster_entry(
    session: AsyncSession, group: Group, wait_count: int | None, status: str = "active"
) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname="P", status=status, wait_count=wait_count)
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@pytest.mark.asyncio
async def test_selected_reset_others_incremented(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    selected = await _make_roster_entry(db_session, group, wait_count=5)
    not_selected_finite = await _make_roster_entry(db_session, group, wait_count=2)
    not_selected_never_played = await _make_roster_entry(db_session, group, wait_count=None)

    await apply_wait_count_updates(db_session, group.id, [selected.id])
    await db_session.commit()

    await db_session.refresh(selected)
    await db_session.refresh(not_selected_finite)
    await db_session.refresh(not_selected_never_played)

    assert selected.wait_count == 0
    assert not_selected_finite.wait_count == 3
    assert not_selected_never_played.wait_count == 1


@pytest.mark.asyncio
async def test_left_members_are_not_touched(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    left_member = await _make_roster_entry(db_session, group, wait_count=2, status="left")

    await apply_wait_count_updates(db_session, group.id, [])
    await db_session.commit()

    await db_session.refresh(left_member)
    assert left_member.wait_count == 2


@pytest.mark.asyncio
async def test_no_selected_players_increments_everyone_active(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entry = await _make_roster_entry(db_session, group, wait_count=0)

    await apply_wait_count_updates(db_session, group.id, [])
    await db_session.commit()

    await db_session.refresh(entry)
    assert entry.wait_count == 1
