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


async def _make_group(session: AsyncSession, name: str, match_mode: str = "singles") -> Group:
    group = Group(
        name=name,
        max_members=8,
        match_mode=match_mode,
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

    response = await build_member_match_records(db_session, member.id, opponents=["阿強"])

    assert response.total_matches == 1
    assert response.matches[0].team_b[0].nickname == "阿強"


async def test_filters_by_two_opponent_nicknames_requires_distinct_players(
    db_session: AsyncSession,
) -> None:
    member = await _make_member(db_session, "filter-two-opponents@example.com")
    group = await _make_group(db_session, "Filter Doubles Group", match_mode="doubles")
    me = await _make_entry(db_session, group, "小明", member.id)
    partner = await _make_entry(db_session, group, "隊友", None)
    opp_a = await _make_entry(db_session, group, "阿強", None)
    opp_b = await _make_entry(db_session, group, "阿美", None)
    await _make_completed_match(
        db_session, group, round_number=1, winner_team="A",
        team_a=[me.id, partner.id], team_b=[opp_a.id, opp_b.id],
    )

    both_named = await build_member_match_records(
        db_session, member.id, opponents=["阿強", "阿美"]
    )
    assert both_named.total_matches == 1

    # Both search terms matching the *same* single opponent must not count —
    # doubles has two distinct opponents, and "against 阿強 and 阿強" is a
    # different (impossible, here) query than "against 阿強".
    same_name_twice = await build_member_match_records(
        db_session, member.id, opponents=["阿強", "阿強"]
    )
    assert same_name_twice.total_matches == 0


async def test_filters_by_partner_nickname(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "filter-partner@example.com")
    group = await _make_group(db_session, "Filter Partner Group", match_mode="doubles")
    me = await _make_entry(db_session, group, "小明", member.id)
    partner1 = await _make_entry(db_session, group, "隊友甲", None)
    partner2 = await _make_entry(db_session, group, "隊友乙", None)
    opp1 = await _make_entry(db_session, group, "對手1", None)
    opp2 = await _make_entry(db_session, group, "對手2", None)
    await _make_completed_match(
        db_session, group, round_number=1, winner_team="A",
        team_a=[me.id, partner1.id], team_b=[opp1.id],
    )
    await _make_completed_match(
        db_session, group, round_number=2, winner_team="A",
        team_a=[me.id, partner2.id], team_b=[opp2.id],
    )

    response = await build_member_match_records(db_session, member.id, partners=["隊友甲"])

    assert response.total_matches == 1
    assert response.matches[0].round_number == 1


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


async def test_filters_by_self_score(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "filter-self-score@example.com")
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

    scored_11 = await build_member_match_records(
        db_session, member.id, self_score_cmp="eq", self_score=11
    )
    assert scored_11.total_matches == 1
    assert scored_11.matches[0].round_number == 1

    scored_below_10 = await build_member_match_records(
        db_session, member.id, self_score_cmp="lt", self_score=10
    )
    assert scored_below_10.total_matches == 1
    assert scored_below_10.matches[0].round_number == 2


async def test_filters_by_opponent_score(db_session: AsyncSession) -> None:
    member = await _make_member(db_session, "filter-opponent-score@example.com")
    group = await _make_group(db_session, "Filter Group 5")
    me = await _make_entry(db_session, group, "小明", member.id)
    opp = await _make_entry(db_session, group, "對手", None)
    # _make_completed_match always sets score_a=11, score_b=5 — round 1 has
    # me on team_a (my opponent scored 5), round 2 has me on team_b (my
    # opponent scored 11).
    await _make_completed_match(
        db_session, group, round_number=1, winner_team="A", team_a=[me.id], team_b=[opp.id]
    )
    await _make_completed_match(
        db_session, group, round_number=2, winner_team="A", team_a=[opp.id], team_b=[me.id]
    )

    opponent_scored_low = await build_member_match_records(
        db_session, member.id, opponent_score_cmp="lt", opponent_score=10
    )
    assert opponent_scored_low.total_matches == 1
    assert opponent_scored_low.matches[0].round_number == 1

    opponent_scored_high = await build_member_match_records(
        db_session, member.id, opponent_score_cmp="gt", opponent_score=10
    )
    assert opponent_scored_high.total_matches == 1
    assert opponent_scored_high.matches[0].round_number == 2


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
