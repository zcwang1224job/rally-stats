"""Unit tests for 018-plan-then-start: the admin-facing three-step "結束這一
輪" (end) -> "規劃賽程安排" (plan) -> "比賽開始" (start) flow for algorithmic
scheduling mechanisms — `end_current_round()` force-abandons an unfinished
round without generating a new one, `plan_next_round()` generates the next
round's matches without pulling them onto courts, `start_planned_round()`
confirms and pulls them, `get_round_phase()` derives which state a round is
in, `reorder_planned_matches()` lets the admin drag-reorder the call-up
order before the round starts, and `swap_planned_match_players()` /
`change_match_player()` let the admin adjust who's playing in any
not-yet-terminal match — including mid-round, not just while still
`awaiting_start` (a follow-up requirement: substituting an injured player
must work for matches that are already `in_progress`). Manual mode is
deliberately untouched by this feature and keeps using
`generate_next_round()` directly."""

import math
import uuid

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.court.models import Court
from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant
from app.domains.schedule.service import (
    change_match_player,
    end_current_round,
    generate_next_round,
    get_round_phase,
    plan_next_round,
    reorder_planned_matches,
    start_planned_round,
    swap_planned_match_players,
)


async def _make_group(session: AsyncSession, **overrides: object) -> Group:
    defaults: dict[str, object] = {
        "name": "Plan Then Start Test",
        "max_members": 16,
        "match_mode": "singles",
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


async def _make_court(session: AsyncSession, group: Group, name: str = "1號場") -> Court:
    court = Court(group_id=group.id, name=name)
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
async def test_get_round_phase_is_awaiting_plan_before_anything_generated(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    assert await get_round_phase(db_session, group) == "awaiting_plan"


@pytest.mark.asyncio
async def test_plan_next_round_creates_matches_without_starting(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    updated = await plan_next_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.round_number == 1)
    )
    matches = result.scalars().all()
    assert len(matches) == math.comb(5, 2)
    assert all(m.status == "queued" for m in matches)
    assert all(m.court_id is None for m in matches)
    assert await get_round_phase(db_session, updated) == "awaiting_start"


@pytest.mark.asyncio
async def test_plan_next_round_rejects_manual_mode(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, scheduling_mechanism="manual")
    await _make_court(db_session, group)

    with pytest.raises(ApiError) as exc_info:
        await plan_next_round(db_session, group)

    assert exc_info.value.error_code == "SCHEDULING_MECHANISM_MISMATCH"


@pytest.mark.asyncio
async def test_start_planned_round_pulls_matches_onto_one_court_per_court(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group, "1號場")
    await _make_court(db_session, group, "2號場")
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)
    updated = await start_planned_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.round_number == 1)
    )
    matches = result.scalars().all()
    in_progress = [m for m in matches if m.status == "in_progress"]
    assert len(in_progress) == 2  # two courts -> two matches picked up
    assert all(m.court_id is not None for m in in_progress)
    assert await get_round_phase(db_session, updated) == "in_progress"


@pytest.mark.asyncio
async def test_start_planned_round_without_a_plan_is_rejected(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)

    with pytest.raises(ApiError) as exc_info:
        await start_planned_round(db_session, group)

    assert exc_info.value.error_code == "ROUND_NOT_PLANNED"


@pytest.mark.asyncio
async def test_start_planned_round_twice_is_rejected(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)
    await start_planned_round(db_session, group)

    with pytest.raises(ApiError) as exc_info:
        await start_planned_round(db_session, group)

    assert exc_info.value.error_code == "ROUND_NOT_PLANNED"


@pytest.mark.asyncio
async def test_round_phase_returns_to_awaiting_plan_once_round_finishes(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)
    updated = await start_planned_round(db_session, group)

    await db_session.execute(
        update(Match)
        .where(Match.group_id == group.id, Match.round_number == 1)
        .values(status="completed")
    )
    await db_session.commit()

    assert await get_round_phase(db_session, updated) == "awaiting_plan"


