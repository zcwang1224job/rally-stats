"""Unit test: `handle_member_left()` writes `left_at` on transition to
left/kicked, and `left_at` stays NULL while a member is still `active`
(005-member-view research.md #3)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import handle_member_left


async def _make_group(session: AsyncSession, mechanism: str = "fair_rotation") -> Group:
    group = Group(
        name="Left At Test",
        max_members=8,
        match_mode="doubles",
        scheduling_mechanism=mechanism,
        current_round_number=1,
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
async def test_left_at_null_while_active(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entry = await _make_roster_entry(db_session, group)

    assert entry.left_at is None


@pytest.mark.asyncio
async def test_handle_member_left_writes_left_at_on_left(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entry = await _make_roster_entry(db_session, group)

    await handle_member_left(db_session, group, entry, new_status="left")
    await db_session.commit()
    await db_session.refresh(entry)

    assert entry.status == "left"
    assert entry.left_at is not None


@pytest.mark.asyncio
async def test_handle_member_left_writes_left_at_on_kicked(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    entry = await _make_roster_entry(db_session, group)

    await handle_member_left(db_session, group, entry, new_status="kicked")
    await db_session.commit()
    await db_session.refresh(entry)

    assert entry.status == "kicked"
    assert entry.left_at is not None
