"""Integration tests: US2 (025-delete-account) — everything that reads a
deleted member's historical data keeps working exactly as before, showing
the placeholder nickname instead of erroring or going blank. Proves
FR-006 (no cascade row deletion) and FR-003a (roster nickname cascade)
together, from the other member's point of view."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.group.service import build_group_final_standings
from app.domains.member.models import Member
from app.domains.member.service import (
    DELETED_MEMBER_PLACEHOLDER_NICKNAME,
    build_member_match_records,
    delete_account,
    register,
)
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant

pytestmark = pytest.mark.asyncio


async def _make_group(session: AsyncSession, *, created_by: Member | None = None) -> Group:
    group = Group(
        name="History Preserved Test",
        max_members=4,
        match_mode="doubles",
        scheduling_mechanism="manual",
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
        created_by_member_id=created_by.id if created_by else None,
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_entry(
    session: AsyncSession, group: Group, nickname: str, member_id: uuid.UUID
) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname=nickname, member_id=member_id, status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def test_completed_match_still_shows_correctly_after_opponent_deletes_account(
    db_session: AsyncSession,
) -> None:
    member_a = await register(db_session, "history-a@example.com", "abc12345")
    member_b = await register(db_session, "history-b@example.com", "abc12345")
    group = await _make_group(db_session)
    entry_a = await _make_entry(db_session, group, "真實姓名A", member_a.id)
    entry_b = await _make_entry(db_session, group, "真實姓名B", member_b.id)

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
    db_session.add(MatchParticipant(match_id=match.id, roster_entry_id=entry_a.id, team="A"))
    db_session.add(MatchParticipant(match_id=match.id, roster_entry_id=entry_b.id, team="B"))
    await db_session.commit()

    await delete_account(db_session, member_a, "abc12345")

    response = await build_member_match_records(db_session, member_b.id, page=1)

    assert response.total_matches == 1
    participants = response.matches[0].team_a + response.matches[0].team_b
    nicknames = {p.nickname for p in participants}
    assert DELETED_MEMBER_PLACEHOLDER_NICKNAME in nicknames
    assert "真實姓名A" not in nicknames
    assert "真實姓名B" in nicknames


async def test_group_still_functions_after_its_member_creator_deletes_account(
    db_session: AsyncSession,
) -> None:
    creator = await register(db_session, "history-creator@example.com", "abc12345")
    other = await register(db_session, "history-other@example.com", "abc12345")
    group = await _make_group(db_session, created_by=creator)
    creator_entry = await _make_entry(db_session, group, "真實姓名創辦人", creator.id)
    other_entry = await _make_entry(db_session, group, "其他成員", other.id)

    await delete_account(db_session, creator, "abc12345")

    standings = await build_group_final_standings(db_session, group.id, viewer_member_id=other.id)

    by_id = {row.roster_entry_id: row for row in standings}
    assert by_id[str(creator_entry.id)].nickname == DELETED_MEMBER_PLACEHOLDER_NICKNAME
    assert by_id[str(other_entry.id)].nickname == "其他成員"
