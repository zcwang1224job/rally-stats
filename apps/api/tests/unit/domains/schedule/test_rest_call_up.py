"""037-rest-ready-toggle US2 (FR-015～FR-018, FR-027): what happens to a
queued match with a resting player in it when a court frees up. Nothing
changes when "rest" is pressed; the decision is made at call-up — matches
without a resting player go first; after that, fair-rotation doubles and
individual-mixed call a substitute who can play right now, while singles
round-robin and fixed partners keep the match for the player's return."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domains.group.models import Group
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant, PairHistory
from app.domains.schedule.service import (
    _seat_waiting_players_on_court,
    create_match_with_participants,
    peek_next_call,
    plan_next_round,
    pull_queued_match_for_court,
    start_planned_round,
)
from tests.conftest import TEST_DATABASE_URL
from tests.unit.domains.schedule._rest_helpers import (
    in_progress,
    make_courts,
    make_group,
    make_players,
    participants,
    played_match,
    set_ready,
    set_resting,
)


async def _queue(
    session: AsyncSession,
    group: Group,
    team_a: list[RosterEntry],
    team_b: list[RosterEntry],
    position: int,
) -> Match:
    match = await create_match_with_participants(
        session,
        group,
        court_id=None,
        round_number=group.current_round_number,
        status="queued",
        team_a=[p.id for p in team_a],
        team_b=[p.id for p in team_b],
        queue_position=position,
    )
    await session.commit()
    return match


async def _pull(session: AsyncSession, group: Group, court_id: object) -> Match | None:
    match = await pull_queued_match_for_court(
        session, group.id, group.current_round_number, court_id  # type: ignore[arg-type]
    )
    await session.commit()
    return match


async def _sides(session: AsyncSession, match: Match) -> dict[str, set[object]]:
    rows = await session.execute(
        select(MatchParticipant.team, MatchParticipant.roster_entry_id).where(
            MatchParticipant.match_id == match.id
        )
    )
    sides: dict[str, set[object]] = {"A": set(), "B": set()}
    for team, roster_entry_id in rows.all():
        sides[team].add(roster_entry_id)
    return sides


@pytest.mark.asyncio
async def test_matches_without_a_resting_player_go_first(db_session: AsyncSession) -> None:
    group = await make_group(db_session, match_mode="singles")
    [court] = await make_courts(db_session, group, 1)
    a, b, c, d = await make_players(db_session, group, 4)
    await _queue(db_session, group, [a], [b], 0)
    later = await _queue(db_session, group, [c], [d], 1)
    await set_resting(db_session, a)

    pulled = await _pull(db_session, group, court.id)

    assert pulled is not None and pulled.id == later.id


@pytest.mark.asyncio
async def test_singles_round_robin_keeps_the_match(db_session: AsyncSession) -> None:
    group = await make_group(db_session, match_mode="singles")
    [court] = await make_courts(db_session, group, 1)
    a, b, _c = await make_players(db_session, group, 3)
    kept = await _queue(db_session, group, [a], [b], 0)
    await set_resting(db_session, a)

    assert await _pull(db_session, group, court.id) is None

    await db_session.refresh(kept)
    assert kept.status == "queued"
    assert await participants(db_session, kept.id) == {a.id, b.id}


@pytest.mark.asyncio
async def test_fixed_partner_keeps_the_match(db_session: AsyncSession) -> None:
    group = await make_group(
        db_session, scheduling_mechanism="fixed_partner", partner_source="manual"
    )
    [court] = await make_courts(db_session, group, 1)
    a, b, c, d, _spare = await make_players(db_session, group, 5)
    kept = await _queue(db_session, group, [a, b], [c, d], 0)
    await set_resting(db_session, a)

    assert await _pull(db_session, group, court.id) is None
    assert await participants(db_session, kept.id) == {a.id, b.id, c.id, d.id}


@pytest.mark.asyncio
async def test_individual_mixed_calls_a_substitute(db_session: AsyncSession) -> None:
    group = await make_group(db_session, scheduling_mechanism="individual_mixed")
    [court] = await make_courts(db_session, group, 1)
    a, b, c, d, sub = await make_players(db_session, group, 5)
    match = await _queue(db_session, group, [a, b], [c, d], 0)
    await set_resting(db_session, a)

    pulled = await _pull(db_session, group, court.id)

    assert pulled is not None and pulled.id == match.id
    assert pulled.status == "in_progress"
    assert await _sides(db_session, match) == {"A": {sub.id, b.id}, "B": {c.id, d.id}}


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["resting", "on_court"])
async def test_a_substitute_must_be_able_to_play_now(
    db_session: AsyncSession, reason: str
) -> None:
    group = await make_group(db_session, scheduling_mechanism="individual_mixed")
    court, other_court = await make_courts(db_session, group, 2)
    a, b, c, d, sub, x, y, z = await make_players(db_session, group, 8)
    match = await _queue(db_session, group, [a, b], [c, d], 0)
    if reason == "resting":
        await set_resting(db_session, sub)
        await set_resting(db_session, x)
        await set_resting(db_session, y)
        await set_resting(db_session, z)
    else:
        await create_match_with_participants(
            db_session,
            group,
            court_id=other_court.id,
            round_number=group.current_round_number,
            status="in_progress",
            team_a=[sub.id, x.id],
            team_b=[y.id, z.id],
        )
        await db_session.commit()
    await set_resting(db_session, a)

    assert await _pull(db_session, group, court.id) is None
    await db_session.refresh(match)
    assert match.status == "queued"
    assert await participants(db_session, match.id) == {a.id, b.id, c.id, d.id}


@pytest.mark.asyncio
async def test_two_resting_players_need_two_different_substitutes(
    db_session: AsyncSession,
) -> None:
    group = await make_group(db_session, scheduling_mechanism="individual_mixed")
    [court] = await make_courts(db_session, group, 1)
    a, b, c, d, e, f = await make_players(db_session, group, 6)
    match = await _queue(db_session, group, [a, b], [c, d], 0)
    await set_resting(db_session, a)
    await set_resting(db_session, c)

    pulled = await _pull(db_session, group, court.id)

    assert pulled is not None
    assert await participants(db_session, match.id) == {b.id, d.id, e.id, f.id}


@pytest.mark.asyncio
async def test_no_half_substitution(db_session: AsyncSession) -> None:
    group = await make_group(db_session, scheduling_mechanism="individual_mixed")
    [court] = await make_courts(db_session, group, 1)
    a, b, c, d, _e = await make_players(db_session, group, 5)
    match = await _queue(db_session, group, [a, b], [c, d], 0)
    await set_resting(db_session, a)
    await set_resting(db_session, c)

    assert await _pull(db_session, group, court.id) is None
    assert await participants(db_session, match.id) == {a.id, b.id, c.id, d.id}


@pytest.mark.asyncio
async def test_the_substitute_is_whoever_has_played_least_this_round(
    db_session: AsyncSession,
) -> None:
    group = await make_group(db_session, scheduling_mechanism="individual_mixed")
    [court] = await make_courts(db_session, group, 1)
    a, b, c, d, busy_one, fresh = await make_players(db_session, group, 6)
    # busy_one has already played a match this round.
    now = datetime.now(UTC)
    await played_match(db_session, group, [busy_one, b], [c, d], now - timedelta(minutes=20), now)
    match = await _queue(db_session, group, [a, b], [c, d], 0)
    await set_resting(db_session, a)

    await _pull(db_session, group, court.id)

    assert fresh.id in await participants(db_session, match.id)


@pytest.mark.asyncio
async def test_among_equals_the_earliest_joiner_substitutes(db_session: AsyncSession) -> None:
    group = await make_group(db_session, scheduling_mechanism="individual_mixed")
    [court] = await make_courts(db_session, group, 1)
    a, b, c, d, first, _second = await make_players(db_session, group, 6)
    match = await _queue(db_session, group, [a, b], [c, d], 0)
    await set_resting(db_session, a)

    await _pull(db_session, group, court.id)

    assert first.id in await participants(db_session, match.id)


@pytest.mark.asyncio
async def test_fair_rotation_resets_the_substitute_wait_count_only(
    db_session: AsyncSession,
) -> None:
    """FR-027: as if stage 1 had picked the substitute. The resting
    player's count stays frozen."""
    group = await make_group(db_session, scheduling_mechanism="fair_rotation")
    [court] = await make_courts(db_session, group, 1)
    a, b, c, d, sub = await make_players(db_session, group, 5)
    a.wait_count = 3
    sub.wait_count = 2
    await db_session.commit()
    await _queue(db_session, group, [a, b], [c, d], 0)
    await set_resting(db_session, a)

    await _pull(db_session, group, court.id)

    await db_session.refresh(a)
    await db_session.refresh(sub)
    assert sub.wait_count == 0
    assert a.wait_count == 3


