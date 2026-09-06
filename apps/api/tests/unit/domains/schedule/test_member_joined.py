"""Unit test: handle_member_joined never touches the current round's
already-generated schedule (FR-038) — a mid-round joiner is added to the
roster but the queued/in_progress matches are byte-for-byte unaffected. Only
fixed_partner's auto-pairing (already covered by
test_partnership_membership_changes.py) is a side effect of this function."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.group.models import Group
from app.domains.group.security import hash_admin_pin
from app.domains.roster.models import RosterEntry
from app.domains.schedule.models import Match, MatchParticipant
from app.domains.schedule.service import handle_member_joined


async def _make_group(session: AsyncSession) -> Group:
    group = Group(
        name="Member Joined Test",
        max_members=8,
        match_mode="doubles",
        scheduling_mechanism="fair_rotation",
        current_round_number=3,
        current_member_count=1,
        status="active",
        admin_pin_hash=hash_admin_pin("111111"),
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def _make_roster_entry(session: AsyncSession, group: Group, nickname: str) -> RosterEntry:
    entry = RosterEntry(group_id=group.id, nickname=nickname, status="active")
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@pytest.mark.asyncio
async def test_member_joined_does_not_alter_current_round_matches(
    db_session: AsyncSession,
) -> None:
    group = await _make_group(db_session)
    a = await _make_roster_entry(db_session, group, "A")
    b = await _make_roster_entry(db_session, group, "B")

    match = Match(
        group_id=group.id,
        court_id=None,
        round_number=group.current_round_number,
        status="queued",
        target_score=21,
        deuce_threshold=20,
        cap_score=30,
    )
    db_session.add(match)
    await db_session.flush()
    db_session.add_all(
        [
            MatchParticipant(match_id=match.id, roster_entry_id=a.id, team="A"),
            MatchParticipant(match_id=match.id, roster_entry_id=b.id, team="B"),
        ]
    )
    await db_session.commit()

    new_member = await _make_roster_entry(db_session, group, "新成員")
    await handle_member_joined(db_session, group, new_member)
    await db_session.commit()

    await db_session.refresh(match)
    assert match.status == "queued"
    assert match.round_number == group.current_round_number

    participants = await db_session.execute(
        select(MatchParticipant).where(MatchParticipant.match_id == match.id)
    )
    ids = {p.roster_entry_id for p in participants.scalars()}
    assert ids == {a.id, b.id}  # new member not injected into it


@pytest.mark.asyncio
async def test_member_joined_added_to_roster_as_active(db_session: AsyncSession) -> None:
    group = await _make_group(db_session)
    new_member = await _make_roster_entry(db_session, group, "新成員")

    await handle_member_joined(db_session, group, new_member)
    await db_session.commit()

    await db_session.refresh(new_member)
    assert new_member.status == "active"
