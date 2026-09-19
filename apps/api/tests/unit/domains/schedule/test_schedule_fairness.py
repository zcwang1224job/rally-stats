"""Scheduling fairness and flow improvements:
- fair_rotation doubles stage 1 ties go to whoever has played least, and
  only whole matches' worth of players count as selected;
- a freed court prefers the queued match whose players rested longest;
- PairHistory splits teammates from opponents and counts a match when it
  starts, not when it's planned;
- late joiners get matches in the current round; leavers get substitutes;
- continuous rotation for fair_rotation doubles;
- the round matches list reports what's left, a time estimate and byes."""

import math
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.member import models as member_models
from app.domains.roster.models import RosterEntry
from app.domains.schedule.algorithms import (
    greedy_pair_by_cost,
    min_cost_pairing,
    pick_next_match,
    stage1_select_players,
)
from app.domains.schedule.models import Match, MatchParticipant, PairHistory, Partnership
from app.domains.schedule.service import (
    build_round_matches_list,
    create_match_with_participants,
    end_match_early,
    generate_next_round,
    handle_member_joined,
    handle_member_left,
    peek_next_queued_match,
    plan_next_round,
    pull_queued_match_for_court,
    refresh_courts_after_roster_change,
    set_continuous_rotation,
    start_planned_round,
    swap_planned_match_players,
)

# groups.created_by_member_id references members; the table has to be in the
# ORM metadata even though no test here touches it directly.
assert member_models.Member.__tablename__ == "members"

# ---------------------------------------------------------------- helpers


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Schedule Fairness Test",
        "max_members": 20,
        "match_mode": "doubles",
        "scheduling_mechanism": "fair_rotation",
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


async def _make_courts(session: AsyncSession, group: Group, count: int) -> list[Court]:
    courts = []
    for i in range(count):
        court = Court(group_id=group.id, name=f"{i + 1}號場")
        session.add(court)
        await session.commit()
        await session.refresh(court)
        courts.append(court)
    return courts


async def _make_entries(session: AsyncSession, group: Group, count: int) -> list[RosterEntry]:
    """One commit per entry, so joined_at (transaction time) follows the
    list order."""
    entries = []
    for i in range(count):
        entry = RosterEntry(group_id=group.id, nickname=f"P{i}", status="active")
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        entries.append(entry)
    return entries


async def _add_entry(session: AsyncSession, group: Group, nickname: str) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname=nickname, status="active")
    session.add(entry)
    await session.flush()
    return entry


async def _appearances(session: AsyncSession, group: Group) -> Counter[uuid.UUID]:
    result = await session.execute(
        select(MatchParticipant.roster_entry_id)
        .join(Match, Match.id == MatchParticipant.match_id)
        .where(Match.group_id == group.id, Match.started_at.is_not(None))
    )
    return Counter(result.scalars())


async def _lineup(session: AsyncSession, match_id: uuid.UUID) -> dict[str, set[uuid.UUID]]:
    result = await session.execute(
        select(MatchParticipant.team, MatchParticipant.roster_entry_id).where(
            MatchParticipant.match_id == match_id
        )
    )
    lineup: dict[str, set[uuid.UUID]] = {"A": set(), "B": set()}
    for team, roster_entry_id in result.all():
        lineup[team].add(roster_entry_id)
    return lineup


async def _pair_row(
    session: AsyncSession, group: Group, a: uuid.UUID, b: uuid.UUID
) -> tuple[int, int]:
    lo, hi = sorted((a, b))
    result = await session.execute(
        select(PairHistory.pair_count, PairHistory.teammate_count).where(
            PairHistory.group_id == group.id,
            PairHistory.player_lo_id == lo,
            PairHistory.player_hi_id == hi,
        )
    )
    row = result.one_or_none()
    return (row[0], row[1]) if row else (0, 0)


