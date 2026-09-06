"""Unit test: build_group_match_records() — only completed matches, sorted
newest-round-first, scoped to one group (005-member-view US3, FR-011/012)."""

import uuid

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
