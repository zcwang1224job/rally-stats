"""037-rest-ready-toggle US1: `set_rest_state()` — the one function both
rest-state endpoints call, after their own authorization check."""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.roster.models import RosterEntry, RosterRestPeriod
from app.domains.schedule import rest as rest_module
from app.domains.schedule.rest import set_rest_state
from app.domains.schedule.service import (
    handle_member_left,
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


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict[str, Any]]]:
    events: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_publish(channel: str, event: str, payload: dict[str, Any]) -> None:
        events.append((channel, event, payload))

    monkeypatch.setattr(rest_module, "publish", fake_publish)
    return events


async def _periods(session: AsyncSession, entry: RosterEntry) -> list[RosterRestPeriod]:
    result = await session.execute(
        select(RosterRestPeriod).where(RosterRestPeriod.roster_entry_id == entry.id)
    )
    return list(result.scalars())


@pytest.mark.asyncio
async def test_ready_to_resting(db_session: AsyncSession, published: list) -> None:
    group = await make_group(db_session)
    [player] = await make_players(db_session, group, 1)

    response = await set_rest_state(db_session, group, player, resting=True)

    await db_session.refresh(player)
    assert player.resting_since is not None
    assert response.resting is True
    assert response.resting_since == player.resting_since
    assert response.changed is True
    assert response.currently_playing is False


@pytest.mark.asyncio
async def test_resting_again_is_a_no_op(db_session: AsyncSession, published: list) -> None:
    group = await make_group(db_session)
    [player] = await make_players(db_session, group, 1)
    await set_rest_state(db_session, group, player, resting=True)
    await db_session.refresh(player)
    since = player.resting_since
    published.clear()

    response = await set_rest_state(db_session, group, player, resting=True)

    await db_session.refresh(player)
    assert response.changed is False
    assert player.resting_since == since
    assert await _periods(db_session, player) == []
    assert published == []


@pytest.mark.asyncio
async def test_back_to_ready_records_the_period(db_session: AsyncSession, published: list) -> None:
    group = await make_group(db_session)
    [player] = await make_players(db_session, group, 1)
    await set_rest_state(db_session, group, player, resting=True)
    await db_session.refresh(player)
    since = player.resting_since

    response = await set_rest_state(db_session, group, player, resting=False)

    await db_session.refresh(player)
    assert response.changed is True
    assert response.resting is False
    assert response.resting_since is None
    assert player.resting_since is None
    [period] = await _periods(db_session, player)
    assert period.started_at == since
    assert period.ended_at >= period.started_at
    assert period.group_id == group.id


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["left", "kicked"])
async def test_an_entry_no_longer_in_the_group_is_not_found(
    db_session: AsyncSession, published: list, status: str
) -> None:
    group = await make_group(db_session)
    [player] = await make_players(db_session, group, 1)
    player.status = status
    await db_session.commit()

    with pytest.raises(ApiError) as caught:
        await set_rest_state(db_session, group, player, resting=True)
    assert caught.value.error_code == "ROSTER_ENTRY_NOT_FOUND"
    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_an_entry_of_another_group_is_not_found(
    db_session: AsyncSession, published: list
) -> None:
    group = await make_group(db_session)
    other = await make_group(db_session)
    [player] = await make_players(db_session, other, 1)

    with pytest.raises(ApiError) as caught:
        await set_rest_state(db_session, group, player, resting=True)
    assert caught.value.error_code == "ROSTER_ENTRY_NOT_FOUND"


@pytest.mark.asyncio
async def test_a_disbanded_group_is_rejected(db_session: AsyncSession, published: list) -> None:
    group = await make_group(db_session)
    [player] = await make_players(db_session, group, 1)
    group.status = "disbanded"
    await db_session.commit()

    with pytest.raises(ApiError) as caught:
        await set_rest_state(db_session, group, player, resting=True)
    assert caught.value.error_code == "GROUP_DISBANDED"
    assert caught.value.status_code == 409


@pytest.mark.asyncio
async def test_resting_on_court_leaves_the_match_alone(
    db_session: AsyncSession, published: list
) -> None:
    """FR-014: the match goes on; they rest after it."""
    group = await make_group(db_session, match_mode="singles")
    await make_courts(db_session, group, 1)
    players = await make_players(db_session, group, 2)
    await plan_next_round(db_session, group)
    await start_planned_round(db_session, group)
    [live] = await in_progress(db_session, group)
    before = await participants(db_session, live.id)

    response = await set_rest_state(db_session, group, players[0], resting=True)

    await db_session.refresh(live)
    assert live.status == "in_progress"
    assert await participants(db_session, live.id) == before
    assert response.currently_playing is True


@pytest.mark.asyncio
async def test_resting_changes_none_of_their_queued_matches(
    db_session: AsyncSession, published: list
) -> None:
    """FR-013: anything about their matches happens when one is called."""
    group = await make_group(db_session, match_mode="singles")
    await make_courts(db_session, group, 1)
    players = await make_players(db_session, group, 4)
    await plan_next_round(db_session, group)
    before = {
        match.id: (match.status, await participants(db_session, match.id))
        for match in await round_matches(db_session, group)
    }

    await set_rest_state(db_session, group, players[0], resting=True)

    after = {
        match.id: (match.status, await participants(db_session, match.id))
        for match in await round_matches(db_session, group)
    }
    assert after == before


@pytest.mark.asyncio
async def test_a_change_is_published_once(db_session: AsyncSession, published: list) -> None:
    group = await make_group(db_session)
    [player] = await make_players(db_session, group, 1)

    await set_rest_state(db_session, group, player, resting=True)

    rest_events = [e for e in published if e[1] == "roster.restChanged"]
    assert rest_events == [
        (
            f"group:{group.id}:notifications",
            "roster.restChanged",
            {"roster_entry_id": str(player.id), "nickname": player.nickname, "resting": True},
        )
    ]


@pytest.mark.asyncio
async def test_leaving_while_resting_works_and_a_rejoin_starts_ready(
    db_session: AsyncSession, published: list
) -> None:
    """FR-001, FR-030: leaving is unchanged; coming back is a new entry."""
    group = await make_group(db_session)
    [player] = await make_players(db_session, group, 1)
    await set_resting(db_session, player)

    await handle_member_left(db_session, group, player, new_status="left")
    await db_session.commit()
    rejoined = RosterEntry(group_id=group.id, nickname=player.nickname, status="active")
    db_session.add(rejoined)
    await db_session.commit()
    await db_session.refresh(rejoined)

    assert player.status == "left"
    assert rejoined.resting_since is None