@pytest.mark.asyncio
async def test_swap_planned_match_players_trades_two_players(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    entries = await _make_entries(db_session, group, 5)
    entry_by_nickname = {e.nickname: e.id for e in entries}

    await plan_next_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.round_number == 1)
    )
    matches = result.scalars().all()

    async def lineup(match_id: object) -> set:
        rows = await db_session.execute(
            select(MatchParticipant.roster_entry_id).where(MatchParticipant.match_id == match_id)
        )
        return set(rows.scalars())

    # Pick two matches that don't already share a player.
    match_a, match_b = None, None
    for i, m1 in enumerate(matches):
        for m2 in matches[i + 1 :]:
            lineup_1, lineup_2 = await lineup(m1.id), await lineup(m2.id)
            if not (lineup_1 & lineup_2):
                match_a, match_b = m1, m2
                break
        if match_a is not None:
            break
    assert match_a is not None and match_b is not None

    lineup_a_before = await lineup(match_a.id)
    lineup_b_before = await lineup(match_b.id)
    player_from_a = next(iter(lineup_a_before))
    player_from_b = next(iter(lineup_b_before))

    await swap_planned_match_players(
        db_session, group, match_a.id, player_from_a, match_b.id, player_from_b
    )

    lineup_a_after = await lineup(match_a.id)
    lineup_b_after = await lineup(match_b.id)
    assert lineup_a_after == (lineup_a_before - {player_from_a}) | {player_from_b}
    assert lineup_b_after == (lineup_b_before - {player_from_b}) | {player_from_a}
    del entry_by_nickname  # only used to keep nicknames reachable for debugging


@pytest.mark.asyncio
async def test_swap_is_allowed_once_round_has_started_for_unfinished_matches(
    db_session: AsyncSession,
) -> None:
    """Follow-up to 018-plan-then-start: the admin also needs to swap
    players mid-round (e.g. an injury substitution), for any of its matches
    that haven't finished yet — not just while still `awaiting_start`."""
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)
    await start_planned_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.round_number == 1)
    )
    matches = result.scalars().all()

    async def first_participant(match_id: object) -> object:
        rows = await db_session.execute(
            select(MatchParticipant.roster_entry_id).where(MatchParticipant.match_id == match_id)
        )
        return rows.scalars().first()

    async def lineup(match_id: object) -> set:
        rows = await db_session.execute(
            select(MatchParticipant.roster_entry_id).where(MatchParticipant.match_id == match_id)
        )
        return set(rows.scalars())

    # Round is now 'in_progress' — pick two matches that don't share a
    # player and are both still unfinished (queued or in_progress).
    match_a, match_b = None, None
    for i, m1 in enumerate(matches):
        for m2 in matches[i + 1 :]:
            lineup_1, lineup_2 = await lineup(m1.id), await lineup(m2.id)
            if not (lineup_1 & lineup_2):
                match_a, match_b = m1, m2
                break
        if match_a is not None:
            break
    assert match_a is not None and match_b is not None

    player_from_a = await first_participant(match_a.id)
    player_from_b = await first_participant(match_b.id)

    await swap_planned_match_players(
        db_session, group, match_a.id, player_from_a, match_b.id, player_from_b
    )

    lineup_a_after = await lineup(match_a.id)
    lineup_b_after = await lineup(match_b.id)
    assert player_from_b in lineup_a_after
    assert player_from_a in lineup_b_after


@pytest.mark.asyncio
async def test_swap_rejects_when_a_match_has_already_ended(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)
    await start_planned_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.round_number == 1)
    )
    matches = result.scalars().all()
    ended_match, other_match = matches[0], matches[1]

    await db_session.execute(
        update(Match).where(Match.id == ended_match.id).values(status="completed")
    )
    await db_session.commit()

    async def first_participant(match_id: object) -> object:
        rows = await db_session.execute(
            select(MatchParticipant.roster_entry_id).where(MatchParticipant.match_id == match_id)
        )
        return rows.scalars().first()

    player_from_ended = await first_participant(ended_match.id)
    player_from_other = await first_participant(other_match.id)

    with pytest.raises(ApiError) as exc_info:
        await swap_planned_match_players(
            db_session,
            group,
            ended_match.id,
            player_from_ended,
            other_match.id,
            player_from_other,
        )

    assert exc_info.value.error_code == "MATCH_ALREADY_ENDED"


