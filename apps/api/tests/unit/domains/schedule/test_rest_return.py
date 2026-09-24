"""037-rest-ready-toggle US2 (FR-012, FR-019): coming back mid-round. A
player left out when the round was generated gets their share of it the
way a late joiner does, and a match they were holding up goes on court the
moment they're back — without waiting for another match to end."""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.roster.models import RosterEntry
from app.domains.schedule import rest as rest_module
from app.domains.schedule.models import Match, Partnership
from app.domains.schedule.rest import set_rest_state
from app.domains.schedule.service import (
    create_match_with_participants,
    handle_member_joined,
    plan_next_round,
    start_planned_round,
)
from tests.unit.domains.schedule._rest_helpers import (
    in_progress,
    make_courts,
    make_group,
    make_players,
    participants,
    round_matches,
    set_resting,
)


@pytest.fixture(autouse=True)
def quiet_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_publish(*_args: Any) -> None:
        return None

    monkeypatch.setattr(rest_module, "publish", fake_publish)


async def _matches_with(session: AsyncSession, group: Group, player: RosterEntry) -> list[Match]:
    return [
        match
        for match in await round_matches(session, group)
        if player.id in await participants(session, match.id)
    ]


async def _start_round_with(
    session: AsyncSession, group: Group, resting: list[RosterEntry]
) -> None:
    for entry in resting:
        await set_resting(session, entry)
    await plan_next_round(session, group)
    await start_planned_round(session, group)


@pytest.mark.asyncio
async def test_singles_round_robin_adds_their_matches(db_session: AsyncSession) -> None:
    group = await make_group(db_session, match_mode="singles")
    await make_courts(db_session, group, 1)
    a, *others = await make_players(db_session, group, 4)
    a.wait_count = 2
    await db_session.commit()
    await _start_round_with(db_session, group, [a])
    assert await _matches_with(db_session, group, a) == []

    await set_rest_state(db_session, group, a, resting=False)

    theirs = await _matches_with(db_session, group, a)
    opponents = set()
    for match in theirs:
        opponents |= await participants(db_session, match.id) - {a.id}
    assert opponents == {p.id for p in others}
    await db_session.refresh(a)
    assert a.wait_count == 2


@pytest.mark.asyncio
async def test_individual_mixed_adds_their_matches(db_session: AsyncSession) -> None:
    group = await make_group(db_session, scheduling_mechanism="individual_mixed")
    await make_courts(db_session, group, 1)
    a, *_others = await make_players(db_session, group, 5)
    await _start_round_with(db_session, group, [a])

    await set_rest_state(db_session, group, a, resting=False)

    assert await _matches_with(db_session, group, a)


@pytest.mark.asyncio
async def test_fixed_partners_come_back_as_their_team(db_session: AsyncSession) -> None:
    group = await make_group(
        db_session, scheduling_mechanism="fixed_partner", partner_source="manual"
    )
    await make_courts(db_session, group, 1)
    a, b, c, d, e, f = await make_players(db_session, group, 6)
    for x, y in ((a, b), (c, d), (e, f)):
        db_session.add(Partnership(group_id=group.id, player_a_id=x.id, player_b_id=y.id))
    await db_session.commit()
    await _start_round_with(db_session, group, [a])
    assert await _matches_with(db_session, group, b) == []

    await set_rest_state(db_session, group, a, resting=False)

    theirs = await _matches_with(db_session, group, a)
    assert theirs
    for match in theirs:
        lineup = await participants(db_session, match.id)
        assert b.id in lineup  # always together


@pytest.mark.asyncio
async def test_a_partner_still_resting_means_no_temporary_pairing(
    db_session: AsyncSession,
) -> None:
    """research.md Decision 8, first risk: A is back but B isn't — A waits
    for B instead of being paired with someone else."""
    group = await make_group(
        db_session, scheduling_mechanism="fixed_partner", partner_source="manual"
    )
    await make_courts(db_session, group, 1)
    a, b, c, d, e, f, g = await make_players(db_session, group, 7)
    for x, y in ((a, b), (c, d), (e, f)):
        db_session.add(Partnership(group_id=group.id, player_a_id=x.id, player_b_id=y.id))
    await db_session.commit()
    await _start_round_with(db_session, group, [a, b])

    await set_rest_state(db_session, group, a, resting=False)
    assert await _matches_with(db_session, group, a) == []

    await set_rest_state(db_session, group, b, resting=False)
    theirs = await _matches_with(db_session, group, a)
    assert theirs
    for match in theirs:
        assert b.id in await participants(db_session, match.id)
    assert g.id not in {p for m in theirs for p in await participants(db_session, m.id)}


