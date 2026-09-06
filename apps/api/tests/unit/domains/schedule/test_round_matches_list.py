"""Unit test: build_round_matches_list() — the admin-facing "本輪賽程清單"
read model, showing every match in the current round regardless of status
(not just each court's current match, per build_schedule_snapshot())."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import build_round_matches_list, create_match_with_participants


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Round Matches List Test",
        max_members=8,
        match_mode="singles",
        scheduling_mechanism="fair_rotation",
        current_member_count=1,
        current_round_number=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_court(session: AsyncSession, group: Group, name: str) -> Court:
    court = Court(group_id=group.id, name=name)
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


async def _make_entry(session: AsyncSession, group: Group, nickname: str) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname=nickname, status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@pytest.mark.asyncio
async def test_lists_every_match_regardless_of_status(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group, "1號場")
    p1 = await _make_entry(db_session, group, "P1")
    p2 = await _make_entry(db_session, group, "P2")
    p3 = await _make_entry(db_session, group, "P3")
    p4 = await _make_entry(db_session, group, "P4")

    in_progress = await create_match_with_participants(
        db_session, group, court_id=court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    queued = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p3.id], team_b=[p4.id],
    )
    await db_session.commit()

    response = await build_round_matches_list(db_session, group)

    assert response.round_number == 1
    assert len(response.matches) == 2
    by_id = {m.match_id: m for m in response.matches}

    assert by_id[str(in_progress.id)].status == "in_progress"
    assert by_id[str(in_progress.id)].court_name == "1號場"
    assert {p.nickname for p in by_id[str(in_progress.id)].participants} == {"P1", "P2"}

    assert by_id[str(queued.id)].status == "queued"
    assert by_id[str(queued.id)].court_name is None
    assert {p.nickname for p in by_id[str(queued.id)].participants} == {"P3", "P4"}


@pytest.mark.asyncio
async def test_only_includes_current_round(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    group.current_round_number = 2
    await db_session.commit()
    p1 = await _make_entry(db_session, group, "P1")
    p2 = await _make_entry(db_session, group, "P2")

    await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="abandoned",
        team_a=[p1.id], team_b=[p2.id],
    )
    current = await create_match_with_participants(
        db_session, group, court_id=None, round_number=2, status="queued",
        team_a=[p1.id], team_b=[p2.id],
    )
    await db_session.commit()

    response = await build_round_matches_list(db_session, group)

    assert response.round_number == 2
    assert [m.match_id for m in response.matches] == [str(current.id)]


@pytest.mark.asyncio
async def test_empty_when_no_round_generated_yet(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)

    response = await build_round_matches_list(db_session, group)

    assert response.round_number == 1
    assert response.matches == []