@pytest.mark.asyncio
async def test_swap_rejects_when_it_would_duplicate_a_participant(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.round_number == 1)
    )
    matches = result.scalars().all()

    async def lineup(match_id: object) -> set:
        rows = await db_session.execute(
            select(MatchParticipant.roster_entry_id).where(MatchParticipant.match_id == match_id)
        )
        return set(rows.scalars())

    # Round-robin singles: every player appears in several matches at once,
    # so two matches sharing exactly one player always exist.
    match_a, match_b, shared_player = None, None, None
    for i, m1 in enumerate(matches):
        for m2 in matches[i + 1 :]:
            lineup_1, lineup_2 = await lineup(m1.id), await lineup(m2.id)
            overlap = lineup_1 & lineup_2
            if len(overlap) == 1:
                match_a, match_b, shared_player = m1, m2, next(iter(overlap))
                break
        if match_a is not None:
            break
    assert match_a is not None and match_b is not None

    lineup_a = await lineup(match_a.id)
    other_in_a = next(iter(lineup_a - {shared_player}))

    with pytest.raises(ApiError) as exc_info:
        # Moving `other_in_a` into match_b would leave match_b with
        # `shared_player` twice (it's already there).
        await swap_planned_match_players(
            db_session, group, match_a.id, other_in_a, match_b.id, shared_player
        )

    assert exc_info.value.error_code == "DUPLICATE_PARTICIPANT"


@pytest.mark.asyncio
async def test_manual_mode_next_round_is_unaffected(db_session: AsyncSession) -> None:
    """018-plan-then-start MUST NOT change manual mode's existing
    single-button behavior — generate_next_round() still fully advances it
    in one call, with no plan/start split."""
    group = await _make_group(db_session, scheduling_mechanism="manual")
    await _make_court(db_session, group)

    updated = await generate_next_round(db_session, group)

    assert updated.current_round_number == 1
    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.round_number == 1)
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_end_current_round_abandons_without_bumping_round_number(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)
    await start_planned_round(db_session, group)

    updated = await end_current_round(db_session, group)

    assert updated.current_round_number == 1  # unchanged — no new round yet
    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.round_number == 1)
    )
    matches = result.scalars().all()
    assert len(matches) == math.comb(5, 2)
    assert all(m.status == "abandoned" for m in matches)
    assert await get_round_phase(db_session, updated) == "awaiting_plan"


@pytest.mark.asyncio
async def test_end_current_round_rejects_manual_mode(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, scheduling_mechanism="manual")
    await _make_court(db_session, group)

    with pytest.raises(ApiError) as exc_info:
        await end_current_round(db_session, group)

    assert exc_info.value.error_code == "SCHEDULING_MECHANISM_MISMATCH"


@pytest.mark.asyncio
async def test_end_current_round_rejects_when_nothing_is_in_progress(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)

    with pytest.raises(ApiError) as exc_info:
        await end_current_round(db_session, group)

    assert exc_info.value.error_code == "ROUND_NOT_IN_PROGRESS"


@pytest.mark.asyncio
async def test_end_then_plan_then_start_full_cycle_bumps_round_number_once(
    db_session: AsyncSession,
) -> None:
    """The round number MUST only bump at plan_next_round() — end_current_
    round() ending an unfinished round 1 and then planning round 2 must not
    double-bump or skip a round number."""
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)
    await start_planned_round(db_session, group)
    await end_current_round(db_session, group)
    updated = await plan_next_round(db_session, group)

    assert updated.current_round_number == 2


@pytest.mark.asyncio
async def test_reorder_planned_matches_changes_call_up_order(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)

    result = await db_session.execute(
        select(Match.id)
        .where(Match.group_id == group.id, Match.round_number == 1)
        .order_by(Match.created_at)
    )
    original_order = list(result.scalars())
    new_order = list(reversed(original_order))

    await reorder_planned_matches(db_session, group, new_order)

    result = await db_session.execute(
        select(Match.id)
        .where(Match.group_id == group.id, Match.round_number == 1)
        .order_by(Match.created_at)
    )
    assert list(result.scalars()) == new_order