@pytest.mark.asyncio
async def test_a_resting_player_is_not_a_late_joiners_opponent(db_session: AsyncSession) -> None:
    group = await make_group(db_session, match_mode="singles")
    await make_courts(db_session, group, 1)
    a, *_others = await make_players(db_session, group, 3)
    await plan_next_round(db_session, group)
    await start_planned_round(db_session, group)
    await set_resting(db_session, a)
    newcomer = RosterEntry(group_id=group.id, nickname="New", status="active")
    db_session.add(newcomer)
    await db_session.commit()
    await db_session.refresh(newcomer)

    await handle_member_joined(db_session, group, newcomer)
    await db_session.commit()

    for match in await _matches_with(db_session, group, newcomer):
        assert a.id not in await participants(db_session, match.id)


@pytest.mark.asyncio
async def test_nothing_added_before_the_round_is_planned(db_session: AsyncSession) -> None:
    group = await make_group(db_session, match_mode="singles")
    await make_courts(db_session, group, 1)
    a, *_others = await make_players(db_session, group, 3)
    await set_resting(db_session, a)

    await set_rest_state(db_session, group, a, resting=False)

    assert await round_matches(db_session, group) == []


@pytest.mark.asyncio
async def test_fair_rotation_doubles_adds_nothing(db_session: AsyncSession) -> None:
    """The next selection simply includes them."""
    group = await make_group(db_session, scheduling_mechanism="fair_rotation")
    await make_courts(db_session, group, 1)
    a, *_others = await make_players(db_session, group, 5)
    await _start_round_with(db_session, group, [a])
    before = len(await round_matches(db_session, group))

    await set_rest_state(db_session, group, a, resting=False)

    assert len(await round_matches(db_session, group)) == before


async def _match(
    session: AsyncSession,
    group: Group,
    team_a: list[RosterEntry],
    team_b: list[RosterEntry],
    *,
    status: str,
    court_id: object = None,
) -> Match:
    match = await create_match_with_participants(
        session,
        group,
        court_id=court_id,  # type: ignore[arg-type]
        round_number=group.current_round_number,
        status="in_progress" if court_id is not None else "queued",
        team_a=[p.id for p in team_a],
        team_b=[p.id for p in team_b],
    )
    if status == "completed":
        match.status = "completed"
        match.winner_team = "A"
    await session.commit()
    return match


@pytest.mark.asyncio
async def test_a_held_match_goes_on_the_idle_court_at_once(db_session: AsyncSession) -> None:
    """FR-019: no need to wait for another match to end. The round is under
    way (a match has been played), the court is idle, and the only queued
    match is held for A."""
    group = await make_group(db_session, match_mode="singles")
    [court] = await make_courts(db_session, group, 1)
    a, b, c = await make_players(db_session, group, 3)
    await _match(db_session, group, [b], [c], status="completed", court_id=court.id)
    held = await _match(db_session, group, [a], [b], status="queued")
    await set_resting(db_session, a)

    await set_rest_state(db_session, group, a, resting=False)

    [started] = await in_progress(db_session, group)
    assert started.id == held.id
    assert started.court_id == court.id


@pytest.mark.asyncio
async def test_continuous_rotation_seats_the_fourth_player_back(db_session: AsyncSession) -> None:
    """US3 scenario 5: three idle ready players and an empty court; the
    fourth coming back fills it straight away."""
    group = await make_group(db_session, continuous_rotation=True)
    busy_court, idle_court = await make_courts(db_session, group, 2)
    returning, *on_court, w1, w2, w3 = await make_players(db_session, group, 8)
    await _match(db_session, group, on_court[:2], on_court[2:], status="in_progress",
                 court_id=busy_court.id)
    await set_resting(db_session, returning)

    await set_rest_state(db_session, group, returning, resting=False)

    seated = [m for m in await in_progress(db_session, group) if m.court_id == idle_court.id]
    assert len(seated) == 1
    assert await participants(db_session, seated[0].id) == {returning.id, w1.id, w2.id, w3.id}


@pytest.mark.asyncio
async def test_a_planned_round_is_not_started_for_the_admin(db_session: AsyncSession) -> None:
    group = await make_group(db_session, match_mode="singles")
    await make_courts(db_session, group, 1)
    a, *_others = await make_players(db_session, group, 3)
    await plan_next_round(db_session, group)
    await set_resting(db_session, a)

    await set_rest_state(db_session, group, a, resting=False)

    assert await in_progress(db_session, group) == []
    result = await db_session.execute(select(Match.court_id).where(Match.group_id == group.id))
    assert all(court_id is None for court_id in result.scalars())
