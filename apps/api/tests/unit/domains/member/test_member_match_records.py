"""Unit test: build_member_match_records() — aggregates a member's
completed matches across all their groups, excludes any Guest-era match
even after the same person later registers (005-member-view US5,
research.md #9), and never divides by zero (FR-018)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.member.models import Member
from app.domains.member.service import build_member_match_records
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, name: str) -> Group:
    group = Group(
        name=name,
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


async def _make_member(session: AsyncSession, email: str) -> Member:
    member = Member(
        email=email,
        password_hash="x",
        nickname="小明",
        user_number=str(uuid.uuid4())[:8],
        verification_status="verified",
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def _make_entry(
    session: AsyncSession, group: Group, nickname: str, member_id: uuid.UUID | None
) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname=nickname, member_id=member_id, status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def _make_completed_match(
    session: AsyncSession,
    group: Group,
    *,
    round_number: int,
    winner_team: str,
    team_a: list[uuid.UUID],
    team_b: list[uuid.UUID],
) -> Match:
    match = Match(
        group_id=group.id,
        court_id=None,
        round_number=round_number,
        status="completed",
        winner_team=winner_team,
        score_a=11,
        score_b=5,
        target_score=21,
        deuce_threshold=20,
        cap_score=30,
    )
    session.add(match)
    await session.flush()
    for pid in team_a:
        session.add(MatchParticipant(match_id=match.id, roster_entry_id=pid, team="A"))
    for pid in team_b:
        session.add(MatchParticipant(match_id=match.id, roster_entry_id=pid, team="B"))
    await session.commit()
    return match


async def test_aggregates_across_multiple_groups(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "cross-group@example.com")
    group_a = await _make_group(db_session, "Group A")
    group_b = await _make_group(db_session, "Group B")

    my_entry_a = await _make_entry(db_session, group_a, "小明", member.id)
    opp_a = await _make_entry(db_session, group_a, "對手A", None)
    await _make_completed_match(
        db_session, group_a, round_number=2, winner_team="A",
        team_a=[my_entry_a.id], team_b=[opp_a.id],
    )

    my_entry_b = await _make_entry(db_session, group_b, "小明", member.id)
    opp_b = await _make_entry(db_session, group_b, "對手B", None)
    await _make_completed_match(
        db_session, group_b, round_number=2, winner_team="B",
        team_a=[my_entry_b.id], team_b=[opp_b.id],
    )

    response = await build_member_match_records(db_session, member.id)

    assert response.total_matches == 2
    assert response.total_wins == 1
    assert response.total_losses == 1
    assert {m.group_name for m in response.matches} == {"Group A", "Group B"}


async def test_win_rate_zero_when_no_matches(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "no-matches@example.com")

    response = await build_member_match_records(db_session, member.id)

    assert response.total_matches == 0
    assert response.win_rate == 0.0


async def test_filters_by_result(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "filter-result@example.com")
    group = await _make_group(db_session, "Filter Group")
    me = await _make_entry(db_session, group, "小明", member.id)
    opp1 = await _make_entry(db_session, group, "對手1", None)
    opp2 = await _make_entry(db_session, group, "對手2", None)
    await _make_completed_match(
        db_session, group, round_number=1, winner_team="A", team_a=[me.id], team_b=[opp1.id]
    )
    await _make_completed_match(
        db_session, group, round_number=2, winner_team="B", team_a=[me.id], team_b=[opp2.id]
    )

    wins_only = await build_member_match_records(db_session, member.id, result="win")
    assert wins_only.total_matches == 1
    assert wins_only.matches[0].round_number == 1

    losses_only = await build_member_match_records(db_session, member.id, result="loss")
    assert losses_only.total_matches == 1
    assert losses_only.matches[0].round_number == 2


async def test_filters_by_opponent_nickname(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "filter-opponent@example.com")
    group = await _make_group(db_session, "Filter Group 2")
    me = await _make_entry(db_session, group, "小明", member.id)
    opp1 = await _make_entry(db_session, group, "阿強", None)
    opp2 = await _make_entry(db_session, group, "小美", None)
    await _make_completed_match(
        db_session, group, round_number=1, winner_team="A", team_a=[me.id], team_b=[opp1.id]
    )
    await _make_completed_match(
        db_session, group, round_number=2, winner_team="A", team_a=[me.id], team_b=[opp2.id]
    )

    response = await build_member_match_records(db_session, member.id, opponent_or_partner="阿強")

    assert response.total_matches == 1
    assert response.matches[0].team_b[0].nickname == "阿強"


async def test_filters_by_round_range(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "filter-round@example.com")
    group = await _make_group(db_session, "Filter Group 3")
    me = await _make_entry(db_session, group, "小明", member.id)
    opp = await _make_entry(db_session, group, "對手", None)
    for round_number in (1, 2, 3):
        await _make_completed_match(
            db_session, group, round_number=round_number, winner_team="A",
            team_a=[me.id], team_b=[opp.id],
        )

    response = await build_member_match_records(
        db_session, member.id, round_from=2, round_to=3
    )

    assert response.total_matches == 2
    assert {m.round_number for m in response.matches} == {2, 3}


async def test_filters_by_score_comparison(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "filter-score@example.com")
    group = await _make_group(db_session, "Filter Group 4")
    me = await _make_entry(db_session, group, "小明", member.id)
    opp = await _make_entry(db_session, group, "對手", None)
    # _make_completed_match always sets score_a=11, score_b=5.
    await _make_completed_match(
        db_session, group, round_number=1, winner_team="A", team_a=[me.id], team_b=[opp.id]
    )
    await _make_completed_match(
        db_session, group, round_number=2, winner_team="B", team_a=[opp.id], team_b=[me.id]
    )

    self_ahead = await build_member_match_records(db_session, member.id, score_cmp="gt")
    assert self_ahead.total_matches == 1
    assert self_ahead.matches[0].round_number == 1

    self_behind = await build_member_match_records(db_session, member.id, score_cmp="lt")
    assert self_behind.total_matches == 1
    assert self_behind.matches[0].round_number == 2


async def test_round_win_rates_and_opponent_records(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "aggregates@example.com")
    group = await _make_group(db_session, "Aggregates Group")
    me = await _make_entry(db_session, group, "小明", member.id)
    opp1 = await _make_entry(db_session, group, "阿強", None)
    opp2 = await _make_entry(db_session, group, "小美", None)
    await _make_completed_match(
        db_session, group, round_number=1, winner_team="A", team_a=[me.id], team_b=[opp1.id]
    )
    await _make_completed_match(
        db_session, group, round_number=1, winner_team="B", team_a=[me.id], team_b=[opp2.id]
    )
    await _make_completed_match(
        db_session, group, round_number=2, winner_team="A", team_a=[me.id], team_b=[opp1.id]
    )

    response = await build_member_match_records(db_session, member.id)

    assert [(p.round_number, p.wins, p.losses) for p in response.round_win_rates] == [
        (1, 1, 1),
        (2, 1, 0),
    ]
    records_by_name = {r.nickname: r for r in response.opponent_records}
    assert records_by_name["阿強"].wins == 2
    assert records_by_name["阿強"].losses == 0
    assert records_by_name["小美"].wins == 0
    assert records_by_name["小美"].losses == 1


async def test_guest_matches_never_included(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "was-a-guest@example.com")
    group = await _make_group(db_session, "Guest Group")

    guest_entry = await _make_entry(db_session, group, "訪客小明", None)
    opp = await _make_entry(db_session, group, "對手", None)
    await _make_completed_match(
        db_session, group, round_number=2, winner_team="A",
        team_a=[guest_entry.id], team_b=[opp.id],
    )

    # Same person later registers as a member, but a fresh RosterEntry is
    # what carries member_id — the Guest-era entry above is untouched.
    later_entry = await _make_entry(db_session, group, "小明", member.id)
    opp2 = await _make_entry(db_session, group, "對手2", None)
    await _make_completed_match(
        db_session, group, round_number=3, winner_team="A",
        team_a=[later_entry.id], team_b=[opp2.id],
    )

    response = await build_member_match_records(db_session, member.id)

    assert response.total_matches == 1
    assert response.matches[0].round_number == 3
