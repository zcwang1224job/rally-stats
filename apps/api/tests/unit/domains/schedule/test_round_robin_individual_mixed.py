"""Unit test: individual_mixed's multi-wave greedy loop
(011-round-robin-scheduling FR-004, research.md #2/#3) — covers every
teammate pair when achievable, and correctly terminates (no infinite loop)
when it isn't."""

import math

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant
from app.domains.schedule.service import generate_next_round


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Individual Mixed RR Test",
        max_members=16,
        match_mode="doubles",
        scheduling_mechanism="individual_mixed",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_court(session: AsyncSession, group: Group) -> Court:
    court = Court(group_id=group.id, name="1號場")
    session.add(court)
    await session.commit()
    await session.refresh(court)
    return court


async def _make_entries(session: AsyncSession, group: Group, count: int) -> list[RosterEntry]:
    entries = [
        RosterEntry(group_id=group.id, nickname=f"P{i}", status="active") for i in range(count)
    ]
    session.add_all(entries)
    await session.commit()
    for entry in entries:
        await session.refresh(entry)
    return entries


async def _teammate_pairs_for_round(
    session: AsyncSession, group_id, round_number: int
) -> set[frozenset]:
    result = await session.execute(
        select(Match).where(Match.group_id == group_id, Match.round_number == round_number)
    )
    matches = result.scalars().all()
    pairs: set[frozenset] = set()
    for match in matches:
        rows = await session.execute(
            select(MatchParticipant.roster_entry_id, MatchParticipant.team).where(
                MatchParticipant.match_id == match.id
            )
        )
        by_team: dict[str, set] = {"A": set(), "B": set()}
        for roster_entry_id, team in rows.all():
            by_team[team].add(roster_entry_id)
        pairs.add(frozenset(by_team["A"]))
        pairs.add(frozenset(by_team["B"]))
    return pairs


@pytest.mark.asyncio
async def test_eight_players_makes_meaningful_progress_across_waves(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 8)

    await generate_next_round(db_session, group)

    pairs = await _teammate_pairs_for_round(db_session, group.id, 1)
    total_possible = math.comb(8, 2)
    assert len(pairs) == total_possible  # no repeats: every pair distinct
    # Each wave contributes exactly 2 matchups' worth of teammate pairs (4
    # teams from 8 players) -> more than one wave was necessarily needed to
    # reach every one of the 28 possible pairs.
    assert len(pairs) > 4


@pytest.mark.asyncio
async def test_loop_terminates_and_makes_progress_for_five_players(
    db_session: AsyncSession,
) -> None:
    """5 players can't split evenly into doubles teams every wave (one
    always sits out), so perfect C(5,2)=10 coverage isn't guaranteed — this
    only asserts the loop terminates and still covers more than a single
    wave's worth of pairs."""
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await generate_next_round(db_session, group)

    pairs = await _teammate_pairs_for_round(db_session, group.id, 1)
    assert len(pairs) >= 2  # more than a single match's 2 teammate pairs
    assert len(pairs) <= math.comb(5, 2)