async def _finished_match(
    session: AsyncSession,
    group: Group,
    team_a: list[uuid.UUID],
    team_b: list[uuid.UUID],
    ended_ago: timedelta,
) -> Match:
    """A completed match that ended `ended_ago` before now."""
    match = await create_match_with_participants(
        session, group, court_id=None, round_number=1, status="completed",
        team_a=team_a, team_b=team_b,
    )
    ended_at = datetime.now(UTC) - ended_ago
    match.started_at = ended_at - timedelta(minutes=12)
    match.ended_at = ended_at
    await session.commit()
    return match


# ------------------------------------------------------- pure algorithms


def test_stage1_ties_go_to_fewest_matches_played_then_least_recent() -> None:
    joined = datetime(2026, 1, 1, tzinfo=UTC)
    early, middle, late = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    roster = [
        (early, 0, joined),
        (middle, 0, joined + timedelta(minutes=1)),
        (late, 0, joined + timedelta(minutes=2)),
    ]
    stats = {
        early: (3, joined + timedelta(hours=2)),
        middle: (2, joined + timedelta(hours=2)),
        late: (2, joined + timedelta(hours=1)),
    }
    # Without stats the earliest joiner wins the tie, as before.
    assert stage1_select_players(roster, 1) == [early]
    # With them: fewest played first (middle/late), then least recent (late).
    assert stage1_select_players(roster, 3, stats) == [late, middle, early]


def test_stage1_wait_count_still_outranks_play_stats() -> None:
    joined = datetime(2026, 1, 1, tzinfo=UTC)
    waited, fresh = uuid.uuid4(), uuid.uuid4()
    roster = [(fresh, 0, joined), (waited, 1, joined)]
    stats = {waited: (10, joined), fresh: (0, None)}
    assert stage1_select_players(roster, 1, stats) == [waited]


def test_min_cost_pairing_finds_what_greedy_misses() -> None:
    a, b, c, d = "a", "b", "c", "d"
    costs = {frozenset((a, b)): 0, frozenset((c, d)): 10, frozenset((a, c)): 1,
             frozenset((b, d)): 1, frozenset((a, d)): 5, frozenset((b, c)): 5}

    def cost(x: str, y: str) -> int:
        return costs[frozenset((x, y))]

    assert sum(cost(*p) for p in greedy_pair_by_cost([a, b, c, d], cost)) == 10
    pairs = min_cost_pairing([a, b, c, d], cost)
    assert sum(cost(*p) for p in pairs) == 2
    assert {frozenset(p) for p in pairs} == {frozenset((a, c)), frozenset((b, d))}


def test_min_cost_pairing_keeps_greedy_order_when_costs_tie() -> None:
    units = list(range(6))
    assert min_cost_pairing(units, lambda _x, _y: 0) == [(0, 1), (2, 3), (4, 5)]


def test_min_cost_pairing_large_roster_pairs_everyone_without_repeats() -> None:
    units = list(range(20))
    repeat = {frozenset((i, i + 1)) for i in range(0, 20, 2)}
    pairs = min_cost_pairing(units, lambda x, y: 5 if frozenset((x, y)) in repeat else 0)
    assert len(pairs) == 10
    assert {u for pair in pairs for u in pair} == set(units)
    assert not any(frozenset(pair) in repeat for pair in pairs)


def test_pick_next_match_prefers_rested_players_then_queue_order() -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    tired, rested, fresh = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    last_ended = {tired: now - timedelta(seconds=30), rested: now - timedelta(minutes=20)}
    candidates = [("first", [tired, fresh]), ("second", [rested, fresh]), ("third", [fresh])]
    assert pick_next_match(candidates, last_ended, now) == "second"
    # Everyone rested past the saturation point: plain call-up order.
    assert pick_next_match(candidates[1:], last_ended, now) == "second"
    assert pick_next_match([], last_ended, now) is None


# ------------------------------------------- fair_rotation doubles stage 1