@pytest.mark.asyncio
async def test_reorder_planned_matches_rejects_non_permutation(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)

    result = await db_session.execute(
        select(Match.id).where(Match.group_id == group.id, Match.round_number == 1)
    )
    match_ids = list(result.scalars())

    with pytest.raises(ApiError) as exc_info:
        await reorder_planned_matches(db_session, group, match_ids[:-1])  # missing one match

    assert exc_info.value.error_code == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_reorder_is_allowed_once_round_has_started_for_still_queued_matches(
    db_session: AsyncSession,
) -> None:
    """Follow-up to 018-plan-then-start: once a round is under way, matches
    that haven't been pulled onto a court yet still have a meaningful
    call-up order — the admin should still be able to drag-reorder them."""
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)
    await start_planned_round(db_session, group)

    result = await db_session.execute(
        select(Match.id).where(
            Match.group_id == group.id, Match.round_number == 1, Match.status == "queued"
        )
    )
    queued_ids = list(result.scalars())
    assert len(queued_ids) == math.comb(5, 2) - 1  # one court -> one match pulled

    new_order = list(reversed(queued_ids))
    await reorder_planned_matches(db_session, group, new_order)

    result = await db_session.execute(
        select(Match.id)
        .where(Match.group_id == group.id, Match.round_number == 1, Match.status == "queued")
        .order_by(Match.created_at)
    )
    assert list(result.scalars()) == new_order


@pytest.mark.asyncio
async def test_reorder_rejects_when_a_stale_id_is_no_longer_queued(
    db_session: AsyncSession,
) -> None:
    """The permutation check must be against the CURRENT queued set — an id
    for a match that has since been pulled onto a court (or the caller
    simply omitting one that's still queued) is rejected, not silently
    dropped."""
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)
    result = await db_session.execute(
        select(Match.id).where(Match.group_id == group.id, Match.round_number == 1)
    )
    all_ids_before_start = list(result.scalars())
    await start_planned_round(db_session, group)

    with pytest.raises(ApiError) as exc_info:
        # This is last round's full set, including the one now-in_progress
        # match — no longer a valid permutation of the queued subset.
        await reorder_planned_matches(db_session, group, all_ids_before_start)

    assert exc_info.value.error_code == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_reorder_rejects_when_nothing_is_queued(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)

    with pytest.raises(ApiError) as exc_info:
        await reorder_planned_matches(db_session, group, [])

    assert exc_info.value.error_code == "ROUND_NOT_PLANNED"


@pytest.mark.asyncio
async def test_reorder_planned_matches_rejects_manual_mode(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, scheduling_mechanism="manual")
    await _make_court(db_session, group)

    with pytest.raises(ApiError) as exc_info:
        await reorder_planned_matches(db_session, group, [])

    assert exc_info.value.error_code == "SCHEDULING_MECHANISM_MISMATCH"


async def _lineup(session: AsyncSession, match_id: object) -> set:
    rows = await session.execute(
        select(MatchParticipant.roster_entry_id).where(MatchParticipant.match_id == match_id)
    )
    return set(rows.scalars())


@pytest.mark.asyncio
async def test_change_match_player_replaces_participant_on_in_progress_match(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    entries = await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)
    await start_planned_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(
            Match.group_id == group.id, Match.round_number == 1, Match.status == "in_progress"
        )
    )
    live_match = result.scalars().one()
    live_lineup = await _lineup(db_session, live_match.id)
    old_player = next(iter(live_lineup))
    # Anyone active and not already in this specific match is a valid
    # substitute for a live match (busy-elsewhere is the only other check).
    new_player = next(e.id for e in entries if e.id not in live_lineup)

    await change_match_player(db_session, group, live_match.id, old_player, new_player)

    updated_lineup = await _lineup(db_session, live_match.id)
    assert old_player not in updated_lineup
    assert new_player in updated_lineup


