"""Unit test: toggling Group.partner_source between "manual" and "auto"
never touches the `partnerships` table — 011-round-robin-scheduling
FR-010/research.md #6. Switching to "auto" and back to "manual" MUST
restore the exact prior manual pairing without the admin re-configuring
anything."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.schemas import EditGroupRequest
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import edit_group
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Partnership

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Partner Source Toggle Test",
        max_members=8,
        match_mode="doubles",
        scheduling_mechanism="fixed_partner",
        partner_source="manual",
        current_member_count=1,
        base_settings_version=0,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def test_toggle_to_auto_and_back_preserves_manual_partnerships(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    p1 = RosterEntry(group_id=group.id, nickname="P1", status="active")
    p2 = RosterEntry(group_id=group.id, nickname="P2", status="active")
    db_session.add_all([p1, p2])
    await db_session.commit()
    await db_session.refresh(p1)
    await db_session.refresh(p2)

    db_session.add(Partnership(group_id=group.id, player_a_id=p1.id, player_b_id=p2.id))
    await db_session.commit()

    async def _partnership_rows() -> list[tuple]:
        result = await db_session.execute(
            select(Partnership.player_a_id, Partnership.player_b_id).where(
                Partnership.group_id == group.id
            )
        )
        return result.all()

    original = await _partnership_rows()
    assert original == [(p1.id, p2.id)]

    updated = await edit_group(
        db_session, group, EditGroupRequest(expected_version=0, partner_source="auto")
    )
    assert updated.partner_source == "auto"
    assert await _partnership_rows() == original

    updated = await edit_group(
        db_session, updated, EditGroupRequest(expected_version=1, partner_source="manual")
    )
    assert updated.partner_source == "manual"
    assert await _partnership_rows() == original


async def test_partner_source_ignored_outside_fixed_partner(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    group.scheduling_mechanism = "fair_rotation"
    group.match_mode = "singles"
    await db_session.commit()

    updated = await edit_group(
        db_session, group, EditGroupRequest(expected_version=0, partner_source="auto")
    )

    assert updated.partner_source == "manual"  # unchanged, field silently ignored