@pytest.mark.asyncio
async def test_non_divisible_roster_spreads_matches_evenly(db_session: AsyncSession) -> None:
    """10 players on 2 courts: 8 play each round. Previously the first 6
    joiners played every round and the last 4 every other round."""
    group = await _make_group(db_session)
    await _make_courts(db_session, group, 2)
    entries = await _make_entries(db_session, group, 10)

    for _ in range(10):
        group = await generate_next_round(db_session, group)

    counts = await _appearances(db_session, group)
    per_player = [counts[entry.id] for entry in entries]
    assert sum(per_player) == 10 * 8
    assert max(per_player) - min(per_player) <= 1


@pytest.mark.asyncio
async def test_small_roster_only_resets_players_who_were_seated(
    db_session: AsyncSession,
) -> None:
    """7 players, 2 courts: only one match fits. The 3 left over must keep
    waiting (wait_count > 0), not be reset as if they had played, so the
    same 3 don't miss out every round."""
    group = await _make_group(db_session)
    await _make_courts(db_session, group, 2)
    entries = await _make_entries(db_session, group, 7)

    group = await generate_next_round(db_session, group)
    seated = set((await _appearances(db_session, group)).keys())
    assert len(seated) == 4
    for entry in entries:
        await db_session.refresh(entry)
        if entry.id in seated:
            assert entry.wait_count == 0
        else:
            assert entry.wait_count == 1

    for _ in range(6):
        group = await generate_next_round(db_session, group)
    counts = await _appearances(db_session, group)
    per_player = [counts[entry.id] for entry in entries]
    assert max(per_player) - min(per_player) <= 1


# ------------------------------------------------ rest-aware call-up order


@pytest.mark.asyncio
async def test_pull_skips_a_match_whose_player_just_finished(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, match_mode="singles")
    [court] = await _make_courts(db_session, group, 1)
    a, b, c, d = (e.id for e in await _make_entries(db_session, group, 4))
    await _finished_match(db_session, group, [a], [d], ended_ago=timedelta(seconds=20))

    first = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[a], team_b=[b], queue_position=0,
    )
    second = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[b], team_b=[c], queue_position=1,
    )
    await db_session.commit()

    preview = await peek_next_queued_match(db_session, group.id, 1, court.id)
    pulled = await pull_queued_match_for_court(db_session, group.id, 1, court.id)
    assert pulled is not None and pulled.id == second.id
    assert preview is not None and preview.id == second.id
    assert first.status == "queued"


@pytest.mark.asyncio
async def test_pull_follows_queue_order_once_everyone_has_rested(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session, match_mode="singles")
    [court] = await _make_courts(db_session, group, 1)
    a, b, c, d = (e.id for e in await _make_entries(db_session, group, 4))
    await _finished_match(db_session, group, [a], [d], ended_ago=timedelta(minutes=30))

    first = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[a], team_b=[b], queue_position=0,
    )
    await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[b], team_b=[c], queue_position=1,
    )
    await db_session.commit()

    pulled = await pull_queued_match_for_court(db_session, group.id, 1, court.id)
    assert pulled is not None and pulled.id == first.id


@pytest.mark.asyncio
async def test_peek_skips_matches_with_a_player_on_another_court(
    db_session: AsyncSession,
) -> None:
    """The "next up" preview used to show the first queued match even when
    one of its players was still playing elsewhere, so it could announce a
    match that the court would never actually call next."""
    group = await _make_group(db_session, match_mode="singles")
    court_1, court_2 = await _make_courts(db_session, group, 2)
    a, b, c, d = (e.id for e in await _make_entries(db_session, group, 4))
    await create_match_with_participants(
        db_session, group, court_id=court_1.id, round_number=1, status="in_progress",
        team_a=[a], team_b=[b],
    )
    await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[a], team_b=[c], queue_position=0,
    )
    free = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[c], team_b=[d], queue_position=1,
    )
    await db_session.commit()

    preview = await peek_next_queued_match(db_session, group.id, 1, court_2.id)
    assert preview is not None and preview.id == free.id


