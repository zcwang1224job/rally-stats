"""Unit test: individual_mixed dispatches to its own multi-wave round-robin
generator (011-round-robin-scheduling FR-004) — no longer the single-wave
fair_rotation doubles pipeline reuse from 003 (spec FR-025 predates this
feature; see research.md #2/#3 for why individual_mixed now needs its own
dispatch)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant, Partnership
from app.domains.schedule.service import generate_next_round


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Individual Mixed Test",
        max_members=8,
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


async def _make_roster_entry(session: AsyncSession, group: Group) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname="P", status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@pytest.mark.asyncio
async def test_individual_mixed_covers_all_teammate_pairs_for_four_players(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    for _ in range(4):
        await _make_roster_entry(db_session, group)

    updated = await generate_next_round(db_session, group)
    assert updated.current_round_number == 1

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.round_number == 1)
    )
    matches = result.scalars().all()
    assert len(matches) >= 1

    seen_teammate_pairs: set[frozenset] = set()
    for match in matches:
        rows = await db_session.execute(
            select(MatchParticipant.roster_entry_id, MatchParticipant.team).where(
                MatchParticipant.match_id == match.id
            )
        )
        by_team: dict[str, set] = {"A": set(), "B": set()}
        for roster_entry_id, team in rows.all():
            by_team[team].add(roster_entry_id)
        assert len(by_team["A"]) == 2
        assert len(by_team["B"]) == 2
        for team in (frozenset(by_team["A"]), frozenset(by_team["B"])):
            assert team not in seen_teammate_pairs  # no repeat teammate pair within this round
            seen_teammate_pairs.add(team)

    # 4 players -> C(4,2) = 6 possible teammate pairs; the classic 3-wave
    # doubles round-robin construction is exactly achievable here.
    assert len(seen_teammate_pairs) == 6


@pytest.mark.asyncio
async def test_individual_mixed_never_creates_partnerships(db_session: AsyncSession) -> None:
    """No Partnership rows are created for individual_mixed — teammates are
    decided fresh every round via PairHistory, never persisted as a
    structural relationship (unlike fixed_partner)."""
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    for _ in range(4):
        await _make_roster_entry(db_session, group)

    await generate_next_round(db_session, group)

    result = await db_session.execute(select(Partnership).where(Partnership.group_id == group.id))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_individual_mixed_too_few_players_generates_nothing(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    for _ in range(2):  # below the 4-player minimum for one doubles match
        await _make_roster_entry(db_session, group)

    await generate_next_round(db_session, group)

    result = await db_session.execute(select(Match).where(Match.group_id == group.id))
    assert result.scalars().all() == []
