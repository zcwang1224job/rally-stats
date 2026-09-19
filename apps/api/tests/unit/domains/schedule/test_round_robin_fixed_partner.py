"""Unit test: fixed_partner's team round-robin produces every team-vs-team
matchup exactly once (011-round-robin-scheduling FR-003, research.md #1's
circle method applied to teams), and requires an even headcount."""

import math

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant, Partnership
from app.domains.schedule.service import generate_next_round


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Fixed Partner Round Robin Test",
        "max_members": 16,
        "match_mode": "doubles",
        "scheduling_mechanism": "fixed_partner",
        "partner_source": "manual",
        "current_member_count": 1,
        "status": "active",
        "admin_pin_hash": hash_admin_pin("111111"),
    }
    defaults.update(overrides)
    group = Group(**defaults)  # type: ignore[arg-type]
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


@pytest.mark.asyncio
async def test_fixed_partner_round_robin_covers_every_team_matchup_once(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    entries = await _make_entries(db_session, group, 8)  # 4 teams

    for i in range(0, 8, 2):
        db_session.add(
            Partnership(group_id=group.id, player_a_id=entries[i].id, player_b_id=entries[i + 1].id)
        )
    await db_session.commit()

    await generate_next_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.round_number == 1)
    )
    matches = result.scalars().all()
    assert len(matches) == math.comb(4, 2)  # 4 teams -> 6 matchups

    seen_team_pairs: set[frozenset] = set()
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
        team_pair = frozenset((frozenset(by_team["A"]), frozenset(by_team["B"])))
        assert team_pair not in seen_team_pairs
        seen_team_pairs.add(team_pair)

    assert len(seen_team_pairs) == math.comb(4, 2)


@pytest.mark.asyncio
async def test_odd_headcount_gives_the_unpartnered_member_a_bye(db_session: AsyncSession) -> None:
    """An odd headcount used to fail with FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT;
    now the member left without a partner sits the round out and the three
    formal teams still play their round-robin."""
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    entries = await _make_entries(db_session, group, 7)

    for i in range(0, 6, 2):
        db_session.add(
            Partnership(group_id=group.id, player_a_id=entries[i].id, player_b_id=entries[i + 1].id)
        )
    await db_session.commit()

    await generate_next_round(db_session, group)

    matches = (
        await db_session.execute(select(Match).where(Match.group_id == group.id))
    ).scalars().all()
    assert len(matches) == math.comb(3, 2)

    players = set(
        (
            await db_session.execute(
                select(MatchParticipant.roster_entry_id).where(
                    MatchParticipant.match_id.in_([m.id for m in matches])
                )
            )
        ).scalars()
    )
    assert players == {entry.id for entry in entries[:6]}


@pytest.mark.asyncio
async def test_bye_rotates_to_whoever_has_played_most(db_session: AsyncSession) -> None:
    """auto partner source, 5 members: round 2's bye must go to someone who
    played in round 1, so the same person doesn't sit out twice in a row."""
    group = await _make_group(db_session, partner_source="auto")
    await _make_court(db_session, group)
    entries = await _make_entries(db_session, group, 5)

    async def round_players(round_number: int) -> set[object]:
        result = await db_session.execute(
            select(MatchParticipant.roster_entry_id)
            .join(Match, Match.id == MatchParticipant.match_id)
            .where(Match.group_id == group.id, Match.round_number == round_number)
        )
        return set(result.scalars())

    group = await generate_next_round(db_session, group)
    first_bye = {entry.id for entry in entries} - await round_players(1)
    assert len(first_bye) == 1

    group = await generate_next_round(db_session, group)
    second_bye = {entry.id for entry in entries} - await round_players(2)
    assert len(second_bye) == 1
    assert second_bye != first_bye
