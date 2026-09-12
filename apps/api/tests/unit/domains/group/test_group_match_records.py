"""Unit test: build_group_match_records() — only completed matches, sorted
newest-round-first, scoped to one group (005-member-view US3, FR-011/012)."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import build_group_match_records
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Match Records Test",
        max_members=8,
        match_mode="singles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_entry(session: AsyncSession, group: Group, nickname: str) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname=nickname, status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def _make_match(
    session: AsyncSession,
    group: Group,
    *,
    round_number: int,
    status: str,
    winner_team: str | None,
    team_a: list[uuid.UUID],
    team_b: list[uuid.UUID],
    ended_at: datetime | None = None,
) -> Match:
    match = Match(
        group_id=group.id,
        court_id=None,
        round_number=round_number,
        status=status,
        winner_team=winner_team,
        score_a=11 if winner_team == "A" else 5,
        score_b=11 if winner_team == "B" else 5,
        target_score=21,
        deuce_threshold=20,
        cap_score=30,
        ended_at=ended_at,
    )
    session.add(match)
    await session.flush()
    for pid in team_a:
        session.add(MatchParticipant(match_id=match.id, roster_entry_id=pid, team="A"))
    for pid in team_b:
        session.add(MatchParticipant(match_id=match.id, roster_entry_id=pid, team="B"))
    await session.commit()
    return match


async def test_only_completed_matches_included(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "A")
    b = await _make_entry(db_session, group, "B")

    completed = await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="A",
        team_a=[a.id], team_b=[b.id],
    )
    await _make_match(
        db_session, group, round_number=2, status="abandoned", winner_team=None,
        team_a=[a.id], team_b=[b.id],
    )
    await _make_match(
        db_session, group, round_number=2, status="queued", winner_team=None,
        team_a=[a.id], team_b=[b.id],
    )
    await _make_match(
        db_session, group, round_number=2, status="in_progress", winner_team=None,
        team_a=[a.id], team_b=[b.id],
    )

    response = await build_group_match_records(db_session, group.id)

    assert [m.match_id for m in response.matches] == [str(completed.id)]
    assert response.matches[0].winner_team == "A"
    assert response.matches[0].team_a[0].nickname == "A"


async def test_sorted_newest_round_first(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "A")
    b = await _make_entry(db_session, group, "B")

    m2 = await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="A",
        team_a=[a.id], team_b=[b.id],
    )
    m3 = await _make_match(
        db_session, group, round_number=3, status="completed", winner_team="B",
        team_a=[a.id], team_b=[b.id],
    )

    response = await build_group_match_records(db_session, group.id)

    assert [m.match_id for m in response.matches] == [str(m3.id), str(m2.id)]


async def test_scope_isolation_excludes_other_groups(db_session: AsyncSession) -> None:
    group_a = await _make_group(db_session)
    group_b = await _make_group(db_session)
    a1 = await _make_entry(db_session, group_a, "A1")
    a2 = await _make_entry(db_session, group_a, "A2")
    b1 = await _make_entry(db_session, group_b, "B1")
    b2 = await _make_entry(db_session, group_b, "B2")

    match_a = await _make_match(
        db_session, group_a, round_number=2, status="completed", winner_team="A",
        team_a=[a1.id], team_b=[a2.id],
    )
    await _make_match(
        db_session, group_b, round_number=2, status="completed", winner_team="A",
        team_a=[b1.id], team_b=[b2.id],
    )

    response = await build_group_match_records(db_session, group_a.id)

    assert [m.match_id for m in response.matches] == [str(match_a.id)]


async def test_group_names_match_regardless_of_which_literal_team_each_group_landed_on(
    db_session: AsyncSession,
) -> None:
    """Alice+Bob vs Carol+Dave, stored with Alice+Bob as team A. Searching
    group1=[Alice,Bob] vs group2=[Carol,Dave] MUST match, and so MUST the
    reverse (group1=[Carol,Dave] vs group2=[Alice,Bob]) — which literal
    on-court team (A/B) anyone landed on is an implementation detail the
    viewer can't see and shouldn't need to guess."""
    group = await _make_group(db_session)
    alice = await _make_entry(db_session, group, "Alice")
    bob = await _make_entry(db_session, group, "Bob")
    carol = await _make_entry(db_session, group, "Carol")
    dave = await _make_entry(db_session, group, "Dave")
    match = await _make_match(
        db_session, group, round_number=1, status="completed", winner_team="A",
        team_a=[alice.id, bob.id], team_b=[carol.id, dave.id],
    )

    as_stored = await build_group_match_records(
        db_session, group.id, group1_names=["Alice", "Bob"], group2_names=["Carol", "Dave"]
    )
    assert [m.match_id for m in as_stored.matches] == [str(match.id)]

    reversed_order = await build_group_match_records(
        db_session, group.id, group1_names=["Carol", "Dave"], group2_names=["Alice", "Bob"]
    )
    assert [m.match_id for m in reversed_order.matches] == [str(match.id)]

    # Mixing one person from each side into the same group must not match —
    # Alice and Carol never played on the same side.
    mixed_sides = await build_group_match_records(
        db_session, group.id, group1_names=["Alice", "Carol"], group2_names=["Bob", "Dave"]
    )
    assert mixed_sides.matches == []


async def test_group_names_with_only_one_group_filled_means_teammates_on_either_side(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    alice = await _make_entry(db_session, group, "Alice")
    bob = await _make_entry(db_session, group, "Bob")
    carol = await _make_entry(db_session, group, "Carol")
    dave = await _make_entry(db_session, group, "Dave")
    match = await _make_match(
        db_session, group, round_number=1, status="completed", winner_team="A",
        team_a=[alice.id, bob.id], team_b=[carol.id, dave.id],
    )

    group1_only = await build_group_match_records(
        db_session, group.id, group1_names=["Alice", "Bob"]
    )
    assert [m.match_id for m in group1_only.matches] == [str(match.id)]

    group2_only = await build_group_match_records(
        db_session, group.id, group2_names=["Carol", "Dave"]
    )
    assert [m.match_id for m in group2_only.matches] == [str(match.id)]

    # Alice and Carol were never teammates (opposite sides) — no match.
    not_teammates = await build_group_match_records(
        db_session, group.id, group1_names=["Alice", "Carol"]
    )
    assert not_teammates.matches == []


async def test_player_records_tallies_wins_and_losses_across_every_player(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    alice = await _make_entry(db_session, group, "Alice")
    bob = await _make_entry(db_session, group, "Bob")
    carol = await _make_entry(db_session, group, "Carol")
    # Round 1: Alice beats Bob. Round 2: Alice beats Carol.
    await _make_match(
        db_session, group, round_number=1, status="completed", winner_team="A",
        team_a=[alice.id], team_b=[bob.id],
    )
    await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="A",
        team_a=[alice.id], team_b=[carol.id],
    )

    response = await build_group_match_records(db_session, group.id)

    records = {r.nickname: r for r in response.player_records}
    assert records["Alice"].wins == 2
    assert records["Alice"].losses == 0
    assert records["Alice"].win_rate == 1.0
    assert records["Bob"].wins == 0
    assert records["Bob"].losses == 1
    assert records["Carol"].wins == 0
    assert records["Carol"].losses == 1
    # Sorted by total matches played, descending.
    assert [r.nickname for r in response.player_records][0] == "Alice"


async def test_player_records_reflects_the_active_filters_not_the_whole_group(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    alice = await _make_entry(db_session, group, "Alice")
    bob = await _make_entry(db_session, group, "Bob")
    await _make_match(
        db_session, group, round_number=1, status="completed", winner_team="A",
        team_a=[alice.id], team_b=[bob.id],
    )
    await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="B",
        team_a=[alice.id], team_b=[bob.id],
    )

    round_1_only = await build_group_match_records(
        db_session, group.id, round_from=1, round_to=1
    )

    records = {r.nickname: r for r in round_1_only.player_records}
    assert records["Alice"].wins == 1
    assert records["Alice"].losses == 0
    assert records["Bob"].wins == 0
    assert records["Bob"].losses == 1


async def test_score_a_and_score_b_comparisons(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "A")
    b = await _make_entry(db_session, group, "B")
    match = Match(
        group_id=group.id,
        court_id=None,
        round_number=1,
        status="completed",
        winner_team="A",
        score_a=21,
        score_b=15,
        target_score=21,
        deuce_threshold=20,
        cap_score=30,
    )
    db_session.add(match)
    await db_session.flush()
    db_session.add(MatchParticipant(match_id=match.id, roster_entry_id=a.id, team="A"))
    db_session.add(MatchParticipant(match_id=match.id, roster_entry_id=b.id, team="B"))
    await db_session.commit()

    gt_match = await build_group_match_records(
        db_session, group.id, score_a_cmp="gt", score_a=20
    )
    assert [m.match_id for m in gt_match.matches] == [str(match.id)]

    gt_no_match = await build_group_match_records(
        db_session, group.id, score_a_cmp="gt", score_a=21
    )
    assert gt_no_match.matches == []

    eq_match = await build_group_match_records(
        db_session, group.id, score_b_cmp="eq", score_b=15
    )
    assert [m.match_id for m in eq_match.matches] == [str(match.id)]

    lt_no_match = await build_group_match_records(
        db_session, group.id, score_b_cmp="lt", score_b=15
    )
    assert lt_no_match.matches == []


async def test_round_range_filter_narrows_by_round_number(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    a = await _make_entry(db_session, group, "A")
    b = await _make_entry(db_session, group, "B")

    r1 = await _make_match(
        db_session, group, round_number=1, status="completed", winner_team="A",
        team_a=[a.id], team_b=[b.id],
    )
    r2 = await _make_match(
        db_session, group, round_number=2, status="completed", winner_team="A",
        team_a=[a.id], team_b=[b.id],
    )
    r3 = await _make_match(
        db_session, group, round_number=3, status="completed", winner_team="A",
        team_a=[a.id], team_b=[b.id],
    )

    response = await build_group_match_records(
        db_session, group.id, round_from=2, round_to=2
    )

    assert [m.match_id for m in response.matches] == [str(r2.id)]
    assert str(r1.id) not in [m.match_id for m in response.matches]
    assert str(r3.id) not in [m.match_id for m in response.matches]
