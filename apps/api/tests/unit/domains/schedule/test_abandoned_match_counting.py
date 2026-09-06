"""Unit test: an abandoned match still counts toward wait_count zeroing and
pair_history (spec FR-009) — because both are recorded at selection/creation
time, never reversed on a later abandon, not because of any special-cased
"abandon-aware" logic."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import (
    apply_wait_count_updates,
    create_match_with_participants,
    get_pair_count,
)


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Abandoned Match Counting Test",
        max_members=4,
        match_mode="singles",
        scheduling_mechanism="fair_rotation",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_roster_entry(session: AsyncSession, group: Group) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname="P", status="active", wait_count=None)
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@pytest.mark.asyncio
async def test_abandoned_match_wait_count_and_pair_history_unaffected(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    player_a = await _make_roster_entry(db_session, group)
    player_b = await _make_roster_entry(db_session, group)

    # Round generation: both selected, wait_count zeroed at selection time.
    await apply_wait_count_updates(db_session, group.id, [player_a.id, player_b.id])
    await db_session.commit()

    match = await create_match_with_participants(
        db_session,
        group,
        court_id=None,
        round_number=1,
        status="in_progress",
        team_a=[player_a.id],
        team_b=[player_b.id],
    )
    await db_session.commit()

    # Simulate the match being abandoned (e.g. via Next Round or court deletion).
    match.status = "abandoned"
    await db_session.commit()

    await db_session.refresh(player_a)
    await db_session.refresh(player_b)
    assert player_a.wait_count == 0
    assert player_b.wait_count == 0

    pair_count = await get_pair_count(db_session, group.id, player_a.id, player_b.id)
    assert pair_count == 1