@pytest.mark.asyncio
async def test_change_match_player_rejects_new_player_busy_on_another_live_match(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group, "1號場")
    await _make_court(db_session, group, "2號場")
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)
    await start_planned_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(
            Match.group_id == group.id, Match.round_number == 1, Match.status == "in_progress"
        )
    )
    live_matches = result.scalars().all()
    assert len(live_matches) == 2  # two courts -> two live matches
    match_1, match_2 = live_matches
    old_player = next(iter(await _lineup(db_session, match_1.id)))
    busy_player = next(iter(await _lineup(db_session, match_2.id)))

    with pytest.raises(ApiError) as exc_info:
        await change_match_player(db_session, group, match_1.id, old_player, busy_player)

    assert exc_info.value.error_code == "PARTICIPANT_ALREADY_PLAYING"


@pytest.mark.asyncio
async def test_change_match_player_allows_a_currently_playing_substitute_into_a_queued_match(
    db_session: AsyncSession,
) -> None:
    """A round-robin schedule already routinely lists the same person in
    several queued matches at once (only one gets pulled onto a court) —
    so a queued match's substitute doesn't need the busy-elsewhere check
    that a live match does."""
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)
    await start_planned_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(
            Match.group_id == group.id, Match.round_number == 1, Match.status == "in_progress"
        )
    )
    live_match = result.scalars().one()
    busy_player = next(iter(await _lineup(db_session, live_match.id)))

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.status == "queued")
    )
    queued_matches = result.scalars().all()
    target_match = None
    for candidate in queued_matches:
        if busy_player not in (await _lineup(db_session, candidate.id)):
            target_match = candidate
            break
    assert target_match is not None
    old_player = next(iter(await _lineup(db_session, target_match.id)))

    await change_match_player(db_session, group, target_match.id, old_player, busy_player)

    updated_lineup = await _lineup(db_session, target_match.id)
    assert busy_player in updated_lineup


@pytest.mark.asyncio
async def test_change_match_player_rejects_duplicate_within_match(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.round_number == 1)
    )
    match = result.scalars().first()
    lineup = await _lineup(db_session, match.id)
    old_player, other_player = list(lineup)

    with pytest.raises(ApiError) as exc_info:
        await change_match_player(db_session, group, match.id, old_player, other_player)

    assert exc_info.value.error_code == "DUPLICATE_PARTICIPANT"


@pytest.mark.asyncio
async def test_change_match_player_rejects_inactive_roster_member(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    entries = await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.round_number == 1)
    )
    match = result.scalars().first()
    old_player = next(iter(await _lineup(db_session, match.id)))
    inactive_player = next(e for e in entries if e.id != old_player)
    inactive_player.status = "left"
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await change_match_player(db_session, group, match.id, old_player, inactive_player.id)

    assert exc_info.value.error_code == "PARTICIPANT_NOT_ACTIVE"


@pytest.mark.asyncio
async def test_change_match_player_rejects_when_match_already_ended(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    await _make_court(db_session, group)
    entries = await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.round_number == 1)
    )
    match = result.scalars().first()
    old_player = next(iter(await _lineup(db_session, match.id)))
    new_player = next(e.id for e in entries if e.id != old_player)

    await db_session.execute(
        update(Match).where(Match.id == match.id).values(status="completed")
    )
    await db_session.commit()

    with pytest.raises(ApiError) as exc_info:
        await change_match_player(db_session, group, match.id, old_player, new_player)

    assert exc_info.value.error_code == "MATCH_ALREADY_ENDED"


@pytest.mark.asyncio
async def test_change_match_player_rejects_manual_mode(db_session: AsyncSession) -> None:
    group = await _make_group(db_session, scheduling_mechanism="manual")
    await _make_court(db_session, group)

    with pytest.raises(ApiError) as exc_info:
        await change_match_player(db_session, group, uuid.uuid4(), uuid.uuid4(), uuid.uuid4())

    assert exc_info.value.error_code == "SCHEDULING_MECHANISM_MISMATCH"


