"""Unit test: editing members.nickname MUST NOT retroactively update any
existing roster_entries.nickname row (research.md #10, FR-024) — the two
are independent columns, snapshot semantics are automatic given the current
schema, not something this feature implements."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.member.service import register, set_nickname
from app.domains.roster.models import RosterEntry

pytestmark = pytest.mark.asyncio


async def test_nickname_change_does_not_affect_existing_roster_entry(
    db_session: AsyncSession,
) -> None:
    member = await register(db_session, "snapshot@example.com", "abc12345")

    group = Group(
        name="Snapshot Test",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    roster_entry = RosterEntry(
        group_id=group.id, member_id=member.id, nickname="舊暱稱", status="active"
    )
    db_session.add(roster_entry)
    await db_session.commit()

    await set_nickname(db_session, member, "新暱稱")

    await db_session.refresh(roster_entry)
    assert roster_entry.nickname == "舊暱稱"


async def test_set_nickname_updates_member(db_session: AsyncSession) -> None:
    member = await register(db_session, "nickname2@example.com", "abc12345")
    updated = await set_nickname(db_session, member, "新暱稱")
    assert updated.nickname == "新暱稱"