@pytest.mark.asyncio
async def test_individual_mixed_leaves_wait_counts_alone(db_session: AsyncSession) -> None:
    group = await make_group(db_session, scheduling_mechanism="individual_mixed")
    [court] = await make_courts(db_session, group, 1)
    a, b, c, d, sub = await make_players(db_session, group, 5)
    sub.wait_count = 2
    await db_session.commit()
    await _queue(db_session, group, [a, b], [c, d], 0)
    await set_resting(db_session, a)

    await _pull(db_session, group, court.id)

    await db_session.refresh(sub)
    assert sub.wait_count == 2


@pytest.mark.asyncio
async def test_pair_history_records_the_substitute_not_the_resting_player(
    db_session: AsyncSession,
) -> None:
    group = await make_group(db_session, scheduling_mechanism="individual_mixed")
    [court] = await make_courts(db_session, group, 1)
    a, b, c, d, sub = await make_players(db_session, group, 5)
    await _queue(db_session, group, [a, b], [c, d], 0)
    await set_resting(db_session, a)

    await _pull(db_session, group, court.id)

    rows = (
        await db_session.execute(select(PairHistory).where(PairHistory.group_id == group.id))
    ).scalars().all()
    recorded = {pid for row in rows for pid in (row.player_lo_id, row.player_hi_id)}
    assert sub.id in recorded
    assert a.id not in recorded


