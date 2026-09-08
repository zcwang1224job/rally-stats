"""Unit test: get_member_group_history() — `matches` is the group's own
shared match history (every completed match, any participant — corrected
per user feedback from the "只有自己的比賽" over-narrowing regression),
optionally searched by nickname across either team; `my_stats` is this
member's own performance in the group, always unfiltered by that search."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.domains.group.schemas import CreateGroupRequest
from app.domains.group.service import create_group, join_group
from app.domains.member.models import Member
from app.domains.member.security import hash_password
from app.domains.member.service import get_member_group_history
from app.domains.schedule.models import Match, MatchParticipant

pytestmark = pytest.mark.asyncio


async def _make_member(session: AsyncSession, email: str, nickname: str) -> Member:
    member = Member(
        email=email,
        password_hash=hash_password("abc12345"),
        user_number=str(uuid.uuid4())[:8],
        nickname=nickname,
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def _make_completed_match(
    session: AsyncSession, group_id, *, round_number: int, winner_team: str, team_a, team_b
) -> Match:
    match = Match(
        group_id=group_id,
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


async def test_match_list_includes_matches_i_did_not_play(db_session: AsyncSession) -> None:
    """FR-004 (corrected): `matches` is the group's shared history, not
    narrowed to the caller — a match between two OTHER members MUST still
    appear."""
    creator = await _make_member(db_session, "history-a2@example.com", "A")
    joiner = await _make_member(db_session, "history-b2@example.com", "B")
    bystander = await _make_member(db_session, "history-c2@example.com", "C")
    payload = CreateGroupRequest(
        name="History Group 2",
        max_members=8,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    group, creator_entry, _pin, _guest_token = await create_group(
        db_session, payload, member=creator
    )
    joiner_entry, _created_new = await join_group(
        db_session, group, member=joiner, password=None, nickname=None
    )
    bystander_entry, _created_new2 = await join_group(
        db_session, group, member=bystander, password=None, nickname=None
    )
    # A match between the creator and the bystander — joiner never played.
    await _make_completed_match(
        db_session, group.id, round_number=1, winner_team="A",
        team_a=[creator_entry.id], team_b=[bystander_entry.id],
    )

    response = await get_member_group_history(db_session, joiner.id, group.id)

    assert len(response.matches) == 1
    assert response.group_name == "History Group 2"


async def test_my_stats_only_counts_matches_i_played(db_session: AsyncSession) -> None:
    """FR-005: `my_stats` stays personal even though `matches` is now
    group-wide — the two sections answer different questions."""
    creator = await _make_member(db_session, "history-a1@example.com", "A")
    joiner = await _make_member(db_session, "history-b1@example.com", "B")
    bystander = await _make_member(db_session, "history-c1@example.com", "C")
    payload = CreateGroupRequest(
        name="History Group 1",
        max_members=8,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    group, creator_entry, _pin, _guest_token = await create_group(
        db_session, payload, member=creator
    )
    joiner_entry, _created_new = await join_group(
        db_session, group, member=joiner, password=None, nickname=None
    )
    bystander_entry, _created_new2 = await join_group(
        db_session, group, member=bystander, password=None, nickname=None
    )
    # Joiner plays and wins one match...
    await _make_completed_match(
        db_session, group.id, round_number=1, winner_team="B",
        team_a=[creator_entry.id], team_b=[joiner_entry.id],
    )
    # ...and a second match between two OTHER members happens too.
    await _make_completed_match(
        db_session, group.id, round_number=2, winner_team="A",
        team_a=[creator_entry.id], team_b=[bystander_entry.id],
    )

    response = await get_member_group_history(db_session, joiner.id, group.id)

    assert len(response.matches) == 2  # group-wide list sees both
    assert response.my_stats.total_matches == 1  # personal stats see only mine
    assert response.my_stats.total_wins == 1
    assert response.my_stats.win_rate == 1.0
    assert response.my_stats.opponent_records[0].nickname == "A"


async def test_scoped_to_this_group_only(db_session: AsyncSession) -> None:
    """A match in a DIFFERENT group must not leak into this group's shared
    history."""
    creator_a = await _make_member(db_session, "history-a5@example.com", "A")
    creator_b = await _make_member(db_session, "history-d5@example.com", "D")
    joiner = await _make_member(db_session, "history-b5@example.com", "B")
    group_a, _creator_entry_a, _pin, _guest_token = await create_group(
        db_session,
        CreateGroupRequest(
            name="History Group 5a",
            max_members=4,
            match_mode="doubles",
            scheduling_mechanism="manual",
            turnstile_token="unused",
        ),
        member=creator_a,
    )
    group_b, creator_entry_b, _pin2, _guest_token2 = await create_group(
        db_session,
        CreateGroupRequest(
            name="History Group 5b",
            max_members=4,
            match_mode="doubles",
            scheduling_mechanism="manual",
            turnstile_token="unused",
        ),
        member=creator_b,
    )
    joiner_entry_b, _created_new2 = await join_group(
        db_session, group_b, member=joiner, password=None, nickname=None
    )
    await _make_completed_match(
        db_session, group_b.id, round_number=1, winner_team="B",
        team_a=[creator_entry_b.id], team_b=[joiner_entry_b.id],
    )

    response = await get_member_group_history(db_session, joiner.id, group_b.id)

    assert len(response.matches) == 1
    assert response.group_name == "History Group 5b"


async def test_nickname_filter_matches_either_team_regardless_of_caller(
    db_session: AsyncSession,
) -> None:
    """FR-009 (corrected): the nickname filter searches the WHOLE group's
    matches, not just the caller's own games — the caller here (bystander)
    never played "阿強", yet the filter still surfaces the match because
    someone else did."""
    a = await _make_member(db_session, "history-a6@example.com", "阿強")
    b = await _make_member(db_session, "history-b6@example.com", "阿美")
    bystander = await _make_member(db_session, "history-c6@example.com", "旁觀者")
    payload = CreateGroupRequest(
        name="History Group 6",
        max_members=8,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    group, a_entry, _pin, _guest_token = await create_group(db_session, payload, member=a)
    b_entry, _created_new = await join_group(
        db_session, group, member=b, password=None, nickname=None
    )
    bystander_entry, _created_new2 = await join_group(
        db_session, group, member=bystander, password=None, nickname=None
    )
    # a vs b — matches the "阿強" filter.
    await _make_completed_match(
        db_session, group.id, round_number=1, winner_team="A",
        team_a=[a_entry.id], team_b=[b_entry.id],
    )
    # b vs bystander — does NOT match "阿強".
    await _make_completed_match(
        db_session, group.id, round_number=2, winner_team="B",
        team_a=[b_entry.id], team_b=[bystander_entry.id],
    )

    response = await get_member_group_history(db_session, bystander.id, group.id, nickname="阿強")

    assert len(response.matches) == 1
    assert response.matches[0].round_number == 1
    # my_stats stays about the caller's OWN history, unaffected by the
    # nickname search (bystander played 1 match total, not involving 阿強).
    assert response.my_stats.total_matches == 1


async def test_no_matches_yet_returns_empty_not_error(db_session: AsyncSession) -> None:
    creator = await _make_member(db_session, "history-a3@example.com", "A")
    payload = CreateGroupRequest(
        name="History Group 3",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    group, _creator_entry, _pin, _guest_token = await create_group(
        db_session, payload, member=creator
    )

    response = await get_member_group_history(db_session, creator.id, group.id)

    assert response.matches == []
    assert response.my_stats.total_matches == 0
    assert response.my_stats.win_rate == 0.0


async def test_rejects_member_who_was_never_in_the_group(db_session: AsyncSession) -> None:
    creator = await _make_member(db_session, "history-a4@example.com", "A")
    stranger = await _make_member(db_session, "history-c4@example.com", "C")
    payload = CreateGroupRequest(
        name="History Group 4",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        turnstile_token="unused",
    )
    group, _creator_entry, _pin, _guest_token = await create_group(
        db_session, payload, member=creator
    )

    with pytest.raises(ApiError) as exc_info:
        await get_member_group_history(db_session, stranger.id, group.id)
    assert exc_info.value.error_code == "GROUP_MEMBERSHIP_NEVER_HELD"
