"""037-rest-ready-toggle US3 (FR-023～FR-026, FR-028): resting must not be
a way to jump the queue. While resting, a player's wait count is frozen and
the matches that go on court don't count as matches they sat out; coming
back, they're credited with played matches so "fewest played" doesn't keep
them first in line (research.md Decisions 3 and 4)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.service import build_group_standings
from app.domains.roster.models import RosterEntry, RosterRestPeriod
from app.domains.schedule.rest import set_rest_state
from app.domains.schedule.service import (
    _get_player_histories,
    _seat_waiting_players_on_court,
    apply_wait_count_updates,
)
from tests.unit.domains.schedule._rest_helpers import (
    make_courts,
    make_group,
    make_players,
    participants,
    played_match,
    set_resting,
)

T0 = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)


def at(minute: int) -> datetime:
    return T0 + timedelta(minutes=minute)


async def _play(
    session: AsyncSession, group: object, player: RosterEntry, times: int, start: int
) -> int:
    """`player` plays `times` one-player matches from minute `start`, one
    per minute. Returns the next free minute."""
    for i in range(times):
        began = at(start + i)
        await played_match(session, group, [player], [], began, began + timedelta(seconds=50))
    return start + times


@pytest.mark.asyncio
async def test_a_resting_player_waits_no_longer(db_session: AsyncSession) -> None:
    group = await make_group(db_session)
    ready, resting, never_played = await make_players(db_session, group, 3)
    resting.wait_count = 2
    await db_session.commit()
    await set_resting(db_session, resting)
    await set_resting(db_session, never_played)

    await apply_wait_count_updates(db_session, group.id, [])
    await db_session.commit()

    for entry in (ready, resting, never_played):
        await db_session.refresh(entry)
    assert ready.wait_count == 1
    assert resting.wait_count == 2
    assert never_played.wait_count is None


@pytest.mark.asyncio
async def test_continuous_rotation_neither_picks_nor_counts_a_resting_player(
    db_session: AsyncSession,
) -> None:
    group = await make_group(db_session, continuous_rotation=True)
    [court] = await make_courts(db_session, group, 1)
    players = await make_players(db_session, group, 6)
    for entry in players:
        entry.wait_count = 0
    players[0].wait_count = 5  # would be picked first if ready
    await db_session.commit()
    await set_resting(db_session, players[0])

    match = await _seat_waiting_players_on_court(
        db_session, group, court.id, group.current_round_number
    )
    await db_session.commit()

    assert match is not None
    await db_session.refresh(players[0])
    assert players[0].id not in await participants(db_session, match.id)
    assert players[0].wait_count == 5  # not passed over: not waiting


@pytest.mark.asyncio
async def test_matches_during_a_rest_are_not_matches_sat_out(db_session: AsyncSession) -> None:
    group = await make_group(db_session)
    a, b = await make_players(db_session, group, 2)
    await played_match(db_session, group, [a], [], at(0), at(10))
    for minute in (20, 30, 40, 50):  # all while A rests
        await played_match(db_session, group, [b], [], at(minute), at(minute + 5))
    await played_match(db_session, group, [b], [], at(70), None)  # after A is back
    db_session.add(
        RosterRestPeriod(
            roster_entry_id=a.id, group_id=group.id, started_at=at(15), ended_at=at(60)
        )
    )
    await db_session.commit()

    histories = await _get_player_histories(db_session, group.id)

    assert histories[a.id].rest == 1


@pytest.mark.asyncio
async def test_an_ongoing_rest_is_left_out_too(db_session: AsyncSession) -> None:
    group = await make_group(db_session)
    a, b = await make_players(db_session, group, 2)
    await played_match(db_session, group, [a], [], at(0), at(10))
    await played_match(db_session, group, [b], [], at(12), at(14))
    await played_match(db_session, group, [b], [], at(20), at(25))
    await set_resting(db_session, a, at(15))

    histories = await _get_player_histories(db_session, group.id)

    assert histories[a.id].rest == 1  # the one at 12


@pytest.mark.asyncio
async def test_coming_back_credits_matches_up_to_the_lower_median(
    db_session: AsyncSession,
) -> None:
    group = await make_group(db_session)
    a, *others = await make_players(db_session, group, 5)
    minute = 0
    for player, count in zip(others, (4, 5, 6, 7), strict=True):
        minute = await _play(db_session, group, player, count, minute)
    minute = await _play(db_session, group, a, 1, minute)
    await set_rest_state(db_session, group, a, resting=True)

    await set_rest_state(db_session, group, a, resting=False)

    await db_session.refresh(a)
    assert a.played_credit == 4  # target 5
    histories = await _get_player_histories(db_session, group.id)
    assert histories[a.id].played == 5


@pytest.mark.asyncio
async def test_a_second_return_adds_to_the_credit(db_session: AsyncSession) -> None:
    group = await make_group(db_session)
    a, *others = await make_players(db_session, group, 3)
    minute = 0
    for player in others:
        minute = await _play(db_session, group, player, 6, minute)
    minute = await _play(db_session, group, a, 2, minute)
    a.played_credit = 2  # from an earlier rest: effective 4
    await db_session.commit()
    await set_rest_state(db_session, group, a, resting=True)

    await set_rest_state(db_session, group, a, resting=False)

    await db_session.refresh(a)
    assert a.played_credit == 4  # 2 + (6 - 4)


@pytest.mark.asyncio
async def test_the_target_ignores_resting_and_departed_players_but_counts_credit(
    db_session: AsyncSession,
) -> None:
    group = await make_group(db_session)
    a, credited, resting, departed = await make_players(db_session, group, 4)
    minute = await _play(db_session, group, credited, 1, 0)
    credited.played_credit = 9  # effective 10
    minute = await _play(db_session, group, resting, 20, minute)
    minute = await _play(db_session, group, departed, 30, minute)
    departed.status = "left"
    minute = await _play(db_session, group, a, 1, minute)
    await db_session.commit()
    await set_resting(db_session, resting)
    await set_rest_state(db_session, group, a, resting=True)

    await set_rest_state(db_session, group, a, resting=False)

    await db_session.refresh(a)
    assert a.played_credit == 9  # only `credited` counts: target 10


@pytest.mark.asyncio
async def test_someone_who_never_played_comes_back_a_newcomer(db_session: AsyncSession) -> None:
    """FR-026 is about players who have played: someone who hasn't is a
    newcomer, and stays one."""
    group = await make_group(db_session)
    a, b = await make_players(db_session, group, 2)
    await _play(db_session, group, b, 3, 0)
    await set_rest_state(db_session, group, a, resting=True)

    await set_rest_state(db_session, group, a, resting=False)

    await db_session.refresh(a)
    assert a.wait_count is None
    assert a.played_credit == 0
    assert a.id not in await _get_player_histories(db_session, group.id)


@pytest.mark.asyncio
async def test_a_returning_player_keeps_their_wait_count(db_session: AsyncSession) -> None:
    group = await make_group(db_session)
    a, b = await make_players(db_session, group, 2)
    await _play(db_session, group, a, 1, 0)
    a.wait_count = 1
    await db_session.commit()
    await set_rest_state(db_session, group, a, resting=True)
    await apply_wait_count_updates(db_session, group.id, [b.id])
    await db_session.commit()

    await set_rest_state(db_session, group, a, resting=False)

    await db_session.refresh(a)
    assert a.wait_count == 1


@pytest.mark.asyncio
async def test_credit_never_reaches_the_standings(db_session: AsyncSession) -> None:
    """FR-028: credit is for scheduling only."""
    group = await make_group(db_session)
    a, b = await make_players(db_session, group, 2)
    await played_match(db_session, group, [a], [b], at(0), at(10))
    before = await build_group_standings(db_session, group)

    a.played_credit = 7
    await db_session.commit()
    after = await build_group_standings(db_session, group)

    assert after == before