# ---------------------------------------------------------- PairHistory


@pytest.mark.asyncio
async def test_pair_history_counts_at_start_and_separates_teammates(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session, scheduling_mechanism="individual_mixed")
    await _make_courts(db_session, group, 1)
    entries = await _make_entries(db_session, group, 4)

    group = await plan_next_round(db_session, group)
    history = await db_session.execute(select(PairHistory).where(PairHistory.group_id == group.id))
    assert history.scalars().all() == []

    group = await start_planned_round(db_session, group)
    [started] = (
        await db_session.execute(
            select(Match).where(Match.group_id == group.id, Match.status == "in_progress")
        )
    ).scalars().all()
    lineup = await _lineup(db_session, started.id)
    a1, a2 = sorted(lineup["A"])
    b1, _b2 = sorted(lineup["B"])
    assert await _pair_row(db_session, group, a1, a2) == (1, 1)
    assert await _pair_row(db_session, group, a1, b1) == (1, 0)
    assert len(entries) == 4


@pytest.mark.asyncio
async def test_swap_during_play_moves_pair_history(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    court_1, court_2 = await _make_courts(db_session, group, 2)
    p = [e.id for e in await _make_entries(db_session, group, 8)]
    match_1 = await create_match_with_participants(
        db_session, group, court_id=court_1.id, round_number=1, status="in_progress",
        team_a=[p[0], p[1]], team_b=[p[2], p[3]],
    )
    match_2 = await create_match_with_participants(
        db_session, group, court_id=court_2.id, round_number=1, status="in_progress",
        team_a=[p[4], p[5]], team_b=[p[6], p[7]],
    )
    await db_session.commit()
    assert await _pair_row(db_session, group, p[0], p[1]) == (1, 1)

    await swap_planned_match_players(db_session, group, match_1.id, p[1], match_2.id, p[4])

    assert await _pair_row(db_session, group, p[0], p[1]) == (0, 0)
    assert await _pair_row(db_session, group, p[0], p[4]) == (1, 1)
    assert await _pair_row(db_session, group, p[5], p[1]) == (1, 1)
    assert await _pair_row(db_session, group, p[4], p[2]) == (1, 0)


# ------------------------------------------------------------ late joiners


@pytest.mark.asyncio
async def test_late_joiner_gets_singles_matches_this_round(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, match_mode="singles")
    await _make_courts(db_session, group, 1)
    entries = await _make_entries(db_session, group, 3)
    group = await plan_next_round(db_session, group)
    group = await start_planned_round(db_session, group)

    newcomer = await _add_entry(db_session, group, "Late")
    assert await handle_member_joined(db_session, group, newcomer) is True
    await db_session.commit()

    result = await db_session.execute(
        select(Match.id)
        .join(MatchParticipant, MatchParticipant.match_id == Match.id)
        .where(
            Match.group_id == group.id,
            Match.round_number == group.current_round_number,
            MatchParticipant.roster_entry_id == newcomer.id,
        )
    )
    new_matches = list(result.scalars())
    opponents = set()
    for match_id in new_matches:
        lineup = await _lineup(db_session, match_id)
        opponents |= (lineup["A"] | lineup["B"]) - {newcomer.id}
    assert opponents == {entry.id for entry in entries}
    assert len(new_matches) == 3


@pytest.mark.asyncio
async def test_joining_a_planned_round_does_not_start_it(db_session: AsyncSession) -> None:
    """A newcomer's catch-up matches are queued, but courts stay empty until
    the admin presses start."""
    group = await _make_group(db_session, match_mode="singles")
    await _make_courts(db_session, group, 1)
    await _make_entries(db_session, group, 3)
    group = await plan_next_round(db_session, group)

    newcomer = await _add_entry(db_session, group, "Late")
    assert await handle_member_joined(db_session, group, newcomer) is True
    await db_session.commit()
    await refresh_courts_after_roster_change(db_session, group)

    started = await db_session.execute(
        select(Match.id).where(Match.group_id == group.id, Match.status == "in_progress")
    )
    assert started.scalars().all() == []


@pytest.mark.asyncio
async def test_no_catch_up_before_the_round_is_planned(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, match_mode="singles")
    await _make_courts(db_session, group, 1)
    await _make_entries(db_session, group, 3)

    newcomer = await _add_entry(db_session, group, "Early")
    assert await handle_member_joined(db_session, group, newcomer) is False


@pytest.mark.asyncio
async def test_late_joiners_in_fixed_partner_form_a_team_and_play_every_team(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session, scheduling_mechanism="fixed_partner")
    await _make_courts(db_session, group, 1)
    entries = await _make_entries(db_session, group, 4)
    for i in (0, 2):
        db_session.add(
            Partnership(group_id=group.id, player_a_id=entries[i].id, player_b_id=entries[i + 1].id)
        )
    await db_session.commit()
    group = await plan_next_round(db_session, group)

    first = await _add_entry(db_session, group, "Late1")
    # Alone, the first newcomer has nobody to team up with yet.
    assert await handle_member_joined(db_session, group, first) is False
    await db_session.commit()

    second = await _add_entry(db_session, group, "Late2")
    assert await handle_member_joined(db_session, group, second) is True
    await db_session.commit()

    result = await db_session.execute(
        select(Match.id)
        .join(MatchParticipant, MatchParticipant.match_id == Match.id)
        .where(Match.group_id == group.id, MatchParticipant.roster_entry_id == first.id)
    )
    new_matches = list(result.scalars())
    assert len(new_matches) == 2
    for match_id in new_matches:
        lineup = await _lineup(db_session, match_id)
        new_side = "A" if first.id in lineup["A"] else "B"
        assert lineup[new_side] == {first.id, second.id}


@pytest.mark.asyncio
async def test_late_joiner_in_individual_mixed_partners_everyone(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session, scheduling_mechanism="individual_mixed")
    await _make_courts(db_session, group, 1)
    entries = await _make_entries(db_session, group, 4)
    group = await plan_next_round(db_session, group)

    newcomer = await _add_entry(db_session, group, "Late")
    assert await handle_member_joined(db_session, group, newcomer) is True
    await db_session.commit()

    result = await db_session.execute(
        select(Match.id)
        .join(MatchParticipant, MatchParticipant.match_id == Match.id)
        .where(Match.group_id == group.id, MatchParticipant.roster_entry_id == newcomer.id)
    )
    partners = set()
    for match_id in result.scalars():
        lineup = await _lineup(db_session, match_id)
        side = lineup["A"] if newcomer.id in lineup["A"] else lineup["B"]
        partners |= side - {newcomer.id}
    assert partners == {entry.id for entry in entries}


# -------------------------------------------------------------- leavers


@pytest.mark.asyncio
async def test_leaver_in_doubles_is_replaced_by_the_least_scheduled_member(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session, scheduling_mechanism="individual_mixed")
    await _make_courts(db_session, group, 1)
    a, b, c, d, e, f = await _make_entries(db_session, group, 6)
    busy = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[a.id, b.id], team_b=[c.id, d.id], queue_position=0,
    )
    await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[e.id, b.id], team_b=[c.id, d.id], queue_position=1,
    )
    await db_session.commit()

    await handle_member_left(db_session, group, a, new_status="left")
    await db_session.commit()
    await db_session.refresh(busy)

    assert busy.status == "queued"
    lineup = await _lineup(db_session, busy.id)
    # e already has a match this round, f has none: f substitutes.
    assert lineup["A"] == {f.id, b.id}