def _patch_publish(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict]]:
    """018-plan-then-start follow-up: records every `publish()` call made by
    the schedule service, so tests can assert a scoreboard/control panel
    would actually be notified — without this, a swap/change/reorder
    silently not notifying anyone would still pass every other test."""
    calls: list[tuple[str, str, dict]] = []

    async def fake_publish(channel: str, event: str, payload: dict) -> None:
        calls.append((channel, event, payload))

    monkeypatch.setattr("app.domains.schedule.service.publish", fake_publish)
    return calls


@pytest.mark.asyncio
async def test_swap_on_live_match_publishes_rotation_updated_to_its_court(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)
    await start_planned_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(
            Match.group_id == group.id, Match.round_number == 1, Match.status == "in_progress"
        )
    )
    live_match = result.scalars().one()
    lineup = await _lineup(db_session, live_match.id)

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.status == "queued")
    )
    queued = result.scalars().all()
    # Pick a queued match with NO overlap with live_match's lineup — a
    # partial-overlap pick (Postgres row order is otherwise unspecified)
    # can make the chosen swap collide with the untouched participant
    # already sitting in the other match, raising DUPLICATE_PARTICIPANT.
    other_queued = None
    for candidate in queued:
        candidate_lineup = await _lineup(db_session, candidate.id)
        if not (candidate_lineup & lineup):
            other_queued = candidate
            other_lineup = candidate_lineup
            break
    assert other_queued is not None
    swap_target = next(iter(other_lineup))

    calls = _patch_publish(monkeypatch)
    await swap_planned_match_players(
        db_session,
        group,
        live_match.id,
        next(iter(lineup)),
        other_queued.id,
        swap_target,
    )

    rotation_calls = [c for c in calls if c[1] == "rotation.updated"]
    assert len(rotation_calls) == 1
    channel, _, payload = rotation_calls[0]
    assert channel == f"court:{group.id}:{court.id}"
    assert payload["match_id"] == str(live_match.id)


@pytest.mark.asyncio
async def test_swap_between_two_queued_matches_broadcasts_next_round_to_all_courts(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    group = await _make_group(db_session)
    court_1 = await _make_court(db_session, group, "1號場")
    court_2 = await _make_court(db_session, group, "2號場")
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)
    await start_planned_round(db_session, group)

    result = await db_session.execute(
        select(Match).where(Match.group_id == group.id, Match.status == "queued")
    )
    queued = result.scalars().all()

    match_a, match_b = None, None
    for i, m1 in enumerate(queued):
        for m2 in queued[i + 1 :]:
            lineup_1, lineup_2 = await _lineup(db_session, m1.id), await _lineup(db_session, m2.id)
            if not (lineup_1 & lineup_2):
                match_a, match_b = m1, m2
                break
        if match_a is not None:
            break
    assert match_a is not None and match_b is not None

    player_a = next(iter(await _lineup(db_session, match_a.id)))
    player_b = next(iter(await _lineup(db_session, match_b.id)))

    calls = _patch_publish(monkeypatch)
    await swap_planned_match_players(db_session, group, match_a.id, player_a, match_b.id, player_b)

    next_round_channels = {c[0] for c in calls if c[1] == "match.nextRound"}
    assert next_round_channels == {
        f"court:{group.id}:{court_1.id}",
        f"court:{group.id}:{court_2.id}",
    }
    assert not any(c[1] == "rotation.updated" for c in calls)


@pytest.mark.asyncio
async def test_reorder_broadcasts_next_round_to_all_courts(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    group = await _make_group(db_session)
    court = await _make_court(db_session, group)
    await _make_entries(db_session, group, 5)

    await plan_next_round(db_session, group)
    result = await db_session.execute(
        select(Match.id).where(Match.group_id == group.id, Match.round_number == 1)
    )
    match_ids = list(result.scalars())

    calls = _patch_publish(monkeypatch)
    await reorder_planned_matches(db_session, group, list(reversed(match_ids)))

    assert calls == [
        (f"court:{group.id}:{court.id}", "match.nextRound", {"round_number": 1}),
    ]
