"""037-rest-ready-toggle US1 (FR-006, FR-009, FR-011, FR-034): a resting
player is left out of every newly generated round, whatever the scheduling
mechanism, while formal partnerships keep including them."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.schedule.models import Match, Partnership
from app.domains.schedule.service import (
    auto_pair_on_enter_fixed_partner,
    build_round_matches_list,
    end_current_round,
    handle_member_joined,
    plan_next_round,
    preview_random_partner_pairing,
    start_planned_round,
)
from app.domains.roster.models import RosterEntry
from tests.unit.domains.schedule._rest_helpers import (
    make_courts,
    make_group,
    make_players,
    participants,
    round_matches,
    set_resting,
)


async def _everyone_scheduled(session: AsyncSession, matches: list[Match]) -> set[object]:
    ids: set[object] = set()
    for match in matches:
        ids |= await participants(session, match.id)
    return ids


@pytest.mark.asyncio
async def test_fair_rotation_doubles_leaves_the_resting_player_out(
    db_session: AsyncSession,
) -> None:
    group = await make_group(db_session, match_mode="doubles", scheduling_mechanism="fair_rotation")
    await make_courts(db_session, group, 2)
    players = await make_players(db_session, group, 9)
    await set_resting(db_session, players[0])

    await plan_next_round(db_session, group)

    matches = await round_matches(db_session, group)
    assert len(matches) == 2
    scheduled = await _everyone_scheduled(db_session, matches)
    assert players[0].id not in scheduled
    assert scheduled == {p.id for p in players[1:]}


@pytest.mark.asyncio
async def test_singles_round_robin_is_built_from_ready_players_only(
    db_session: AsyncSession,
) -> None:
    group = await make_group(db_session, match_mode="singles", scheduling_mechanism="fair_rotation")
    await make_courts(db_session, group, 2)
    players = await make_players(db_session, group, 5)
    await set_resting(db_session, players[2])

    await plan_next_round(db_session, group)

    matches = await round_matches(db_session, group)
    assert len(matches) == 6  # 4 players, everyone once
    assert players[2].id not in await _everyone_scheduled(db_session, matches)


@pytest.mark.asyncio
async def test_individual_mixed_leaves_the_resting_player_out(db_session: AsyncSession) -> None:
    group = await make_group(
        db_session, match_mode="doubles", scheduling_mechanism="individual_mixed"
    )
    await make_courts(db_session, group, 2)
    players = await make_players(db_session, group, 6)
    await set_resting(db_session, players[5])

    await plan_next_round(db_session, group)

    matches = await round_matches(db_session, group)
    assert matches
    assert players[5].id not in await _everyone_scheduled(db_session, matches)


@pytest.mark.asyncio
async def test_fixed_partner_auto_teams_are_formed_from_ready_players(
    db_session: AsyncSession,
) -> None:
    group = await make_group(
        db_session, match_mode="doubles", scheduling_mechanism="fixed_partner", partner_source="auto"
    )
    await make_courts(db_session, group, 2)
    players = await make_players(db_session, group, 8)
    await set_resting(db_session, players[3])

    await plan_next_round(db_session, group)

    matches = await round_matches(db_session, group)
    scheduled = await _everyone_scheduled(db_session, matches)
    assert players[3].id not in scheduled
    assert len(scheduled) == 6  # 7 ready: three teams, one bye
    assert len(matches) == 3


@pytest.mark.asyncio
async def test_fixed_partner_manual_holds_the_whole_team_and_keeps_the_partner_free(
    db_session: AsyncSession,
) -> None:
    """A rests; B, A's formal partner, must neither play nor be handed to
    someone else by the autofill — otherwise A would come back without a
    partner for the rest of the round (research.md Decision 2)."""
    group = await make_group(
        db_session,
        match_mode="doubles",
        scheduling_mechanism="fixed_partner",
        partner_source="manual",
    )
    await make_courts(db_session, group, 2)
    a, b, *others = await make_players(db_session, group, 7)
    db_session.add(Partnership(group_id=group.id, player_a_id=a.id, player_b_id=b.id))
    await db_session.commit()
    await set_resting(db_session, a)

    await plan_next_round(db_session, group)

    matches = await round_matches(db_session, group)
    scheduled = await _everyone_scheduled(db_session, matches)
    assert a.id not in scheduled
    assert b.id not in scheduled
    # The 5 others: two autofilled teams and one bye. Had B joined the
    # autofill there would have been three teams.
    assert len(scheduled) == 4
    assert scheduled <= {p.id for p in others}


@pytest.mark.asyncio
async def test_too_few_ready_players_generates_nothing(db_session: AsyncSession) -> None:
    group = await make_group(db_session, match_mode="doubles", scheduling_mechanism="fair_rotation")
    await make_courts(db_session, group, 1)
    players = await make_players(db_session, group, 4)
    await set_resting(db_session, players[0])

    await plan_next_round(db_session, group)

    assert await round_matches(db_session, group) == []


@pytest.mark.asyncio
async def test_a_new_round_does_not_end_the_rest(db_session: AsyncSession) -> None:
    group = await make_group(db_session, match_mode="singles", scheduling_mechanism="fair_rotation")
    await make_courts(db_session, group, 1)
    players = await make_players(db_session, group, 4)
    since = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)
    await set_resting(db_session, players[0], since)

    await plan_next_round(db_session, group)
    await start_planned_round(db_session, group)
    await end_current_round(db_session, group)
    await plan_next_round(db_session, group)

    await db_session.refresh(players[0])
    assert players[0].resting_since == since


@pytest.mark.asyncio
async def test_sitting_out_does_not_list_resting_players(db_session: AsyncSession) -> None:
    """They have no match because they chose to rest; listing them as a
    bye would be misread."""
    group = await make_group(db_session, match_mode="doubles", scheduling_mechanism="fair_rotation")
    await make_courts(db_session, group, 1)
    players = await make_players(db_session, group, 6)
    await set_resting(db_session, players[0])

    await plan_next_round(db_session, group)
    listing = await build_round_matches_list(db_session, group)

    sitting_out = {row.roster_entry_id for row in listing.sitting_out}
    assert str(players[0].id) not in sitting_out
    assert len(sitting_out) == 1  # 5 ready, 4 seats


@pytest.mark.asyncio
async def test_switching_to_fixed_partner_still_pairs_a_resting_player(
    db_session: AsyncSession,
) -> None:
    """FR-034: resting only affects who plays next, not who partners whom."""
    group = await make_group(
        db_session,
        match_mode="doubles",
        scheduling_mechanism="fixed_partner",
        partner_source="manual",
    )
    players = await make_players(db_session, group, 4)
    await set_resting(db_session, players[1])

    await auto_pair_on_enter_fixed_partner(db_session, group)
    await db_session.commit()

    rows = (
        await db_session.execute(select(Partnership).where(Partnership.group_id == group.id))
    ).scalars().all()
    paired = {pid for row in rows for pid in (row.player_a_id, row.player_b_id)}
    assert players[1].id in paired
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_a_newcomer_partners_the_only_unpaired_player_even_if_resting(
    db_session: AsyncSession,
) -> None:
    group = await make_group(
        db_session,
        match_mode="doubles",
        scheduling_mechanism="fixed_partner",
        partner_source="manual",
    )
    a, b, c = await make_players(db_session, group, 3)
    db_session.add(Partnership(group_id=group.id, player_a_id=a.id, player_b_id=b.id))
    await db_session.commit()
    await set_resting(db_session, c)

    newcomer = RosterEntry(group_id=group.id, nickname="New", status="active")
    db_session.add(newcomer)
    await db_session.commit()
    await db_session.refresh(newcomer)
    await handle_member_joined(db_session, group, newcomer)
    await db_session.commit()

    rows = (
        await db_session.execute(
            select(Partnership).where(
                Partnership.group_id == group.id, Partnership.player_b_id == newcomer.id
            )
        )
    ).scalars().all()
    assert [row.player_a_id for row in rows] == [c.id]


@pytest.mark.asyncio
async def test_the_round_pairing_preview_leaves_resting_players_out(
    db_session: AsyncSession,
) -> None:
    """017's preview is this round's temporary pairing — who plays — so,
    unlike formal partnerships, it only draws on ready players."""
    group = await make_group(
        db_session,
        match_mode="doubles",
        scheduling_mechanism="fixed_partner",
        partner_source="manual",
    )
    players = await make_players(db_session, group, 5)
    await set_resting(db_session, players[4])

    preview = await preview_random_partner_pairing(db_session, group)

    shown = {
        pid
        for pairing in preview.pairings
        for pid in (pairing.player_a.roster_entry_id, pairing.player_b.roster_entry_id)
    }
    assert str(players[4].id) not in shown
    assert len(preview.pairings) == 2