@pytest.mark.asyncio
async def test_leaver_in_singles_round_robin_still_abandons(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, match_mode="singles")
    await _make_courts(db_session, group, 1)
    a, b, c = await _make_entries(db_session, group, 3)
    match = await create_match_with_participants(
        db_session, group, court_id=None, round_number=1, status="queued",
        team_a=[a.id], team_b=[b.id], queue_position=0,
    )
    await db_session.commit()

    await handle_member_left(db_session, group, a, new_status="left")
    await db_session.commit()
    await db_session.refresh(match)
    assert match.status == "abandoned"
    assert c.id not in (await _lineup(db_session, match.id))["A"]


# ----------------------------------------------------- continuous rotation


@pytest.mark.asyncio
async def test_continuous_rotation_refills_a_freed_court(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    courts = await _make_courts(db_session, group, 2)
    entries = await _make_entries(db_session, group, 10)
    group = await set_continuous_rotation(db_session, group, True)
    group = await generate_next_round(db_session, group)

    playing = set((await _appearances(db_session, group)).keys())
    waiting = {entry.id for entry in entries} - playing
    assert len(waiting) == 2

    [finished] = (
        await db_session.execute(
            select(Match).where(Match.court_id == courts[0].id, Match.status == "in_progress")
        )
    ).scalars().all()
    await end_match_early(db_session, courts[0], finished.id)

    [refill] = (
        await db_session.execute(
            select(Match).where(Match.court_id == courts[0].id, Match.status == "in_progress")
        )
    ).scalars().all()
    assert refill.round_number == finished.round_number
    lineup = await _lineup(db_session, refill.id)
    assert waiting <= lineup["A"] | lineup["B"]


@pytest.mark.asyncio
async def test_without_continuous_rotation_a_freed_court_waits(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    courts = await _make_courts(db_session, group, 2)
    await _make_entries(db_session, group, 10)
    group = await generate_next_round(db_session, group)

    [finished] = (
        await db_session.execute(
            select(Match).where(Match.court_id == courts[0].id, Match.status == "in_progress")
        )
    ).scalars().all()
    await end_match_early(db_session, courts[0], finished.id)

    remaining = (
        await db_session.execute(
            select(Match).where(Match.court_id == courts[0].id, Match.status == "in_progress")
        )
    ).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_continuous_rotation_is_rejected_outside_fair_rotation_doubles(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session, match_mode="singles")
    with pytest.raises(ApiError) as exc_info:
        await set_continuous_rotation(db_session, group, True)
    assert exc_info.value.error_code == "CONTINUOUS_ROTATION_NOT_SUPPORTED"


# --------------------------------------------------- round matches summary


@pytest.mark.asyncio
async def test_round_list_reports_remaining_estimate_and_byes(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, match_mode="singles")
    await _make_courts(db_session, group, 1)
    await _make_entries(db_session, group, 4)
    group = await plan_next_round(db_session, group)

    summary = await build_round_matches_list(db_session, group)
    assert summary.remaining_count == math.comb(4, 2)
    # No history yet: 21-point games are guessed at 0.6 min/point, one court.
    assert summary.estimated_remaining_minutes == math.ceil(6 * 21 * 0.6)
    assert summary.sitting_out == []

    await db_session.execute(
        update(Match).where(Match.group_id == group.id).values(status="completed")
    )
    await db_session.commit()
    summary = await build_round_matches_list(db_session, group)
    assert summary.remaining_count == 0
    assert summary.estimated_remaining_minutes is None


@pytest.mark.asyncio
async def test_round_list_names_the_fixed_partner_bye(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, scheduling_mechanism="fixed_partner")
    await _make_courts(db_session, group, 1)
    entries = await _make_entries(db_session, group, 5)
    group = await plan_next_round(db_session, group)

    summary = await build_round_matches_list(db_session, group)
    assert len(summary.sitting_out) == 1
    assert summary.sitting_out[0].roster_entry_id in {str(e.id) for e in entries}
