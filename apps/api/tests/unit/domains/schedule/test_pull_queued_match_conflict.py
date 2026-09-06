"""Unit test: pull_queued_match_for_court() skips any queued match whose
participant is already playing an in_progress match on another court —
011-round-robin-scheduling research.md #4 / FR-005. A full round-robin
schedule puts the same player in several queued matches at once, so this
guard is what prevents a player from appearing on two courts at once."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.service import create_match_with_participants, pull_queued_match_for_court


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Pull Conflict Test",
        max_members=8,
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
async def test_skips_match_with_a_busy_participant(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    busy_court = await _make_court(db_session, group, "忙碌場")
    target_court = await _make_court(db_session, group, "目標場")
    p1 = await _make_entry(db_session, group, "P1")
    p2 = await _make_entry(db_session, group, "P2")
    p3 = await _make_entry(db_session, group, "P3")
    p4 = await _make_entry(db_session, group, "P4")
    p5 = await _make_entry(db_session, group, "P5")

    # P1 is already mid-match on another court.
    await create_match_with_participants(
        db_session, group, court_id=busy_court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p5.id],
    )

    # Queued match #1 (created first) involves the busy P1 -> must be skipped.
    blocked = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p1.id], team_b=[p2.id],
    )
    # Queued match #2 (created second) has no busy participants -> eligible.
    eligible = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p3.id], team_b=[p4.id],
    )
    await db_session.commit()

    pulled = await pull_queued_match_for_court(db_session, group.id, 1, target_court.id)

    assert pulled is not None
    assert pulled.id == eligible.id
    assert pulled.id != blocked.id
    assert pulled.status == "in_progress"
    assert pulled.court_id == target_court.id


@pytest.mark.asyncio
async def test_returns_none_when_every_candidate_is_busy(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    busy_court = await _make_court(db_session, group, "忙碌場")
    target_court = await _make_court(db_session, group, "目標場")
    p1 = await _make_entry(db_session, group, "P1")
    p2 = await _make_entry(db_session, group, "P2")
    p3 = await _make_entry(db_session, group, "P3")

    await create_match_with_participants(
        db_session, group, court_id=busy_court.id, round_number=1, status="in_progress",
        team_a=[p1.id], team_b=[p2.id],
    )
    # Every remaining queued match involves at least one of P1/P2.
    await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[p1.id], team_b=[p3.id],
    )
    await db_session.commit()

    pulled = await pull_queued_match_for_court(db_session, group.id, 1, target_court.id)

    assert pulled is None