@pytest.mark.asyncio
async def test_the_preview_promises_what_is_called_and_writes_nothing(
    db_session: AsyncSession,
) -> None:
    group = await make_group(db_session, scheduling_mechanism="individual_mixed")
    [court] = await make_courts(db_session, group, 1)
    a, b, c, d, sub = await make_players(db_session, group, 5)
    match = await _queue(db_session, group, [a, b], [c, d], 0)
    await set_resting(db_session, a)

    preview = await peek_next_call(
        db_session, group.id, group.current_round_number, court.id
    )

    assert preview is not None
    assert preview.match.id == match.id
    assert preview.substitutions == ((a.id, sub.id),)
    assert await participants(db_session, match.id) == {a.id, b.id, c.id, d.id}

    pulled = await _pull(db_session, group, court.id)
    assert pulled is not None and pulled.id == match.id
    assert await participants(db_session, match.id) == {sub.id, b.id, c.id, d.id}


@pytest.mark.asyncio
async def test_back_before_the_call_plays_the_original_lineup(db_session: AsyncSession) -> None:
    group = await make_group(db_session, scheduling_mechanism="individual_mixed")
    [court] = await make_courts(db_session, group, 1)
    a, b, c, d, _sub = await make_players(db_session, group, 5)
    match = await _queue(db_session, group, [a, b], [c, d], 0)
    await set_resting(db_session, a)
    await peek_next_call(db_session, group.id, group.current_round_number, court.id)
    await set_ready(db_session, a)

    await _pull(db_session, group, court.id)

    assert await participants(db_session, match.id) == {a.id, b.id, c.id, d.id}


@pytest.mark.asyncio
async def test_other_queued_matches_wait_for_their_own_call(db_session: AsyncSession) -> None:
    group = await make_group(db_session, scheduling_mechanism="individual_mixed")
    [court] = await make_courts(db_session, group, 1)
    a, b, c, d, _e = await make_players(db_session, group, 5)
    await _queue(db_session, group, [a, b], [c, d], 0)
    later = await _queue(db_session, group, [a, c], [b, d], 1)
    await set_resting(db_session, a)

    await _pull(db_session, group, court.id)

    assert await participants(db_session, later.id) == {a.id, b.id, c.id, d.id}


@pytest.mark.asyncio
async def test_starting_a_planned_round_follows_the_same_rules(db_session: AsyncSession) -> None:
    group = await make_group(db_session, scheduling_mechanism="individual_mixed")
    await make_courts(db_session, group, 2)
    players = await make_players(db_session, group, 6)
    await plan_next_round(db_session, group)
    await set_resting(db_session, players[0])

    await start_planned_round(db_session, group)

    for match in await in_progress(db_session, group):
        assert players[0].id not in await participants(db_session, match.id)


@pytest.mark.asyncio
async def test_a_substitute_is_never_also_seated_on_another_court(
    db_session: AsyncSession,
) -> None:
    """Court 1 calls a match and picks a substitute; at the same moment
    court 2, with nothing callable (court 1 holds the queued match's row
    lock), seats four waiting players by continuous rotation — which reads
    players, not match rows — and must not seat the substitute too.

    This checks the outcome, not which lock gives it: removing the explicit
    group lock in `pull_queued_match_for_court()` still passes today,
    because starting the match inserts `pair_history` rows whose foreign
    key takes a KEY SHARE lock on the group row, which continuous
    rotation's FOR UPDATE waits for (verified 2026-09-19). The explicit
    lock stays so the guarantee doesn't hang on that side effect."""
    group = await make_group(
        db_session, scheduling_mechanism="fair_rotation", continuous_rotation=True
    )
    court_1, court_2 = await make_courts(db_session, group, 2)
    a, p1, p2, p3, s1, s2, s3, s4 = await make_players(db_session, group, 8)
    for waiting in (s1, s2, s3, s4):
        waiting.wait_count = 5  # continuous rotation seats exactly these four
    for playing in (p1, p2, p3):
        playing.wait_count = 0
    await db_session.commit()
    await _queue(db_session, group, [a, p1], [p2, p3], 0)
    await set_resting(db_session, a)

    engine = create_async_engine(TEST_DATABASE_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as one, sessions() as two:
            pulled = await pull_queued_match_for_court(
                one, group.id, group.current_round_number, court_1.id
            )
            group_two = (await two.execute(select(Group).where(Group.id == group.id))).scalar_one()
            racing = asyncio.create_task(
                _seat_waiting_players_on_court(
                    two, group_two, court_2.id, group.current_round_number
                )
            )
            await asyncio.sleep(0.3)  # let it reach the lock
            await one.commit()
            await racing
            await two.commit()
    finally:
        await engine.dispose()

    assert pulled is not None
    assert s1.id in await participants(db_session, pulled.id)  # earliest joiner
    on_court = [await participants(db_session, m.id) for m in await in_progress(db_session, group)]
    for player in (s1, s2, s3, s4, p1, p2, p3):
        assert sum(player.id in lineup for lineup in on_court) <= 1
